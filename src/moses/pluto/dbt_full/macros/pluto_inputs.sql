{% macro pluto_input(alias) %}
{% if alias == 'dcp_cb2010_wi' %}
-- input_copy/dcp_cb2010_wi.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("cb2010", '') AS "cb2010",
    NULLIF("borocode", '') AS "borocode",
    NULLIF("boroname", '') AS "boroname",
    NULLIF("ct2010", '') AS "ct2010",
    NULLIF("bctcb2010", '') AS "bctcb2010"
  )
FROM {{ source('pluto_inputs', 'dcp_cb2010_wi') }} AS dcp_cb2010_wi
{% elif alias == 'dcp_cb2020_wi' %}
-- input_copy/dcp_cb2020_wi.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("cb2020", '') AS "cb2020",
    NULLIF("borocode", '') AS "borocode",
    NULLIF("boroname", '') AS "boroname",
    NULLIF("ct2020", '') AS "ct2020",
    NULLIF("bctcb2020", '') AS "bctcb2020",
    NULLIF("geoid", '') AS "geoid"
  )
FROM {{ source('pluto_inputs', 'dcp_cb2020_wi') }} AS dcp_cb2020_wi
{% elif alias == 'dcp_colp' %}
-- input_copy/dcp_colp.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("uid", '') AS "uid",
    NULLIF("borough", '') AS "borough",
    NULLIF("block", '') AS "block",
    NULLIF("lot", '') AS "lot",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("mapbbl", '') AS "mapbbl",
    NULLIF("cd", '') AS "cd",
    NULLIF("hnum", '') AS "hnum",
    NULLIF("sname", '') AS "sname",
    NULLIF("address", '') AS "address",
    NULLIF("parcelname", '') AS "parcelname",
    NULLIF("agency", '') AS "agency",
    NULLIF("usecode", '') AS "usecode",
    NULLIF("usetype", '') AS "usetype",
    NULLIF("ownership", '') AS "ownership",
    NULLIF("category", '') AS "category",
    NULLIF("expandcat", '') AS "expandcat",
    NULLIF("excatdesc", '') AS "excatdesc",
    NULLIF("leased", '') AS "leased",
    NULLIF("finalcom", '') AS "finalcom",
    NULLIF("agreement", '') AS "agreement",
    NULLIF("xcoord", '') AS "xcoord",
    NULLIF("ycoord", '') AS "ycoord",
    NULLIF("latitude", '') AS "latitude",
    NULLIF("longitude", '') AS "longitude",
    NULLIF("dcpedited", '') AS "dcpedited"
  )
FROM {{ source('pluto_inputs', 'dcp_colp') }} AS dcp_colp
{% elif alias == 'dcp_commercialoverlay' %}
-- input_copy/dcp_commercialoverlay.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("overlay", '') AS "overlay"
  )
FROM {{ source('pluto_inputs', 'dcp_commercialoverlay') }} AS dcp_commercialoverlay
{% elif alias == 'dcp_ct2010_wi' %}
-- input_copy/dcp_ct2010_wi.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("ctlabel", '') AS "ctlabel",
    NULLIF("borocode", '') AS "borocode",
    NULLIF("boroname", '') AS "boroname",
    NULLIF("ct2010", '') AS "ct2010",
    NULLIF("boroct2010", '') AS "boroct2010",
    NULLIF("cdeligibil", '') AS "cdeligibil",
    NULLIF("ntacode", '') AS "ntacode",
    NULLIF("ntaname", '') AS "ntaname",
    NULLIF("puma", '') AS "puma"
  )
FROM {{ source('pluto_inputs', 'dcp_ct2010_wi') }} AS dcp_ct2010_wi
{% elif alias == 'dcp_ct2020_wi' %}
-- input_copy/dcp_ct2020_wi.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("ctlabel", '') AS "ctlabel",
    NULLIF("borocode", '') AS "borocode",
    NULLIF("boroname", '') AS "boroname",
    NULLIF("ct2020", '') AS "ct2020",
    NULLIF("boroct2020", '') AS "boroct2020",
    NULLIF("cdeligibil", '') AS "cdeligibil",
    NULLIF("ntaname", '') AS "ntaname",
    NULLIF("nta2020", '') AS "nta2020",
    NULLIF("cdta2020", '') AS "cdta2020",
    NULLIF("cdtaname", '') AS "cdtaname",
    NULLIF("geoid", '') AS "geoid",
    NULLIF("puma", '') AS "puma"
  )
FROM {{ source('pluto_inputs', 'dcp_ct2020_wi') }} AS dcp_ct2020_wi
{% elif alias == 'dcp_edesignation' %}
-- input_copy/dcp_edesignation.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("enumber", '') AS "enumber",
    NULLIF("ceqr_num", '') AS "ceqr_num",
    NULLIF("ulurp_num", '') AS "ulurp_num",
    NULLIF("zoning_map", '') AS "zoning_map",
    NULLIF("descriptio", '') AS "descriptio"
  )
FROM {{ source('pluto_inputs', 'dcp_edesignation') }} AS dcp_edesignation
{% elif alias == 'dcp_firecompanies' %}
-- input_copy/dcp_firecompanies.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("firecotype", '') AS "firecotype"
  )
FROM {{ source('pluto_inputs', 'dcp_firecompanies') }} AS dcp_firecompanies
{% elif alias == 'dcp_gis_mandatory_inclusionary_housing' %}
-- input_copy/dcp_gis_mandatory_inclusionary_housing.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("boro", '') AS "boro",
    NULLIF("status", '') AS "status",
    NULLIF("project_name", '') AS "project_name",
    NULLIF("zr_ulurp_no", '') AS "zr_ulurp_no",
    NULLIF("zr_map", '') AS "zr_map",
    NULLIF("cd", '') AS "cd",
    NULLIF("mih_option", '') AS "mih_option",
    NULLIF("zoning_map", '') AS "zoning_map",
    NULLIF("project_id", '') AS "project_id"
  )
