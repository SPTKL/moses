{{ config(materialized='view', alias='qaqc_bbl_diffs') }}
-- Business process: qa_bbl_membership_changes
WITH
current_vs_previous_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/qaqc_bbl_diffs.sql current-release SELECTs
  (
    SELECT
      '{{ var("pluto_version") }}' AS source_version,
      MOSES_TEXT(CAST(CAST(ap.bbl AS DOUBLE) AS BIGINT)) AS bbl,
      'new' AS type
    FROM {{ ref('archive_pluto') }} AS ap
    LEFT JOIN ({{ pluto_input('previous_pluto') }}) AS pp
      ON CAST(CAST(ap.bbl AS DOUBLE) AS BIGINT) = CAST(CAST(pp.bbl AS DOUBLE) AS BIGINT)
    WHERE
      pp.bbl IS NULL
  )
  UNION ALL
  (
    SELECT
      '{{ var("previous_pluto_version") }}' AS source_version,
      MOSES_TEXT(CAST(CAST(pp.bbl AS DOUBLE) AS BIGINT)) AS bbl,
      'vanished' AS type
    FROM ({{ pluto_input('previous_pluto') }}) AS pp
    LEFT JOIN {{ ref('archive_pluto') }} AS ap
      ON CAST(CAST(ap.bbl AS DOUBLE) AS BIGINT) = CAST(CAST(pp.bbl AS DOUBLE) AS BIGINT)
    WHERE
      ap.bbl IS NULL
  )
),
bbl_membership_changes AS NOT MATERIALIZED (
  -- 05_qaqc.sh current-release variants
  SELECT
    *
  FROM current_vs_previous_bbls AS qaqc_bbl_diffs_current
)
SELECT * FROM bbl_membership_changes
