{{ config(materialized='table') }}
-- Business process: service_geography
WITH
unique_parcel_ids_guard AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 3
  SELECT CASE WHEN COUNT(*)=COUNT(id) AND COUNT(*)=COUNT(DISTINCT id) THEN TRUE ELSE error('PLUTO spatial update requires unique non-null serial ids') END AS valid FROM {{ ref('political_geography') }}
),
school_district_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 8
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."schooldist") AS "schooldist"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.schooldist AS "schooldist"
    FROM ({{ pluto_input('stg__dcp_school_districts') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.schooldist IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
council_district_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 9
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."council") AS "council"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      LTRIM(MOSES_TEXT(b.coundist), '0') AS "council"
    FROM ({{ pluto_input('stg__dcp_councildistricts_wi') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.council IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
fire_company_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 10
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."firecomp") AS "firecomp"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.firecotype || LPAD(MOSES_TEXT(b.fireconum), 3, '0') AS "firecomp"
    FROM ({{ pluto_input('stg__dcp_firecompanies') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.firecomp IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
police_precinct_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 11
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."policeprct") AS "policeprct"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.precinct AS "policeprct"
    FROM ({{ pluto_input('stg__dcp_policeprecincts') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.policeprct IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
health_center_district_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 12
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."healthcenterdistrict") AS "healthcenterdistrict"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.hcentdist AS "healthcenterdistrict"
    FROM ({{ pluto_input('stg__dcp_healthcenters') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom)
      AND a.healthcenterdistrict IS NULL
      AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
health_area_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 13
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."healtharea") AS "healtharea"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.healtharea AS "healtharea"
    FROM ({{ pluto_input('stg__dcp_healthareas') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.healtharea IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
sanitation_district_and_subdistrict_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 14
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."sanitsub") AS "sanitsub",
    MOSES_TEXT(__patch."sanitdistrict") AS "sanitdistrict"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      LEFT(schedulecode, 3) AS "sanitdistrict",
      RIGHT(schedulecode, 2) AS "sanitsub"
    FROM ({{ pluto_input('stg__dsny_frequencies') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom)
      AND (
        a.sanitsub IS NULL OR a.sanitsub = ' '
      )
      AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
zip_code_matches AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 15
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."zipcode") AS "zipcode"
  FROM {{ ref('political_geography') }} AS "a"
  CROSS JOIN unique_parcel_ids_guard AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.zipcode AS "zipcode"
    FROM ({{ pluto_input('stg__doitt_zipcodeboundaries') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.zipcode IS NULL AND a.xcoord IS NOT NULL
    ORDER BY
      MOSES_TEXT("b"."zipcode") ASC NULLS LAST,
      MOSES_TEXT("b"."ogc_fid") ASC NULLS LAST,
      MOSES_TEXT("b"."area") ASC NULLS LAST,
      MOSES_TEXT("b"."bldgzip") ASC NULLS LAST,
      MOSES_TEXT("b"."county") ASC NULLS LAST,
      MOSES_TEXT("b"."cty_fips") ASC NULLS LAST,
      HEX(ST_ASWKB("b"."geom")) ASC NULLS LAST,
      MOSES_TEXT("b"."po_name") ASC NULLS LAST,
      MOSES_TEXT("b"."population") ASC NULLS LAST,
      MOSES_TEXT("b"."shape_area") ASC NULLS LAST,
      MOSES_TEXT("b"."shape_len") ASC NULLS LAST,
      MOSES_TEXT("b"."st_fips") ASC NULLS LAST,
      MOSES_TEXT("b"."state") ASC NULLS LAST,
      MOSES_TEXT("b"."url") ASC NULLS LAST,
      HEX(ST_ASWKB("b"."wkb_geometry")) ASC NULLS LAST
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
parcels_with_service_geography AS NOT MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 16
  SELECT p.* EXCLUDE ("centroid") REPLACE (CASE WHEN matched_schooldist.__matched THEN matched_schooldist."schooldist" ELSE p."schooldist" END AS "schooldist", CASE WHEN matched_council.__matched THEN matched_council."council" ELSE p."council" END AS "council", CASE WHEN matched_firecomp.__matched THEN matched_firecomp."firecomp" ELSE p."firecomp" END AS "firecomp", CASE WHEN matched_policeprct.__matched THEN matched_policeprct."policeprct" ELSE p."policeprct" END AS "policeprct", CASE WHEN matched_healthcenterdistrict.__matched THEN matched_healthcenterdistrict."healthcenterdistrict" ELSE p."healthcenterdistrict" END AS "healthcenterdistrict", CASE WHEN matched_healtharea.__matched THEN matched_healtharea."healtharea" ELSE p."healtharea" END AS "healtharea", CASE WHEN matched_sanitsub_sanitdistrict.__matched THEN matched_sanitsub_sanitdistrict."sanitsub" ELSE p."sanitsub" END AS "sanitsub", CASE WHEN matched_sanitsub_sanitdistrict.__matched THEN matched_sanitsub_sanitdistrict."sanitdistrict" ELSE p."sanitdistrict" END AS "sanitdistrict", CASE WHEN matched_zipcode.__matched THEN matched_zipcode."zipcode" ELSE p."zipcode" END AS "zipcode") FROM {{ ref('political_geography') }} AS p
  LEFT JOIN school_district_matches AS matched_schooldist ON p.id=matched_schooldist.id
  LEFT JOIN council_district_matches AS matched_council ON p.id=matched_council.id
  LEFT JOIN fire_company_matches AS matched_firecomp ON p.id=matched_firecomp.id
  LEFT JOIN police_precinct_matches AS matched_policeprct ON p.id=matched_policeprct.id
  LEFT JOIN health_center_district_matches AS matched_healthcenterdistrict ON p.id=matched_healthcenterdistrict.id
  LEFT JOIN health_area_matches AS matched_healtharea ON p.id=matched_healtharea.id
  LEFT JOIN sanitation_district_and_subdistrict_matches AS matched_sanitsub_sanitdistrict ON p.id=matched_sanitsub_sanitdistrict.id
  LEFT JOIN zip_code_matches AS matched_zipcode ON p.id=matched_zipcode.id
  CROSS JOIN unique_parcel_ids_guard AS required_ids WHERE required_ids.valid
)
SELECT * FROM parcels_with_service_geography