FROM {{ source('pluto_inputs', 'dcp_gis_mandatory_inclusionary_housing') }} AS dcp_gis_mandatory_inclusionary_housing
{% elif alias == 'dcp_healthareas' %}
-- input_copy/dcp_healthareas.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("boroname", '') AS "boroname"
  )
FROM {{ source('pluto_inputs', 'dcp_healthareas') }} AS dcp_healthareas
{% elif alias == 'dcp_healthcenters' %}
-- input_copy/dcp_healthcenters.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("boroname", '') AS "boroname"
  )
FROM {{ source('pluto_inputs', 'dcp_healthcenters') }} AS dcp_healthcenters
{% elif alias == 'dcp_limitedheight' %}
-- input_copy/dcp_limitedheight.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("lhname", '') AS "lhname",
    NULLIF("lhlbl", '') AS "lhlbl"
  )
FROM {{ source('pluto_inputs', 'dcp_limitedheight') }} AS dcp_limitedheight
{% elif alias == 'dcp_specialpurpose' %}
-- input_copy/dcp_specialpurpose.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("sdname", '') AS "sdname",
    NULLIF("sdlbl", '') AS "sdlbl"
  )
FROM {{ source('pluto_inputs', 'dcp_specialpurpose') }} AS dcp_specialpurpose
{% elif alias == 'dcp_transit_zone_ranks' %}
-- input_copy/dcp_transit_zone_ranks.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("tz_name")) IN ('', 'null')
      THEN NULL
      ELSE "tz_name"
    END AS "tz_name",
    CAST("tz_rank" AS DECIMAL(38, 12)) AS "tz_rank"
  )
FROM {{ source('pluto_inputs', 'dcp_transit_zone_ranks') }} AS dcp_transit_zone_ranks
{% elif alias == 'dcp_transit_zones' %}
-- input_copy/dcp_transit_zones.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("transit_zone", '') AS "transit_zone",
    NULLIF("shape_leng", '') AS "shape_leng",
    NULLIF("shape_area", '') AS "shape_area"
  )
FROM {{ source('pluto_inputs', 'dcp_transit_zones') }} AS dcp_transit_zones
{% elif alias == 'dcp_zoning_maxfar' %}
-- input_copy/dcp_zoning_maxfar.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("zonedist")) IN ('', 'null')
      THEN NULL
      ELSE "zonedist"
    END AS "zonedist",
    CASE
      WHEN LOWER(TRIM("contextual")) IN ('', 'null')
      THEN NULL
      ELSE "contextual"
    END AS "contextual",
    CASE
      WHEN LOWER(TRIM("zoningdistricttype")) IN ('', 'null')
      THEN NULL
      ELSE "zoningdistricttype"
    END AS "zoningdistricttype",
    CASE
      WHEN LOWER(TRIM("resdisteq")) IN ('', 'null')
      THEN NULL
      ELSE "resdisteq"
    END AS "resdisteq",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("residfar")) IN ('', 'null')
            THEN NULL
            ELSE "residfar"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "residfar",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("affresfar")) IN ('', 'null')
            THEN NULL
            ELSE "affresfar"
          END
        ),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "affresfar",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("facilfar")) IN ('', 'null')
            THEN NULL
            ELSE "facilfar"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "facilfar",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("commfar")) IN ('', 'null')
            THEN NULL
            ELSE "commfar"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "commfar",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("mnffar")) IN ('', 'null')
            THEN NULL
            ELSE "mnffar"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "mnffar",
    CASE
      WHEN LOWER(TRIM("verified")) IN ('', 'null')
      THEN NULL
      ELSE "verified"
    END AS "verified"
  )
FROM {{ source('pluto_inputs', 'dcp_zoning_maxfar') }} AS dcp_zoning_maxfar
{% elif alias == 'dcp_zoningdistricts' %}
-- input_copy/dcp_zoningdistricts.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("zonedist", '') AS "zonedist"
  )
FROM {{ source('pluto_inputs', 'dcp_zoningdistricts') }} AS dcp_zoningdistricts
{% elif alias == 'dof_condo' %}
-- input_copy/dof_condo.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("condo_base_boro", '') AS "condo_base_boro",
    NULLIF("condo_base_block", '') AS "condo_base_block",
    NULLIF("condo_base_lot", '') AS "condo_base_lot",
    NULLIF("condo_base_bbl", '') AS "condo_base_bbl",
    NULLIF("condo_base_bbl_key", '') AS "condo_base_bbl_key",
    NULLIF("condo_key", '') AS "condo_key",
    NULLIF("condo_number", '') AS "condo_number",
    NULLIF("condo_name", '') AS "condo_name",
    NULLIF("condo_billing_bbl", '') AS "condo_billing_bbl",
    NULLIF("cinc_parent_flag", '') AS "cinc_parent_flag",
    NULLIF("cinc_condo_parent", '') AS "cinc_condo_parent",
    NULLIF("cinc_unit_parent", '') AS "cinc_unit_parent",
    NULLIF("cinc_gen", '') AS "cinc_gen",
    NULLIF("created_user", '') AS "created_user",
    NULLIF("last_edited_user", '') AS "last_edited_user"
  )
FROM {{ source('pluto_inputs', 'dof_condo') }} AS dof_condo
{% elif alias == 'dof_dtm' %}
-- input_copy/dof_dtm.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("boro", '') AS "boro",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("condo_flag", '') AS "condo_flag",
    NULLIF("reuc_flag", '') AS "reuc_flag",
    NULLIF("air_lot_fl", '') AS "air_lot_fl",
    NULLIF("sub_lot_fl", '') AS "sub_lot_fl",
    NULLIF("easement_f", '') AS "easement_f",
    NULLIF("lot_note", '') AS "lot_note",
    NULLIF("effective_", '') AS "effective_",
    NULLIF("bill_bbl_f", '') AS "bill_bbl_f",
    NULLIF("nycmap_bld", '') AS "nycmap_bld",
    NULLIF("conversion", '') AS "conversion",
    NULLIF("value_refl", '') AS "value_refl",
    NULLIF("created_us", '') AS "created_us",
    NULLIF("last_edite", '') AS "last_edite"
  )
