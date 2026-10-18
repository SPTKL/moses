{{ config(materialized='table') }}
-- Business process: map_flags
WITH
plutomapid_assign_plutomapid AS NOT MATERIALIZED (
  -- pluto_build/sql/plutomapid.sql statement 1
  -- set the pluto map id based on the following criteria
  -- 1 In PLUTO Data File and DOF Modified DTM Tax Block and Lot
  -- Clipped to the Shoreline File.
  -- 2 In PLUTO Data File Only.
  -- 3 In DOF Modified DTM Tax Block and Lot Clipped to the
  -- Shoreline File but NOT in PLUTO.
  -- 4 In PLUTO Data File and in DOF Modified DTM File but NOT in
  -- DOF Modified DTM Tax Block and Lot Clipped to the Shoreline
  -- File, therefore tshe tax lot is totally under water.
  -- 5 In DOF Modified DTM but NOT in PLUTO, therefore the tax lot
  -- is totally under water.
  -- set the mappluto ID based on the critera above
  -- values can overwrite each other
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN geom IS NOT NULL AND plutomapid IS NULL
        THEN MOSES_TEXT('1')
        ELSE "pluto"."plutomapid"
      END AS "plutomapid"
    )
  FROM {{ ref('normalized_parcels') }} AS "pluto"
),
plutomapid_assign_plutomapid_2 AS NOT MATERIALIZED (
  -- pluto_build/sql/plutomapid.sql statement 2
  SELECT
    "pluto".*
    REPLACE (
      CASE
        WHEN geom IS NULL
        THEN MOSES_TEXT('2')
        ELSE "pluto"."plutomapid"
      END AS "plutomapid"
    )
  FROM plutomapid_assign_plutomapid AS "pluto"
),
plutomapid_1_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/plutomapid_1.sql statement 1
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.bbl IN (
          SELECT
          a.bbl
          FROM (
            SELECT
            a.bbl,
            MOSES_UNION_AGG(b.geom) AS geom
            FROM plutomapid_assign_plutomapid_2 AS a, {{ ref('shoreline_coverage') }} AS b
            WHERE
            a.plutomapid = '1'
            AND a.geom IS NOT NULL
            AND a.geom && moses_makevalid(b.geom)
            AND ST_INTERSECTS(a.geom, moses_makevalid(b.geom))
            GROUP BY
            a.bbl
          ) AS a
          INNER JOIN plutomapid_assign_plutomapid_2 AS pluto
          ON a.bbl = pluto.bbl
          WHERE
          ST_WITHIN(pluto.geom, a.geom)
        )
        THEN MOSES_TEXT('4')
        ELSE "a"."plutomapid"
      END AS "plutomapid"
    )
  FROM plutomapid_assign_plutomapid_2 AS "a"
),
plutomapid_2_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/plutomapid_2.sql statement 1
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN a.bbl IN (
          SELECT
          a.bbl
          FROM (
            SELECT
            a.bbl,
            MOSES_UNION_AGG(b.geom) AS geom
            FROM plutomapid_1_pluto AS a, {{ ref('shoreline_coverage') }} AS b
            WHERE
            a.plutomapid = '3'
            AND a.geom IS NOT NULL
            AND a.geom && moses_makevalid(b.geom)
            AND ST_INTERSECTS(a.geom, moses_makevalid(b.geom))
            GROUP BY
            a.bbl
          ) AS a
          INNER JOIN plutomapid_1_pluto AS pluto
          ON a.bbl = pluto.bbl
          WHERE
          ST_WITHIN(pluto.geom, a.geom)
        )
        THEN MOSES_TEXT('5')
        ELSE "a"."plutomapid"
      END AS "plutomapid"
    )
  FROM plutomapid_1_pluto AS "a"
)
SELECT * FROM plutomapid_2_pluto
