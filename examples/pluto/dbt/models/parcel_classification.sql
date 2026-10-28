{{ config(materialized='table') }}
-- Business process: parcel_classification
WITH
single_condo_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 1
  /* set building class for condo lots if there is only one unique building class value */
  WITH ranked_condo_building_classes AS (
    SELECT DISTINCT
      billingbbl,
      bldgcl,
      ROW_NUMBER() OVER (PARTITION BY billingbbl ORDER BY bldgcl) AS row_number
    FROM (
      SELECT DISTINCT
        billingbbl,
        bldgcl
      FROM {{ ref('tax_lot_attributes') }} AS pluto_rpad_geo
      WHERE
        bldgcl <> 'R0'
        AND bldgcl <> 'RG'
        AND bldgcl <> 'RP'
        AND bldgcl <> 'RT'
        AND CAST(billingbbl AS DECIMAL(38, 12)) > 0
    ) AS x
  ), condo_building_class_counts AS (
    SELECT
      billingbbl,
      MAX(row_number) AS maxrow_number
    FROM ranked_condo_building_classes
    GROUP BY
      billingbbl
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN __patch.__matched
        THEN MOSES_TEXT(__patch."bldgclass")
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM {{ ref('parcel_enriched') }} AS "a"
  LEFT JOIN LATERAL (
    SELECT
      TRUE AS __matched,
      (
        CASE WHEN c.maxrow_number = 1 THEN b.bldgcl END
      ) AS "bldgclass"
    FROM ranked_condo_building_classes AS b, condo_building_class_counts AS c
    WHERE
      a.bbl = b.billingbbl AND c.billingbbl = a.bbl
    LIMIT 1
  ) AS __patch
    ON TRUE
),
multi_condo_building_class_lookup AS MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 2
  -- set building class for condo lots where there are multiple building class values
  WITH ranked_condo_building_classes AS (
    SELECT DISTINCT
      billingbbl,
      bldgcl,
      ROW_NUMBER() OVER (PARTITION BY billingbbl ORDER BY bldgcl) AS row_number
    FROM (
      SELECT DISTINCT
        billingbbl,
        bldgcl
      FROM {{ ref('tax_lot_attributes') }} AS pluto_rpad_geo
      WHERE
        bldgcl <> 'R0'
        AND bldgcl <> 'RG'
        AND bldgcl <> 'RP'
        AND bldgcl <> 'RT'
        AND CAST(billingbbl AS DECIMAL(38, 12)) > 0
    ) AS x
  ), condo_building_class_counts AS (
    SELECT
      billingbbl,
      MAX(row_number) AS maxrow_number
    FROM ranked_condo_building_classes
    GROUP BY
      billingbbl
  ), mapped_condo_building_types AS (
    SELECT
      a.billingbbl,
      a.bldgcl,
      a.row_number,
      c."Type" AS bldg_type
    FROM ranked_condo_building_classes AS a, condo_building_class_counts AS b, ({{ pluto_input('pluto_input_condo_bldgclass') }}) AS c
    WHERE
      b.maxrow_number >= 2 AND a.billingbbl = b.billingbbl AND a.bldgcl = c."Code"
    ORDER BY
      a.billingbbl
  )
  SELECT DISTINCT
    billingbbl,
    bldg_type
  FROM mapped_condo_building_types
  ORDER BY
    billingbbl,
    bldg_type
),
summarized_condo_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 3
  SELECT
    billingbbl,
    LISTAGG(bldg_type, ', ') AS bldg_type
  FROM multi_condo_building_class_lookup AS bblsbldgclasslookup
  GROUP BY
    billingbbl
),
residential_condo_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 4
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RD')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM single_condo_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Res'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
commercial_condo_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 5
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RC')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM residential_condo_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Com'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
commercial_industrial_condo_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 6
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RI')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM commercial_condo_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Com, Ind'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
commercial_residential_condo_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 7
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RM')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM commercial_industrial_condo_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Com, Res'
        OR (
          bldg_type LIKE '%R9%' AND bldg_type NOT LIKE '%Ind%'
        )
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
mixed_use_condo_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 8
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RX')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM commercial_residential_condo_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Com, Ind, Res' OR bldg_type LIKE '%Ind, R9%'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
industrial_residential_condo_classes AS MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 9
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('RZ')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM mixed_use_condo_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM summarized_condo_building_classes AS b
    WHERE
      (
        bldg_type = 'Ind, Res'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.billingbbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.billingbbl
    )
),
park_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 10
  -- set the building class to Q0
  -- where the zoning district is park and the building class is null or vacant
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN zonedist1 = 'PARK' AND (
          bldgclass IS NULL OR bldgclass LIKE 'V%'
        )
        THEN MOSES_TEXT('Q0')
        ELSE "pluto"."bldgclass"
      END AS "bldgclass"
    )
  FROM industrial_residential_condo_classes AS "pluto"
),
garden_building_classes AS MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 11
  /* set the building class to QG */
  /* where the building class is null or vacant */
  /* and more than 15% of the lot is covered by a greenthumb garden */
  /* or more than 25% of the garden is in a lot */
  WITH parcel_garden_overlap AS (
    SELECT
      p.bbl,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(p.geom, n.geom)
          THEN p.geom
          ELSE ST_MULTI(ST_INTERSECTION(p.geom, n.geom))
        END
      ) AS segbblgeom,
      ST_AREA(p.geom) AS allbblgeom,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(n.geom, p.geom)
          THEN n.geom
          ELSE ST_MULTI(ST_INTERSECTION(n.geom, p.geom))
        END
      ) AS segzonegeom,
      ST_AREA(n.geom) AS allzonegeom
    FROM park_building_classes AS p
    INNER JOIN ({{ pluto_input('stg__dpr_greenthumb') }}) AS n
      ON ST_INTERSECTS(p.geom, n.geom)
    WHERE
      p.bldgclass LIKE 'V%' OR p.bldgclass IS NULL
  ), qualifying_garden_parcels AS (
    SELECT
      bbl,
      segbblgeom,
      (
        segbblgeom / allbblgeom
      ) * 100 AS perbblgeom,
      (
        segzonegeom / allzonegeom
      ) * 100 AS pergardengeom
    FROM parcel_garden_overlap
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('QG')
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM park_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM qualifying_garden_parcels AS b
    WHERE
      (
        perbblgeom >= 15 OR pergardengeom >= 25
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    )
),
corrected_z7_building_classes AS NOT MATERIALIZED (
  -- pluto_build/sql/bldgclass.sql statement 12
  /* update Z7 values */
  WITH z7_parcels AS (
    SELECT
      bbl
    FROM garden_building_classes AS pluto
    WHERE
      bldgclass = 'Z7'
  ), candidate_z7_building_classes AS (
    SELECT DISTINCT
      bbl,
      bldgcl,
      ROW_NUMBER() OVER (PARTITION BY bbl ORDER BY bldgcl) AS row_number
    FROM (
      SELECT DISTINCT
        b.bldgcl,
        b.boro || b.tb || b.tl AS bbl
      FROM z7_parcels AS a
      LEFT JOIN {{ ref('tax_lot_attributes') }} AS b
        ON a.bbl = b.boro || b.tb || b.tl
    ) AS x
  ), z7_building_class_lookup AS (
    SELECT
      bbl,
      bldgcl
    FROM candidate_z7_building_classes
    WHERE
      row_number = 1
  )
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.bldgcl)
        ELSE "a"."bldgclass"
      END AS "bldgclass"
    )
  FROM garden_building_classes AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM z7_building_class_lookup AS b
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.bbl) = 1
  ) AS "b"
    ON (
      a.bbl = b.bbl
    ) AND (
      (
        a.bldgclass = 'Z7'
      ) = "b".__matched
    )
),
classified_parcel_land_use AS MATERIALIZED (
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
  FROM corrected_z7_building_classes AS "a"
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
vacant_land_area_sources AS NOT MATERIALIZED (
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
  FROM classified_parcel_land_use AS "a"
),
centroid_coordinate_fallback AS NOT MATERIALIZED (
  -- pluto_build/sql/update_empty_coord.sql statement 1
  /* Update X/Y and Lat/Long fields that are NULL with values from Lot Centroids */
  /* Make sure lot centroids fall within the polygon */
  WITH parcel_centroid_coordinates AS (
    SELECT
      bbl,
      CASE
        WHEN ST_CONTAINS(geom, ST_SETSRID(centroid, 4326)) IS TRUE
        THEN centroid
        ELSE point_surface
      END AS centroid /* check whether the centroid locates in the polygon, otherwise use the PointOnSurface function */
    FROM (
      SELECT
        p.bbl,
        p.geom,
        ST_CENTROID(p.geom) AS centroid,
        ST_POINTONSURFACE(p.geom) AS point_surface
      FROM vacant_land_area_sources AS p
      WHERE
        p.geom IS NOT NULL AND p.xcoord IS NULL
    ) AS tmp
  )
  SELECT
    "b".*
    REPLACE (
      CASE
        WHEN "t".__matched
        THEN MOSES_TEXT(ST_X(MOSES_TRANSFORM_CRS(t.centroid, 4326, 2263)))
        ELSE "b"."xcoord"
      END AS "xcoord",
      CASE
        WHEN "t".__matched
        THEN MOSES_TEXT(ST_Y(MOSES_TRANSFORM_CRS(t.centroid, 4326, 2263)))
        ELSE "b"."ycoord"
      END AS "ycoord",
      CASE
        WHEN "t".__matched
        THEN MOSES_TEXT(ST_Y(t.centroid))
        ELSE "b"."latitude"
      END AS "latitude",
      CASE
        WHEN "t".__matched
        THEN MOSES_TEXT(ST_X(t.centroid))
        ELSE "b"."longitude"
      END AS "longitude",
      CASE
        WHEN "t".__matched
        THEN CAST(ST_SETSRID(t.centroid, 4326) AS GEOMETRY)
        ELSE "b"."centroid"
      END AS "centroid"
    )
  FROM vacant_land_area_sources AS "b"
  LEFT JOIN (
    SELECT
      "t".*,
      TRUE AS __matched
    FROM parcel_centroid_coordinates AS t
    WHERE
      (
        ST_X(MOSES_TRANSFORM_CRS(t.centroid, 4326, 2263)) IS NOT NULL
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY t.bbl) = 1
  ) AS "t"
    ON (
      (
        b.xcoord IS NULL
      ) = "t".__matched
    ) AND (
      b.bbl = t.bbl
    )
)
SELECT * FROM centroid_coordinate_fallback