FROM {{ source('pluto_inputs', 'dof_dtm') }} AS dof_dtm
{% elif alias == 'dof_shoreline' %}
-- input_copy/dof_shoreline.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("created_by", '') AS "created_by",
    NULLIF("last_modif", '') AS "last_modif"
  )
FROM {{ source('pluto_inputs', 'dof_shoreline') }} AS dof_shoreline
{% elif alias == 'dpr_greenthumb' %}
-- input_copy/dpr_greenthumb.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("nta", '') AS "nta",
    NULLIF("zipcode", '') AS "zipcode",
    NULLIF("parksid", '') AS "parksid",
    NULLIF("coundist", '') AS "coundist",
    NULLIF("openhrsf", '') AS "openhrsf",
    NULLIF("openhrsw", '') AS "openhrsw",
    NULLIF("openhrstu", '') AS "openhrstu",
    NULLIF("openhrsm", '') AS "openhrsm",
    NULLIF("censustract", '') AS "censustract",
    NULLIF("congressionaldist", '') AS "congressionaldist",
    NULLIF("openhrsth", '') AS "openhrsth",
    NULLIF("statesenatedist", '') AS "statesenatedist",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("crossstreets", '') AS "crossstreets",
    NULLIF("communityboard", '') AS "communityboard",
    NULLIF("openhrssa", '') AS "openhrssa",
    NULLIF("gardenname", '') AS "gardenname",
    NULLIF("status", '') AS "status",
    NULLIF("address", '') AS "address",
    NULLIF("lon", '') AS "lon",
    NULLIF("policeprecinct", '') AS "policeprecinct",
    NULLIF("juris", '') AS "juris",
    NULLIF("openhrssu", '') AS "openhrssu",
    NULLIF("lat", '') AS "lat",
    NULLIF("borough", '') AS "borough",
    NULLIF("assemblydist", '') AS "assemblydist"
  )
FROM {{ source('pluto_inputs', 'dpr_greenthumb') }} AS dpr_greenthumb
{% elif alias == 'lpc_historic_districts' %}
-- input_copy/lpc_historic_districts.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("build_type", '') AS "build_type",
    NULLIF("style_sec", '') AS "style_sec",
    NULLIF("shape_area", '') AS "shape_area",
    NULLIF("build_nme", '') AS "build_nme",
    NULLIF("mat_sec", '') AS "mat_sec",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("alt_arch_1", '') AS "alt_arch_1",
    NULLIF("date_high", '') AS "date_high",
    NULLIF("use_orig", '') AS "use_orig",
    NULLIF("des_addres", '') AS "des_addres",
    NULLIF("alt_date_1", '') AS "alt_date_1",
    NULLIF("use_other", '') AS "use_other",
    NULLIF("shape_leng", '') AS "shape_leng",
    NULLIF("mat_prim", '') AS "mat_prim",
    NULLIF("alt_arch_2", '') AS "alt_arch_2",
    NULLIF("mat_four", '') AS "mat_four",
    NULLIF("block", '') AS "block",
    NULLIF("mat_third", '') AS "mat_third",
    NULLIF("own_devel", '') AS "own_devel",
    NULLIF("alt_date_2", '') AS "alt_date_2",
    NULLIF("style_prim", '') AS "style_prim",
    NULLIF("hist_dist", '') AS "hist_dist",
    NULLIF("lot", '') AS "lot",
    NULLIF("bin", '') AS "bin",
    NULLIF("notes", '') AS "notes",
    NULLIF("build_oth", '') AS "build_oth",
    NULLIF("circa", '') AS "circa",
    NULLIF("altered", '') AS "altered",
    NULLIF("style_oth", '') AS "style_oth",
    NULLIF("lm_new", '') AS "lm_new",
    NULLIF("mat_other", '') AS "mat_other",
    NULLIF("lm_orig", '') AS "lm_orig",
    NULLIF("date_low", '') AS "date_low",
    NULLIF("borough", '') AS "borough",
    NULLIF("date_combo", '') AS "date_combo",
    NULLIF("arch_build", '') AS "arch_build"
  )
FROM {{ source('pluto_inputs', 'lpc_historic_districts') }} AS lpc_historic_districts
{% elif alias == 'lpc_landmarks' %}
-- input_copy/lpc_landmarks.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("pluto_addr", '') AS "pluto_addr",
    NULLIF("bct2020", '') AS "bct2020",
    NULLIF("last_actio", '') AS "last_actio",
    NULLIF("latitude", '') AS "latitude",
    NULLIF("cd", '') AS "cd",
    NULLIF("boundaries", '') AS "boundaries",
    NULLIF("vacant_lot", '') AS "vacant_lot",
    NULLIF("public_hea", '') AS "public_hea",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("council", '') AS "council",
    NULLIF("desig_addr", '') AS "desig_addr",
    NULLIF("count_bldg", '') AS "count_bldg",
    NULLIF("longitude", '') AS "longitude",
    NULLIF("bin_number", '') AS "bin_number",
    NULLIF("block", '') AS "block",
    NULLIF("status", '') AS "status",
    NULLIF("lm_type", '') AS "lm_type",
    NULLIF("hist_distr", '') AS "hist_distr",
    NULLIF("other_hear", '') AS "other_hear",
    NULLIF("lot", '') AS "lot",
    NULLIF("lp_number", '') AS "lp_number",
    NULLIF("nta2020", '') AS "nta2020",
    NULLIF("non_bldg", '') AS "non_bldg",
    NULLIF("most_curre", '') AS "most_curre",
    NULLIF("boroughid", '') AS "boroughid",
    NULLIF("lm_name", '') AS "lm_name",
    NULLIF("secnd_bldg", '') AS "secnd_bldg"
  )
