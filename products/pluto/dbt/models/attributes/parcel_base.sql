{{ config(materialized='table') }}
-- Business process: parcel_base
WITH
create_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/create.sql statement 2
  SELECT
    CAST(NULL AS BIGINT) AS "id",
    MOSES_TEXT(NULL) AS "borough",
    MOSES_TEXT(NULL) AS "block",
    MOSES_TEXT(NULL) AS "lot",
    MOSES_TEXT(NULL) AS "cd",
    MOSES_TEXT(NULL) AS "bct2020",
    MOSES_TEXT(NULL) AS "bctcb2020",
    MOSES_TEXT(NULL) AS "ct2010",
    MOSES_TEXT(NULL) AS "cb2010",
    MOSES_TEXT(NULL) AS "schooldist",
    MOSES_TEXT(NULL) AS "council",
    MOSES_TEXT(NULL) AS "zipcode",
    MOSES_TEXT(NULL) AS "firecomp",
    MOSES_TEXT(NULL) AS "policeprct",
    MOSES_TEXT(NULL) AS "healtharea",
    MOSES_TEXT(NULL) AS "sanitboro",
    MOSES_TEXT(NULL) AS "sanitsub",
    MOSES_TEXT(NULL) AS "address",
    MOSES_TEXT(NULL) AS "zonedist1",
    MOSES_TEXT(NULL) AS "zonedist2",
    MOSES_TEXT(NULL) AS "zonedist3",
    MOSES_TEXT(NULL) AS "zonedist4",
    MOSES_TEXT(NULL) AS "overlay1",
    MOSES_TEXT(NULL) AS "overlay2",
    MOSES_TEXT(NULL) AS "spdist1",
    MOSES_TEXT(NULL) AS "spdist2",
    MOSES_TEXT(NULL) AS "spdist3",
    MOSES_TEXT(NULL) AS "ltdheight",
    MOSES_TEXT(NULL) AS "splitzone",
    MOSES_TEXT(NULL) AS "bldgclass",
    MOSES_TEXT(NULL) AS "landuse",
    MOSES_TEXT(NULL) AS "easements",
    MOSES_TEXT(NULL) AS "ownertype",
    MOSES_TEXT(NULL) AS "ownername",
    MOSES_TEXT(NULL) AS "lotarea",
    MOSES_TEXT(NULL) AS "bldgarea",
    MOSES_TEXT(NULL) AS "comarea",
    MOSES_TEXT(NULL) AS "resarea",
    MOSES_TEXT(NULL) AS "officearea",
    MOSES_TEXT(NULL) AS "retailarea",
    MOSES_TEXT(NULL) AS "garagearea",
    MOSES_TEXT(NULL) AS "strgearea",
    MOSES_TEXT(NULL) AS "factryarea",
    MOSES_TEXT(NULL) AS "otherarea",
    MOSES_TEXT(NULL) AS "areasource",
    MOSES_TEXT(NULL) AS "numbldgs",
    MOSES_TEXT(NULL) AS "numfloors",
    MOSES_TEXT(NULL) AS "unitsres",
    MOSES_TEXT(NULL) AS "unitstotal",
    MOSES_TEXT(NULL) AS "lotfront",
    MOSES_TEXT(NULL) AS "lotdepth",
    MOSES_TEXT(NULL) AS "bldgfront",
    MOSES_TEXT(NULL) AS "bldgdepth",
    MOSES_TEXT(NULL) AS "ext",
    MOSES_TEXT(NULL) AS "proxcode",
    MOSES_TEXT(NULL) AS "irrlotcode",
    MOSES_TEXT(NULL) AS "lottype",
    MOSES_TEXT(NULL) AS "bsmtcode",
    MOSES_TEXT(NULL) AS "assessland",
    MOSES_TEXT(NULL) AS "assesstot",
    MOSES_TEXT(NULL) AS "exempttot",
    MOSES_TEXT(NULL) AS "yearbuilt",
    MOSES_TEXT(NULL) AS "yearalter1",
    MOSES_TEXT(NULL) AS "yearalter2",
    MOSES_TEXT(NULL) AS "histdist",
    MOSES_TEXT(NULL) AS "landmark",
    MOSES_TEXT(NULL) AS "builtfar",
    MOSES_TEXT(NULL) AS "residfar",
    MOSES_TEXT(NULL) AS "commfar",
    MOSES_TEXT(NULL) AS "facilfar",
    MOSES_TEXT(NULL) AS "borocode",
    MOSES_TEXT(NULL) AS "bbl",
    MOSES_TEXT(NULL) AS "condono",
    MOSES_TEXT(NULL) AS "tract2010",
    MOSES_TEXT(NULL) AS "xcoord",
    MOSES_TEXT(NULL) AS "ycoord",
    MOSES_TEXT(NULL) AS "latitude",
    MOSES_TEXT(NULL) AS "longitude",
    MOSES_TEXT(NULL) AS "zonemap",
    MOSES_TEXT(NULL) AS "zmcode",
    MOSES_TEXT(NULL) AS "sanborn",
    MOSES_TEXT(NULL) AS "taxmap",
    MOSES_TEXT(NULL) AS "edesignum",
    MOSES_TEXT(NULL) AS "appbbl",
    MOSES_TEXT(NULL) AS "appdate",
    MOSES_TEXT(NULL) AS "mappluto_f",
    MOSES_TEXT(NULL) AS "plutomapid",
    MOSES_TEXT('{{ var("pluto_version") }}') AS "version",
    MOSES_TEXT(NULL) AS "sanitdistrict",
    MOSES_TEXT(NULL) AS "healthcenterdistrict",
    MOSES_TEXT(NULL) AS "firm07_flag",
    MOSES_TEXT(NULL) AS "pfirm15_flag",
    MOSES_TEXT(NULL) AS "rpaddate",
    MOSES_TEXT(NULL) AS "dcasdate",
    MOSES_TEXT(NULL) AS "zoningdate",
    MOSES_TEXT(NULL) AS "landmkdate",
    MOSES_TEXT(NULL) AS "basempdate",
    MOSES_TEXT(NULL) AS "masdate",
    MOSES_TEXT(NULL) AS "polidate",
    MOSES_TEXT(NULL) AS "edesigdate",
    MOSES_TEXT(NULL) AS "mih_opt1",
    MOSES_TEXT(NULL) AS "mih_opt2",
    MOSES_TEXT(NULL) AS "mih_opt3",
    MOSES_TEXT(NULL) AS "mih_opt4",
    MOSES_TEXT(NULL) AS "trnstzone",
    MOSES_TEXT(NULL) AS "affresfar",
    MOSES_TEXT(NULL) AS "mnffar",
    CAST(NULL AS GEOMETRY) AS "centroid"
  WHERE
    FALSE
),
bbl_pluto AS MATERIALIZED (
  -- pluto_build/sql/bbl.sql statement 1
  -- adding in unqique BBL information
  SELECT
    *
  FROM create_pluto AS pluto
  UNION ALL
  SELECT
    CAST((
      SELECT
        COALESCE(MAX("id"), 0)
      FROM create_pluto AS pluto
    ) + ROW_NUMBER() OVER () AS BIGINT) AS "id",
    MOSES_TEXT(__new."borough") AS "borough",
    MOSES_TEXT(__new."block") AS "block",
    MOSES_TEXT(__new."lot") AS "lot",
    MOSES_TEXT(NULL) AS "cd",
    MOSES_TEXT(NULL) AS "bct2020",
    MOSES_TEXT(NULL) AS "bctcb2020",
    MOSES_TEXT(NULL) AS "ct2010",
    MOSES_TEXT(NULL) AS "cb2010",
    MOSES_TEXT(NULL) AS "schooldist",
    MOSES_TEXT(NULL) AS "council",
    MOSES_TEXT(NULL) AS "zipcode",
    MOSES_TEXT(NULL) AS "firecomp",
    MOSES_TEXT(NULL) AS "policeprct",
    MOSES_TEXT(NULL) AS "healtharea",
    MOSES_TEXT(NULL) AS "sanitboro",
    MOSES_TEXT(NULL) AS "sanitsub",
    MOSES_TEXT(NULL) AS "address",
    MOSES_TEXT(NULL) AS "zonedist1",
    MOSES_TEXT(NULL) AS "zonedist2",
    MOSES_TEXT(NULL) AS "zonedist3",
    MOSES_TEXT(NULL) AS "zonedist4",
    MOSES_TEXT(NULL) AS "overlay1",
    MOSES_TEXT(NULL) AS "overlay2",
    MOSES_TEXT(NULL) AS "spdist1",
    MOSES_TEXT(NULL) AS "spdist2",
    MOSES_TEXT(NULL) AS "spdist3",
    MOSES_TEXT(NULL) AS "ltdheight",
    MOSES_TEXT(NULL) AS "splitzone",
    MOSES_TEXT(NULL) AS "bldgclass",
    MOSES_TEXT(NULL) AS "landuse",
    MOSES_TEXT(NULL) AS "easements",
    MOSES_TEXT(NULL) AS "ownertype",
    MOSES_TEXT(NULL) AS "ownername",
    MOSES_TEXT(NULL) AS "lotarea",
    MOSES_TEXT(NULL) AS "bldgarea",
    MOSES_TEXT(NULL) AS "comarea",
    MOSES_TEXT(NULL) AS "resarea",
    MOSES_TEXT(NULL) AS "officearea",
    MOSES_TEXT(NULL) AS "retailarea",
    MOSES_TEXT(NULL) AS "garagearea",
    MOSES_TEXT(NULL) AS "strgearea",
    MOSES_TEXT(NULL) AS "factryarea",
    MOSES_TEXT(NULL) AS "otherarea",
    MOSES_TEXT(NULL) AS "areasource",
    MOSES_TEXT(NULL) AS "numbldgs",
    MOSES_TEXT(NULL) AS "numfloors",
    MOSES_TEXT(NULL) AS "unitsres",
    MOSES_TEXT(NULL) AS "unitstotal",
    MOSES_TEXT(NULL) AS "lotfront",
    MOSES_TEXT(NULL) AS "lotdepth",
    MOSES_TEXT(NULL) AS "bldgfront",
    MOSES_TEXT(NULL) AS "bldgdepth",
    MOSES_TEXT(NULL) AS "ext",
    MOSES_TEXT(NULL) AS "proxcode",
    MOSES_TEXT(NULL) AS "irrlotcode",
    MOSES_TEXT(NULL) AS "lottype",
    MOSES_TEXT(NULL) AS "bsmtcode",
    MOSES_TEXT(NULL) AS "assessland",
    MOSES_TEXT(NULL) AS "assesstot",
    MOSES_TEXT(NULL) AS "exempttot",
    MOSES_TEXT(NULL) AS "yearbuilt",
    MOSES_TEXT(NULL) AS "yearalter1",
    MOSES_TEXT(NULL) AS "yearalter2",
    MOSES_TEXT(NULL) AS "histdist",
    MOSES_TEXT(NULL) AS "landmark",
    MOSES_TEXT(NULL) AS "builtfar",
    MOSES_TEXT(NULL) AS "residfar",
    MOSES_TEXT(NULL) AS "commfar",
    MOSES_TEXT(NULL) AS "facilfar",
    MOSES_TEXT(__new."borocode") AS "borocode",
    MOSES_TEXT(__new."bbl") AS "bbl",
    MOSES_TEXT(NULL) AS "condono",
    MOSES_TEXT(NULL) AS "tract2010",
    MOSES_TEXT(NULL) AS "xcoord",
    MOSES_TEXT(NULL) AS "ycoord",
    MOSES_TEXT(NULL) AS "latitude",
    MOSES_TEXT(NULL) AS "longitude",
    MOSES_TEXT(NULL) AS "zonemap",
    MOSES_TEXT(NULL) AS "zmcode",
    MOSES_TEXT(NULL) AS "sanborn",
    MOSES_TEXT(NULL) AS "taxmap",
    MOSES_TEXT(NULL) AS "edesignum",
    MOSES_TEXT(NULL) AS "appbbl",
    MOSES_TEXT(NULL) AS "appdate",
    MOSES_TEXT(NULL) AS "mappluto_f",
    MOSES_TEXT(NULL) AS "plutomapid",
    MOSES_TEXT('{{ var("pluto_version") }}') AS "version",
    MOSES_TEXT(NULL) AS "sanitdistrict",
    MOSES_TEXT(NULL) AS "healthcenterdistrict",
    MOSES_TEXT(NULL) AS "firm07_flag",
    MOSES_TEXT(NULL) AS "pfirm15_flag",
    MOSES_TEXT(NULL) AS "rpaddate",
    MOSES_TEXT(NULL) AS "dcasdate",
    MOSES_TEXT(NULL) AS "zoningdate",
    MOSES_TEXT(NULL) AS "landmkdate",
    MOSES_TEXT(NULL) AS "basempdate",
    MOSES_TEXT(NULL) AS "masdate",
    MOSES_TEXT(NULL) AS "polidate",
    MOSES_TEXT(NULL) AS "edesigdate",
    MOSES_TEXT(NULL) AS "mih_opt1",
    MOSES_TEXT(NULL) AS "mih_opt2",
    MOSES_TEXT(NULL) AS "mih_opt3",
    MOSES_TEXT(NULL) AS "mih_opt4",
    MOSES_TEXT(NULL) AS "trnstzone",
    MOSES_TEXT(NULL) AS "affresfar",
    MOSES_TEXT(NULL) AS "mnffar",
    CAST(NULL AS GEOMETRY) AS "centroid"
  FROM (
    SELECT
      b.primebbl AS bbl,
      LEFT(b.primebbl, 1) AS borocode,
      CASE
        WHEN LEFT(b.primebbl, 1) = '1'
        THEN 'MN'
        WHEN LEFT(b.primebbl, 1) = '2'
        THEN 'BX'
        WHEN LEFT(b.primebbl, 1) = '3'
        THEN 'BK'
        WHEN LEFT(b.primebbl, 1) = '4'
        THEN 'QN'
        WHEN LEFT(b.primebbl, 1) = '5'
        THEN 'SI'
      END AS borough,
      LTRIM(SUBSTRING(b.primebbl, 2, 5), '0') AS block,
      LTRIM(RIGHT(b.primebbl, 4), '0') AS lot
    FROM (
      SELECT DISTINCT
        primebbl
      FROM {{ ref('tax_lot_attributes') }} AS pluto_rpad_geo
    ) AS b
  ) AS __new("bbl", "borocode", "borough", "block", "lot")
),
allocated_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/allocated.sql statement 1
  -- Adding on data from allocated input table
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgclass)
        ELSE "a"."bldgclass"
      END AS "bldgclass",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ownertype)
        ELSE "a"."ownertype"
      END AS "ownertype",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ownername)
        ELSE "a"."ownername"
      END AS "ownername",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.lotarea)
        ELSE "a"."lotarea"
      END AS "lotarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgarea)
        ELSE "a"."bldgarea"
      END AS "bldgarea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.numbldgs)
        ELSE "a"."numbldgs"
      END AS "numbldgs",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.numfloors)
        ELSE "a"."numfloors"
      END AS "numfloors",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.unitsres)
        ELSE "a"."unitsres"
      END AS "unitsres",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.unitstotal)
        ELSE "a"."unitstotal"
      END AS "unitstotal",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.lotfront)
        ELSE "a"."lotfront"
      END AS "lotfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.lotdepth)
        ELSE "a"."lotdepth"
      END AS "lotdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgfront)
        ELSE "a"."bldgfront"
      END AS "bldgfront",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgdepth)
        ELSE "a"."bldgdepth"
      END AS "bldgdepth",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ext)
        ELSE "a"."ext"
      END AS "ext",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.irrlotcode)
        ELSE "a"."irrlotcode"
      END AS "irrlotcode",
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
      END AS "exempttot",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.yearbuilt)
        ELSE "a"."yearbuilt"
      END AS "yearbuilt",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.yearalter1)
        ELSE "a"."yearalter1"
      END AS "yearalter1",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.yearalter2)
        ELSE "a"."yearalter2"
      END AS "yearalter2",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.condono)
        ELSE "a"."condono"
      END AS "condono",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.appbbl)
        ELSE "a"."appbbl"
      END AS "appbbl",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.appdate)
        ELSE "a"."appdate"
      END AS "appdate"
    )
  FROM bbl_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('allocated_lots') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
