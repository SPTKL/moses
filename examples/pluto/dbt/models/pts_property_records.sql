{{ config(materialized='table') }}
-- Business process: pts_property_records
WITH
property_records_base AS NOT MATERIALIZED (
  -- pluto_build/sql/primebbl.sql statement 2
  SELECT
    *,
    MOSES_TEXT(NULL) AS "primebbl"
  FROM ({{ pluto_input('pts_properties_base') }}) AS dof_pts_propmaster
),
condo_property_prime_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/primebbl.sql statement 5
  -- assign the prime BBL to each PTS record
  -- assign prime bbl for condo records
  SELECT
    "a".*
    REPLACE (
      CASE
        WHEN "b".__matched
        THEN MOSES_TEXT(b.billingbbl)
        ELSE "a"."primebbl"
      END AS "primebbl"
    )
  FROM property_records_base AS "a"
  LEFT JOIN (
    SELECT
      "b".*,
      TRUE AS __matched
    FROM {{ ref('geocode_attributes') }} AS b
    WHERE
      (
        b.billingbbl IS NOT NULL
      ) AND (
        billingbbl <> '0000000000'
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY b.borough || LPAD(b.block, 5, '0') || LPAD(b.lot, 4, '0')) = 1
  ) AS "b"
    ON (
      a.boro || a.tb || a.tl = b.borough || LPAD(b.block, 5, '0') || LPAD(b.lot, 4, '0')
    )
),
property_prime_bbls AS NOT MATERIALIZED (
  -- pluto_build/sql/primebbl.sql statement 6
  -- assign prime bbl for noncondo lots
  SELECT
    "dof_pts_propmaster".*
    REPLACE (
      CASE
        WHEN primebbl IS NULL
        THEN MOSES_TEXT(boro || tb || tl)
        ELSE "dof_pts_propmaster"."primebbl"
      END AS "primebbl"
    )
  FROM condo_property_prime_bbls AS "dof_pts_propmaster"
)
SELECT * FROM property_prime_bbls