FROM {{ source('pluto_inputs', 'lpc_landmarks') }} AS lpc_landmarks
{% elif alias == 'pluto_input_bsmtcode' %}
-- input_copy/pluto_input_bsmtcode.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("bsmnt_type")) IN ('', 'null')
      THEN NULL
      ELSE "bsmnt_type"
    END AS "bsmnt_type",
    CASE
      WHEN LOWER(TRIM("bsmntgradient")) IN ('', 'null')
      THEN NULL
      ELSE "bsmntgradient"
    END AS "bsmntgradient",
    CASE
      WHEN LOWER(TRIM("bsmtcode")) IN ('', 'null')
      THEN NULL
      ELSE "bsmtcode"
    END AS "bsmtcode",
    CASE
      WHEN LOWER(TRIM("bsmnt_typevalue")) IN ('', 'null')
      THEN NULL
      ELSE "bsmnt_typevalue"
    END AS "bsmnt_typevalue",
    CASE
      WHEN LOWER(TRIM(" bsmntgradientvalue")) IN ('', 'null')
      THEN NULL
      ELSE " bsmntgradientvalue"
    END AS " bsmntgradientvalue",
    CASE
      WHEN LOWER(TRIM(" bsmtcodevalue")) IN ('', 'null')
      THEN NULL
      ELSE " bsmtcodevalue"
    END AS " bsmtcodevalue"
  )
FROM {{ source('pluto_inputs', 'pluto_input_bsmtcode') }} AS pluto_input_bsmtcode
{% elif alias == 'pluto_input_cama_dof' %}
-- input_copy/pluto_input_cama_dof.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("bbl", '') AS "bbl",
    NULLIF("parcelcard", '') AS "parcelcard",
    NULLIF("bldgnum", '') AS "bldgnum",
    NULLIF("bldgclass", '') AS "bldgclass",
    NULLIF("primaryusecode", '') AS "primaryusecode",
    NULLIF("developmentname", '') AS "developmentname",
    NULLIF("streettype", '') AS "streettype",
    NULLIF("lottype", '') AS "lottype",
    NULLIF("residarea", '') AS "residarea",
    NULLIF("officearea", '') AS "officearea",
    NULLIF("retailarea", '') AS "retailarea",
    NULLIF("garagearea", '') AS "garagearea",
    NULLIF("storagearea", '') AS "storagearea",
    NULLIF("factoryarea", '') AS "factoryarea",
    NULLIF("otherarea", '') AS "otherarea",
    NULLIF("grossarea", '') AS "grossarea",
    NULLIF("ownerarea", '') AS "ownerarea",
    NULLIF("grossvolume", '') AS "grossvolume",
    NULLIF("commercialarea", '') AS "commercialarea",
    NULLIF("proxcode", '') AS "proxcode",
    NULLIF("bsmnt_type", '') AS "bsmnt_type",
    NULLIF("bsmntgradient", '') AS "bsmntgradient",
    NULLIF("bsmntarea", '') AS "bsmntarea",
    NULLIF("firstfloorarea", '') AS "firstfloorarea",
    NULLIF("secondfloorarea", '') AS "secondfloorarea",
    NULLIF("upperfloorarea", '') AS "upperfloorarea",
    NULLIF("partresfloorarea", '') AS "partresfloorarea",
    NULLIF("unfinishedfloorarea", '') AS "unfinishedfloorarea",
    NULLIF("finishedfloorarea", '') AS "finishedfloorarea",
    NULLIF("nonresidfloorarea", '') AS "nonresidfloorarea",
    NULLIF("residconstrtype", '') AS "residconstrtype",
    NULLIF("commercialconstrtype", '') AS "commercialconstrtype",
    NULLIF("condomainconstrtype", '') AS "condomainconstrtype",
    NULLIF("condounitsconstrtype", '') AS "condounitsconstrtype"
  )
FROM {{ source('pluto_inputs', 'pluto_input_cama_dof') }} AS pluto_input_cama_dof
{% elif alias == 'pluto_input_condo_bldgclass' %}
-- input_copy/pluto_input_condo_bldgclass.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("Code")) IN ('', 'null')
      THEN NULL
      ELSE "Code"
    END AS "Code",
    CASE
      WHEN LOWER(TRIM("Description")) IN ('', 'null')
      THEN NULL
      ELSE "Description"
    END AS "Description",
    CASE
      WHEN LOWER(TRIM("Type")) IN ('', 'null')
      THEN NULL
      ELSE "Type"
    END AS "Type",
    CASE
      WHEN LOWER(TRIM("DCP created")) IN ('', 'null')
      THEN NULL
      ELSE "DCP created"
    END AS "DCP created",
    CASE
      WHEN LOWER(TRIM("Logic for codes created by DCP")) IN ('', 'null')
      THEN NULL
      ELSE "Logic for codes created by DCP"
    END AS "Logic for codes created by DCP"
  )
