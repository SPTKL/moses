{{ config(materialized='table') }}
-- Business process: parcel_cama
WITH
create_cama_primebbl_input_cama AS NOT MATERIALIZED (
  -- pluto_build/sql/create_cama_primebbl.sql statement 2
  SELECT
    a.*,
    b.billingbbl
  FROM ({{ pluto_input('pluto_input_cama_dof') }}) AS a
  LEFT JOIN {{ ref('geocode_attributes') }} AS b
    ON LEFT(a.bbl, 10) = b.borough || LPAD(b.block, 5, '0') || LPAD(b.lot, 4, '0')
),
create_cama_primebbl_input_cama_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/create_cama_primebbl.sql statement 3
  -- test logic to mimic pts logic
  SELECT
    *,
    MOSES_TEXT(NULL) AS "primebbl"
  FROM create_cama_primebbl_input_cama AS pluto_input_cama
),
create_cama_primebbl_assign_primebbl AS NOT MATERIALIZED (
  -- pluto_build/sql/create_cama_primebbl.sql statement 4
  SELECT
    "pluto_input_cama".*
    REPLACE (
      CASE
        WHEN billingbbl IS NOT NULL AND billingbbl <> '0000000000'
        THEN MOSES_TEXT(billingbbl)
        ELSE "pluto_input_cama"."primebbl"
      END AS "primebbl"
    )
  FROM create_cama_primebbl_input_cama_2 AS "pluto_input_cama"
),
create_cama_primebbl_assign_primebbl_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/create_cama_primebbl.sql statement 5
  -- assign prime bbl for noncondo lots
  SELECT
    "pluto_input_cama".*
    REPLACE (
      CASE
        WHEN primebbl IS NULL
        THEN MOSES_TEXT(LEFT(bbl, 10))
        ELSE "pluto_input_cama"."primebbl"
      END AS "primebbl"
    )
  FROM create_cama_primebbl_assign_primebbl AS "pluto_input_cama"
),
cama_bsmttype_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bsmttype.sql statement 1
  /* assigning basement type */
  /* remove 0 (Unknown) bsmnt_type */
  /* get highest bsmnt_type and bsmntgradient value for each lot */
  /* match bsmnt_type and bsmntgradient values to pluto_input_bsmtcode lookup table to get and assign bsmtcode value */
  WITH dcpcamavals AS (
    SELECT DISTINCT
      x.bbl,
      x.bsmnt_type,
      x.bsmntgradient,
      b.bsmtcode
    FROM (
      SELECT
        primebbl AS bbl,
        bsmnt_type,
        bsmntgradient,
        ROW_NUMBER() OVER (
          PARTITION BY primebbl
          ORDER BY bsmnt_type DESC NULLS FIRST, bsmntgradient DESC NULLS FIRST
        ) AS row_number
      FROM create_cama_primebbl_assign_primebbl_2 AS pluto_input_cama
      WHERE
        bsmnt_type <> '0' AND bldgnum = '1'
    ) AS x
    LEFT JOIN ({{ pluto_input('pluto_input_bsmtcode') }}) AS b
      ON x.bsmnt_type = b.bsmnt_type AND x.bsmntgradient = b.bsmntgradient
    WHERE
      x.row_number = 1
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bsmtcode)
        ELSE "a"."bsmtcode"
      END AS "bsmtcode"
    )
  FROM {{ ref('parcel_base') }} AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM dcpcamavals AS b
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.bbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmnt_type") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntgradient") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmtcode") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
cama_bsmttype_assign_bsmtcode AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bsmttype.sql statement 2
  -- assign 5 (Unknown) to remaining records
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN bsmtcode IS NULL
        THEN MOSES_TEXT('5')
        ELSE "pluto"."bsmtcode"
      END AS "bsmtcode"
    )
  FROM cama_bsmttype_pluto AS "pluto"
),
cama_lottype_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_lottype.sql statement 1
  /* assigning lot type */
  /* remove 0s (Not Available) and 5 (none of the other types) */
  /* select lowest lot type value for record where bldgnum is 1 */
  WITH dcpcamavals AS (
    SELECT DISTINCT
      bbl,
      lottype
    FROM (
      SELECT
        primebbl AS bbl,
        lottype,
        ROW_NUMBER() OVER (PARTITION BY primebbl ORDER BY lottype) AS row_number
      FROM create_cama_primebbl_assign_primebbl_2 AS pluto_input_cama
      WHERE
        lottype <> '0' AND lottype <> '5' AND bldgnum = '1'
    ) AS x
    WHERE
      x.row_number = 1
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "dcpcamavals".__matched
        THEN MOSES_TEXT(dcpcamavals.lottype)
        ELSE "a"."lottype"
      END AS "lottype"
    )
  FROM cama_bsmttype_assign_bsmtcode AS "a"
  LEFT JOIN (
    SELECT
      "dcpcamavals".*,
      TRUE AS __matched
    FROM dcpcamavals
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY dcpcamavals.bbl
        ORDER BY MOSES_TEXT("dcpcamavals"."bbl") ASC NULLS LAST, MOSES_TEXT("dcpcamavals"."lottype") ASC NULLS LAST
      ) = 1
  ) AS "dcpcamavals"
    ON (
      a.bbl = dcpcamavals.bbl
    )
),
cama_lottype_pluto_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_lottype.sql statement 2
  -- update lots with lot type value of 5
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.lottype)
        ELSE "a"."lottype"
      END AS "lottype"
    )
  FROM cama_lottype_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM create_cama_primebbl_assign_primebbl_2 AS b
    WHERE
      (
        b.lottype = '5'
      )
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgnum") ASC NULLS LAST,
          MOSES_TEXT("b"."primebbl") ASC NULLS LAST,
          MOSES_TEXT("b"."billingbbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgclass") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmnt_type") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntarea") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntgradient") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialarea") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condomainconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condounitsconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."developmentname") ASC NULLS LAST,
          MOSES_TEXT("b"."factoryarea") ASC NULLS LAST,
          MOSES_TEXT("b"."finishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."firstfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."garagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossarea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossvolume") ASC NULLS LAST,
          MOSES_TEXT("b"."lottype") ASC NULLS LAST,
          MOSES_TEXT("b"."nonresidfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."officearea") ASC NULLS LAST,
          MOSES_TEXT("b"."otherarea") ASC NULLS LAST,
          MOSES_TEXT("b"."ownerarea") ASC NULLS LAST,
          MOSES_TEXT("b"."parcelcard") ASC NULLS LAST,
          MOSES_TEXT("b"."partresfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."primaryusecode") ASC NULLS LAST,
          MOSES_TEXT("b"."proxcode") ASC NULLS LAST,
          MOSES_TEXT("b"."residarea") ASC NULLS LAST,
          MOSES_TEXT("b"."residconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."retailarea") ASC NULLS LAST,
          MOSES_TEXT("b"."secondfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."storagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."streettype") ASC NULLS LAST,
          MOSES_TEXT("b"."unfinishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."upperfloorarea") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    ) AND (
      (
        a.lottype IS NULL
      ) = "b".__matched
    )
),
cama_lottype_assign_lottype AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_lottype.sql statement 3
  -- assign 0 (Mixed or Unknown) to remaining records
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN lottype IS NULL
        THEN MOSES_TEXT('0')
        ELSE "pluto"."lottype"
      END AS "lottype"
    )
  FROM cama_lottype_pluto_2 AS "pluto"
),
cama_proxcode_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_proxcode.sql statement 1
  /* assigning proxy code */
  /* recode DOF values to DCP values and remove 0s (Not Available) */
  /* select proxcode for lot from record where bldgnum is 1 */
  /* all bbl reocrds have at least one record with a bldgnum = '1' */
  WITH dcpcamavals AS (
    SELECT
      primebbl AS bbl,
      (
        CASE
          WHEN proxcode = '5'
          THEN '2'
          WHEN proxcode = '4'
          THEN '3'
          WHEN proxcode = '6'
          THEN '3'
          ELSE proxcode
        END
      ) AS proxcode
    FROM create_cama_primebbl_assign_primebbl_2 AS pluto_input_cama
    WHERE
      proxcode <> '0' AND proxcode <> 'N' AND bldgnum = '1'
  ), max_bbl_proxcodes AS (
    SELECT
      bbl,
      MAX(proxcode) AS proxcode
    FROM dcpcamavals
    GROUP BY
      bbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "m".__matched
        THEN MOSES_TEXT(m.proxcode)
        ELSE "a"."proxcode"
      END AS "proxcode"
    )
  FROM cama_lottype_assign_lottype AS "a"
  LEFT JOIN (
    SELECT
      "m".*,
      TRUE AS __matched
    FROM max_bbl_proxcodes AS m
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY m.bbl
        ORDER BY MOSES_TEXT("m"."bbl") ASC NULLS LAST, MOSES_TEXT("m"."proxcode") ASC NULLS LAST
      ) = 1
  ) AS "m"
    ON (
      a.bbl = m.bbl
    )
),
cama_proxcode_assign_proxcode AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_proxcode.sql statement 2
  -- assign 0 (Not Available) to remaining records
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN proxcode IS NULL
        THEN MOSES_TEXT('0')
        ELSE "pluto"."proxcode"
      END AS "proxcode"
    )
  FROM cama_proxcode_pluto AS "pluto"
),
cama_bldgarea_1_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_1.sql statement 7
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CAST(b.officearea AS DECIMAL(38, 12)) + CAST(b.retailarea AS DECIMAL(38, 12)) + CAST(b.garagearea AS DECIMAL(38, 12)) + CAST(b.storagearea AS DECIMAL(38, 12)) + CAST(b.factoryarea AS DECIMAL(38, 12)) + CAST(b.otherarea AS DECIMAL(38, 12))
          )
        )
        ELSE "a"."comarea"
      END AS "comarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.residarea)
        ELSE "a"."resarea"
      END AS "resarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.officearea)
        ELSE "a"."officearea"
      END AS "officearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.retailarea)
        ELSE "a"."retailarea"
      END AS "retailarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.garagearea)
        ELSE "a"."garagearea"
      END AS "garagearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.storagearea)
        ELSE "a"."strgearea"
      END AS "strgearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.factoryarea)
        ELSE "a"."factryarea"
      END AS "factryarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.otherarea)
        ELSE "a"."otherarea"
      END AS "otherarea"
    )
  FROM cama_proxcode_assign_proxcode AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    WHERE
      (
        CAST(b.residarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.officearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.retailarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.garagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.storagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.factoryarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.otherarea AS DECIMAL(38, 12)) > 0
      )
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST,
          MOSES_TEXT("b"."primebbl") ASC NULLS LAST,
          MOSES_TEXT("b"."billingbbl") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_block") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_boro") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_date") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_datef") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_ease") ASC NULLS LAST,
          MOSES_TEXT("b"."ap_lot") ASC NULLS LAST,
          MOSES_TEXT("b"."aptno") ASC NULLS LAST,
          MOSES_TEXT("b"."bdft") ASC NULLS LAST,
          MOSES_TEXT("b"."bfft") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgcl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgs") ASC NULLS LAST,
          MOSES_TEXT("b"."block") ASC NULLS LAST,
          MOSES_TEXT("b"."boepreferredstreetname") ASC NULLS LAST,
          MOSES_TEXT("b"."boro") ASC NULLS LAST,
          MOSES_TEXT("b"."borough") ASC NULLS LAST,
          MOSES_TEXT("b"."cb2010") ASC NULLS LAST,
          MOSES_TEXT("b"."cb2020") ASC NULLS LAST,
          MOSES_TEXT("b"."cd") ASC NULLS LAST,
          MOSES_TEXT("b"."condo_number") ASC NULLS LAST,
          MOSES_TEXT("b"."coop_apts") ASC NULLS LAST,
          MOSES_TEXT("b"."council") ASC NULLS LAST,
          MOSES_TEXT("b"."ct2010") ASC NULLS LAST,
          MOSES_TEXT("b"."ct2020") ASC NULLS LAST,
          MOSES_TEXT("b"."curavl_act") ASC NULLS LAST,
          MOSES_TEXT("b"."curavt_act") ASC NULLS LAST,
          MOSES_TEXT("b"."curext_act") ASC NULLS LAST,
          MOSES_TEXT("b"."ease") ASC NULLS LAST,
          MOSES_TEXT("b"."easement") ASC NULLS LAST,
          MOSES_TEXT("b"."ext") ASC NULLS LAST,
          MOSES_TEXT("b"."factoryarea") ASC NULLS LAST,
          MOSES_TEXT("b"."firecomp") ASC NULLS LAST,
          MOSES_TEXT("b"."garagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."geo_bbl") ASC NULLS LAST,
          HEX(ST_ASWKB("b"."geom")) ASC NULLS LAST,
          MOSES_TEXT("b"."grc") ASC NULLS LAST,
          MOSES_TEXT("b"."grc2") ASC NULLS LAST,
          MOSES_TEXT("b"."gross_sqft") ASC NULLS LAST,
          MOSES_TEXT("b"."healtharea") ASC NULLS LAST,
          MOSES_TEXT("b"."healthcenterdistrict") ASC NULLS LAST,
          MOSES_TEXT("b"."housenum_hi") ASC NULLS LAST,
          MOSES_TEXT("b"."housenum_lo") ASC NULLS LAST,
          MOSES_TEXT("b"."input_hnum") ASC NULLS LAST,
          MOSES_TEXT("b"."input_sname") ASC NULLS LAST,
          MOSES_TEXT("b"."irreg") ASC NULLS LAST,
          MOSES_TEXT("b"."land_area") ASC NULLS LAST,
          MOSES_TEXT("b"."latitude") ASC NULLS LAST,
          MOSES_TEXT("b"."ldft") ASC NULLS LAST,
          MOSES_TEXT("b"."lfft") ASC NULLS LAST,
          MOSES_TEXT("b"."longitude") ASC NULLS LAST,
          MOSES_TEXT("b"."lot") ASC NULLS LAST,
          MOSES_TEXT("b"."msg") ASC NULLS LAST,
          MOSES_TEXT("b"."msg2") ASC NULLS LAST,
          MOSES_TEXT("b"."numberofexistingstructuresonlot") ASC NULLS LAST,
          MOSES_TEXT("b"."officearea") ASC NULLS LAST,
          MOSES_TEXT("b"."otherarea") ASC NULLS LAST,
          MOSES_TEXT("b"."owner") ASC NULLS LAST,
          MOSES_TEXT("b"."policeprct") ASC NULLS LAST,
          MOSES_TEXT("b"."residarea") ASC NULLS LAST,
          MOSES_TEXT("b"."retailarea") ASC NULLS LAST,
          MOSES_TEXT("b"."row_number") ASC NULLS LAST,
          MOSES_TEXT("b"."sanbornmapidentifier") ASC NULLS LAST,
          MOSES_TEXT("b"."sanitdistrict") ASC NULLS LAST,
          MOSES_TEXT("b"."sanitsub") ASC NULLS LAST,
          MOSES_TEXT("b"."schooldist") ASC NULLS LAST,
          MOSES_TEXT("b"."storagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."story") ASC NULLS LAST,
          MOSES_TEXT("b"."street_name") ASC NULLS LAST,
          MOSES_TEXT("b"."taxmap") ASC NULLS LAST,
          MOSES_TEXT("b"."tb") ASC NULLS LAST,
          MOSES_TEXT("b"."tl") ASC NULLS LAST,
          MOSES_TEXT("b"."units") ASC NULLS LAST,
          MOSES_TEXT("b"."xcoord") ASC NULLS LAST,
          MOSES_TEXT("b"."ycoord") ASC NULLS LAST,
          MOSES_TEXT("b"."yralt1") ASC NULLS LAST,
          MOSES_TEXT("b"."yralt2") ASC NULLS LAST,
          MOSES_TEXT("b"."yrbuilt") ASC NULLS LAST,
          MOSES_TEXT("b"."zip") ASC NULLS LAST,
          MOSES_TEXT("b"."zipcode") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    ) AND (
      (
        a.lot NOT LIKE '75%'
      ) = "b".__matched
    )
),
cama_bldgarea_2_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_2.sql statement 1
  -- 2 fill in area for each use from CAMA if not filled in from PTS
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.commercialarea)
        ELSE "a"."comarea"
      END AS "comarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.residarea)
        ELSE "a"."resarea"
      END AS "resarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.officearea)
        ELSE "a"."officearea"
      END AS "officearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.retailarea)
        ELSE "a"."retailarea"
      END AS "retailarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.garagearea)
        ELSE "a"."garagearea"
      END AS "garagearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.storagearea)
        ELSE "a"."strgearea"
      END AS "strgearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.factoryarea)
        ELSE "a"."factryarea"
      END AS "factryarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.otherarea)
        ELSE "a"."otherarea"
      END AS "otherarea"
    )
  FROM cama_bldgarea_1_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM create_cama_primebbl_assign_primebbl_2 AS b
    WHERE
      (
        b.bldgnum = '1'
      )
      AND (
        CAST(b.commercialarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.residarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.officearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.retailarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.garagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.storagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.factoryarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.otherarea AS DECIMAL(38, 12)) > 0
      )
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgnum") ASC NULLS LAST,
          MOSES_TEXT("b"."primebbl") ASC NULLS LAST,
          MOSES_TEXT("b"."billingbbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgclass") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmnt_type") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntarea") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntgradient") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialarea") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condomainconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condounitsconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."developmentname") ASC NULLS LAST,
          MOSES_TEXT("b"."factoryarea") ASC NULLS LAST,
          MOSES_TEXT("b"."finishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."firstfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."garagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossarea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossvolume") ASC NULLS LAST,
          MOSES_TEXT("b"."lottype") ASC NULLS LAST,
          MOSES_TEXT("b"."nonresidfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."officearea") ASC NULLS LAST,
          MOSES_TEXT("b"."otherarea") ASC NULLS LAST,
          MOSES_TEXT("b"."ownerarea") ASC NULLS LAST,
          MOSES_TEXT("b"."parcelcard") ASC NULLS LAST,
          MOSES_TEXT("b"."partresfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."primaryusecode") ASC NULLS LAST,
          MOSES_TEXT("b"."proxcode") ASC NULLS LAST,
          MOSES_TEXT("b"."residarea") ASC NULLS LAST,
          MOSES_TEXT("b"."residconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."retailarea") ASC NULLS LAST,
          MOSES_TEXT("b"."secondfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."storagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."streettype") ASC NULLS LAST,
          MOSES_TEXT("b"."unfinishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."upperfloorarea") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
    AND (
      (
        a.lot NOT LIKE '75%'
      ) = "b".__matched
    )
    AND (
      (
        a.comarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.resarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.officearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.retailarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.garagearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.strgearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.factryarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.otherarea IS NULL
      ) = "b".__matched
    )
),
cama_bldgarea_3_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_3.sql statement 1
  /* 3 populate the fields that where values are aggregated */
  WITH primesums AS (
    SELECT
      billingbbl AS primebbl,
      SUM(CAST(commercialarea AS DOUBLE)) AS commercialarea,
      SUM(CAST(residarea AS DOUBLE)) AS residarea,
      SUM(CAST(officearea AS DOUBLE)) AS officearea,
      SUM(CAST(retailarea AS DOUBLE)) AS retailarea,
      SUM(CAST(garagearea AS DOUBLE)) AS garagearea,
      SUM(CAST(storagearea AS DOUBLE)) AS storagearea,
      SUM(CAST(factoryarea AS DOUBLE)) AS factoryarea,
      SUM(CAST(otherarea AS DOUBLE)) AS otherarea
    FROM create_cama_primebbl_assign_primebbl_2 AS pluto_input_cama
    WHERE
      bldgnum = '1' AND CAST(billingbbl AS DECIMAL(38, 12)) > 0
    GROUP BY
      billingbbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.commercialarea)
        ELSE "a"."comarea"
      END AS "comarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.residarea)
        ELSE "a"."resarea"
      END AS "resarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.officearea)
        ELSE "a"."officearea"
      END AS "officearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.retailarea)
        ELSE "a"."retailarea"
      END AS "retailarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.garagearea)
        ELSE "a"."garagearea"
      END AS "garagearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.storagearea)
        ELSE "a"."strgearea"
      END AS "strgearea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.factoryarea)
        ELSE "a"."factryarea"
      END AS "factryarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.otherarea)
        ELSE "a"."otherarea"
      END AS "otherarea"
    )
  FROM cama_bldgarea_2_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM primesums AS b
    WHERE
      (
        CAST(b.commercialarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.residarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.officearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.retailarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.garagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.storagearea AS DECIMAL(38, 12)) > 0
        OR CAST(b.factoryarea AS DECIMAL(38, 12)) > 0
        OR CAST(b.otherarea AS DECIMAL(38, 12)) > 0
      )
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."primebbl") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialarea") ASC NULLS LAST,
          MOSES_TEXT("b"."factoryarea") ASC NULLS LAST,
          MOSES_TEXT("b"."garagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."officearea") ASC NULLS LAST,
          MOSES_TEXT("b"."otherarea") ASC NULLS LAST,
          MOSES_TEXT("b"."residarea") ASC NULLS LAST,
          MOSES_TEXT("b"."retailarea") ASC NULLS LAST,
          MOSES_TEXT("b"."storagearea") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
    AND (
      (
        a.lot LIKE '75%'
      ) = "b".__matched
    )
    AND (
      (
        a.comarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.resarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.officearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.retailarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.garagearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.strgearea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.factryarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.otherarea IS NULL
      ) = "b".__matched
    )
),
cama_bldgarea_4_assign_areasource AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 1
  -- 4 assign an area source to records that aready have bldgarea from RPAD
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN CAST(bldgarea AS DECIMAL(38, 12)) <> 0 AND bldgarea IS NOT NULL
        THEN MOSES_TEXT('2')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_3_pluto AS "a"
),
cama_bldgarea_4_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 2
  -- 5 populate bldgarea from CAMA data
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.grossarea)
        ELSE "a"."bldgarea"
      END AS "bldgarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('7')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_4_assign_areasource AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM create_cama_primebbl_assign_primebbl_2 AS b
    WHERE
      (
        b.bldgnum = '1'
      )
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgnum") ASC NULLS LAST,
          MOSES_TEXT("b"."primebbl") ASC NULLS LAST,
          MOSES_TEXT("b"."billingbbl") ASC NULLS LAST,
          MOSES_TEXT("b"."bldgclass") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmnt_type") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntarea") ASC NULLS LAST,
          MOSES_TEXT("b"."bsmntgradient") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialarea") ASC NULLS LAST,
          MOSES_TEXT("b"."commercialconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condomainconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."condounitsconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."developmentname") ASC NULLS LAST,
          MOSES_TEXT("b"."factoryarea") ASC NULLS LAST,
          MOSES_TEXT("b"."finishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."firstfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."garagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossarea") ASC NULLS LAST,
          MOSES_TEXT("b"."grossvolume") ASC NULLS LAST,
          MOSES_TEXT("b"."lottype") ASC NULLS LAST,
          MOSES_TEXT("b"."nonresidfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."officearea") ASC NULLS LAST,
          MOSES_TEXT("b"."otherarea") ASC NULLS LAST,
          MOSES_TEXT("b"."ownerarea") ASC NULLS LAST,
          MOSES_TEXT("b"."parcelcard") ASC NULLS LAST,
          MOSES_TEXT("b"."partresfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."primaryusecode") ASC NULLS LAST,
          MOSES_TEXT("b"."proxcode") ASC NULLS LAST,
          MOSES_TEXT("b"."residarea") ASC NULLS LAST,
          MOSES_TEXT("b"."residconstrtype") ASC NULLS LAST,
          MOSES_TEXT("b"."retailarea") ASC NULLS LAST,
          MOSES_TEXT("b"."secondfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."storagearea") ASC NULLS LAST,
          MOSES_TEXT("b"."streettype") ASC NULLS LAST,
          MOSES_TEXT("b"."unfinishedfloorarea") ASC NULLS LAST,
          MOSES_TEXT("b"."upperfloorarea") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
    AND (
      (
        CAST(bldgarea AS DECIMAL(38, 12)) = 0 OR bldgarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.lot NOT LIKE '75%'
      ) = "b".__matched
    )
),
cama_bldgarea_4_pluto_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 3
  /* for condos */
  WITH primesums AS (
    SELECT
      billingbbl AS primebbl,
      SUM(CAST(grossarea AS DOUBLE)) AS grossarea
    FROM create_cama_primebbl_assign_primebbl_2 AS pluto_input_cama
    WHERE
      bldgnum = '1' AND CAST(billingbbl AS DECIMAL(38, 12)) > 0
    GROUP BY
      billingbbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.grossarea)
        ELSE "a"."bldgarea"
      END AS "bldgarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('7')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_4_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM primesums AS b
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.primebbl
        ORDER BY MOSES_TEXT("b"."primebbl") ASC NULLS LAST, MOSES_TEXT("b"."grossarea") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    )
    AND (
      (
        CAST(bldgarea AS DECIMAL(38, 12)) = 0 OR bldgarea IS NULL
      ) = "b".__matched
    )
    AND (
      (
        a.lot LIKE '75%'
      ) = "b".__matched
    )
),
cama_bldgarea_4_assign_areasource_bldgarea AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 4
  -- calcualte bldgarea by multiplying bldgfront x bldgdepth X num stories
  -- set area source to 5
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN (
          CAST(a.bldgarea AS DECIMAL(38, 12)) = 0 OR a.bldgarea IS NULL
        )
        AND CAST(a.bldgfront AS DECIMAL(38, 12)) <> 0
        AND CAST(a.numfloors AS DECIMAL(38, 12)) <> 0
        AND a.areasource IS NULL
        THEN MOSES_TEXT(
          CAST(CAST(CAST(a.bldgfront AS DECIMAL(38, 12)) * CAST(a.bldgdepth AS DECIMAL(38, 12)) AS DECIMAL(38, 12)) * CAST(numfloors AS DECIMAL(38, 12)) AS DECIMAL(38, 12))
        )
        ELSE "a"."bldgarea"
      END AS "bldgarea",
      CASE
        WHEN (
          CAST(a.bldgarea AS DECIMAL(38, 12)) = 0 OR a.bldgarea IS NULL
        )
        AND CAST(a.bldgfront AS DECIMAL(38, 12)) <> 0
        AND CAST(a.numfloors AS DECIMAL(38, 12)) <> 0
        AND a.areasource IS NULL
        THEN MOSES_TEXT('5')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_4_pluto_2 AS "a"
),
cama_bldgarea_4_assign_areasource_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 5
  -- set area source to 4 for vacant lots
  -- for vacant lots and number of buildings is 0 and building floor area is 0
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN areasource IS NULL
        AND landuse = '11'
        AND (
          CAST(numbldgs AS DECIMAL(38, 12)) = 0 OR numbldgs IS NULL
        )
        AND (
          CAST(bldgarea AS DECIMAL(38, 12)) = 0 OR bldgarea IS NULL
        )
        THEN MOSES_TEXT('4')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_4_assign_areasource_bldgarea AS "a"
),
cama_bldgarea_4_assign_areasource_3 AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_bldgarea_4.sql statement 6
  -- set area source to 0 where building area is not avialble because it's still 0 or null
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.areasource IS NULL
        AND (
          CAST(bldgarea AS DECIMAL(38, 12)) = 0 OR bldgarea IS NULL
        )
        THEN MOSES_TEXT('0')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM cama_bldgarea_4_assign_areasource_2 AS "a"
),
cama_easements_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_easements.sql statement 1
  -- set the number of easements for the lot
  /* set the number of easements associated with a lot */
  /* get a list of distinct easements for each lot */
  WITH distincteasements AS (
    SELECT DISTINCT
      primebbl AS bbl,
      ease
    FROM {{ ref('pts_property_records') }} AS dof_pts_propmaster
    WHERE
      ease IS NOT NULL AND ease <> ' '
  ), counteasements /* count the number of distinct easements for a lot */ AS (
    SELECT
      bbl,
      COUNT(*) AS numeasements
    FROM distincteasements AS b
    WHERE
      b.ease IS NOT NULL
    GROUP BY
      b.bbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.numeasements)
        ELSE "a"."easements"
      END AS "easements"
    )
  FROM cama_bldgarea_4_assign_areasource_3 AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM counteasements AS b
    QUALIFY
      ROW_NUMBER() OVER (
        PARTITION BY b.bbl
        ORDER BY MOSES_TEXT("b"."bbl") ASC NULLS LAST, MOSES_TEXT("b"."numeasements") ASC NULLS LAST
      ) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
cama_easements_assign_easements AS NOT MATERIALIZED (
  -- pluto_build/sql/cama_easements.sql statement 2
  -- for recrods whith no easement set number of easements to 0
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN easements IS NULL
        THEN MOSES_TEXT('0')
        ELSE "pluto"."easements"
      END AS "easements"
    )
  FROM cama_easements_pluto AS "pluto"
)
SELECT * FROM cama_easements_assign_easements