allocated_assign_ext AS NOT MATERIALIZED (
  -- pluto_build/sql/allocated.sql statement 2
  -- where ext is just spaces set to NULL
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN NOT REGEXP_MATCHES(a.ext, '[A-Z]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."ext"
      END AS "ext"
    )
  FROM allocated_pluto AS "a"
),
allocated_pluto_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/allocated.sql statement 3
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(MOSES_TEXT(count))
        ELSE "a"."numbldgs"
      END AS "numbldgs"
    )
  FROM allocated_assign_ext AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ({{ pluto_input('pluto_input_numbldgs') }}) AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY CAST(b.bbl AS BIGINT)) = 1
  ) AS "b"
    ON (
      CAST(a.bbl AS BIGINT) = CAST(b.bbl AS BIGINT)
    )
),
geocodes_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/geocodes.sql statement 1
  -- Adding on data from geocodes input table
  -- might need to get fire company type
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.cd)
        ELSE "a"."cd"
      END AS "cd",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(b.ct2020 AS DECIMAL(38, 12)) = 0
              THEN NULL
              ELSE a.borocode || b.ct2020
            END
          )
        )
        ELSE "a"."bct2020"
      END AS "bct2020",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(b.ct2020 AS DECIMAL(38, 12)) = 0
              THEN NULL
              ELSE a.borocode || b.ct2020 || b.cb2020
            END
          )
        )
        ELSE "a"."bctcb2020"
      END AS "bctcb2020",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ct2010)
        ELSE "a"."ct2010"
      END AS "ct2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.cb2010)
        ELSE "a"."cb2010"
      END AS "cb2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.schooldist)
        ELSE "a"."schooldist"
      END AS "schooldist",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.council, '0'))
        ELSE "a"."council"
      END AS "council",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.zipcode)
        ELSE "a"."zipcode"
      END AS "zipcode",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.firecomp)
        ELSE "a"."firecomp"
      END AS "firecomp",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.policeprct, '0'))
        ELSE "a"."policeprct"
      END AS "policeprct",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.healtharea, '0'))
        ELSE "a"."healtharea"
      END AS "healtharea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanitsub)
        ELSE "a"."sanitsub"
      END AS "sanitsub",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CONCAT(b.housenum_lo, ' ', b.street_name))
        ELSE "a"."address"
      END AS "address",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ct2010)
        ELSE "a"."tract2010"
      END AS "tract2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.xcoord, '0'))
        ELSE "a"."xcoord"
      END AS "xcoord",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.ycoord, '0'))
        ELSE "a"."ycoord"
      END AS "ycoord",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanbornmapidentifier)
        ELSE "a"."sanborn"
      END AS "sanborn",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.taxmap)
        ELSE "a"."taxmap"
      END AS "taxmap",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanitdistrict)
        ELSE "a"."sanitdistrict"
      END AS "sanitdistrict",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.healthcenterdistrict)
        ELSE "a"."healthcenterdistrict"
      END AS "healthcenterdistrict"
    )
  FROM allocated_pluto_2 AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.primebbl
    ) AND (
      (
        a.lot NOT LIKE '75%'
      ) = "b".__matched
    )
),
geocodes_pluto_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/geocodes.sql statement 2
  -- updating the building code if it was not updated in alloceted
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgcl)
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM geocodes_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.primebbl) = 1
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
        bldgclass IS NULL
      ) = "b".__matched
    )
),
geocodes_pluto_3 AS NOT MATERIALIZED (
  -- pluto_build/sql/geocodes.sql statement 3
  -- If lot is a condo lot, instead of joining on
  -- primebbl, we join on borough||block||lot
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.cd)
        ELSE "a"."cd"
      END AS "cd",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(b.ct2020 AS DECIMAL(38, 12)) = 0
              THEN NULL
              ELSE a.borocode || b.ct2020
            END
          )
        )
        ELSE "a"."bct2020"
      END AS "bct2020",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(
          (
            CASE
              WHEN CAST(b.ct2020 AS DECIMAL(38, 12)) = 0
              THEN NULL
              ELSE a.borocode || b.ct2020 || b.cb2020
            END
          )
        )
        ELSE "a"."bctcb2020"
      END AS "bctcb2020",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ct2010)
        ELSE "a"."ct2010"
      END AS "ct2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.cb2010)
        ELSE "a"."cb2010"
      END AS "cb2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.schooldist)
        ELSE "a"."schooldist"
      END AS "schooldist",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.zipcode)
        ELSE "a"."zipcode"
      END AS "zipcode",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.firecomp)
        ELSE "a"."firecomp"
      END AS "firecomp",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.policeprct, '0'))
        ELSE "a"."policeprct"
      END AS "policeprct",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.healtharea, '0'))
        ELSE "a"."healtharea"
      END AS "healtharea",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanitsub)
        ELSE "a"."sanitsub"
      END AS "sanitsub",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(CONCAT(b.housenum_lo, ' ', b.street_name))
        ELSE "a"."address"
      END AS "address",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.ct2010)
        ELSE "a"."tract2010"
      END AS "tract2010",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.xcoord, '0'))
        ELSE "a"."xcoord"
      END AS "xcoord",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LTRIM(b.ycoord, '0'))
        ELSE "a"."ycoord"
      END AS "ycoord",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanbornmapidentifier)
        ELSE "a"."sanborn"
      END AS "sanborn",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.taxmap)
        ELSE "a"."taxmap"
      END AS "taxmap",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.sanitdistrict)
        ELSE "a"."sanitdistrict"
      END AS "sanitdistrict",
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.healthcenterdistrict)
        ELSE "a"."healthcenterdistrict"
      END AS "healthcenterdistrict"
    )
  FROM geocodes_pluto_2 AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.borough || b.block || b.lot) = 1
  ) AS "b"
    ON (
      a.bbl = b.borough || b.block || b.lot
    )
    AND (
      (
        a.lot LIKE '75%'
      ) = "b".__matched
    )
),
geocodes_pluto_4 AS NOT MATERIALIZED (
  -- pluto_build/sql/geocodes.sql statement 4
  -- updating the building code if it was not updated in alloceted
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgcl)
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM geocodes_pluto_3 AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_attributes') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.borough || b.block || b.lot) = 1
  ) AS "b"
    ON (
      a.bbl = b.borough || b.block || b.lot
    )
    AND (
      (
        a.lot LIKE '75%'
      ) = "b".__matched
    )
    AND (
      (
        bldgclass IS NULL
      ) = "b".__matched
    )
),
landuse_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/landuse.sql statement 1
  -- Setting the landuse of the lot based on the building class
  -- uses the pluto_input_landuse_bldgclass lookup table
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.landuse)
        ELSE "a"."landuse"
      END AS "landuse"
    )
  FROM geocodes_pluto_4 AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ({{ pluto_input('pluto_input_landuse_bldgclass') }}) AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bldgclass) = 1
  ) AS "b"
    ON (
      a.bldgclass = b.bldgclass
    )
),
landuse_assign_areasource AS NOT MATERIALIZED (
  -- pluto_build/sql/landuse.sql statement 2
  -- set area source to 4 for vacant lots
  -- for vacant lots and number of buildings is 0 and building floor area is 0
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN (
          areasource IS NULL OR areasource = '0'
        )
        AND landuse = '11'
        AND CAST(numbldgs AS DECIMAL(38, 12)) = 0
        AND (
          CAST(bldgarea AS DECIMAL(38, 12)) = 0 OR bldgarea IS NULL
        )
        THEN MOSES_TEXT('4')
        ELSE "a"."areasource"
      END AS "areasource"
    )
  FROM landuse_pluto AS "a"
)
SELECT * FROM landuse_assign_areasource