FROM {{ source('pluto_inputs', 'pluto_input_condo_bldgclass') }} AS pluto_input_condo_bldgclass
{% elif alias == 'pluto_input_condolot_descriptiveattributes' %}
-- input_copy/pluto_input_condolot_descriptiveattributes.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("CondNO")) IN ('', 'null')
      THEN NULL
      ELSE "CondNO"
    END AS "CondNO",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("Boro")) IN ('', 'null')
            THEN NULL
            ELSE "Boro"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "Boro",
    CASE
      WHEN LOWER(TRIM("PARID")) IN ('', 'null')
      THEN NULL
      ELSE "PARID"
    END AS "PARID",
    CASE
      WHEN LOWER(TRIM("BC")) IN ('', 'null')
      THEN NULL
      ELSE "BC"
    END AS "BC",
    CAST(REPLACE(TRIM(
          CASE
            WHEN LOWER(TRIM("TC")) IN ('', 'null')
            THEN NULL
            ELSE "TC"
          END), ',', '') AS DECIMAL(38, 12)) AS "TC",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("LandSize")) IN ('', 'null')
            THEN NULL
            ELSE "LandSize"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "LandSize",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("Story")) IN ('', 'null')
            THEN NULL
            ELSE "Story"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "Story",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("YearBuilt")) IN ('', 'null')
            THEN NULL
            ELSE "YearBuilt"
          END
        ),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "YearBuilt"
  )
FROM {{ source('pluto_inputs', 'pluto_input_condolot_descriptiveattributes') }} AS pluto_input_condolot_descriptiveattributes
{% elif alias == 'pluto_input_geocodes' %}
-- input_copy/pluto_input_geocodes.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("billingbbl", '') AS "billingbbl",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("cd", '') AS "cd",
    NULLIF("ct2010", '') AS "ct2010",
    NULLIF("cb2010", '') AS "cb2010",
    NULLIF("ct2020", '') AS "ct2020",
    NULLIF("cb2020", '') AS "cb2020",
    NULLIF("schooldist", '') AS "schooldist",
    NULLIF("council", '') AS "council",
    NULLIF("zipcode", '') AS "zipcode",
    NULLIF("policeprct", '') AS "policeprct",
    NULLIF("healthcenterdistrict", '') AS "healthcenterdistrict",
    NULLIF("healtharea", '') AS "healtharea",
    NULLIF("sanitdistrict", '') AS "sanitdistrict",
    NULLIF("sanitsub", '') AS "sanitsub",
    NULLIF("boepreferredstreetname", '') AS "boepreferredstreetname",
    NULLIF("taxmap", '') AS "taxmap",
    NULLIF("sanbornmapidentifier", '') AS "sanbornmapidentifier",
    NULLIF("latitude", '') AS "latitude",
    NULLIF("longitude", '') AS "longitude",
    NULLIF("grc", '') AS "grc",
    NULLIF("grc2", '') AS "grc2",
    NULLIF("msg", '') AS "msg",
    NULLIF("msg2", '') AS "msg2",
    NULLIF("firecomp", '') AS "firecomp",
    NULLIF("borough", '') AS "borough",
    NULLIF("block", '') AS "block",
    NULLIF("lot", '') AS "lot",
    NULLIF("easement", '') AS "easement",
    NULLIF("input_sname", '') AS "input_sname",
    NULLIF("input_hnum", '') AS "input_hnum",
    NULLIF("numberofexistingstructures", '') AS "numberofexistingstructures"
  )
FROM {{ source('pluto_inputs', 'pluto_input_geocodes') }} AS pluto_input_geocodes
{% elif alias == 'pluto_input_landuse_bldgclass' %}
-- input_copy/pluto_input_landuse_bldgclass.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("bldgclass")) IN ('', 'null')
      THEN NULL
      ELSE "bldgclass"
    END AS "bldgclass",
    CASE
      WHEN LOWER(TRIM("landuse")) IN ('', 'null')
      THEN NULL
      ELSE "landuse"
    END AS "landuse",
    CASE
      WHEN LOWER(TRIM("landusevalue")) IN ('', 'null')
      THEN NULL
      ELSE "landusevalue"
    END AS "landusevalue"
  )
FROM {{ source('pluto_inputs', 'pluto_input_landuse_bldgclass') }} AS pluto_input_landuse_bldgclass
{% elif alias == 'pluto_input_numbldgs' %}
-- input_copy/pluto_input_numbldgs.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("bbl", '') AS "bbl"
  )
FROM {{ source('pluto_inputs', 'pluto_input_numbldgs') }} AS pluto_input_numbldgs
{% elif alias == 'pluto_input_research' %}
-- input_copy/pluto_input_research.sql
-- Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.
SELECT
  *
  REPLACE (
    CASE
      WHEN LOWER(TRIM("bbl")) IN ('', 'null')
      THEN NULL
      ELSE "bbl"
    END AS "bbl",
    CASE
      WHEN LOWER(TRIM("field")) IN ('', 'null')
      THEN NULL
      ELSE "field"
    END AS "field",
    CASE
      WHEN LOWER(TRIM("old_value")) IN ('', 'null')
      THEN NULL
      ELSE "old_value"
    END AS "old_value",
    CASE
      WHEN LOWER(TRIM("new_value")) IN ('', 'null')
      THEN NULL
      ELSE "new_value"
    END AS "new_value",
    CAST(REPLACE(
        TRIM(
          CASE
            WHEN LOWER(TRIM("Type")) IN ('', 'null')
            THEN NULL
            ELSE "Type"
          END),
        ',',
        ''
      ) AS DECIMAL(38, 12)) AS "Type",
    CASE
      WHEN LOWER(TRIM("reason")) IN ('', 'null')
      THEN NULL
      ELSE "reason"
    END AS "reason",
    CASE
      WHEN LOWER(TRIM("version")) IN ('', 'null')
      THEN NULL
      ELSE "version"
    END AS "version"
  )
