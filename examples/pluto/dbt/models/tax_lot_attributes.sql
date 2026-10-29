{{ config(materialized='table') }}
-- Business process: tax_lot_attributes
WITH
pts_lots_with_geocodes AS MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 6
  WITH ranked_pts_lots AS (
    SELECT
      a.*,
      ROW_NUMBER() OVER (
        PARTITION BY boro || tb || tl
        ORDER BY curavt_act DESC NULLS FIRST, land_area DESC NULLS FIRST, ease ASC
      ) AS row_number
    FROM ({{ pluto_input('pts_properties_base') }}) AS a
  ), preferred_pts_lots AS (
    SELECT
      *
    FROM ranked_pts_lots
    WHERE
      row_number = 1
  )
  SELECT
    a.*,
    b.*
  FROM preferred_pts_lots AS a
  LEFT JOIN {{ ref('geocode_attributes') }} AS b
    ON a.boro || a.tb || a.tl = b.borough || LPAD(b.block, 5, '0') || LPAD(b.lot, 4, '0')
),
renamed_structure_counts AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 7
  SELECT
    *
    RENAME ("numberofexistingstructures" AS "numberofexistingstructuresonlot")
  FROM pts_lots_with_geocodes AS pluto_rpad_geo
),
initialized_apportionment_dates AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 8
  SELECT
    *,
    MOSES_TEXT(NULL) AS "ap_datef"
  FROM renamed_structure_counts AS pluto_rpad_geo
),
tax_lots_with_bbl AS NOT MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 9
  SELECT
    "pluto_rpad_geo".*
    REPLACE (
      MOSES_TEXT(borough || LPAD(block, 5, '0') || LPAD(lot, 4, '0')) AS "bbl"
    )
  FROM initialized_apportionment_dates AS "pluto_rpad_geo"
),
tax_lots_with_coordinates AS MATERIALIZED (
  -- pluto_build/sql/create_rpad_geo.sql statement 10
  -- backfill X and Y coordinates
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CAST(ST_X(MOSES_TRANSFORM_CRS(b.geom, 4326, 2263)) AS INT))
        ELSE "a"."xcoord"
      END AS "xcoord",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CAST(ST_Y(MOSES_TRANSFORM_CRS(b.geom, 4326, 2263)) AS INT))
        ELSE "a"."ycoord"
      END AS "ycoord"
    )
  FROM tax_lots_with_bbl AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM (
      SELECT
        a.bbl,
        ST_SETSRID(ST_POINT(CAST(a.longitude AS DOUBLE), CAST(a.latitude AS DOUBLE)), 4326) AS geom
      FROM tax_lots_with_bbl AS a
      WHERE
        a.longitude IS NOT NULL
    ) AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
vacant_lot_building_values AS NOT MATERIALIZED (
  -- pluto_build/sql/zerovacantlots.sql statement 1
  -- Zeroing out values for vacant land
  -- If vacant building and AV land = AV total
  -- then zero out building frontage, building debth, num stories, and number of buildings
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.curavl_act = a.curavt_act AND UPPER(bldgcl) LIKE 'V%'
        THEN CAST('0' AS DOUBLE)
        ELSE "a"."bldgs"
      END AS "bldgs",
      CASE
        WHEN a.curavl_act = a.curavt_act AND UPPER(bldgcl) LIKE 'V%'
        THEN CAST('0' AS DOUBLE)
        ELSE "a"."story"
      END AS "story",
      CASE
        WHEN a.curavl_act = a.curavt_act AND UPPER(bldgcl) LIKE 'V%'
        THEN CAST('0' AS DECIMAL(38, 2))
        ELSE "a"."bfft"
      END AS "bfft",
      CASE
        WHEN a.curavl_act = a.curavt_act AND UPPER(bldgcl) LIKE 'V%'
        THEN CAST('0' AS DECIMAL(38, 2))
        ELSE "a"."bdft"
      END AS "bdft"
    )
  FROM tax_lots_with_coordinates AS "a"
),
inferred_lot_areas AS NOT MATERIALIZED (
  -- pluto_build/sql/lotarea.sql statement 1
  -- Setting the lot area (land_area) field in pluto_rpad_geo
  -- if lot area = 0 or is NULL and if lot is not irregular and
  -- and if lot depth and lot front have valid values then
  -- multiply lot front x lot depth to get lot area
  SELECT
    "b".*
    REPLACE (
      CASE
        WHEN "a".__matched
        THEN CAST((
            a.lfft * a.ldft
          ) AS DOUBLE)
        ELSE "b"."land_area"
      END AS "land_area"
    )
  FROM vacant_lot_building_values AS "b"
  LEFT JOIN (
    SELECT
      "a".*,
      TRUE AS __matched
    FROM vacant_lot_building_values AS a
    WHERE
      (
        a.land_area IS NULL OR a.land_area = '0'
      )
      AND (
        a.irreg <> 'I'
      )
      AND (
        a.lfft > 0
      )
      AND (
        a.ldft > 0
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY a.boro || a.tb || a.tl) = 1
  ) AS "a"
    ON (
      a.boro || a.tb || a.tl = b.boro || b.tb || b.tl
    )
),
tax_lots_with_prime_bbl AS NOT MATERIALIZED (
  -- pluto_build/sql/primebbl.sql statement 1
  -- assign the prime BBL to each PTS collapsed record
  -- assign prime bbl for condo records
  -- billingbbl is coming from pluto_input_geocodes
  SELECT
    *,
    MOSES_TEXT(NULL) AS "primebbl"
  FROM inferred_lot_areas AS pluto_rpad_geo
),
condo_prime_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/primebbl.sql statement 3
  SELECT
    "pluto_rpad_geo".*
    REPLACE (
      CASE
        WHEN billingbbl IS NOT NULL AND billingbbl <> '0000000000'
        THEN MOSES_TEXT(billingbbl)
        ELSE "pluto_rpad_geo"."primebbl"
      END AS "primebbl"
    )
  FROM tax_lots_with_prime_bbl AS "pluto_rpad_geo"
),
formatted_apportionment_dates AS NOT MATERIALIZED (
  -- pluto_build/sql/apdate.sql statement 1
  /* assign prime bbl for noncondo lots */
  /* -- no longer need to do because ap_date now comes in MM/DD/YY format */
  /* -- converting datetime from year and day of year e.g. 93005 to 1993-01-05 then MM/DD/YYYY */
  /* UPDATE pluto_rpad_geo */
  /* SET ap_datef = to_char(to_date(lpad(ap_date, 5, '0'), 'YYDDD'), 'MM/DD/YYYY') */
  /* WHERE ap_date::numeric > 0; */
  /* format from MM/DD/YY to MM/DD/YYYY */
  SELECT
    "pluto_rpad_geo".*
    REPLACE (
      CASE
        WHEN primebbl IS NULL
        THEN MOSES_TEXT(boro || tb || tl)
        ELSE "pluto_rpad_geo"."primebbl"
      END AS "primebbl",
      CASE
        WHEN NOT ap_date IS NULL
        THEN MOSES_TEXT(STRFTIME(CAST(STRPTIME(ap_date, '%m/%d/%y') AS DATE), '%m/%d/%Y'))
        ELSE "pluto_rpad_geo"."ap_datef"
      END AS "ap_datef"
    )
  FROM condo_prime_bbls AS "pluto_rpad_geo"
)
SELECT * FROM formatted_apportionment_dates
