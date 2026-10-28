{{ config(materialized='table') }}
-- Business process: allocated_lots
WITH
empty_allocation_schema AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 2
  SELECT
    MOSES_TEXT(NULL) AS "bbl",
    MOSES_TEXT(NULL) AS "bldgclass",
    MOSES_TEXT(NULL) AS "ownertype",
    MOSES_TEXT(NULL) AS "ownername",
    MOSES_TEXT(NULL) AS "lotarea",
    MOSES_TEXT(NULL) AS "bldgarea",
    MOSES_TEXT(NULL) AS "numbldgs",
    MOSES_TEXT(NULL) AS "numfloors",
    MOSES_TEXT(NULL) AS "unitsres",
    MOSES_TEXT(NULL) AS "unitstotal",
    MOSES_TEXT(NULL) AS "lotfront",
    MOSES_TEXT(NULL) AS "lotdepth",
    MOSES_TEXT(NULL) AS "bldgfront",
    MOSES_TEXT(NULL) AS "bldgdepth",
    MOSES_TEXT(NULL) AS "ext",
    MOSES_TEXT(NULL) AS "irrlotcode",
    MOSES_TEXT(NULL) AS "assessland",
    MOSES_TEXT(NULL) AS "assesstot",
    MOSES_TEXT(NULL) AS "exemptland",
    MOSES_TEXT(NULL) AS "exempttot",
    MOSES_TEXT(NULL) AS "yearbuilt",
    MOSES_TEXT(NULL) AS "yearalter1",
    MOSES_TEXT(NULL) AS "yearalter2",
    MOSES_TEXT(NULL) AS "condono",
    MOSES_TEXT(NULL) AS "appbbl",
    MOSES_TEXT(NULL) AS "appdate",
    MOSES_TEXT(NULL) AS "address"
  WHERE
    FALSE
),
allocation_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 3
  SELECT
    *
  FROM empty_allocation_schema AS pluto_allocated
  UNION ALL
  SELECT
    MOSES_TEXT(__new."bbl") AS "bbl",
    MOSES_TEXT(NULL) AS "bldgclass",
    MOSES_TEXT(NULL) AS "ownertype",
    MOSES_TEXT(NULL) AS "ownername",
    MOSES_TEXT(NULL) AS "lotarea",
    MOSES_TEXT(NULL) AS "bldgarea",
    MOSES_TEXT(NULL) AS "numbldgs",
    MOSES_TEXT(NULL) AS "numfloors",
    MOSES_TEXT(NULL) AS "unitsres",
    MOSES_TEXT(NULL) AS "unitstotal",
    MOSES_TEXT(NULL) AS "lotfront",
    MOSES_TEXT(NULL) AS "lotdepth",
    MOSES_TEXT(NULL) AS "bldgfront",
    MOSES_TEXT(NULL) AS "bldgdepth",
    MOSES_TEXT(NULL) AS "ext",
    MOSES_TEXT(NULL) AS "irrlotcode",
    MOSES_TEXT(NULL) AS "assessland",
    MOSES_TEXT(NULL) AS "assesstot",
    MOSES_TEXT(NULL) AS "exemptland",
    MOSES_TEXT(NULL) AS "exempttot",
    MOSES_TEXT(NULL) AS "yearbuilt",
    MOSES_TEXT(NULL) AS "yearalter1",
    MOSES_TEXT(NULL) AS "yearalter2",
    MOSES_TEXT(NULL) AS "condono",
    MOSES_TEXT(NULL) AS "appbbl",
    MOSES_TEXT(NULL) AS "appdate",
    MOSES_TEXT(NULL) AS "address"
  FROM (
    SELECT
      b.primebbl
    FROM (
      SELECT DISTINCT
        primebbl
      FROM {{ ref('tax_lot_attributes') }} AS pluto_rpad_geo
    ) AS b
  ) AS __new("bbl")
),
noncondo_allocation_attributes AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 4
  -- fill in one-to-one attributes
  -- for noncondo records
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bldgcl)
        ELSE "a"."bldgclass"
      END AS "bldgclass",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(owner)
        ELSE "a"."ownername"
      END AS "ownername",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(land_area)
        ELSE "a"."lotarea"
      END AS "lotarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(gross_sqft)
        ELSE "a"."bldgarea"
      END AS "bldgarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(numberofexistingstructuresonlot AS INT) > 0
              THEN CAST(numberofexistingstructuresonlot AS INT)
              ELSE bldgs
            END
          )
        )
        ELSE "a"."numbldgs"
      END AS "numbldgs",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(story)
        ELSE "a"."numfloors"
      END AS "numfloors",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(lfft)
        ELSE "a"."lotfront"
      END AS "lotfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ldft)
        ELSE "a"."lotdepth"
      END AS "lotdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bfft)
        ELSE "a"."bldgfront"
      END AS "bldgfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bdft)
        ELSE "a"."bldgdepth"
      END AS "bldgdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ext)
        ELSE "a"."ext"
      END AS "ext",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(irreg)
        ELSE "a"."irrlotcode"
      END AS "irrlotcode",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yrbuilt)
        ELSE "a"."yearbuilt"
      END AS "yearbuilt",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yralt1)
        ELSE "a"."yearalter1"
      END AS "yearalter1",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yralt2)
        ELSE "a"."yearalter2"
      END AS "yearalter2",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(condo_number)
        ELSE "a"."condono"
      END AS "condono",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ap_boro || LPAD(ap_block, 5, '0') || LPAD(ap_lot, 4, '0'))
        ELSE "a"."appbbl"
      END AS "appbbl",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ap_datef)
        ELSE "a"."appdate"
      END AS "appdate",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CONCAT(housenum_lo, ' ', street_name))
        ELSE "a"."address"
      END AS "address"
    )
  FROM allocation_bbls AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      (
        b.tl NOT LIKE '75%'
      ) AND (
        b.condo_number IS NULL
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
),
condo_allocation_attributes AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 5
  -- for condos get values from records where tax lot starts with 75, which indicates that this is the condo
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bldgcl)
        ELSE "a"."bldgclass"
      END AS "bldgclass",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(owner)
        ELSE "a"."ownername"
      END AS "ownername",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(land_area)
        ELSE "a"."lotarea"
      END AS "lotarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(numberofexistingstructuresonlot AS INT) > 0
              THEN CAST(numberofexistingstructuresonlot AS INT)
              ELSE bldgs
            END
          )
        )
        ELSE "a"."numbldgs"
      END AS "numbldgs",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(story)
        ELSE "a"."numfloors"
      END AS "numfloors",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(lfft)
        ELSE "a"."lotfront"
      END AS "lotfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ldft)
        ELSE "a"."lotdepth"
      END AS "lotdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bfft)
        ELSE "a"."bldgfront"
      END AS "bldgfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bdft)
        ELSE "a"."bldgdepth"
      END AS "bldgdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ext)
        ELSE "a"."ext"
      END AS "ext",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(irreg)
        ELSE "a"."irrlotcode"
      END AS "irrlotcode",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yrbuilt)
        ELSE "a"."yearbuilt"
      END AS "yearbuilt",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yralt1)
        ELSE "a"."yearalter1"
      END AS "yearalter1",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(yralt2)
        ELSE "a"."yearalter2"
      END AS "yearalter2",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(condo_number)
        ELSE "a"."condono"
      END AS "condono",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ap_boro || LPAD(ap_block, 5, '0') || LPAD(ap_lot, 4, '0'))
        ELSE "a"."appbbl"
      END AS "appbbl",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(ap_datef)
        ELSE "a"."appdate"
      END AS "appdate",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CONCAT(housenum_lo, ' ', street_name))
        ELSE "a"."address"
      END AS "address"
    )
  FROM noncondo_allocation_attributes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      (
        b.tl LIKE '75%'
      )
      AND (
        b.condo_number IS NOT NULL
      )
      AND (
        b.condo_number <> '0'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
),
allocated_building_areas AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 6
  /* populate the fields that where values are aggregated */
  /* Building area */
  WITH condo_building_area_totals AS (
    SELECT
      primebbl,
      SUM(CAST(b.gross_sqft AS DECIMAL(38, 12))) AS bldgareasum
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      b.tl NOT LIKE '75%' AND b.condo_number IS NOT NULL AND b.condo_number <> '0'
    GROUP BY
      primebbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(bldgareasum)
        ELSE "a"."bldgarea"
      END AS "bldgarea"
    )
  FROM condo_allocation_attributes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM condo_building_area_totals AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
),
allocated_unit_counts AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 7
  /* unit fields */
  WITH condo_unit_totals AS (
    SELECT
      primebbl,
      SUM(CAST(coop_apts AS INT)) AS unitsres,
      SUM(CAST(units AS INT)) AS unitstotal
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      b.tl NOT LIKE '75%'
    GROUP BY
      primebbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.unitsres)
        ELSE "a"."unitsres"
      END AS "unitsres",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.unitstotal)
        ELSE "a"."unitstotal"
      END AS "unitstotal"
    )
  FROM allocated_building_areas AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM condo_unit_totals AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
),
allocated_assessments AS MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 8
  /* $ fields */
  WITH condo_assessment_totals AS (
    SELECT
      primebbl,
      SUM(CAST(curavl_act AS DOUBLE)) AS assessland,
      SUM(CAST(curavt_act AS DOUBLE)) AS assesstot,
      SUM(CAST(curext_act AS DOUBLE)) AS exempttot /* field no longer exists */ /* SUM(curexl_act::double precision) as exemptland, */
    FROM {{ ref('tax_lot_attributes') }} AS pluto_rpad_geo
    GROUP BY
      primebbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.assessland)
        ELSE "a"."assessland"
      END AS "assessland",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.assesstot)
        ELSE "a"."assesstot"
      END AS "assesstot",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.exempttot)
        ELSE "a"."exempttot"
      END AS "exempttot"
    )
  FROM allocated_unit_counts AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM condo_assessment_totals AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
),
allocated_approval_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 9
  /* appbbl - when missing from condo lot, assign from unit lot */
  WITH unit_appbbls AS (
    SELECT
      prg.primebbl,
      MIN(prg.ap_boro || LPAD(prg.ap_block, 5, '0') || LPAD(prg.ap_lot, 4, '0')) AS appbbl
    FROM allocated_assessments AS pa
    INNER JOIN {{ ref('tax_lot_attributes') }} AS prg
      ON pa.bbl = prg.primebbl AND prg.primebbl <> prg.bbl
    WHERE
      pa.appbbl IS NULL AND RIGHT(pa.bbl, 4) LIKE '75%'
    GROUP BY
      prg.primebbl
  )
  SELECT
    "pa".*
    REPLACE (
      CASE
        WHEN "unit_appbbls".__matched
        THEN MOSES_TEXT(unit_appbbls.appbbl)
        ELSE "pa"."appbbl"
      END AS "appbbl"
    )
  FROM allocated_assessments AS "pa"
  LEFT JOIN (
    SELECT
      "unit_appbbls".*,
      TRUE AS __matched
    FROM unit_appbbls
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY unit_appbbls.primebbl) = 1
  ) AS "unit_appbbls"
    ON (
      pa.bbl = unit_appbbls.primebbl
    )
),
supplemented_allocation_attributes AS NOT MATERIALIZED (
  -- pluto_build/sql/create_allocated.sql statement 10
  -- fill in missing attributes from supplementary table (temp solution)
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b."LandSize")
        ELSE "a"."lotarea"
      END AS "lotarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b."Story")
        ELSE "a"."numfloors"
      END AS "numfloors",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b."YearBuilt")
        ELSE "a"."yearbuilt"
      END AS "yearbuilt"
    )
  FROM allocated_approval_bbls AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ({{ pluto_input('pluto_input_condolot_descriptiveattributes') }}) AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b."PARID") = 1
  ) AS "b"
    ON (
      a.bbl = b."PARID"
    )
    AND (
      (
        CAST(a.lotarea AS DECIMAL(38, 12)) = 0
      ) = "b".__matched
    )
    AND (
      (
        CAST(a.numfloors AS DECIMAL(38, 12)) = 0
      ) = "b".__matched
    )
    AND (
      (
        CAST(a.yearbuilt AS DECIMAL(38, 12)) = 0
      ) = "b".__matched
    )
),
normalized_construction_years AS NOT MATERIALIZED (
  -- pluto_build/sql/yearbuiltalt.sql statement 3
  /* clean up year values by making them valid years */
  /* yearbuilt */
  /* UPDATE pluto_allocated */
  /* SET yearbuilt = (CASE */
  /* WHEN LEFT(yearbuilt,1) = '0' THEN '1'||RIGHT(yearbuilt,3) */
  /* ELSE yearbuilt */
  /* END) */
  /* WHERE yearbuilt::integer > 0; */
  /* UPDATE pluto_allocated */
  /* SET yearbuilt = '19'||yearbuilt */
  /* WHERE length(yearbuilt) = 2 */
  /* AND yearbuilt::integer > 0; */
  /* yearalter1 */
  /* UPDATE pluto_allocated */
  /* SET yearalter1 = (CASE */
  /* WHEN LEFT(yearalter1,1) = '0' THEN '1'||RIGHT(yearalter1,3) */
  /* ELSE '1'||yearalter1 */
  /* END) */
  /* WHERE yearalter1::integer > 0; */
  /* UPDATE pluto_allocated */
  /* SET yearalter1 = '19'||yearalter1 */
  /* WHERE length(yearalter1) = 2 */
  /* AND yearalter1::integer > 0; */
  /* yearalter2 */
  /* UPDATE pluto_allocated */
  /* SET yearalter2 = (CASE */
  /* WHEN LEFT(yearalter2,1) = '0' THEN '1'||RIGHT(yearalter2,3) */
  /* ELSE '1'||yearalter2 */
  /* END) */
  /* WHERE yearalter2::integer > 0; */
  /* UPDATE pluto_allocated */
  /* SET yearalter2 = '19'||yearalter2 */
  /* WHERE length(yearalter2) = 2 */
  /* AND yearalter2::integer > 0; */
  SELECT
    "pluto_allocated".*
    REPLACE (
      CASE
        WHEN yearbuilt IS NULL OR CAST(yearbuilt AS INT) = 0
        THEN MOSES_TEXT('0')
        ELSE "pluto_allocated"."yearbuilt"
      END AS "yearbuilt",
      CASE
        WHEN yearalter1 IS NULL OR CAST(yearalter1 AS INT) = 0
        THEN MOSES_TEXT('0')
        ELSE "pluto_allocated"."yearalter1"
      END AS "yearalter1",
      CASE
        WHEN yearalter2 IS NULL OR CAST(yearalter2 AS INT) = 0
        THEN MOSES_TEXT('0')
        ELSE "pluto_allocated"."yearalter2"
      END AS "yearalter2"
    )
  FROM supplemented_allocation_attributes AS "pluto_allocated"
)
SELECT * FROM normalized_construction_years
