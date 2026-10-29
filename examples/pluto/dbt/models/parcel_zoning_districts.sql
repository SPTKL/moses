{{ config(materialized='table', alias='zoning') }}
-- Business process: parcel_zoning_districts
WITH
valid_parcel_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 2
  SELECT
    id,
    bbl,
    moses_makevalid(geom) AS geom
  FROM {{ ref('parcel_geometry') }} AS pluto
  WHERE
    moses_geometrytype(moses_makevalid(geom)) = 'ST_MultiPolygon'
),
valid_zoning_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 6
  SELECT
    CASE
      WHEN zonedist = ANY(
        ['BALL FIELD', 'PLAYGROUND', 'PUBLIC PLACE']
      )
      THEN 'PARK'
      ELSE zonedist
    END AS zonedist,
    moses_makevalid(geom) AS geom
  FROM ({{ pluto_input('stg__dcp_zoningdistricts') }}) AS stg__dcp_zoningdistricts
  WHERE
    moses_geometrytype(moses_makevalid(geom)) = 'ST_MultiPolygon'
),
parcel_zone_intersection_areas AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 10
  SELECT
    p.id,
    bbl,
    n.zonedist,
    ST_AREA_SPHEROID(
      ST_FLIPCOORDINATES(
        CASE
          WHEN ST_COVEREDBY(p.geom, n.geom)
          THEN p.geom
          ELSE ST_MULTI(ST_INTERSECTION(p.geom, n.geom))
        END
      )
    ) AS segbblgeom,
    ST_AREA_SPHEROID(
      ST_FLIPCOORDINATES(
        CASE
          WHEN ST_COVEREDBY(n.geom, p.geom)
          THEN n.geom
          ELSE ST_MULTI(ST_INTERSECTION(n.geom, p.geom))
        END
      )
    ) AS segzonegeom,
    ST_AREA_SPHEROID(ST_FLIPCOORDINATES(p.geom)) AS allbblgeom,
    ST_AREA_SPHEROID(ST_FLIPCOORDINATES(n.geom)) AS allzonegeom
  FROM valid_parcel_polygons AS p
  INNER JOIN valid_zoning_polygons AS n
    ON ST_INTERSECTS(p.geom, n.geom)
),
grouped_parcel_zone_areas AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 14
  SELECT
    id,
    bbl,
    zonedist,
    allbblgeom,
    SUM(segbblgeom) AS segbblgeom,
    SUM(segzonegeom) AS segzonegeom,
    SUM(allzonegeom) AS allzonegeom
  FROM parcel_zone_intersection_areas AS lotzoneper
  GROUP BY
    id,
    bbl,
    allbblgeom,
    zonedist
),
initial_zone_coverage_rankings AS MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 16
  WITH parcel_zone_rankings AS (
    SELECT
      id,
      bbl,
      zonedist,
      segbblgeom,
      allbblgeom,
      segzonegeom,
      allzonegeom,
      (
        segbblgeom / allbblgeom
      ) * 100 AS perbblgeom,
      (
        segzonegeom / allzonegeom
      ) * 100 AS perzonegeom,
      ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) AS bbl_row_number, /* zone districts per lot ranked by percent of lot covered */
      ROW_NUMBER() OVER (
        PARTITION BY zonedist
        ORDER BY (
          segbblgeom / allbblgeom
        ) * 100 < 10, segzonegeom DESC NULLS FIRST
      ) AS zonedist_row_number /* per zoning district type, rank by */ /*   1) if lot meets 10% coverage by zoning district threshold */ /*   2) area of coverage */ /* This is to get cases where special zoning district may only be assigned to one lot. */ /* 1) is to cover edge case where largest section of specific large (but common) zoning district that happens to have largest area on small fraction of huge lot */
    FROM grouped_parcel_zone_areas AS lotzoneper_grouped
  )
  SELECT
    id,
    bbl,
    zonedist,
    segbblgeom,
    allbblgeom,
    perbblgeom,
    segzonegeom,
    allzonegeom,
    perzonegeom,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) AS row_number,
    CASE
      WHEN ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) = 1
      OR LAG(segbblgeom, 1, segbblgeom) OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) - segbblgeom > 0.01
      THEN 1
      ELSE 0
    END AS group_start /* identifying whether zone of rank n for a lot is within 0.01 sq m of zone of rank (n-1) for same lot for tie-breaking logic in next query */
  FROM parcel_zone_rankings
  WHERE
    bbl_row_number = 1 OR perbblgeom >= 10 OR zonedist_row_number = 1
),
empty_zoning_priority_schema AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_create_priority.sql statement 2
  SELECT
    MOSES_TEXT(NULL) AS "zonedist",
    CAST(NULL AS SMALLINT) AS "priority"
  WHERE
    FALSE
),
zoning_district_priorities AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_create_priority.sql statement 3
  SELECT
    *
  FROM empty_zoning_priority_schema AS zonedist_priority
  UNION ALL
  SELECT
    MOSES_TEXT(__new."zonedist") AS "zonedist",
    CAST(__new."priority" AS SMALLINT) AS "priority"
  FROM (VALUES
    ('R1-1', 1),
    ('R1-2', 2),
    ('R1-2A', 3),
    ('R10', 4),
    ('R10A', 5),
    ('R10H', 6),
    ('R2', 7),
    ('R2A', 8),
    ('R2X', 9),
    ('R3-1', 10),
    ('R3-2', 11),
    ('R3A', 12),
    ('R3X', 13),
    ('R4', 14),
    ('R4-1', 15),
    ('R4A', 16),
    ('R4B', 17),
    ('R5', 18),
    ('R5A', 19),
    ('R5B', 20),
    ('R5D', 21),
    ('R6', 22),
    ('R6A', 23),
    ('R6B', 24),
    ('R7-1', 25),
    ('R7-2', 26),
    ('R7-3', 27),
    ('R7A', 28),
    ('R7B', 29),
    ('R7D', 30),
    ('R7X', 31),
    ('R8', 32),
    ('R8A', 33),
    ('R8B', 34),
    ('R8X', 35),
    ('R9', 36),
    ('R9A', 37),
    ('R9X', 38),
    ('C1-6', 39),
    ('C1-6A', 40),
    ('C1-7', 41),
    ('C1-7A', 42),
    ('C1-8', 43),
    ('C1-8A', 44),
    ('C1-8X', 45),
    ('C1-9', 46),
    ('C1-9A', 47),
    ('C2-6', 48),
    ('C2-6A', 49),
    ('C2-7', 50),
    ('C2-7A', 51),
    ('C2-8', 52),
    ('C2-8A', 53),
    ('C3', 54),
    ('C3A', 55),
    ('C4-1', 56),
    ('C4-2', 57),
    ('C4-2A', 58),
    ('C4-2F', 59),
    ('C4-3', 60),
    ('C4-3A', 61),
    ('C4-4', 62),
    ('C4-4A', 63),
    ('C4-4D', 64),
    ('C4-4L', 65),
    ('C4-5', 66),
    ('C4-5A', 67),
    ('C4-5D', 68),
    ('C4-5X', 69),
    ('C4-6', 70),
    ('C4-6A', 71),
    ('C4-7', 72),
    ('C5-1', 73),
    ('C5-1A', 74),
    ('C5-2', 75),
    ('C5-2.5', 76),
    ('C5-2A', 77),
    ('C5-3', 78),
    ('C5-4', 79),
    ('C5-5', 80),
    ('C5-P', 81),
    ('C6-1', 82),
    ('C6-1A', 83),
    ('C6-1G', 84),
    ('C6-2', 85),
    ('C6-2A', 86),
    ('C6-2G', 87),
    ('C6-2M', 88),
    ('C6-3', 89),
    ('C6-3A', 90),
    ('C6-3D', 91),
    ('C6-3X', 92),
    ('C6-4', 93),
    ('C6-4.5', 94),
    ('C6-4A', 95),
    ('C6-4M', 96),
    ('C6-4X', 97),
    ('C6-5', 98),
    ('C6-5.5', 99),
    ('C6-6', 100),
    ('C6-6.5', 101),
    ('C6-7', 102),
    ('C6-7T', 103),
    ('C6-9', 104),
    ('C7', 105),
    ('C8-1', 106),
    ('C8-2', 107),
    ('C8-3', 108),
    ('C8-4', 109),
    ('M1-1', 110),
    ('M1-1/R5', 111),
    ('M1-1/R6A', 112),
    ('M1-1/R7-2', 113),
    ('M1-1/R7D', 114),
    ('M1-1D', 115),
    ('M1-2', 116),
    ('M1-2/R5B', 117),
    ('M1-2/R5D', 118),
    ('M1-2/R6', 119),
    ('M1-2/R6A', 120),
    ('M1-2/R6B', 121),
    ('M1-2/R7-2', 122),
    ('M1-2/R7A', 123),
    ('M1-2/R8', 124),
    ('M1-2/R8A', 125),
    ('M1-2D', 126),
    ('M1-3', 127),
    ('M1-3/R7X', 128),
    ('M1-3/R8', 129),
    ('M1-4', 130),
    ('M1-4/R6A', 131),
    ('M1-4/R6B', 132),
    ('M1-4/R7-2', 133),
    ('M1-4/R7A', 134),
    ('M1-4/R7D', 135),
    ('M1-4/R7X', 136),
    ('M1-4/R8A', 137),
    ('M1-4/R9A', 138),
    ('M1-4D', 139),
    ('M1-5', 140),
    ('M1-5/R10', 141),
    ('M1-5/R7-2', 142),
    ('M1-5/R7-3', 143),
    ('M1-5/R7X', 144),
    ('M1-5/R8A', 145),
    ('M1-5/R9', 146),
    ('M1-5/R9-1', 147),
    ('M1-5A', 148),
    ('M1-5B', 149),
    ('M1-5M', 150),
    ('M1-6', 151),
    ('M1-6/R10', 152),
    ('M1-6/R8X', 153),
    ('M1-6/R9', 154),
    ('M1-6D', 155),
    ('M2-1', 156),
    ('M2-2', 157),
    ('M2-3', 158),
    ('M2-4', 159),
    ('M3-1', 160),
    ('M3-2', 161),
    ('BPC', 162),
    ('PARK', 163),
    ('PUBLIC PLACE', 164),
    ('PLAYGROUND', 165),
    ('BALL FIELD', 166)) AS __new("zonedist", "priority")
),
prioritized_parcel_zones AS MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 18
  WITH tied_zone_groups AS (
    SELECT
      id,
      zonedist, /* this is not summing by any sql grouping, but rather summing in a window function as the rows are iterated through */ /* output column ends up being a grouping of lot/zone pairings that are "tied" within some limit and should be reordered */ /*     based on ranking in zonedist_priority */
      row_number,
      SUM(group_start) OVER (PARTITION BY id ORDER BY row_number) AS reorder_group
    FROM initial_zone_coverage_rankings AS lotzoneperorder_init
  ), reorder_groups AS (
    SELECT
      id,
      reorder_group,
      MIN(row_number) - 1 AS order_start, /* starting point for re-ordering in "new_order" CTE down below */
      ARRAY_AGG(zonedist) AS zonedist
    FROM tied_zone_groups
    GROUP BY
      id,
      reorder_group
    HAVING
      COUNT(*) > 1 /* Filter to actual groups and not just individual rows */
  ), rows_to_reorder AS (
    SELECT
      id,
      reorder_group,
      order_start,
      UNNEST(zonedist) AS zonedist
    FROM reorder_groups
  ), priority_zone_order AS (
    SELECT
      g.id,
      g.zonedist,
      ROW_NUMBER() OVER (PARTITION BY id, reorder_group ORDER BY priority ASC) + g.order_start AS row_number
    FROM rows_to_reorder AS g
    INNER JOIN zoning_district_priorities AS zdp
      ON g.zonedist = zdp.zonedist
  )
  SELECT
    a.id,
    a.bbl,
    a.zonedist,
    segbblgeom,
    allbblgeom,
    perbblgeom,
    segzonegeom,
    allzonegeom,
    perzonegeom,
    COALESCE(new.row_number, a.row_number) AS row_number
  FROM initial_zone_coverage_rankings AS a
  LEFT JOIN priority_zone_order AS new
    ON a.id = new.id AND a.zonedist = new.zonedist
),
parcel_first_zoning_district AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 19
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(zonedist)
        ELSE "a"."zonedist1"
      END AS "zonedist1"
    )
  FROM {{ ref('parcel_geometry') }} AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM prioritized_parcel_zones AS b
    WHERE
      (
        row_number = 1
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_second_zoning_district AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 20
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(zonedist)
        ELSE "a"."zonedist2"
      END AS "zonedist2"
    )
  FROM parcel_first_zoning_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM prioritized_parcel_zones AS b
    WHERE
      (
        row_number = 2
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_third_zoning_district AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 21
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(zonedist)
        ELSE "a"."zonedist3"
      END AS "zonedist3"
    )
  FROM parcel_second_zoning_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM prioritized_parcel_zones AS b
    WHERE
      (
        row_number = 3
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_fourth_zoning_district AS MATERIALIZED (
  -- pluto_build/sql/zoning_zoningdistrict.sql statement 22
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(zonedist)
        ELSE "a"."zonedist4"
      END AS "zonedist4"
    )
  FROM parcel_third_zoning_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM prioritized_parcel_zones AS b
    WHERE
      (
        row_number = 4
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
ranked_commercial_overlays AS MATERIALIZED (
  -- pluto_build/sql/zoning_commercialoverlay.sql statement 2
  WITH parcel_overlay_coverage AS (
    SELECT
      p.id,
      p.bbl,
      n.overlay,
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
    FROM parcel_fourth_zoning_district AS p
    INNER JOIN ({{ pluto_input('stg__dcp_commercialoverlay') }}) AS n
      ON ST_INTERSECTS(p.geom, n.geom)
  ), grouped_overlay_coverage AS (
    SELECT
      id,
      bbl,
      overlay,
      SUM(segbblgeom) AS segbblgeom,
      SUM(segzonegeom) AS segzonegeom,
      SUM(segbblgeom / allbblgeom) * 100 AS perbblgeom,
      MAX(segzonegeom / allzonegeom) * 100 AS maxperzonegeom
    FROM parcel_overlay_coverage
    GROUP BY
      id,
      bbl,
      overlay
  )
  SELECT
    id,
    bbl,
    overlay,
    segbblgeom,
    perbblgeom,
    maxperzonegeom,
    ROW_NUMBER() OVER (
      PARTITION BY id
      ORDER BY segbblgeom DESC NULLS FIRST, segzonegeom DESC NULLS FIRST
    ) AS row_number
  FROM grouped_overlay_coverage
  WHERE
    perbblgeom >= 10 OR maxperzonegeom >= 50
),
parcel_first_commercial_overlay AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_commercialoverlay.sql statement 3
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(overlay)
        ELSE "a"."overlay1"
      END AS "overlay1"
    )
  FROM parcel_fourth_zoning_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_commercial_overlays AS b
    WHERE
      (
        row_number = 1
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_second_commercial_overlay AS MATERIALIZED (
  -- pluto_build/sql/zoning_commercialoverlay.sql statement 4
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(overlay)
        ELSE "a"."overlay2"
      END AS "overlay2"
    )
  FROM parcel_first_commercial_overlay AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_commercial_overlays AS b
    WHERE
      (
        row_number = 2
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_special_district_areas AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 2
  SELECT
    p.id,
    p.bbl,
    n.sdlbl,
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
  FROM parcel_second_commercial_overlay AS p
  INNER JOIN ({{ pluto_input('stg__dcp_specialpurpose') }}) AS n
    ON ST_INTERSECTS(p.geom, n.geom)
),
ranked_special_districts AS MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 4
  WITH initial_special_district_rankings AS (
    SELECT
      id,
      bbl,
      sdlbl,
      segbblgeom,
      (
        segbblgeom / allbblgeom
      ) * 100 AS perbblgeom,
      (
        segzonegeom / allzonegeom
      ) * 100 AS perzonegeom,
      ROW_NUMBER() OVER (
        PARTITION BY sdlbl
        ORDER BY (
          segbblgeom / allbblgeom
        ) * 100 < 10, segzonegeom DESC NULLS FIRST
      ) AS sd_row_number /* per sp district type, rank by */ /*   1) if lot meets 10% coverage by sp district threshold */ /*   2) area of coverage */ /* This is to get cases where special sp district may only be assigned to one lot. */ /* 1) is to cover edge case where largest section of specific large (but common) sp district that happens to have largest area on small fraction of huge lot */ /* See BBL 1013730001 in ZoLa - largest section of special district but should not be assigned spdist SRI */
    FROM parcel_special_district_areas AS specialpurposeper
  )
  SELECT
    id,
    bbl,
    sdlbl,
    segbblgeom,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST, sdlbl ASC) AS row_number
  FROM initial_special_district_rankings
  WHERE
    perbblgeom >= 10 OR sd_row_number = 1
),
parcel_first_special_district AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 5
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(sdlbl)
        ELSE "a"."spdist1"
      END AS "spdist1"
    )
  FROM parcel_second_commercial_overlay AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_special_districts AS b
    WHERE
      (
        row_number = 1
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_second_special_district AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 6
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(sdlbl)
        ELSE "a"."spdist2"
      END AS "spdist2"
    )
  FROM parcel_first_special_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_special_districts AS b
    WHERE
      (
        row_number = 2
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_third_special_district AS MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 7
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(sdlbl)
        ELSE "a"."spdist3"
      END AS "spdist3"
    )
  FROM parcel_second_special_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_special_districts AS b
    WHERE
      (
        row_number = 3
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
special_districts_cl_before_mid AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 8
  -- set the order of special districts
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'MiD' AND spdist2 = 'CL'
        THEN MOSES_TEXT('CL')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'MiD' AND spdist2 = 'CL'
        THEN MOSES_TEXT('MiD')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM parcel_third_special_district AS "pluto"
),
special_districts_mid_before_ta AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 9
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = 'MiD'
        THEN MOSES_TEXT('MiD')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = 'MiD'
        THEN MOSES_TEXT('TA')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_cl_before_mid AS "pluto"
),
special_districts_125th_before_ta AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 10
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = '125th'
        THEN MOSES_TEXT('125th')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = '125th'
        THEN MOSES_TEXT('TA')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_mid_before_ta AS "pluto"
),
special_districts_ec5_before_mx16 AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 11
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'MX-16' AND spdist2 = 'EC-5'
        THEN MOSES_TEXT('EC-5')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'MX-16' AND spdist2 = 'EC-5'
        THEN MOSES_TEXT('MX-16')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_125th_before_ta AS "pluto"
),
special_districts_ec6_before_mx16 AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 12
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'MX-16' AND spdist2 = 'EC-6'
        THEN MOSES_TEXT('EC-6')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'MX-16' AND spdist2 = 'EC-6'
        THEN MOSES_TEXT('MX-16')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_ec5_before_mx16 AS "pluto"
),
special_districts_ehc_before_ta AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 13
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = 'EHC'
        THEN MOSES_TEXT('EHC')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'TA' AND spdist2 = 'EHC'
        THEN MOSES_TEXT('TA')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_ec6_before_mx16 AS "pluto"
),
special_districts_mx1_before_g AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_specialdistrict.sql statement 14
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN spdist1 = 'G' AND spdist2 = 'MX-1'
        THEN MOSES_TEXT('MX-1')
        ELSE "pluto"."spdist1"
      END AS "spdist1",
      CASE
        WHEN spdist1 = 'G' AND spdist2 = 'MX-1'
        THEN MOSES_TEXT('G')
        ELSE "pluto"."spdist2"
      END AS "spdist2"
    )
  FROM special_districts_ehc_before_ta AS "pluto"
),
ranked_limited_height_districts AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_limitedheight.sql statement 2
  WITH parcel_limited_height_coverage AS (
    SELECT
      p.id,
      p.bbl,
      n.lhlbl,
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
    FROM special_districts_mx1_before_g AS p
    INNER JOIN ({{ pluto_input('stg__dcp_limitedheight') }}) AS n
      ON ST_INTERSECTS(p.geom, n.geom)
  )
  SELECT
    id,
    bbl,
    lhlbl,
    segbblgeom,
    (
      segbblgeom / allbblgeom
    ) * 100 AS perbblgeom,
    (
      segzonegeom / allzonegeom
    ) * 100 AS perzonegeom,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) AS row_number
  FROM parcel_limited_height_coverage
),
parcel_limited_height_district AS MATERIALIZED (
  -- pluto_build/sql/zoning_limitedheight.sql statement 3
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(lhlbl)
        ELSE "a"."ltdheight"
      END AS "ltdheight"
    )
  FROM special_districts_mx1_before_g AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_limited_height_districts AS b
    WHERE
      (
        perbblgeom >= 10
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
ranked_zoning_maps AS MATERIALIZED (
  -- pluto_build/sql/zoning_zonemap.sql statement 2
  WITH parcel_zoning_map_coverage AS (
    SELECT
      p.id,
      p.bbl,
      n.zoning_map,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(moses_makevalid(p.geom), n.geom)
          THEN p.geom
          ELSE ST_MULTI(ST_INTERSECTION(moses_makevalid(p.geom), n.geom))
        END
      ) AS segbblgeom,
      ST_AREA(p.geom) AS allbblgeom,
      ST_AREA(
        CASE
          WHEN ST_COVEREDBY(n.geom, moses_makevalid(p.geom))
          THEN n.geom
          ELSE ST_MULTI(ST_INTERSECTION(n.geom, moses_makevalid(p.geom)))
        END
      ) AS segzonegeom,
      ST_AREA(n.geom) AS allzonegeom
    FROM parcel_limited_height_district AS p
    INNER JOIN ({{ pluto_input('stg__dcp_zoningmapindex') }}) AS n
      ON ST_INTERSECTS(p.geom, n.geom)
  )
  SELECT
    id,
    bbl,
    zoning_map,
    segbblgeom,
    (
      segbblgeom / allbblgeom
    ) * 100 AS perbblgeom,
    (
      segzonegeom / allzonegeom
    ) * 100 AS perzonegeom,
    ROW_NUMBER() OVER (PARTITION BY id ORDER BY segbblgeom DESC NULLS FIRST) AS row_number
  FROM parcel_zoning_map_coverage
),
parcel_primary_zoning_map AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zonemap.sql statement 3
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(LOWER(zoning_map))
        ELSE "a"."zonemap"
      END AS "zonemap"
    )
  FROM parcel_limited_height_district AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_zoning_maps AS b
    WHERE
      (
        row_number = 1
      ) AND (
        perbblgeom >= 10
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
parcel_second_zoning_map AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_zonemap.sql statement 4
  -- set the zoningmapcode to Y where a lot is covered by a second zoning map
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT('Y')
        ELSE "a"."zmcode"
      END AS "zmcode"
    )
  FROM parcel_primary_zoning_map AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM ranked_zoning_maps AS b
    WHERE
      (
        row_number = 2
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.id) = 1
  ) AS "b"
    ON (
      a.id = b.id
    )
),
park_parcel_zoning_cleanup AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_parks.sql statement 1
  -- where zoningdistrict1 = 'PARK' NULL out all other zoning information
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."overlay1"
      END AS "overlay1",
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."overlay2"
      END AS "overlay2",
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."spdist1"
      END AS "spdist1",
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."spdist2"
      END AS "spdist2",
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."spdist3"
      END AS "spdist3",
      CASE
        WHEN zonedist1 = 'PARK' AND zonedist2 IS NULL
        THEN MOSES_TEXT(NULL)
        ELSE "a"."ltdheight"
      END AS "ltdheight"
    )
  FROM parcel_second_zoning_map AS "a"
),
split_zone_candidates AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_splitzone.sql statement 1
  -- calculate if tax lot is split by two or more zoning boundary lines and update splitzone
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN zonedist2 IS NOT NULL OR overlay2 IS NOT NULL OR spdist2 IS NOT NULL
        THEN MOSES_TEXT('Y')
        ELSE "pluto"."splitzone"
      END AS "splitzone"
    )
  FROM park_parcel_zoning_cleanup AS "pluto"
),
parcel_split_zone_flags AS NOT MATERIALIZED (
  -- pluto_build/sql/zoning_splitzone.sql statement 2
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN splitzone IS NULL AND zonedist1 IS NOT NULL
        THEN MOSES_TEXT('N')
        ELSE "pluto"."splitzone"
      END AS "splitzone"
    )
  FROM split_zone_candidates AS "pluto"
)
SELECT * FROM parcel_split_zone_flags
