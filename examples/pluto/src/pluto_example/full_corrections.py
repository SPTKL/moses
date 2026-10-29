"""Readable, SELECT-only models for the pinned PLUTO correction process.

Research decisions form one materialized ledger shared by the final lots and
both audit exports. Specific parcel corrections precede global value matches;
NULL writes and audit multiplicity remain explicit. Conflicting eligible new
values fail instead of silently selecting a new business rule. Equivalent
proposals use a stable ordering of the complete research metadata.
"""
from __future__ import annotations


TEXT_FIELDS = (
    'yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs',
    'unitsres', 'unitstotal', 'bct2020', 'address',
)
AREA_FIELDS = ('lotarea', 'bldgarea', 'lotfront', 'lotdepth')
AUDIT_FIELDS = ('bbl', 'field', 'old_value', 'new_value', 'Type', 'reason', 'version')


def _q(name):
    return '"' + name.replace('"', '""') + '"'


def _field_value(alias, fields, selector='r.field'):
    return ('CASE ' + selector + '\n' + '\n'.join(
        f"          WHEN '{field}' THEN {alias}.{_q(field)}" for field in fields)
        + '\n        END')


def _selected_proposals(relation, *, scopes=None):
    """Choose equivalent writes while keeping all audit proposals in the ledger."""
    scope_filter = '' if scopes is None else ' AND match_scope IN (' + ','.join("'" + scope + "'" for scope in scopes) + ')'
    order = ', '.join(_q(field) + ' NULLS FIRST' for field in AUDIT_FIELDS)
    return f'''SELECT * REPLACE (
    CASE
      WHEN count(DISTINCT struct_pack(value := new_value)) OVER (
        PARTITION BY target_id, field, match_scope
      ) > 1 THEN error('Conflicting research corrections for BBL ' || bbl || ', field ' || field || ', pass ' || match_scope)
      ELSE new_value
    END AS new_value
  )
  FROM {relation}
  WHERE audit_status = 'applied'{scope_filter}
  QUALIFY row_number() OVER (
    PARTITION BY target_id, field, match_scope
    ORDER BY {order}
  ) = 1'''


