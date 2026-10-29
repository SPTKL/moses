{{ config(materialized='table') }}
-- Business process: political_geography
WITH
spatialjoins_assign_ycoord AS NOT MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 2
  /* if a lot did not get assigned service areas through Geosupport assign service areas spatially */
  /* DROP INDEX dcp_censusblocks_gix; */
  /* CREATE INDEX dcp_censusblocks_gix ON dcp_censusblocks USING GIST (geom); */
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN NOT REGEXP_MATCHES(a.xcoord, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."xcoord"
      END AS "xcoord",
      CASE
        WHEN NOT REGEXP_MATCHES("a".ycoord, '[0-9]')
        THEN MOSES_TEXT(NULL)
        ELSE "a"."ycoord"
      END AS "ycoord"
    )
  FROM {{ ref('flood') }} AS "a"
),
spatialjoins_require_unique_parcel_ids AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 3
  SELECT CASE WHEN COUNT(*)=COUNT(id) AND COUNT(*)=COUNT(DISTINCT id) THEN TRUE ELSE error('PLUTO spatial update requires unique non-null serial ids') END AS valid FROM spatialjoins_assign_ycoord
),
spatialjoins_match_cd AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 3
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."cd") AS "cd"
  FROM spatialjoins_assign_ycoord AS "a"
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS __guard
  INNER JOIN LATERAL (
    SELECT
      b.borocd AS "cd"
    FROM ({{ pluto_input('stg__dcp_cdboundaries_wi') }}) AS b
    WHERE
      ST_WITHIN(a.centroid, b.geom) AND a.cd IS NULL AND a.xcoord IS NOT NULL
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
spatialjoins_match_ct2010_tract2010 AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 4
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."ct2010") AS "ct2010",
    MOSES_TEXT(__patch."tract2010") AS "tract2010"
  FROM spatialjoins_assign_ycoord AS "a"
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS __guard
  INNER JOIN LATERAL (
    SELECT
      LEFT(b.ct2010, 4) || '.' || RIGHT(b.ct2010, 2) AS "ct2010",
      LEFT(b.ct2010, 4) || '.' || RIGHT(b.ct2010, 2) AS "tract2010"
    FROM ({{ pluto_input('stg__dcp_ct2010_wi') }}) AS b
    WHERE
      a.geom && b.geom
      AND ST_WITHIN(a.centroid, b.geom)
      AND (
        a.ct2010 IS NULL OR CAST(a.ct2010 AS DECIMAL(38, 12)) = 0
      )
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
spatialjoins_match_cb2010 AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 5
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."cb2010") AS "cb2010"
  FROM spatialjoins_assign_ycoord AS "a"
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS __guard
  INNER JOIN LATERAL (
    SELECT
      COALESCE(a.cb2010, b.cb2010) AS "cb2010"
    FROM ({{ pluto_input('stg__dcp_cb2010_wi') }}) AS b
    WHERE
      a.geom && b.geom AND ST_WITHIN(a.centroid, b.geom)
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
spatialjoins_match_bct2020 AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 6
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."bct2020") AS "bct2020"
  FROM spatialjoins_assign_ycoord AS "a"
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS __guard
  INNER JOIN LATERAL (
    SELECT
      COALESCE(a.bct2020, b.boroct2020) AS "bct2020"
    FROM ({{ pluto_input('stg__dcp_ct2020_wi') }}) AS b
    WHERE
      a.geom && b.geom AND ST_WITHIN(a.centroid, b.geom)
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
spatialjoins_match_bctcb2020 AS MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 7
  SELECT
    "a".id,
    TRUE AS __matched,
    MOSES_TEXT(__patch."bctcb2020") AS "bctcb2020"
  FROM spatialjoins_assign_ycoord AS "a"
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS __guard
  INNER JOIN LATERAL (
    SELECT
      COALESCE(a.bctcb2020, b.bctcb2020) AS "bctcb2020"
    FROM ({{ pluto_input('stg__dcp_cb2020_wi') }}) AS b
    WHERE
      a.geom && b.geom AND ST_WITHIN(a.centroid, b.geom)
    LIMIT 1
  ) AS __patch
    ON TRUE
  WHERE
    __guard.valid
),
spatialjoins_pluto AS NOT MATERIALIZED (
  -- pluto_build/sql/spatialjoins.sql statement 7
  SELECT p.* REPLACE (
    CASE
      WHEN matched_cd.__matched
      THEN matched_cd."cd"
      ELSE p."cd"
    END AS "cd",
    CASE
      WHEN matched_ct2010_tract2010.__matched
      THEN matched_ct2010_tract2010."ct2010"
      ELSE p."ct2010"
    END AS "ct2010",
    CASE
      WHEN matched_ct2010_tract2010.__matched
      THEN matched_ct2010_tract2010."tract2010"
      ELSE p."tract2010"
    END AS "tract2010",
    CASE
      WHEN matched_cb2010.__matched
      THEN matched_cb2010."cb2010"
      ELSE p."cb2010"
    END AS "cb2010",
    CASE
      WHEN matched_bct2020.__matched
      THEN matched_bct2020."bct2020"
      ELSE p."bct2020"
    END AS "bct2020",
    CASE
      WHEN matched_bctcb2020.__matched
      THEN matched_bctcb2020."bctcb2020"
      ELSE p."bctcb2020"
    END AS "bctcb2020"
  ) FROM spatialjoins_assign_ycoord AS p
  LEFT JOIN spatialjoins_match_cd AS matched_cd ON p.id=matched_cd.id
  LEFT JOIN spatialjoins_match_ct2010_tract2010 AS matched_ct2010_tract2010 ON p.id=matched_ct2010_tract2010.id
  LEFT JOIN spatialjoins_match_cb2010 AS matched_cb2010 ON p.id=matched_cb2010.id
  LEFT JOIN spatialjoins_match_bct2020 AS matched_bct2020 ON p.id=matched_bct2020.id
  LEFT JOIN spatialjoins_match_bctcb2020 AS matched_bctcb2020 ON p.id=matched_bctcb2020.id
  CROSS JOIN spatialjoins_require_unique_parcel_ids AS required_ids WHERE required_ids.valid
)
SELECT * FROM spatialjoins_pluto
