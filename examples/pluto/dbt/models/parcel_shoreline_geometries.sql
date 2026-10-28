{{ config(materialized='table', alias='pluto_geom') }}
-- Business process: parcel_shoreline_geometries
WITH
shoreline_intersecting_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 2
  SELECT DISTINCT
    CAST(bbl AS BIGINT) AS "bbl"
  FROM {{ ref('parcel_mapping_flags') }} AS a, {{ ref('shoreline_coverage') }} AS b
  WHERE
    ST_INTERSECTS(a.geom, b.geom)
),
parcel_geometries_with_shoreline_flag AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 4
  SELECT
    bbl,
    moses_makevalid(MOSES_TRANSFORM_CRS(a.geom, 4326, 2263)) AS geom_2263,
    moses_makevalid(a.geom) AS geom_4326,
    CASE
      WHEN CAST(bbl AS BIGINT) IN (
        SELECT
          CAST(bbl AS BIGINT) AS "bbl"
        FROM shoreline_intersecting_bbls AS shoreline_bbl
      )
      THEN 1
      ELSE 0
    END AS shoreline
  FROM {{ ref('parcel_mapping_flags') }} AS a
),
parcel_geometries_clipped_to_shoreline AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 7
  WITH shoreline_intersections AS (
    SELECT
      a.bbl,
      b.geom
    FROM parcel_geometries_with_shoreline_flag AS a, {{ ref('shoreline_coverage') }} AS b
    WHERE
      shoreline = 1 AND ST_INTERSECTS(a.geom_4326, b.geom)
  ), shoreline_union_by_lot AS (
    SELECT
      CAST(bbl AS BIGINT) AS "bbl",
      moses_makevalid(MOSES_UNION_AGG(geom)) AS geom
    FROM shoreline_intersections
    GROUP BY
      bbl
  ), landward_parcel_geometries AS (
    SELECT
      CAST(a.bbl AS BIGINT) AS "bbl",
      ST_MULTI(ST_COLLECTIONEXTRACT(ST_DIFFERENCE(a.geom_4326, b.geom), 3)) AS geom
    FROM parcel_geometries_with_shoreline_flag AS a, shoreline_union_by_lot AS b
    WHERE
      CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
  )
  SELECT
    a.bbl,
    a.geom_2263,
    a.geom_4326,
    COALESCE(b.geom, a.geom_4326) AS clipped_4326,
    COALESCE(MOSES_TRANSFORM_CRS(b.geom, 4326, 2263), a.geom_2263) AS clipped_2263
  FROM parcel_geometries_with_shoreline_flag AS a
  LEFT JOIN landward_parcel_geometries AS b
    ON CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
)
SELECT * FROM parcel_geometries_clipped_to_shoreline