def _decisions(base, research):
    area_value = _field_value('a', AREA_FIELDS)
    text_value = _field_value('a', TEXT_FIELDS)
    global_value = _field_value('a', TEXT_FIELDS, 'f.field')
    selected_specific = _selected_proposals('specific_events')
    return f'''-- Sources: corr_create.sql, corr_lotarea.sql, corr_template.sql.
-- Every DISTINCT corresponds to one upstream audit INSERT. UNION ALL preserves
-- metadata rows and multiplicity across different correction passes.
WITH
research AS (
  SELECT * FROM {research}
),
area_candidates AS (
  SELECT a.id AS target_id, r.*, {area_value} AS found_value
  FROM {base} AS a
  JOIN research AS r ON a.bbl = r.bbl
  WHERE r.field IN ({', '.join(repr(f) for f in AREA_FIELDS)})
),
area_research_events AS (
  SELECT DISTINCT
    target_id,
    CASE field WHEN 'lotarea' THEN 20 WHEN 'bldgarea' THEN 30
      WHEN 'lotfront' THEN 40 WHEN 'lotdepth' THEN 50 END AS phase,
    'specific' AS match_scope,
    CASE
      WHEN CAST(old_value AS DECIMAL(38,12)) = CAST(found_value AS DECIMAL(38,12)) THEN 'applied'
      WHEN CAST(old_value AS DECIMAL(38,12)) <> CAST(found_value AS DECIMAL(38,12)) THEN 'not_applied'
    END AS audit_status,
    bbl, field, old_value, new_value, "Type", reason, version, found_value
  FROM area_candidates
),
automatic_area_events AS (
  SELECT DISTINCT
    a.id AS target_id, 10 AS phase, 'automatic' AS match_scope,
    'applied' AS audit_status, a.bbl, 'lotarea' AS field,
    a.lotarea AS old_value,
    MOSES_TEXT(round(ST_Area(moses_transform_crs(a.geom, 4326, 2263)))) AS new_value,
    1 AS "Type", 'Zero lot area' AS reason, a.version, a.lotarea AS found_value
  FROM {base} AS a
  WHERE a.lotarea = '0' AND a.geom IS NOT NULL
    AND a.bbl NOT IN (SELECT bbl FROM research WHERE field = 'lotarea')
),
text_candidates AS (
  SELECT a.id AS target_id, r.*, {text_value} AS found_value
  FROM {base} AS a
  JOIN research AS r ON a.bbl = r.bbl
  WHERE r.field IN ({', '.join(repr(f) for f in TEXT_FIELDS)})
),
specific_text_events AS (
  SELECT DISTINCT target_id,
    100 + list_position([{', '.join(repr(f) for f in TEXT_FIELDS)}], field) * 10 AS phase,
    'specific' AS match_scope,
    CASE WHEN found_value IS NOT DISTINCT FROM old_value THEN 'applied' ELSE 'not_applied' END AS audit_status,
    bbl, field, old_value, new_value, "Type", reason, version, found_value
  FROM text_candidates
),
specific_events AS (
  SELECT * FROM area_research_events WHERE audit_status IS NOT NULL
  UNION ALL SELECT * FROM automatic_area_events
  UNION ALL SELECT * FROM specific_text_events
),
selected_specific AS (
  {selected_specific}
),
global_fields AS (
  SELECT DISTINCT field FROM research
  WHERE bbl IS NULL AND field IN ({', '.join(repr(f) for f in TEXT_FIELDS)})
),
values_after_specific AS (
  -- Global matches see the value after the parcel-specific pass, not the
  -- original lot or final row. Project each relevant field once, then hash-join
  -- old values; avoid a citywide lot-by-research-rule Cartesian product.
  SELECT a.id AS target_id, a.bbl, f.field,
    CASE WHEN s.target_id IS NOT NULL THEN s.new_value ELSE {global_value} END AS found_value
  FROM {base} AS a
  CROSS JOIN global_fields AS f
  LEFT JOIN selected_specific AS s ON a.id = s.target_id AND f.field = s.field
),
global_candidates AS (
  SELECT v.target_id, v.bbl, r.field, r.old_value, r.new_value,
    r."Type", r.reason, r.version, v.found_value
  FROM values_after_specific AS v
  JOIN research AS r ON r.bbl IS NULL AND r.field = v.field
    AND v.found_value IS NOT DISTINCT FROM r.old_value
),
global_events AS (
  SELECT DISTINCT target_id,
    101 + list_position([{', '.join(repr(f) for f in TEXT_FIELDS)}], field) * 10 AS phase,
    'global' AS match_scope, 'applied' AS audit_status,
    bbl, field, old_value, new_value, "Type", reason, version, found_value
  FROM global_candidates
  WHERE found_value IS NOT DISTINCT FROM old_value
)
SELECT * FROM specific_events
UNION ALL SELECT * FROM global_events'''


