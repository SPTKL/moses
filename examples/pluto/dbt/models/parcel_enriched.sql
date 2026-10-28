{{ config(materialized='table') }}
-- Business process: parcel_enriched
WITH
parcel_floor_area_ratios AS NOT MATERIALIZED (
  -- models/int_pluto__far.sql
  /* Calculate Floor Area Ratio (FAR) metrics for each tax lot */
  /* 1. Built FAR: ratio of building area to lot area */
  /* 2. Max FAR values by zoning district: residential, commercial, facility, affordable residential, manufacturing */
  WITH zoned_parcels_for_far AS (
    SELECT
      bbl,
      zonedist1,
      bldgarea,
      lotarea
    FROM {{ ref('parcel_zoning_districts') }} AS pluto
  ), far_calculated AS (
    SELECT
      bbl,
      zonedist1,
      CASE
        WHEN lotarea IS NOT NULL AND lotarea <> '0'
        THEN ROUND(
          CAST((
            CAST(bldgarea AS DECIMAL(38, 12)) / CAST(lotarea AS DECIMAL(38, 12))
          ) AS DECIMAL(38, 12)),
          2
        )
      END AS builtfar /* Calculate built FAR (building area / lot area) */ /* Only calculate when lotarea is non-zero and non-null */
    FROM zoned_parcels_for_far
  ), max_far_lookup AS (
    SELECT
      f.bbl,
      f.builtfar,
      COALESCE(CAST(z.residfar AS DOUBLE), CAST(0 AS DOUBLE)) AS residfar,
      COALESCE(CAST(z.commfar AS DOUBLE), CAST(0 AS DOUBLE)) AS commfar,
      COALESCE(CAST(z.facilfar AS DOUBLE), CAST(0 AS DOUBLE)) AS facilfar,
      COALESCE(CAST(z.affresfar AS DOUBLE), CAST(0 AS DOUBLE)) AS affresfar,
      COALESCE(CAST(z.mnffar AS DOUBLE), CAST(0 AS DOUBLE)) AS mnffar
    FROM far_calculated AS f
    LEFT JOIN ({{ pluto_input('dcp_zoning_maxfar') }}) AS z
      ON f.zonedist1 = z.zonedist
  )
  SELECT
    bbl,
    builtfar,
    residfar,
    commfar,
    facilfar,
    affresfar,
    mnffar
  FROM max_far_lookup
),
parcel_irregular_lot_flags AS NOT MATERIALIZED (
  -- models/int_pluto__irrlotcode.sql
  /* Transform irregular lot code from RPAD format (I/R) to Y/N format */
  /* I (Irregular) -> Y */
  /* R -> N */
  /* NOTE: Legacy SQL bug - converts NULL to 'N'. Preserving for exact match. */
  /* TODO: Consider fixing this in future to preserve NULL values */
  SELECT
    bbl,
    CASE WHEN irrlotcode = 'I' THEN 'Y' ELSE 'N' END AS irrlotcode
  FROM {{ ref('allocated_lots') }} AS pluto_allocated
),
formatted_condo_numbers AS NOT MATERIALIZED (
  -- models/int_pluto__condono.sql
  /* Format condo number: remove borough code prefix and leading zeros */
  /* Takes rightmost 5 characters and converts to numeric then back to text to strip leading zeros */
  SELECT
    bbl,
    MOSES_TEXT((
      CAST(RIGHT(condono, 5) AS DECIMAL(38, 12))
    )) AS condono
  FROM {{ ref('parcel_zoning_districts') }} AS pluto
),
parcel_landmark_designations AS NOT MATERIALIZED (
  -- models/int_pluto__lpc.sql
  /* Assign historic district and landmark designations from LPC data */
  /* Historic district: first alphabetical district per BBL */
  /* Landmark: type determination based on number of landmark types per BBL */
  WITH zoned_parcels_for_landmarks AS (
    SELECT
      bbl,
      borocode,
      block,
      lot
    FROM {{ ref('parcel_zoning_districts') }} AS pluto
  ), histdistricts AS (
    SELECT
      bbl,
      hist_dist
    FROM (
      SELECT
        bbl,
        hist_dist,
        ROW_NUMBER() OVER (PARTITION BY bbl ORDER BY hist_dist) AS row_number
      FROM ({{ pluto_input('stg__lpc_historic_districts') }}) AS stg__lpc_historic_districts
      WHERE
        hist_dist <> '0' AND hist_dist NOT LIKE 'Individual Landmark%'
    ) AS x
    WHERE
      x.row_number = 1
  ), landmarks AS (
    SELECT DISTINCT
      bbl,
      lm_type,
      ROW_NUMBER() OVER (PARTITION BY bbl ORDER BY lm_type) AS row_number
    FROM (
      SELECT DISTINCT
        bbl,
        lm_type
      FROM ({{ pluto_input('stg__lpc_landmarks') }}) AS stg__lpc_landmarks
      WHERE
        (
          lm_type = 'Interior Landmark' OR lm_type = 'Individual Landmark'
        )
        AND status = 'DESIGNATED'
        AND most_curre = '1'
        AND (
          last_actio = 'DESIGNATED'
          OR last_actio = 'DESIGNATED (AMENDMENT/MODIFICATION ACCEPTED)'
        )
    ) AS x
  ), landmark_type_counts AS (
    SELECT
      bbl,
      MAX(row_number) AS maxrow_number
    FROM landmarks
    GROUP BY
      bbl
  ), landmark_types AS (
    SELECT
      l.bbl,
      CASE
        WHEN m.maxrow_number = 1
        THEN UPPER(l.lm_type)
        WHEN m.maxrow_number = 2
        THEN UPPER('Individual and Interior Landmark')
        ELSE UPPER(l.lm_type)
      END AS landmark
    FROM landmarks AS l
    INNER JOIN landmark_type_counts AS m
      ON l.bbl = m.bbl
    WHERE
      l.row_number = 1
  )
  SELECT
    p.bbl,
    h.hist_dist AS histdist,
    lt.landmark
  FROM zoned_parcels_for_landmarks AS p
  LEFT JOIN histdistricts AS h
    ON p.borocode || LPAD(p.block, 5, '0') || LPAD(p.lot, 4, '0') = h.bbl
  LEFT JOIN landmark_types AS lt
    ON p.borocode || LPAD(p.block, 5, '0') || LPAD(p.lot, 4, '0') = lt.bbl
),
cleaned_numeric_attributes AS NOT MATERIALIZED (
  -- models/int_pluto__numericfields.sql
  /* Clean numeric fields by removing invalid values */
  /* lotdepth, numfloors: must be numeric (except decimal point) */
  /* numfloors: must be >= 1 */
  /* lotarea: remove commas */
  /* sanborn: must contain at least one digit */
  SELECT
    bbl,
    CASE
      WHEN REGEXP_MATCHES(lotdepth, '[^0-9]') AND lotdepth NOT LIKE '%.%'
      THEN NULL
      ELSE lotdepth
    END AS lotdepth,
    CASE
      WHEN REGEXP_MATCHES(numfloors, '[^0-9]') AND numfloors NOT LIKE '%.%'
      THEN NULL
      WHEN numfloors IS NOT NULL AND CAST(numfloors AS DECIMAL(38, 12)) < 1
      THEN NULL
      ELSE numfloors
    END AS numfloors,
    CASE WHEN lotarea LIKE '%,%' THEN REPLACE(lotarea, ',', '') ELSE lotarea END AS lotarea,
    CASE WHEN NOT REGEXP_MATCHES(sanborn, '[0-9]') THEN NULL ELSE sanborn END AS sanborn
  FROM {{ ref('parcel_zoning_districts') }} AS pluto
),
parcel_latitude_longitude AS NOT MATERIALIZED (
  -- models/int_pluto__latlong.sql
  /* Calculate latitude and longitude from x/y coordinates */
  /* Transform from State Plane (SRID 2263) to WGS84 (SRID 4326) */
  /* Also create centroid geometry point */
  /* Use CTE to compute transform once and reuse to avoid floating-point drift */
  WITH parcel_points_in_wgs84 AS (
    SELECT
      bbl,
      MOSES_TRANSFORM_CRS(ST_POINT(CAST(xcoord AS DOUBLE), CAST(ycoord AS DOUBLE)), 2263, 4326) AS point_4326
    FROM {{ ref('parcel_zoning_districts') }} AS pluto
    WHERE
      xcoord IS NOT NULL
  )
  SELECT
    bbl,
    ST_Y(point_4326) AS latitude,
    ST_X(point_4326) AS longitude,
    ST_SETSRID(ST_POINT(CAST(ST_X(point_4326) AS DOUBLE), CAST(ST_Y(point_4326) AS DOUBLE)), 4326) AS centroid
  FROM parcel_points_in_wgs84
),
joined_parcel_enrichments AS NOT MATERIALIZED (
  -- models/pluto_enriched.sql
  /* Assemble enriched PLUTO data from intermediate models */
  /* This model joins all simple enrichment models to the base pluto table */
  /* The results are used to batch UPDATE the pluto table */
  SELECT
    p.bbl,
    far.builtfar,
    far.residfar,
    far.commfar,
    far.facilfar,
    far.affresfar,
    far.mnffar,
    irr.irrlotcode,
    cn.condono,
    lpc.histdist,
    lpc.landmark,
    nf.lotdepth,
    nf.numfloors,
    nf.lotarea,
    nf.sanborn,
    ll.latitude,
    ll.longitude,
    ll.centroid,
    mih.mih_opt1,
    mih.mih_opt2,
    mih.mih_opt3,
    mih.mih_opt4,
    tz.trnstzone
  FROM {{ ref('parcel_zoning_districts') }} AS p
  LEFT JOIN parcel_floor_area_ratios AS far
    ON p.bbl = far.bbl
  LEFT JOIN parcel_irregular_lot_flags AS irr
    ON p.bbl = irr.bbl
  LEFT JOIN formatted_condo_numbers AS cn
    ON p.bbl = cn.bbl
  LEFT JOIN parcel_landmark_designations AS lpc
    ON p.bbl = lpc.bbl
  LEFT JOIN cleaned_numeric_attributes AS nf
    ON p.bbl = nf.bbl
  LEFT JOIN parcel_latitude_longitude AS ll
    ON p.bbl = ll.bbl
  LEFT JOIN {{ ref('parcel_mandatory_housing_options') }} AS mih
    ON p.bbl = mih.bbl
  LEFT JOIN {{ ref('parcel_transit_zones') }} AS tz
    ON p.bbl = tz.bbl
),
applied_parcel_enrichments AS NOT MATERIALIZED (
  -- pluto_build/sql/apply_dbt_enrichments.sql statement 1
  -- Apply DBT enrichments from pluto_enriched table to pluto
  -- This batch UPDATE applies all the business logic computed by dbt intermediate models
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.lotarea)
        ELSE "pluto"."lotarea"
      END AS "lotarea",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.numfloors)
        ELSE "pluto"."numfloors"
      END AS "numfloors",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.lotdepth)
        ELSE "pluto"."lotdepth"
      END AS "lotdepth",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.irrlotcode)
        ELSE "pluto"."irrlotcode"
      END AS "irrlotcode",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.histdist)
        ELSE "pluto"."histdist"
      END AS "histdist",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.landmark)
        ELSE "pluto"."landmark"
      END AS "landmark",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.builtfar)
        ELSE "pluto"."builtfar"
      END AS "builtfar",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.residfar)
        ELSE "pluto"."residfar"
      END AS "residfar",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.commfar)
        ELSE "pluto"."commfar"
      END AS "commfar",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.facilfar)
        ELSE "pluto"."facilfar"
      END AS "facilfar",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.condono)
        ELSE "pluto"."condono"
      END AS "condono",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.latitude)
        ELSE "pluto"."latitude"
      END AS "latitude",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.longitude)
        ELSE "pluto"."longitude"
      END AS "longitude",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.sanborn)
        ELSE "pluto"."sanborn"
      END AS "sanborn",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.mih_opt1)
        ELSE "pluto"."mih_opt1"
      END AS "mih_opt1",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.mih_opt2)
        ELSE "pluto"."mih_opt2"
      END AS "mih_opt2",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.mih_opt3)
        ELSE "pluto"."mih_opt3"
      END AS "mih_opt3",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.mih_opt4)
        ELSE "pluto"."mih_opt4"
      END AS "mih_opt4",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.trnstzone)
        ELSE "pluto"."trnstzone"
      END AS "trnstzone",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.affresfar)
        ELSE "pluto"."affresfar"
      END AS "affresfar",
      CASE
        WHEN "pe".__matched
        THEN MOSES_TEXT(pe.mnffar)
        ELSE "pluto"."mnffar"
      END AS "mnffar",
      CASE
        WHEN "pe".__matched
        THEN CAST(pe.centroid AS GEOMETRY)
        ELSE "pluto"."centroid"
      END AS "centroid"
    )
  FROM {{ ref('parcel_zoning_districts') }} AS "pluto"
  LEFT JOIN (
    SELECT
      "pe".*,
      TRUE AS __matched
    FROM joined_parcel_enrichments AS pe
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY pe.bbl) = 1
  ) AS "pe"
    ON (
      pluto.bbl = pe.bbl
    )
)
SELECT * FROM applied_parcel_enrichments
