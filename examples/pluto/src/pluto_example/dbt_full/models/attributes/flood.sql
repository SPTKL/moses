{{ config(materialized='table') }}
-- Business process: flood
WITH
flood_flag_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/flood_flag.sql statement 1
  -- Code of 1 means that some portion of the tax lot falls within the 1% annual chance floodplain
  -- using defs from here https://snmapmod.snco.us/fmm/document/fema-flood-zone-definitions.pdf
  -- for 2007 floodplain
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN __patch.__matched
        THEN MOSES_TEXT(__patch."firm07_flag")
        ELSE "a"."firm07_flag"
      END AS "firm07_flag"
    )
  FROM {{ ref('parcel_classification') }} AS "a"
  LEFT JOIN LATERAL (
    SELECT
      TRUE AS __matched,
      '1' AS "firm07_flag"
    FROM (
      SELECT
        (
          UNNEST(ST_DUMP(MOSES_SUBDIVIDE(moses_makevalid(geom), 256)))
        ).geom AS geom
      FROM ({{ pluto_input('stg__fema_firms2007_100yr') }}) AS b
      WHERE
        b.fld_zone <> 'X' AND b.fld_zone <> '0.2 PCT ANNUAL CHANCE FLOOD HAZARD'
    ) AS b
    WHERE
      a.geom && b.geom AND ST_INTERSECTS(a.geom, b.geom)
    LIMIT 1
  ) AS __patch
    ON TRUE
),
flood_flag_pluto_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/flood_flag.sql statement 2
  -- for 2015 p floodplain
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN __patch.__matched
        THEN MOSES_TEXT(__patch."pfirm15_flag")
        ELSE "a"."pfirm15_flag"
      END AS "pfirm15_flag"
    )
  FROM flood_flag_pluto AS "a"
  LEFT JOIN LATERAL (
    SELECT
      TRUE AS __matched,
      '1' AS "pfirm15_flag"
    FROM (
      SELECT
        (
          UNNEST(ST_DUMP(MOSES_SUBDIVIDE(moses_makevalid(geom), 256)))
        ).geom AS geom
      FROM ({{ pluto_input('stg__fema_pfirms2015_100yr') }}) AS b
      WHERE
        b.fld_zone <> 'X' AND b.fld_zone <> '0.2 PCT ANNUAL CHANCE FLOOD HAZARD'
    ) AS b
    WHERE
      a.geom && b.geom AND ST_INTERSECTS(a.geom, b.geom)
    LIMIT 1
  ) AS __patch
    ON TRUE
)
SELECT * FROM flood_flag_pluto_2