def _macros():
    selected = _selected_proposals('eligible_writes')
    # Keep matched NULL writes separate from missing proposals. A MAX pivot is
    # safe only after the eligible-write uniqueness assertion above.
    pivots = []
    replacements = []
    for field in AREA_FIELDS + TEXT_FIELDS:
        specific = f"field='{field}' AND match_scope IN ('specific','automatic')"
        global_ = f"field='{field}' AND match_scope='global'"
        pivots.extend([
            f"    count(*) FILTER (WHERE {specific}) > 0 AS {_q(field + '_specific_matched')}",
            f"    max(new_value) FILTER (WHERE {specific}) AS {_q(field + '_specific_value')}",
            f"    count(*) FILTER (WHERE {global_}) > 0 AS {_q(field + '_global_matched')}",
            f"    max(new_value) FILTER (WHERE {global_}) AS {_q(field + '_global_value')}",
        ])
        replacements.append(
            f"    CASE WHEN p.{_q(field + '_global_matched')} THEN p.{_q(field + '_global_value')} "
            f"WHEN p.{_q(field + '_specific_matched')} THEN p.{_q(field + '_specific_value')} "
            f"ELSE a.{_q(field)} END AS {_q(field)}")
    pivot_sql = ',\n'.join(pivots)
    replace_sql = ',\n'.join(replacements)
    return r'''{% macro corrected_lot_rows(base_relation, decisions_relation) %}
-- corr_lotarea.sql: apply area values, then recalculate FAR from both corrected
-- operands. corr_template.sql: each field uses specific before global matches.
WITH
audit_decisions AS (
  SELECT * FROM {{ decisions_relation }}
),
eligible_area_writes AS (
  -- Area UPDATEs match applied audit rows by BBL and numeric old value. An
  -- automatic estimate logged for one mapped row also updates an unmapped
  -- sibling with the same BBL and zero area; the sibling creates no new audit.
  SELECT d.* REPLACE (a.id AS target_id)
  FROM {{ base_relation }} AS a
  JOIN audit_decisions AS d ON a.bbl = d.bbl
    AND d.audit_status = 'applied'
    AND d.field IN ('lotarea','bldgarea','lotfront','lotdepth')
    AND CAST(CASE d.field WHEN 'lotarea' THEN a.lotarea
      WHEN 'bldgarea' THEN a.bldgarea WHEN 'lotfront' THEN a.lotfront
      WHEN 'lotdepth' THEN a.lotdepth END AS DECIMAL(38,12)) =
        CAST(d.old_value AS DECIMAL(38,12))
),
eligible_writes AS (
  SELECT * FROM eligible_area_writes
  UNION ALL
  SELECT * FROM audit_decisions
  WHERE field NOT IN ('lotarea','bldgarea','lotfront','lotdepth')
),
selected_proposals AS (
''' + selected + r'''
),
values_by_lot AS (
  SELECT target_id,
''' + pivot_sql + r'''
  FROM selected_proposals
  GROUP BY target_id
),
researched_lots AS (
  SELECT a.* REPLACE (
''' + replace_sql + r'''
  ), CASE WHEN p.target_id IS NOT NULL THEN 't' END::VARCHAR AS dcpedited,
    EXISTS (SELECT 1 FROM audit_decisions AS d
      WHERE d.bbl = a.bbl AND d.audit_status = 'applied'
        AND d.field IN ('lotarea','bldgarea')) AS area_applied
  FROM {{ base_relation }} AS a
  LEFT JOIN values_by_lot AS p ON a.id = p.target_id
),
area_recalculated AS (
  SELECT * EXCLUDE (area_applied) REPLACE (
    CASE WHEN lotarea <> '0' AND lotarea IS NOT NULL AND area_applied
      THEN MOSES_TEXT(round(CAST(CAST(bldgarea AS DECIMAL(38,12)) /
        CAST(lotarea AS DECIMAL(38,12)) AS DECIMAL(38,12)), 2))
      ELSE builtfar END AS builtfar
  )
  FROM researched_lots
)
-- corr_ownername_punctuation.sql is deliberately not a research audit event.
-- corr_inwoodrezoning.sql only resets notes; its spatial update is commented out.
SELECT * REPLACE (
  CASE WHEN regexp_matches(ownername, '^([.,;><\-_!?`%]+).*')
    THEN trim(regexp_replace(ownername, '^([.,;><\-_!?`%]+)(.*)', '\2'))
    ELSE ownername END AS ownername,
  CASE WHEN regexp_matches(ownername, '^([.,;><\-_!?`%]+).*')
    THEN 't' ELSE dcpedited END AS dcpedited
), NULL::VARCHAR AS notes
FROM area_recalculated
{% endmacro %}

{% macro classified_corrected_lots(base_relation, decisions_relation) %}
-- remove_unitlots.sql: the first deletion changes the population used by the
-- second duplicate count. The concatenated membership key is upstream behavior.
WITH
corrected AS (
  {{ corrected_lot_rows(base_relation, decisions_relation) }}
),
first_removal AS (
  SELECT *, CASE WHEN CAST(lot AS DECIMAL(38,12)) >= 1000
    AND lot NOT LIKE '75%' AND CAST(unitstotal AS DECIMAL(38,12)) > 1
    AND geom IS NULL THEN 1 END AS __first_removal
  FROM corrected
),
surviving_lots AS (
  SELECT * FROM first_removal WHERE __first_removal IS NULL
),
duplicate_address_areas AS (
  SELECT address, bldgarea
  FROM surviving_lots
  WHERE CAST(lot AS DECIMAL(38,12)) >= 1000 AND lot NOT LIKE '75%'
    AND address IS NOT NULL AND CAST(bldgarea AS DECIMAL(38,12)) > 0
  GROUP BY address, bldgarea HAVING count(*) > 1
)
SELECT * EXCLUDE (__first_removal),
  CASE WHEN __first_removal = 1 THEN 1
    WHEN CAST(lot AS DECIMAL(38,12)) >= 1000 AND lot NOT LIKE '75%'
      AND address || bldgarea IN (
        SELECT address || bldgarea FROM duplicate_address_areas
      ) THEN 2 END AS __removal_phase
FROM first_removal
{% endmacro %}
'''


