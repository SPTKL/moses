{{ config(materialized='table') }}
-- Business process: shoreline_coverage
WITH
subdivided_shoreline_coverage AS NOT MATERIALIZED (
  -- pluto_build/sql/plutomapid.sql statement 4
  SELECT
    (
      UNNEST(ST_DUMP(MOSES_SUBDIVIDE(moses_makevalid(geom), 100)))
    ).geom AS geom
  FROM (
    SELECT
      MOSES_UNION_AGG(geom) AS geom
    FROM ({{ pluto_input('stg__dof_shoreline') }}) AS stg__dof_shoreline
  ) AS a
)
SELECT * FROM subdivided_shoreline_coverage
