{{ config(materialized='view') }}
-- Business process: archive_pluto
WITH
export_archive_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/export.sql statement 4
  SELECT
    a.*,
    b.clipped_4326 AS geom
  FROM {{ ref('export_pluto') }} AS a
  LEFT JOIN {{ ref('pluto_geom') }} AS b
    ON CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
)
SELECT * FROM export_archive_pluto
