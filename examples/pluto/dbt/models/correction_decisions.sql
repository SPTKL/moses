{{ config(materialized='table') }}
-- Business process: correction_decisions
-- Sources: corr_create.sql, corr_lotarea.sql, corr_template.sql.
-- Every DISTINCT corresponds to one upstream audit INSERT. UNION ALL preserves
-- metadata rows and multiplicity across different correction passes.
WITH
research AS (
  SELECT * FROM ({{ pluto_input('pluto_input_research') }})
),
area_candidates AS (
  SELECT a.id AS target_id, r.*, CASE r.field
          WHEN 'lotarea' THEN a."lotarea"
          WHEN 'bldgarea' THEN a."bldgarea"
          WHEN 'lotfront' THEN a."lotfront"
          WHEN 'lotdepth' THEN a."lotdepth"
        END AS found_value
  FROM {{ ref('parcel_mapping_flags') }} AS a
  JOIN research AS r ON a.bbl = r.bbl
  WHERE r.field IN ('lotarea', 'bldgarea', 'lotfront', 'lotdepth')
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
  FROM {{ ref('parcel_mapping_flags') }} AS a
  WHERE a.lotarea = '0' AND a.geom IS NOT NULL
    AND a.bbl NOT IN (SELECT bbl FROM research WHERE field = 'lotarea')
),
text_candidates AS (
  SELECT a.id AS target_id, r.*, CASE r.field
          WHEN 'yearbuilt' THEN a."yearbuilt"
          WHEN 'ownername' THEN a."ownername"
          WHEN 'cd' THEN a."cd"
          WHEN 'numfloors' THEN a."numfloors"
          WHEN 'numbldgs' THEN a."numbldgs"
          WHEN 'unitsres' THEN a."unitsres"
          WHEN 'unitstotal' THEN a."unitstotal"
          WHEN 'bct2020' THEN a."bct2020"
          WHEN 'address' THEN a."address"
        END AS found_value
  FROM {{ ref('parcel_mapping_flags') }} AS a
  JOIN research AS r ON a.bbl = r.bbl
  WHERE r.field IN ('yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs', 'unitsres', 'unitstotal', 'bct2020', 'address')
),
specific_text_events AS (
  SELECT DISTINCT target_id,
    100 + list_position(['yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs', 'unitsres', 'unitstotal', 'bct2020', 'address'], field) * 10 AS phase,
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
  SELECT * REPLACE (
    CASE
      WHEN count(DISTINCT struct_pack(value := new_value)) OVER (
        PARTITION BY target_id, field, match_scope
      ) > 1 THEN error('Conflicting research corrections for BBL ' || bbl || ', field ' || field || ', pass ' || match_scope)
      ELSE new_value
    END AS new_value
  )
  FROM specific_events
  WHERE audit_status = 'applied'
  QUALIFY row_number() OVER (
    PARTITION BY target_id, field, match_scope
    ORDER BY "bbl" NULLS FIRST, "field" NULLS FIRST, "old_value" NULLS FIRST, "new_value" NULLS FIRST, "Type" NULLS FIRST, "reason" NULLS FIRST, "version" NULLS FIRST
  ) = 1
),
global_fields AS (
  SELECT DISTINCT field FROM research
  WHERE bbl IS NULL AND field IN ('yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs', 'unitsres', 'unitstotal', 'bct2020', 'address')
),
values_after_specific AS (
  -- Global matches see the value after the parcel-specific pass, not the
  -- original lot or final row. Project each relevant field once, then hash-join
  -- old values; avoid a citywide lot-by-research-rule Cartesian product.
  SELECT a.id AS target_id, a.bbl, f.field,
    CASE WHEN s.target_id IS NOT NULL THEN s.new_value ELSE CASE f.field
          WHEN 'yearbuilt' THEN a."yearbuilt"
          WHEN 'ownername' THEN a."ownername"
          WHEN 'cd' THEN a."cd"
          WHEN 'numfloors' THEN a."numfloors"
          WHEN 'numbldgs' THEN a."numbldgs"
          WHEN 'unitsres' THEN a."unitsres"
          WHEN 'unitstotal' THEN a."unitstotal"
          WHEN 'bct2020' THEN a."bct2020"
          WHEN 'address' THEN a."address"
        END END AS found_value
  FROM {{ ref('parcel_mapping_flags') }} AS a
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
    101 + list_position(['yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs', 'unitsres', 'unitstotal', 'bct2020', 'address'], field) * 10 AS phase,
    'global' AS match_scope, 'applied' AS audit_status,
    bbl, field, old_value, new_value, "Type", reason, version, found_value
  FROM global_candidates
  WHERE found_value IS NOT DISTINCT FROM old_value
)
SELECT * FROM specific_events
UNION ALL SELECT * FROM global_events