FROM {{ source('pluto_inputs', 'pluto_input_research') }} AS pluto_input_research
{% elif alias == 'pluto_pts' %}
-- input_copy/pluto_pts.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("boro", '') AS "boro",
    NULLIF("block", '') AS "block",
    NULLIF("lot", '') AS "lot",
    NULLIF("street_name", '') AS "street_name",
    NULLIF("housenum_lo", '') AS "housenum_lo",
    NULLIF("housenum_hi", '') AS "housenum_hi",
    NULLIF("aptno", '') AS "aptno",
    NULLIF("zip_code", '') AS "zip_code",
    NULLIF("bldg_class", '') AS "bldg_class",
    NULLIF("ease", '') AS "ease",
    NULLIF("av_owner", '') AS "av_owner",
    NULLIF("land_area", '') AS "land_area",
    NULLIF("gross_sqft", '') AS "gross_sqft",
    NULLIF("residential_area_gross", '') AS "residential_area_gross",
    NULLIF("office_area_gross", '') AS "office_area_gross",
    NULLIF("retail_area_gross", '') AS "retail_area_gross",
    NULLIF("garage_area", '') AS "garage_area",
    NULLIF("storage_area_gross", '') AS "storage_area_gross",
    NULLIF("factory_area_gross", '') AS "factory_area_gross",
    NULLIF("other_area_gross", '') AS "other_area_gross",
    NULLIF("num_bldgs", '') AS "num_bldgs",
    NULLIF("bld_story", '') AS "bld_story",
    NULLIF("coop_apts", '') AS "coop_apts",
    NULLIF("units", '') AS "units",
    NULLIF("lot_frt", '') AS "lot_frt",
    NULLIF("lot_dep", '') AS "lot_dep",
    NULLIF("bld_frt", '') AS "bld_frt",
    NULLIF("bld_dep", '') AS "bld_dep",
    NULLIF("bld_ext", '') AS "bld_ext",
    NULLIF("lot_irreg", '') AS "lot_irreg",
    NULLIF("curactland", '') AS "curactland",
    NULLIF("curacttot", '') AS "curacttot",
    NULLIF("curactextot", '') AS "curactextot",
    NULLIF("yrbuilt", '') AS "yrbuilt",
    NULLIF("yralt1", '') AS "yralt1",
    NULLIF("yralt2", '') AS "yralt2",
    NULLIF("condo_number", '') AS "condo_number",
    NULLIF("appt_boro", '') AS "appt_boro",
    NULLIF("appt_block", '') AS "appt_block",
    NULLIF("appt_lot", '') AS "appt_lot",
    NULLIF("appt_ease", '') AS "appt_ease",
    NULLIF("appt_date", '') AS "appt_date",
    NULLIF("parid", '') AS "parid"
  )
FROM {{ source('pluto_inputs', 'pluto_pts') }} AS pluto_pts
{% elif alias == 'previous_pluto' %}
-- input_copy/previous_pluto.sql
-- The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.
SELECT
  *
  REPLACE (
    NULLIF("borough", '') AS "borough",
    NULLIF("block", '') AS "block",
    NULLIF("lot", '') AS "lot",
    NULLIF("cd", '') AS "cd",
    NULLIF("bct2020", '') AS "bct2020",
    NULLIF("bctcb2020", '') AS "bctcb2020",
    NULLIF("ct2010", '') AS "ct2010",
    NULLIF("cb2010", '') AS "cb2010",
    NULLIF("schooldist", '') AS "schooldist",
    NULLIF("council", '') AS "council",
    NULLIF("zipcode", '') AS "zipcode",
    NULLIF("firecomp", '') AS "firecomp",
    NULLIF("policeprct", '') AS "policeprct",
    NULLIF("healthcenterdistrict", '') AS "healthcenterdistrict",
    NULLIF("healtharea", '') AS "healtharea",
    NULLIF("sanitboro", '') AS "sanitboro",
    NULLIF("sanitdistrict", '') AS "sanitdistrict",
    NULLIF("sanitsub", '') AS "sanitsub",
    NULLIF("address", '') AS "address",
    NULLIF("zonedist1", '') AS "zonedist1",
    NULLIF("zonedist2", '') AS "zonedist2",
    NULLIF("zonedist3", '') AS "zonedist3",
    NULLIF("zonedist4", '') AS "zonedist4",
    NULLIF("overlay1", '') AS "overlay1",
    NULLIF("overlay2", '') AS "overlay2",
    NULLIF("spdist1", '') AS "spdist1",
    NULLIF("spdist2", '') AS "spdist2",
    NULLIF("spdist3", '') AS "spdist3",
    NULLIF("ltdheight", '') AS "ltdheight",
    NULLIF("splitzone", '') AS "splitzone",
    NULLIF("bldgclass", '') AS "bldgclass",
    NULLIF("landuse", '') AS "landuse",
    NULLIF("easements", '') AS "easements",
    NULLIF("ownertype", '') AS "ownertype",
    NULLIF("ownername", '') AS "ownername",
    NULLIF("lotarea", '') AS "lotarea",
    NULLIF("bldgarea", '') AS "bldgarea",
    NULLIF("comarea", '') AS "comarea",
    NULLIF("resarea", '') AS "resarea",
    NULLIF("officearea", '') AS "officearea",
    NULLIF("retailarea", '') AS "retailarea",
    NULLIF("garagearea", '') AS "garagearea",
    NULLIF("strgearea", '') AS "strgearea",
    NULLIF("factryarea", '') AS "factryarea",
    NULLIF("otherarea", '') AS "otherarea",
    NULLIF("areasource", '') AS "areasource",
    NULLIF("numbldgs", '') AS "numbldgs",
    NULLIF("numfloors", '') AS "numfloors",
    NULLIF("unitsres", '') AS "unitsres",
    NULLIF("unitstotal", '') AS "unitstotal",
    NULLIF("lotfront", '') AS "lotfront",
    NULLIF("lotdepth", '') AS "lotdepth",
    NULLIF("bldgfront", '') AS "bldgfront",
    NULLIF("bldgdepth", '') AS "bldgdepth",
    NULLIF("ext", '') AS "ext",
    NULLIF("proxcode", '') AS "proxcode",
    NULLIF("irrlotcode", '') AS "irrlotcode",
    NULLIF("lottype", '') AS "lottype",
    NULLIF("bsmtcode", '') AS "bsmtcode",
    NULLIF("assessland", '') AS "assessland",
    NULLIF("assesstot", '') AS "assesstot",
    NULLIF("exempttot", '') AS "exempttot",
    NULLIF("yearbuilt", '') AS "yearbuilt",
    NULLIF("yearalter1", '') AS "yearalter1",
    NULLIF("yearalter2", '') AS "yearalter2",
    NULLIF("histdist", '') AS "histdist",
    NULLIF("landmark", '') AS "landmark",
    NULLIF("builtfar", '') AS "builtfar",
    NULLIF("residfar", '') AS "residfar",
    NULLIF("commfar", '') AS "commfar",
    NULLIF("facilfar", '') AS "facilfar",
    NULLIF("borocode", '') AS "borocode",
    NULLIF("bbl", '') AS "bbl",
    NULLIF("condono", '') AS "condono",
    NULLIF("tract2010", '') AS "tract2010",
    NULLIF("xcoord", '') AS "xcoord",
    NULLIF("ycoord", '') AS "ycoord",
    NULLIF("zonemap", '') AS "zonemap",
    NULLIF("zmcode", '') AS "zmcode",
    NULLIF("sanborn", '') AS "sanborn",
    NULLIF("taxmap", '') AS "taxmap",
    NULLIF("edesignum", '') AS "edesignum",
    NULLIF("appbbl", '') AS "appbbl",
    NULLIF("appdate", '') AS "appdate",
    NULLIF("plutomapid", '') AS "plutomapid",
    NULLIF("firm07_flag", '') AS "firm07_flag",
    NULLIF("pfirm15_flag", '') AS "pfirm15_flag",
    NULLIF("version", '') AS "version",
    NULLIF("dcpedited", '') AS "dcpedited",
    NULLIF("latitude", '') AS "latitude",
    NULLIF("longitude", '') AS "longitude",
    NULLIF("notes", '') AS "notes",
    NULLIF("mih_opt1", '') AS "mih_opt1",
    NULLIF("mih_opt2", '') AS "mih_opt2",
    NULLIF("mih_opt3", '') AS "mih_opt3",
    NULLIF("mih_opt4", '') AS "mih_opt4",
    NULLIF("trnstzone", '') AS "trnstzone",
    NULLIF("affresfar", '') AS "affresfar",
    NULLIF("mnffar", '') AS "mnffar"
  )
