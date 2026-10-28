{{ config(materialized='view', alias='qaqc_expected') }}
-- Business process: qa_expected_derived_values
WITH
current_expected_values AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_expected.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS v,
      TO_JSON(LIST(t)) AS expected
    FROM (
      SELECT
        TO_JSON(LIST(zonedist1)) AS values,
        'zonedist1' AS field
      FROM (
        SELECT DISTINCT
          zonedist1
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(zonedist2)) AS values,
        'zonedist2' AS field
      FROM (
        SELECT DISTINCT
          zonedist2
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(zonedist3)) AS values,
        'zonedist3' AS field
      FROM (
        SELECT DISTINCT
          zonedist3
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(zonedist4)) AS values,
        'zonedist4' AS field
      FROM (
        SELECT DISTINCT
          zonedist4
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(overlay1)) AS values,
        'overlay1' AS field
      FROM (
        SELECT DISTINCT
          overlay1
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(overlay2)) AS values,
        'overlay2' AS field
      FROM (
        SELECT DISTINCT
          overlay2
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(spdist1)) AS values,
        'spdist1' AS field
      FROM (
        SELECT DISTINCT
          spdist1
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(spdist2)) AS values,
        'spdist2' AS field
      FROM (
        SELECT DISTINCT
          spdist2
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(spdist3)) AS values,
        'spdist3' AS field
      FROM (
        SELECT DISTINCT
          spdist3
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(ext)) AS values,
        'ext' AS field
      FROM (
        SELECT DISTINCT
          ext
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(proxcode)) AS values,
        'proxcode' AS field
      FROM (
        SELECT DISTINCT
          proxcode
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(irrlotcode)) AS values,
        'irrlotcode' AS field
      FROM (
        SELECT DISTINCT
          irrlotcode
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(lottype)) AS values,
        'lottype' AS field
      FROM (
        SELECT DISTINCT
          lottype
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(bsmtcode)) AS values,
        'bsmtcode' AS field
      FROM (
        SELECT DISTINCT
          bsmtcode
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
      UNION
      SELECT
        TO_JSON(LIST(bldgclasslanduse)) AS values,
        'bldgclasslanduse' AS field
      FROM (
        SELECT DISTINCT
          bldgclass || '/' || landuse AS bldgclasslanduse
        FROM {{ ref('archive_pluto') }} AS archive_pluto
      ) AS a
    ) AS t
  )
),
expected_value_report AS NOT MATERIALIZED (
  -- 05_qaqc.sh current-release variants
  SELECT
    *
  FROM current_expected_values AS qaqc_expected_current
)
SELECT * FROM expected_value_report
