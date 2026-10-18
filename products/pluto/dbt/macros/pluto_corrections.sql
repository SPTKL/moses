{% macro corrected_lot_rows(base_relation, decisions_relation) %}
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
SELECT * REPLACE (
    CASE
      WHEN count(DISTINCT struct_pack(value := new_value)) OVER (
        PARTITION BY target_id, field, match_scope
      ) > 1 THEN error('Conflicting research corrections for BBL ' || bbl || ', field ' || field || ', pass ' || match_scope)
      ELSE new_value
    END AS new_value
  )
  FROM eligible_writes
  WHERE audit_status = 'applied'
  QUALIFY row_number() OVER (
    PARTITION BY target_id, field, match_scope
    ORDER BY "bbl" NULLS FIRST, "field" NULLS FIRST, "old_value" NULLS FIRST, "new_value" NULLS FIRST, "Type" NULLS FIRST, "reason" NULLS FIRST, "version" NULLS FIRST
  ) = 1
),
values_by_lot AS (
  SELECT target_id,
    count(*) FILTER (WHERE field='lotarea' AND match_scope IN ('specific','automatic')) > 0 AS "lotarea_specific_matched",
    max(new_value) FILTER (WHERE field='lotarea' AND match_scope IN ('specific','automatic')) AS "lotarea_specific_value",
    count(*) FILTER (WHERE field='lotarea' AND match_scope='global') > 0 AS "lotarea_global_matched",
    max(new_value) FILTER (WHERE field='lotarea' AND match_scope='global') AS "lotarea_global_value",
    count(*) FILTER (WHERE field='bldgarea' AND match_scope IN ('specific','automatic')) > 0 AS "bldgarea_specific_matched",
    max(new_value) FILTER (WHERE field='bldgarea' AND match_scope IN ('specific','automatic')) AS "bldgarea_specific_value",
    count(*) FILTER (WHERE field='bldgarea' AND match_scope='global') > 0 AS "bldgarea_global_matched",
    max(new_value) FILTER (WHERE field='bldgarea' AND match_scope='global') AS "bldgarea_global_value",
    count(*) FILTER (WHERE field='lotfront' AND match_scope IN ('specific','automatic')) > 0 AS "lotfront_specific_matched",
    max(new_value) FILTER (WHERE field='lotfront' AND match_scope IN ('specific','automatic')) AS "lotfront_specific_value",
    count(*) FILTER (WHERE field='lotfront' AND match_scope='global') > 0 AS "lotfront_global_matched",
    max(new_value) FILTER (WHERE field='lotfront' AND match_scope='global') AS "lotfront_global_value",
    count(*) FILTER (WHERE field='lotdepth' AND match_scope IN ('specific','automatic')) > 0 AS "lotdepth_specific_matched",
    max(new_value) FILTER (WHERE field='lotdepth' AND match_scope IN ('specific','automatic')) AS "lotdepth_specific_value",
    count(*) FILTER (WHERE field='lotdepth' AND match_scope='global') > 0 AS "lotdepth_global_matched",
    max(new_value) FILTER (WHERE field='lotdepth' AND match_scope='global') AS "lotdepth_global_value",
    count(*) FILTER (WHERE field='yearbuilt' AND match_scope IN ('specific','automatic')) > 0 AS "yearbuilt_specific_matched",
    max(new_value) FILTER (WHERE field='yearbuilt' AND match_scope IN ('specific','automatic')) AS "yearbuilt_specific_value",
    count(*) FILTER (WHERE field='yearbuilt' AND match_scope='global') > 0 AS "yearbuilt_global_matched",
    max(new_value) FILTER (WHERE field='yearbuilt' AND match_scope='global') AS "yearbuilt_global_value",
    count(*) FILTER (WHERE field='ownername' AND match_scope IN ('specific','automatic')) > 0 AS "ownername_specific_matched",
    max(new_value) FILTER (WHERE field='ownername' AND match_scope IN ('specific','automatic')) AS "ownername_specific_value",
    count(*) FILTER (WHERE field='ownername' AND match_scope='global') > 0 AS "ownername_global_matched",
    max(new_value) FILTER (WHERE field='ownername' AND match_scope='global') AS "ownername_global_value",
    count(*) FILTER (WHERE field='cd' AND match_scope IN ('specific','automatic')) > 0 AS "cd_specific_matched",
    max(new_value) FILTER (WHERE field='cd' AND match_scope IN ('specific','automatic')) AS "cd_specific_value",
    count(*) FILTER (WHERE field='cd' AND match_scope='global') > 0 AS "cd_global_matched",
    max(new_value) FILTER (WHERE field='cd' AND match_scope='global') AS "cd_global_value",
    count(*) FILTER (WHERE field='numfloors' AND match_scope IN ('specific','automatic')) > 0 AS "numfloors_specific_matched",
    max(new_value) FILTER (WHERE field='numfloors' AND match_scope IN ('specific','automatic')) AS "numfloors_specific_value",
    count(*) FILTER (WHERE field='numfloors' AND match_scope='global') > 0 AS "numfloors_global_matched",
    max(new_value) FILTER (WHERE field='numfloors' AND match_scope='global') AS "numfloors_global_value",
    count(*) FILTER (WHERE field='numbldgs' AND match_scope IN ('specific','automatic')) > 0 AS "numbldgs_specific_matched",
    max(new_value) FILTER (WHERE field='numbldgs' AND match_scope IN ('specific','automatic')) AS "numbldgs_specific_value",
    count(*) FILTER (WHERE field='numbldgs' AND match_scope='global') > 0 AS "numbldgs_global_matched",
    max(new_value) FILTER (WHERE field='numbldgs' AND match_scope='global') AS "numbldgs_global_value",
    count(*) FILTER (WHERE field='unitsres' AND match_scope IN ('specific','automatic')) > 0 AS "unitsres_specific_matched",
    max(new_value) FILTER (WHERE field='unitsres' AND match_scope IN ('specific','automatic')) AS "unitsres_specific_value",
    count(*) FILTER (WHERE field='unitsres' AND match_scope='global') > 0 AS "unitsres_global_matched",
    max(new_value) FILTER (WHERE field='unitsres' AND match_scope='global') AS "unitsres_global_value",
    count(*) FILTER (WHERE field='unitstotal' AND match_scope IN ('specific','automatic')) > 0 AS "unitstotal_specific_matched",
    max(new_value) FILTER (WHERE field='unitstotal' AND match_scope IN ('specific','automatic')) AS "unitstotal_specific_value",
    count(*) FILTER (WHERE field='unitstotal' AND match_scope='global') > 0 AS "unitstotal_global_matched",
    max(new_value) FILTER (WHERE field='unitstotal' AND match_scope='global') AS "unitstotal_global_value",
    count(*) FILTER (WHERE field='bct2020' AND match_scope IN ('specific','automatic')) > 0 AS "bct2020_specific_matched",
    max(new_value) FILTER (WHERE field='bct2020' AND match_scope IN ('specific','automatic')) AS "bct2020_specific_value",
    count(*) FILTER (WHERE field='bct2020' AND match_scope='global') > 0 AS "bct2020_global_matched",
    max(new_value) FILTER (WHERE field='bct2020' AND match_scope='global') AS "bct2020_global_value",
    count(*) FILTER (WHERE field='address' AND match_scope IN ('specific','automatic')) > 0 AS "address_specific_matched",
    max(new_value) FILTER (WHERE field='address' AND match_scope IN ('specific','automatic')) AS "address_specific_value",
    count(*) FILTER (WHERE field='address' AND match_scope='global') > 0 AS "address_global_matched",
    max(new_value) FILTER (WHERE field='address' AND match_scope='global') AS "address_global_value"
  FROM selected_proposals
  GROUP BY target_id
),
researched_lots AS (
  SELECT a.* REPLACE (
    CASE WHEN p."lotarea_global_matched" THEN p."lotarea_global_value" WHEN p."lotarea_specific_matched" THEN p."lotarea_specific_value" ELSE a."lotarea" END AS "lotarea",
    CASE WHEN p."bldgarea_global_matched" THEN p."bldgarea_global_value" WHEN p."bldgarea_specific_matched" THEN p."bldgarea_specific_value" ELSE a."bldgarea" END AS "bldgarea",
    CASE WHEN p."lotfront_global_matched" THEN p."lotfront_global_value" WHEN p."lotfront_specific_matched" THEN p."lotfront_specific_value" ELSE a."lotfront" END AS "lotfront",
    CASE WHEN p."lotdepth_global_matched" THEN p."lotdepth_global_value" WHEN p."lotdepth_specific_matched" THEN p."lotdepth_specific_value" ELSE a."lotdepth" END AS "lotdepth",
    CASE WHEN p."yearbuilt_global_matched" THEN p."yearbuilt_global_value" WHEN p."yearbuilt_specific_matched" THEN p."yearbuilt_specific_value" ELSE a."yearbuilt" END AS "yearbuilt",
    CASE WHEN p."ownername_global_matched" THEN p."ownername_global_value" WHEN p."ownername_specific_matched" THEN p."ownername_specific_value" ELSE a."ownername" END AS "ownername",
    CASE WHEN p."cd_global_matched" THEN p."cd_global_value" WHEN p."cd_specific_matched" THEN p."cd_specific_value" ELSE a."cd" END AS "cd",
    CASE WHEN p."numfloors_global_matched" THEN p."numfloors_global_value" WHEN p."numfloors_specific_matched" THEN p."numfloors_specific_value" ELSE a."numfloors" END AS "numfloors",
    CASE WHEN p."numbldgs_global_matched" THEN p."numbldgs_global_value" WHEN p."numbldgs_specific_matched" THEN p."numbldgs_specific_value" ELSE a."numbldgs" END AS "numbldgs",
    CASE WHEN p."unitsres_global_matched" THEN p."unitsres_global_value" WHEN p."unitsres_specific_matched" THEN p."unitsres_specific_value" ELSE a."unitsres" END AS "unitsres",
    CASE WHEN p."unitstotal_global_matched" THEN p."unitstotal_global_value" WHEN p."unitstotal_specific_matched" THEN p."unitstotal_specific_value" ELSE a."unitstotal" END AS "unitstotal",
    CASE WHEN p."bct2020_global_matched" THEN p."bct2020_global_value" WHEN p."bct2020_specific_matched" THEN p."bct2020_specific_value" ELSE a."bct2020" END AS "bct2020",
    CASE WHEN p."address_global_matched" THEN p."address_global_value" WHEN p."address_specific_matched" THEN p."address_specific_value" ELSE a."address" END AS "address"
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