FROM {{ source('pluto_inputs', 'previous_pluto') }} AS previous_pluto
{% elif alias == 'pts_properties_base' %}
-- pluto_build/sql/create_pts.sql statement 2
SELECT
  boro,
  block AS tb,
  lot AS tl,
  parid AS bbl,
  street_name,
  housenum_lo,
  housenum_hi,
  aptno,
  zip_code AS zip,
  bldg_class AS bldgcl,
  ease,
  av_owner AS owner,
  CAST(REPLACE(land_area, '+', '') AS DOUBLE) AS land_area,
  CAST(REPLACE(gross_sqft, '+', '') AS DOUBLE) AS gross_sqft,
  CAST(REPLACE(residential_area_gross, '+', '') AS DOUBLE) AS residarea,
  CAST(REPLACE(office_area_gross, '+', '') AS DOUBLE) AS officearea,
  CAST(REPLACE(retail_area_gross, '+', '') AS DOUBLE) AS retailarea,
  CAST(REPLACE(garage_area, '+', '') AS DOUBLE) AS garagearea,
  CAST(REPLACE(storage_area_gross, '+', '') AS DOUBLE) AS storagearea,
  CAST(REPLACE(factory_area_gross, '+', '') AS DOUBLE) AS factoryarea,
  CAST(REPLACE(other_area_gross, '+', '') AS DOUBLE) AS otherarea,
  CAST(REPLACE(num_bldgs, '+', '') AS DOUBLE) AS bldgs,
  CAST(REPLACE(bld_story, '+', '') AS DOUBLE) AS story,
  CAST(REPLACE(coop_apts, '+', '') AS DOUBLE) AS coop_apts,
  CAST(REPLACE(units, '+', '') AS DOUBLE) AS units,
  bld_ext AS ext,
  lot_irreg AS irreg,
  CAST(REPLACE(curactland, '+', '') AS DOUBLE) AS curavl_act,
  CAST(REPLACE(curacttot, '+', '') AS DOUBLE) AS curavt_act,
  CAST(REPLACE(curactextot, '+', '') AS DOUBLE) AS curext_act,
  yrbuilt,
  yralt1, /* current values contain the most up to date public values.  */ /* June to January current values have the Final value from the prior year. */ /* January to May current values contain the Tentative values. */ /* After May current values contain the Final values. */ /* After May 25th (the date the final roll is released)  it will contain the final values */
  yralt2, /* pyactland */
  condo_number, /* pyacttot */
  appt_boro AS ap_boro, /* pyactextot */
  appt_block AS ap_block,
  appt_lot AS ap_lot,
  appt_ease AS ap_ease,
  appt_date AS ap_date,
  ROUND(CAST(REPLACE(lot_frt, '+', '') AS DECIMAL(38, 12)), 2) AS lfft,
  ROUND(CAST(REPLACE(lot_dep, '+', '') AS DECIMAL(38, 12)), 2) AS ldft,
  ROUND(CAST(REPLACE(bld_frt, '+', '') AS DECIMAL(38, 12)), 2) AS bfft,
  ROUND(CAST(REPLACE(bld_dep, '+', '') AS DECIMAL(38, 12)), 2) AS bdft
