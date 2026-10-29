{% macro pluto_input(alias) %}
{% if alias == 'dcp_cb2010_wi' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_cb2010_wi') }}
{% elif alias == 'dcp_cb2020_wi' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_cb2020_wi') }}
{% elif alias == 'dcp_colp' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_colp') }}
{% elif alias == 'dcp_commercialoverlay' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_commercialoverlay') }}
{% elif alias == 'dcp_ct2010_wi' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_ct2010_wi') }}
{% elif alias == 'dcp_ct2020_wi' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_ct2020_wi') }}
{% elif alias == 'dcp_edesignation' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_edesignation') }}
{% elif alias == 'dcp_firecompanies' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_firecompanies') }}
{% elif alias == 'dcp_gis_mandatory_inclusionary_housing' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_gis_mandatory_inclusionary_housing') }}
{% elif alias == 'dcp_healthareas' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_healthareas') }}
{% elif alias == 'dcp_healthcenters' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_healthcenters') }}
{% elif alias == 'dcp_limitedheight' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_limitedheight') }}
{% elif alias == 'dcp_specialpurpose' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_specialpurpose') }}
{% elif alias == 'dcp_transit_zone_ranks' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_transit_zone_ranks') }}
{% elif alias == 'dcp_transit_zones' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_transit_zones') }}
{% elif alias == 'dcp_zoning_maxfar' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_zoning_maxfar') }}
{% elif alias == 'dcp_zoningdistricts' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dcp_zoningdistricts') }}
{% elif alias == 'dof_condo' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dof_condo') }}
{% elif alias == 'dof_dtm' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dof_dtm') }}
{% elif alias == 'dof_shoreline' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dof_shoreline') }}
{% elif alias == 'dpr_greenthumb' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'dpr_greenthumb') }}
{% elif alias == 'lpc_historic_districts' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'lpc_historic_districts') }}
{% elif alias == 'lpc_landmarks' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'lpc_landmarks') }}
{% elif alias == 'pluto_input_bsmtcode' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_bsmtcode') }}
{% elif alias == 'pluto_input_cama_dof' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_cama_dof') }}
{% elif alias == 'pluto_input_condo_bldgclass' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_condo_bldgclass') }}
{% elif alias == 'pluto_input_condolot_descriptiveattributes' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_condolot_descriptiveattributes') }}
{% elif alias == 'pluto_input_geocodes' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_geocodes') }}
{% elif alias == 'pluto_input_landuse_bldgclass' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_landuse_bldgclass') }}
{% elif alias == 'pluto_input_numbldgs' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_numbldgs') }}
{% elif alias == 'pluto_input_research' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_input_research') }}
{% elif alias == 'pluto_pts' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'pluto_pts') }}
{% elif alias == 'previous_pluto' %}
-- Prepared upstream input; physical types/null policy are contracted.
SELECT * FROM {{ source('pluto_inputs', 'previous_pluto') }}
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
