{{ config(materialized='table') }}
-- Business process: pluto_geom
WITH
shorelineclip_shoreline_bbl AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 2
  SELECT DISTINCT
    CAST(bbl AS BIGINT) AS "bbl"
  FROM {{ ref('map_flags') }} AS a, {{ ref('shoreline_coverage') }} AS b
  WHERE
    ST_INTERSECTS(a.geom, b.geom)
),
shorelineclip_geom_tmp AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 4
  SELECT
    bbl,
    moses_makevalid(MOSES_TRANSFORM_CRS(a.geom, 4326, 2263)) AS geom_2263,
    moses_makevalid(a.geom) AS geom_4326,
    CASE
      WHEN CAST(bbl AS BIGINT) IN (
        SELECT
          CAST(bbl AS BIGINT) AS "bbl"
        FROM shorelineclip_shoreline_bbl AS shoreline_bbl
      )
      THEN 1
      ELSE 0
    END AS shoreline
  FROM {{ ref('map_flags') }} AS a
),
shorelineclip_geom AS NOT MATERIALIZED (
  -- pluto_build/sql/shorelineclip.sql statement 7
  WITH subdivided AS (
    SELECT
      a.bbl,
      b.geom
    FROM shorelineclip_geom_tmp AS a, {{ ref('shoreline_coverage') }} AS b
    WHERE
      shoreline = 1 AND ST_INTERSECTS(a.geom_4326, b.geom)
  ), subdivided_union AS (
    SELECT
      CAST(bbl AS BIGINT) AS "bbl",
      moses_makevalid(MOSES_UNION_AGG(geom)) AS geom
    FROM subdivided
    GROUP BY
      bbl
  ), clipped AS (
    SELECT
      CAST(a.bbl AS BIGINT) AS "bbl",
      ST_MULTI(ST_COLLECTIONEXTRACT(ST_DIFFERENCE(a.geom_4326, b.geom), 3)) AS geom
    FROM shorelineclip_geom_tmp AS a, subdivided_union AS b
    WHERE
      CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
  )
  SELECT
    a.bbl,
    a.geom_2263,
    a.geom_4326,
    COALESCE(b.geom, a.geom_4326) AS clipped_4326,
    COALESCE(MOSES_TRANSFORM_CRS(b.geom, 4326, 2263), a.geom_2263) AS clipped_2263
  FROM shorelineclip_geom_tmp AS a
  LEFT JOIN clipped AS b
    ON CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
)
SELECT * FROM shorelineclip_geom
