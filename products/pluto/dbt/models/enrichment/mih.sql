{{ config(materialized='table') }}
-- Business process: mih
WITH
int_mih__cleaned_mih__cleaned AS NOT MATERIALIZED (
  -- models/int_mih__cleaned.sql
  /* Clean MIH option names and create unique identifiers */
  /* Handles typos and standardizes formatting */
  SELECT
    project_id || '-' || mih_option AS mih_id,
    *,
    TRIM(
      REGEXP_REPLACE(
        REGEXP_REPLACE(
          REGEXP_REPLACE(REPLACE(mih_option, 'Affordablility', 'Affordability'), 'Option(\d)', 'Option \1', 'g') /* Step 1: Add space between "Option" and number */,
          '\s*(,|and)\s*',
          ',',
          'g'
        ) /* Step 2a: Replace "and" or "," (with any spaces) with a single comma */,
        ',+',
        ',',
        'g'
      ) /* Step 2b: collapse any sequence of commas (e.g., ",,", ",,,") */,
      ', '
    ) AS cleaned_option
  FROM ({{ pluto_input('stg__dcp_gis_mandatory_inclusionary_housing') }}) AS stg__dcp_gis_mandatory_inclusionary_housing
),
int_mih__lot_overlap_mih__lot_overlap AS NOT MATERIALIZED (
  -- models/int_mih__lot_overlap.sql
  /* Calculate spatial overlap between tax lots and MIH areas */
  /* A lot is assigned to a MIH area if: */
  /*   1. ≥10% of the lot area is covered by the MIH area, OR */
  /*   2. ≥50% of the MIH area is covered by the lot */
  WITH mih_per_area AS (
    SELECT
      p.bbl,
      m.project_id,
      m.mih_id,
      m.wkb_geometry AS mih_geom,
      p.geom AS lot_geom,
      m.cleaned_option,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(p.geom, m.wkb_geometry)
          THEN p.geom
          ELSE ST_MULTI(ST_INTERSECTION(p.geom, m.wkb_geometry))
        END
      ) AS segbblgeom,
      ST_AREA(p.geom) AS allbblgeom,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(m.wkb_geometry, p.geom)
          THEN m.wkb_geometry
          ELSE ST_MULTI(ST_INTERSECTION(m.wkb_geometry, p.geom))
        END
      ) AS segmihgeom,
      ST_AREA(m.wkb_geometry) AS allmihgeom
    FROM {{ ref('zoning') }} AS p
    INNER JOIN int_mih__cleaned_mih__cleaned AS m
      ON ST_INTERSECTS(p.geom, m.wkb_geometry)
  ), mih_areas AS (
    SELECT
      bbl,
      cleaned_option,
      project_id,
      mih_id,
      SUM(segbblgeom) AS segbblgeom,
      SUM(segmihgeom) AS segmihgeom,
      SUM(segbblgeom / allbblgeom) * 100 AS perbblgeom,
      MAX(segmihgeom / allmihgeom) * 100 AS maxpermihgeom
    FROM mih_per_area
    GROUP BY
      bbl,
      cleaned_option,
      project_id,
      mih_id
  )
  SELECT
    *
  FROM mih_areas
  WHERE
    perbblgeom >= 10 OR maxpermihgeom >= 50
),
int_pluto__miharea_pluto__miharea AS NOT MATERIALIZED (
  -- models/int_pluto__miharea.sql
  /* Pivot MIH options into binary columns */
  /* A single lot can have multiple MIH options that all apply */
  WITH bbls_with_all_options AS (
    SELECT
      bbl,
      LISTAGG(cleaned_option, ',') AS all_options
    FROM int_mih__lot_overlap_mih__lot_overlap AS int_mih__lot_overlap
    GROUP BY
      bbl
  ), pivoted AS (
    SELECT
      bbl,
      CASE WHEN all_options LIKE '%Option 1%' THEN '1' END AS mih_opt1,
      CASE WHEN all_options LIKE '%Option 2%' THEN '1' END AS mih_opt2,
      CASE
        WHEN all_options LIKE '%Option 3%' OR all_options LIKE '%Deep Affordability Option%'
        THEN '1'
      END AS mih_opt3,
      CASE WHEN all_options LIKE '%Workforce Option%' THEN '1' END AS mih_opt4
    FROM bbls_with_all_options
  )
  SELECT
    bbl,
    mih_opt1,
    mih_opt2,
    mih_opt3,
    mih_opt4
  FROM pivoted
)
SELECT * FROM int_pluto__miharea_pluto__miharea
