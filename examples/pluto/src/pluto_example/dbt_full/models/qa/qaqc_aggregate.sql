{{ config(materialized='view') }}
-- Business process: qaqc_aggregate
WITH
qaqc_aggregate_qaqc_aggregate_true_true AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_aggregate.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS v,
      TRUE AS condo,
      TRUE AS mapped,
      CAST(SUM(CAST(unitsres AS DECIMAL(38, 12))) AS BIGINT) AS unitsres,
      CAST(SUM(CAST(lotarea AS DECIMAL(38, 12))) AS BIGINT) AS lotarea,
      CAST(SUM(CAST(bldgarea AS DECIMAL(38, 12))) AS BIGINT) AS bldgarea,
      CAST(SUM(CAST(comarea AS DECIMAL(38, 12))) AS BIGINT) AS comarea,
      CAST(SUM(CAST(resarea AS DECIMAL(38, 12))) AS BIGINT) AS resarea,
      CAST(SUM(CAST(officearea AS DECIMAL(38, 12))) AS BIGINT) AS officearea,
      CAST(SUM(CAST(retailarea AS DECIMAL(38, 12))) AS BIGINT) AS retailarea,
      CAST(SUM(CAST(garagearea AS DECIMAL(38, 12))) AS BIGINT) AS garagearea,
      CAST(SUM(CAST(strgearea AS DECIMAL(38, 12))) AS BIGINT) AS strgearea,
      CAST(SUM(CAST(factryarea AS DECIMAL(38, 12))) AS BIGINT) AS factryarea,
      CAST(SUM(CAST(otherarea AS DECIMAL(38, 12))) AS BIGINT) AS otherarea,
      CAST(SUM(CAST(assessland AS DECIMAL(38, 12))) AS BIGINT) AS assessland,
      CAST(SUM(CAST(assesstot AS DECIMAL(38, 12))) AS BIGINT) AS assesstot,
      CAST(SUM(CAST(exempttot AS DECIMAL(38, 12))) AS BIGINT) AS exempttot,
      CAST(SUM(CAST(firm07_flag AS DECIMAL(38, 12))) AS BIGINT) AS firm07_flag,
      CAST(SUM(CAST(pfirm15_flag AS DECIMAL(38, 12))) AS BIGINT) AS pfirm15_flag
    FROM {{ ref('archive_pluto') }} AS a
    WHERE
      a.geom IS NOT NULL AND RIGHT(MOSES_TEXT(CAST(a.bbl AS BIGINT)), 4) LIKE '75%%'
  )
),
qaqc_aggregate_qaqc_aggregate_true_false AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_aggregate.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS v,
      FALSE AS condo,
      TRUE AS mapped,
      CAST(SUM(CAST(unitsres AS DECIMAL(38, 12))) AS BIGINT) AS unitsres,
      CAST(SUM(CAST(lotarea AS DECIMAL(38, 12))) AS BIGINT) AS lotarea,
      CAST(SUM(CAST(bldgarea AS DECIMAL(38, 12))) AS BIGINT) AS bldgarea,
      CAST(SUM(CAST(comarea AS DECIMAL(38, 12))) AS BIGINT) AS comarea,
      CAST(SUM(CAST(resarea AS DECIMAL(38, 12))) AS BIGINT) AS resarea,
      CAST(SUM(CAST(officearea AS DECIMAL(38, 12))) AS BIGINT) AS officearea,
      CAST(SUM(CAST(retailarea AS DECIMAL(38, 12))) AS BIGINT) AS retailarea,
      CAST(SUM(CAST(garagearea AS DECIMAL(38, 12))) AS BIGINT) AS garagearea,
      CAST(SUM(CAST(strgearea AS DECIMAL(38, 12))) AS BIGINT) AS strgearea,
      CAST(SUM(CAST(factryarea AS DECIMAL(38, 12))) AS BIGINT) AS factryarea,
      CAST(SUM(CAST(otherarea AS DECIMAL(38, 12))) AS BIGINT) AS otherarea,
      CAST(SUM(CAST(assessland AS DECIMAL(38, 12))) AS BIGINT) AS assessland,
      CAST(SUM(CAST(assesstot AS DECIMAL(38, 12))) AS BIGINT) AS assesstot,
      CAST(SUM(CAST(exempttot AS DECIMAL(38, 12))) AS BIGINT) AS exempttot,
      CAST(SUM(CAST(firm07_flag AS DECIMAL(38, 12))) AS BIGINT) AS firm07_flag,
      CAST(SUM(CAST(pfirm15_flag AS DECIMAL(38, 12))) AS BIGINT) AS pfirm15_flag
    FROM {{ ref('archive_pluto') }} AS a
    WHERE
      a.geom IS NOT NULL
  )
),
qaqc_aggregate_qaqc_aggregate_false_true AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_aggregate.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS v,
      TRUE AS condo,
      FALSE AS mapped,
      CAST(SUM(CAST(unitsres AS DECIMAL(38, 12))) AS BIGINT) AS unitsres,
      CAST(SUM(CAST(lotarea AS DECIMAL(38, 12))) AS BIGINT) AS lotarea,
      CAST(SUM(CAST(bldgarea AS DECIMAL(38, 12))) AS BIGINT) AS bldgarea,
      CAST(SUM(CAST(comarea AS DECIMAL(38, 12))) AS BIGINT) AS comarea,
      CAST(SUM(CAST(resarea AS DECIMAL(38, 12))) AS BIGINT) AS resarea,
      CAST(SUM(CAST(officearea AS DECIMAL(38, 12))) AS BIGINT) AS officearea,
      CAST(SUM(CAST(retailarea AS DECIMAL(38, 12))) AS BIGINT) AS retailarea,
      CAST(SUM(CAST(garagearea AS DECIMAL(38, 12))) AS BIGINT) AS garagearea,
      CAST(SUM(CAST(strgearea AS DECIMAL(38, 12))) AS BIGINT) AS strgearea,
      CAST(SUM(CAST(factryarea AS DECIMAL(38, 12))) AS BIGINT) AS factryarea,
      CAST(SUM(CAST(otherarea AS DECIMAL(38, 12))) AS BIGINT) AS otherarea,
      CAST(SUM(CAST(assessland AS DECIMAL(38, 12))) AS BIGINT) AS assessland,
      CAST(SUM(CAST(assesstot AS DECIMAL(38, 12))) AS BIGINT) AS assesstot,
      CAST(SUM(CAST(exempttot AS DECIMAL(38, 12))) AS BIGINT) AS exempttot,
      CAST(SUM(CAST(firm07_flag AS DECIMAL(38, 12))) AS BIGINT) AS firm07_flag,
      CAST(SUM(CAST(pfirm15_flag AS DECIMAL(38, 12))) AS BIGINT) AS pfirm15_flag
    FROM {{ ref('archive_pluto') }} AS a
    WHERE
      RIGHT(MOSES_TEXT(CAST(a.bbl AS BIGINT)), 4) LIKE '75%%'
  )
),
qaqc_aggregate_qaqc_aggregate_false_false AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_aggregate.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS v,
      FALSE AS condo,
      FALSE AS mapped,
      CAST(SUM(CAST(unitsres AS DECIMAL(38, 12))) AS BIGINT) AS unitsres,
      CAST(SUM(CAST(lotarea AS DECIMAL(38, 12))) AS BIGINT) AS lotarea,
      CAST(SUM(CAST(bldgarea AS DECIMAL(38, 12))) AS BIGINT) AS bldgarea,
      CAST(SUM(CAST(comarea AS DECIMAL(38, 12))) AS BIGINT) AS comarea,
      CAST(SUM(CAST(resarea AS DECIMAL(38, 12))) AS BIGINT) AS resarea,
      CAST(SUM(CAST(officearea AS DECIMAL(38, 12))) AS BIGINT) AS officearea,
      CAST(SUM(CAST(retailarea AS DECIMAL(38, 12))) AS BIGINT) AS retailarea,
      CAST(SUM(CAST(garagearea AS DECIMAL(38, 12))) AS BIGINT) AS garagearea,
      CAST(SUM(CAST(strgearea AS DECIMAL(38, 12))) AS BIGINT) AS strgearea,
      CAST(SUM(CAST(factryarea AS DECIMAL(38, 12))) AS BIGINT) AS factryarea,
      CAST(SUM(CAST(otherarea AS DECIMAL(38, 12))) AS BIGINT) AS otherarea,
      CAST(SUM(CAST(assessland AS DECIMAL(38, 12))) AS BIGINT) AS assessland,
      CAST(SUM(CAST(assesstot AS DECIMAL(38, 12))) AS BIGINT) AS assesstot,
      CAST(SUM(CAST(exempttot AS DECIMAL(38, 12))) AS BIGINT) AS exempttot,
      CAST(SUM(CAST(firm07_flag AS DECIMAL(38, 12))) AS BIGINT) AS firm07_flag,
      CAST(SUM(CAST(pfirm15_flag AS DECIMAL(38, 12))) AS BIGINT) AS pfirm15_flag
    FROM {{ ref('archive_pluto') }} AS a
  )
),
rule_05_qaqc_qaqc_aggregate AS NOT MATERIALIZED (
  -- 05_qaqc.sh current-release variants
  SELECT
    *
  FROM qaqc_aggregate_qaqc_aggregate_true_true AS qaqc_aggregate_true_true
  UNION ALL
  SELECT
    *
  FROM qaqc_aggregate_qaqc_aggregate_true_false AS qaqc_aggregate_true_false
  UNION ALL
  SELECT
    *
  FROM qaqc_aggregate_qaqc_aggregate_false_true AS qaqc_aggregate_false_true
  UNION ALL
  SELECT
    *
  FROM qaqc_aggregate_qaqc_aggregate_false_false AS qaqc_aggregate_false_false
)
SELECT * FROM rule_05_qaqc_qaqc_aggregate