def build_correction_models(*, base_model='map_flags',
                            research_sql="{{ pluto_input('pluto_input_research') }}"):
    """Return five business SQL bodies and shared Jinja macros for the writer.

    ``base_model`` has the pre-corr_create schema, including unique non-null
    serial ``id``, geometry, text attributes, and no ``dcpedited`` or ``notes``.
    Research keeps its native metadata types and the seven pinned columns.
    """
    base = "{{ ref(" + repr(base_model) + ") }}"
    classified = "{{ classified_corrected_lots(ref(" + repr(base_model) + "), ref('correction_decisions')) }}"
    audit_fields = ', '.join(_q(field) for field in AUDIT_FIELDS)
    models = {
        'correction_decisions': _decisions(base, research_sql),
        'pluto_removed_records': '-- Corrected full rows, captured before each removal.\n'
                                 'WITH classified AS (\n' + classified + '\n)\n'
                                 'SELECT * EXCLUDE (__removal_phase) FROM classified WHERE __removal_phase IS NOT NULL',
        'pluto': '-- Final corrected lots after both ordered unit-lot removals.\n'
                 'WITH corrected AS (\n{{ corrected_lot_rows(ref(' + repr(base_model) + "), ref('correction_decisions')) }}\n)\n"
                 '-- The first DELETE uses its predicate; the final DELETE uses BBLs\n'
                 '-- from the removed-record table, rather than just target serial ids.\n'
                 'SELECT a.* FROM corrected AS a\n'
                 "WHERE NOT COALESCE((CAST(lot AS DECIMAL(38,12)) >= 1000\n"
                 "  AND lot NOT LIKE '75%' AND CAST(unitstotal AS DECIMAL(38,12)) > 1\n"
                 '  AND geom IS NULL), FALSE)\n'
                 "AND NOT EXISTS (SELECT 1 FROM {{ ref('pluto_removed_records') }} AS r WHERE r.bbl = a.bbl)",
        'pluto_changes_applied': '-- Preserve every upstream applied INSERT event, including lots later removed.\n'
                                 '-- Audit DISTINCT excludes internal target ids and found values.\n'
                                 f'SELECT {audit_fields} FROM (SELECT DISTINCT phase, {audit_fields} '
                                 "FROM {{ ref('correction_decisions') }} WHERE audit_status = 'applied') AS audit_events",
        'pluto_changes_not_applied': '-- Only specific research mismatches were recorded upstream.\n'
                                     f'SELECT {audit_fields}, found_value FROM (SELECT DISTINCT phase, {audit_fields}, found_value '
                                     "FROM {{ ref('correction_decisions') }} WHERE audit_status = 'not_applied') AS audit_events",
    }
    return {'models': models, 'macros': {'pluto_corrections.sql': _macros()},
            'materialized': {name: 'table' for name in models}}