FROM ({{ pluto_input('stg__pluto_pts') }}) AS stg__pluto_pts
{% elif alias == 'stg__dcp_cb2010_wi' %}
-- models/stg__dcp_cb2010_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_cb2010_wi') }}) AS dcp_cb2010_wi
{% elif alias == 'stg__dcp_cb2020_wi' %}
-- models/stg__dcp_cb2020_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_cb2020_wi') }}) AS dcp_cb2020_wi
{% elif alias == 'stg__dcp_cdboundaries_wi' %}
-- models/stg__dcp_cdboundaries_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dcp_cdboundaries_wi') }} AS dcp_cdboundaries_wi
{% elif alias == 'stg__dcp_colp' %}
-- models/stg__dcp_colp.sql
SELECT
  *
FROM ({{ pluto_input('dcp_colp') }}) AS dcp_colp
{% elif alias == 'stg__dcp_commercialoverlay' %}
-- models/stg__dcp_commercialoverlay.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_commercialoverlay') }}) AS dcp_commercialoverlay
{% elif alias == 'stg__dcp_councildistricts_wi' %}
-- models/stg__dcp_councildistricts_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dcp_councildistricts_wi') }} AS dcp_councildistricts_wi
{% elif alias == 'stg__dcp_ct2010_wi' %}
-- models/stg__dcp_ct2010_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_ct2010_wi') }}) AS dcp_ct2010_wi
{% elif alias == 'stg__dcp_ct2020_wi' %}
-- models/stg__dcp_ct2020_wi.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_ct2020_wi') }}) AS dcp_ct2020_wi
{% elif alias == 'stg__dcp_edesignation' %}
-- models/stg__dcp_edesignation.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_edesignation') }}) AS dcp_edesignation
{% elif alias == 'stg__dcp_firecompanies' %}
-- models/stg__dcp_firecompanies.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_firecompanies') }}) AS dcp_firecompanies
{% elif alias == 'stg__dcp_gis_mandatory_inclusionary_housing' %}
-- models/stg__dcp_gis_mandatory_inclusionary_housing.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_gis_mandatory_inclusionary_housing') }}) AS dcp_gis_mandatory_inclusionary_housing
{% elif alias == 'stg__dcp_healthareas' %}
-- models/stg__dcp_healthareas.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_healthareas') }}) AS dcp_healthareas
{% elif alias == 'stg__dcp_healthcenters' %}
-- models/stg__dcp_healthcenters.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_healthcenters') }}) AS dcp_healthcenters
{% elif alias == 'stg__dcp_limitedheight' %}
-- models/stg__dcp_limitedheight.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_limitedheight') }}) AS dcp_limitedheight
{% elif alias == 'stg__dcp_policeprecincts' %}
-- models/stg__dcp_policeprecincts.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dcp_policeprecincts') }} AS dcp_policeprecincts
{% elif alias == 'stg__dcp_school_districts' %}
-- models/stg__dcp_school_districts.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dcp_school_districts') }} AS dcp_school_districts
{% elif alias == 'stg__dcp_specialpurpose' %}
-- models/stg__dcp_specialpurpose.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_specialpurpose') }}) AS dcp_specialpurpose
{% elif alias == 'stg__dcp_transit_zones' %}
-- models/stg__dcp_transit_zones.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_transit_zones') }}) AS dcp_transit_zones
{% elif alias == 'stg__dcp_zoningdistricts' %}
-- models/stg__dcp_zoningdistricts.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dcp_zoningdistricts') }}) AS dcp_zoningdistricts
{% elif alias == 'stg__dcp_zoningmapindex' %}
-- models/stg__dcp_zoningmapindex.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dcp_zoningmapindex') }} AS dcp_zoningmapindex
{% elif alias == 'stg__dof_dtm' %}
-- models/stg__dof_dtm.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dof_dtm') }}) AS dof_dtm
{% elif alias == 'stg__dof_shoreline' %}
-- models/stg__dof_shoreline.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dof_shoreline') }}) AS dof_shoreline
{% elif alias == 'stg__doitt_zipcodeboundaries' %}
-- models/stg__doitt_zipcodeboundaries.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'doitt_zipcodeboundaries') }} AS doitt_zipcodeboundaries
{% elif alias == 'stg__dpr_greenthumb' %}
-- models/stg__dpr_greenthumb.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('dpr_greenthumb') }}) AS dpr_greenthumb
{% elif alias == 'stg__dsny_frequencies' %}
-- models/stg__dsny_frequencies.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'dsny_frequencies') }} AS dsny_frequencies
{% elif alias == 'stg__fema_firms2007_100yr' %}
-- models/stg__fema_firms2007_100yr.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'fema_firms2007_100yr') }} AS fema_firms2007_100yr
{% elif alias == 'stg__fema_pfirms2015_100yr' %}
-- models/stg__fema_pfirms2015_100yr.sql
SELECT
  *,
  wkb_geometry AS geom
FROM {{ source('pluto_inputs', 'fema_pfirms2015_100yr') }} AS fema_pfirms2015_100yr
{% elif alias == 'stg__lpc_historic_districts' %}
-- models/stg__lpc_historic_districts.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('lpc_historic_districts') }}) AS lpc_historic_districts
{% elif alias == 'stg__lpc_landmarks' %}
-- models/stg__lpc_landmarks.sql
SELECT
  *,
  wkb_geometry AS geom
FROM ({{ pluto_input('lpc_landmarks') }}) AS lpc_landmarks
{% elif alias == 'stg__pluto_input_geocodes' %}
-- models/stg__pluto_input_geocodes.sql
SELECT
  *
FROM ({{ pluto_input('pluto_input_geocodes') }}) AS pluto_input_geocodes
{% elif alias == 'stg__pluto_pts' %}
-- models/stg__pluto_pts.sql
SELECT
  *
FROM ({{ pluto_input('pluto_pts') }}) AS pluto_pts
{% else %}
{{ exceptions.raise_compiler_error('Unknown PLUTO input: ' ~ alias) }}
{% endif %}
{% endmacro %}
