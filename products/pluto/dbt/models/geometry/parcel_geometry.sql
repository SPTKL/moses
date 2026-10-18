{{ config(materialized='table') }}
-- Business process: parcel_geometry
WITH
plutogeoms_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/plutogeoms.sql statement 1
  -- add geometry information onto pluto
  -- add a geometry column
  SELECT
    *,
    CAST(NULL AS GEOMETRY) AS geom
  FROM {{ ref('property_attributes') }} AS pluto
),
plutogeoms_pluto_2 AS MATERIALIZED (
  -- pluto_build/sql/plutogeoms.sql statement 2
  -- join on geometry data
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN CAST(moses_makevalid(ST_MULTI(b.geom)) AS GEOMETRY)
        ELSE "a"."geom"
      END AS "geom"
    )
  FROM plutogeoms_pluto AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('tax_lot_geometry') }} AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
dtmgeoms_pluto AS MATERIALIZED (
  -- pluto_build/sql/dtmgeoms.sql statement 3
  SELECT
    *
  FROM plutogeoms_pluto_2 AS pluto
  UNION ALL
  SELECT
    CAST((
      SELECT
        COALESCE(MAX("id"), 0)
      FROM plutogeoms_pluto_2 AS pluto
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
    MOSES_TEXT(__new."plutomapid") AS "plutomapid",
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
    CAST(NULL AS GEOMETRY) AS "centroid",
    CAST(__new."geom" AS GEOMETRY) AS "geom"
  FROM (
    WITH notinpluto AS (
      SELECT
        a.*
      FROM {{ ref('tax_lot_geometry') }} AS a
      LEFT JOIN plutogeoms_pluto_2 AS b
        ON a.bbl = b.bbl
      WHERE
        b.bbl IS NULL
    )
    /* insert bbl information and geometry of lots not in RPAD but in DTM */
    SELECT
      b.bbl,
      LEFT(b.bbl, 1) AS borocode,
      CASE
        WHEN LEFT(b.bbl, 1) = '1'
        THEN 'MN'
        WHEN LEFT(b.bbl, 1) = '2'
        THEN 'BX'
        WHEN LEFT(b.bbl, 1) = '3'
        THEN 'BK'
        WHEN LEFT(b.bbl, 1) = '4'
        THEN 'QN'
        WHEN LEFT(b.bbl, 1) = '5'
        THEN 'SI'
      END AS borough,
      LTRIM(SUBSTRING(b.bbl, 2, 5), '0') AS block,
      LTRIM(RIGHT(b.bbl, 4), '0') AS lot,
      moses_makevalid(ST_MULTI(b.geom)) AS geom,
      '3' AS plutomapid
    FROM notinpluto AS b
  ) AS __new("bbl", "borocode", "borough", "block", "lot", "geom", "plutomapid")
),
dtmgeoms_assign_lot AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmgeoms.sql statement 5
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN block = ''
        THEN MOSES_TEXT('0')
        ELSE "pluto"."block"
      END AS "block",
      CASE
        WHEN lot = ''
        THEN MOSES_TEXT('0')
        ELSE "pluto"."lot"
      END AS "lot"
    )
  FROM dtmgeoms_pluto AS "pluto"
)
SELECT * FROM dtmgeoms_assign_lot
