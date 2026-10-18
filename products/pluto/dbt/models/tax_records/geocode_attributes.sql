{{ config(materialized='table') }}
-- Business process: geocode_attributes
WITH
create_rpad_geo_stg__pluto_input_geocodes AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 1
  -- getting distinct BBLs FROM raw data
  SELECT
    *
    RENAME ("bbl" AS "geo_bbl")
  FROM ({{ pluto_input('stg__pluto_input_geocodes') }}) AS stg__pluto_input_geocodes
),
create_rpad_geo_stg__pluto_input_geocodes_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 2
  SELECT
    *,
    MOSES_TEXT(NULL) AS "xcoord"
  FROM create_rpad_geo_stg__pluto_input_geocodes AS stg__pluto_input_geocodes
),
create_rpad_geo_stg__pluto_input_geocodes_3 AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 3
  SELECT
    *,
    MOSES_TEXT(NULL) AS "ycoord"
  FROM create_rpad_geo_stg__pluto_input_geocodes_2 AS stg__pluto_input_geocodes
),
create_rpad_geo_assign_ct2010_xcoord_ycoord AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 4
  SELECT
    "stg__pluto_input_geocodes".*
    REPLACE (
      MOSES_TEXT((
          CASE
            WHEN CAST(ct2010 AS DECIMAL(38, 12)) = 0
            THEN NULL
            ELSE ct2010
          END
        )) AS "ct2010",
      MOSES_TEXT(CAST(ST_X(MOSES_TRANSFORM_CRS(geom, 4326, 2263)) AS INT)) AS "xcoord",
      MOSES_TEXT(CAST(ST_Y(MOSES_TRANSFORM_CRS(geom, 4326, 2263)) AS INT)) AS "ycoord"
    )
  FROM create_rpad_geo_stg__pluto_input_geocodes_3 AS "stg__pluto_input_geocodes"
)
SELECT * FROM create_rpad_geo_assign_ct2010_xcoord_ycoord
