{{ config(materialized='table') }}
-- Business process: normalized_parcels
WITH
numericfields_geomfields_assign_ct2010 AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 1
  -- add decimal in ct2010 where there is a suffix
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN REGEXP_MATCHES(a.ct2010, '[0-9]') AND ct2010 NOT LIKE '%00'
        THEN MOSES_TEXT(LEFT(a.ct2010, 4) || '.' || RIGHT(a.ct2010, 2))
        ELSE "a"."ct2010"
      END AS "ct2010"
    )
  FROM {{ ref('service_geography') }} AS "a"
),
numericfields_geomfields_assign_ct2010_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 2
  -- remove suffix in ct2010 where it is only zero after decimal
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN REGEXP_MATCHES(a.ct2010, '[0-9]') AND ct2010 LIKE '%00'
        THEN MOSES_TEXT(LEFT(a.ct2010, 4))
        ELSE "a"."ct2010"
      END AS "ct2010"
    )
  FROM numericfields_geomfields_assign_ct2010 AS "a"
),
numericfields_geomfields_assign_ct2010_3 AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 3
  -- make values numeric
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN REGEXP_MATCHES(a.ct2010, '[0-9]')
        THEN MOSES_TEXT(MOSES_CENSUS_TRACT_NUMERIC_TEXT("a".ct2010))
        ELSE "a"."ct2010"
      END AS "ct2010"
    )
  FROM numericfields_geomfields_assign_ct2010_2 AS "a"
),
numericfields_geomfields_assign_tract2010 AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 5
  /* only allow numeric values in the ct2010 field */
  /* remove end zeros for numbers with only zeros past decimal and pad to 4 characters */
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN NOT REGEXP_MATCHES(a.ct2010, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."ct2010"
      END AS "ct2010",
      CASE
        WHEN tract2010 LIKE '%00'
        THEN MOSES_TEXT(LEFT("a".tract2010, 4))
        ELSE "a"."tract2010"
      END AS "tract2010"
    )
  FROM numericfields_geomfields_assign_ct2010_3 AS "a"
),
numericfields_geomfields_assign_tract2010_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 6
  -- remove decimal place and pad to 6 characters
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN tract2010 LIKE '%.%'
        THEN MOSES_TEXT(LPAD(MOSES_TEXT(REPLACE(tract2010, '.', '')), 6, '0'))
        ELSE "a"."tract2010"
      END AS "tract2010"
    )
  FROM numericfields_geomfields_assign_tract2010 AS "a"
),
numericfields_geomfields_assign_sanitdistrict AS NOT MATERIALIZED (
  -- pluto_build/sql/numericfields_geomfields.sql statement 13
  /* only allow numeric values in the tract2010 field */
  /* pad school district to 2 characters */
  /* where sanborn is just spaces set to NULL */
  /* where x/y cood is just spaces set to NULL */
  /* make appbbl a single 0 where it's zero */
  /* make sanitdistrict numeric */
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN REGEXP_MATCHES(a.tract2010, '[^0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."tract2010"
      END AS "tract2010",
      MOSES_TEXT(LPAD(schooldist, 2, '0')) AS "schooldist",
      CASE
        WHEN NOT REGEXP_MATCHES("a".sanborn, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."sanborn"
      END AS "sanborn",
      CASE
        WHEN NOT REGEXP_MATCHES("a".xcoord, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."xcoord"
      END AS "xcoord",
      CASE
        WHEN NOT REGEXP_MATCHES("a".ycoord, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."ycoord"
      END AS "ycoord",
      CASE
        WHEN CAST(appbbl AS DECIMAL(38, 12)) = 0
        THEN MOSES_TEXT('0')
        ELSE "a"."appbbl"
      END AS "appbbl",
      MOSES_TEXT(CAST(sanitdistrict AS INT)) AS "sanitdistrict"
    )
  FROM numericfields_geomfields_assign_tract2010_2 AS "a"
),
sanitboro_assign_sanitdistrict AS NOT MATERIALIZED (
  -- pluto_build/sql/sanitboro.sql statement 2
  /* set the sanitation boro */
  /* set the sanitdistrict to not include sanitboro */
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN NOT sanitdistrict IS NULL
        THEN MOSES_TEXT(LEFT(sanitdistrict, 1))
        ELSE "pluto"."sanitboro"
      END AS "sanitboro",
      CASE
        WHEN NOT sanitdistrict IS NULL
        THEN MOSES_TEXT(RIGHT(sanitdistrict, 2))
        ELSE "pluto"."sanitdistrict"
      END AS "sanitdistrict"
    )
  FROM numericfields_geomfields_assign_sanitdistrict AS "pluto"
)
SELECT * FROM sanitboro_assign_sanitdistrict
