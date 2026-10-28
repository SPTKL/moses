{{ config(materialized='table') }}
-- Business process: tax_lot_geometry
WITH
source_tax_lot_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 2
  SELECT
    *
  FROM ({{ pluto_input('stg__dof_dtm') }}) AS stg__dof_dtm
),
tax_lots_with_empty_prime_bbl AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 3
  SELECT
    *,
    MOSES_TEXT(NULL) AS "primebbl"
  FROM source_tax_lot_polygons AS pluto_dtm
),
raw_condo_mappings AS NOT MATERIALIZED (
  -- pluto_build/sql/dedupecondotable.sql statement 2
  SELECT
    *
  FROM ({{ pluto_input('dof_condo') }}) AS dof_condo
),
numbered_condo_mappings AS MATERIALIZED (
  -- pluto_build/sql/dedupecondotable.sql statement 3
  SELECT
    *,
    ROW_NUMBER() OVER () AS "id"
  FROM raw_condo_mappings AS pluto_condo
),
deduplicated_condo_mappings AS MATERIALIZED (
  -- pluto_build/sql/dedupecondotable.sql statement 4
  -- remove duplicate records
  SELECT
    *
  FROM numbered_condo_mappings AS "pluto_condo"
  WHERE
    NOT COALESCE(
      (
        id IN (
          SELECT
            id
          FROM (
            SELECT
              id,
              ROW_NUMBER() OVER (
                PARTITION BY condo_base_bbl, condo_billing_bbl
                ORDER BY condo_base_bbl, condo_billing_bbl
              ) AS row_num
            FROM numbered_condo_mappings AS pluto_condo
          ) AS t
          WHERE
            t.row_num > 1
        )
      ),
      FALSE
    )
),
condo_mappings_without_null_billing_duplicates AS MATERIALIZED (
  -- pluto_build/sql/dedupecondotable.sql statement 5
  -- remove duplicate records where billing bbl is NULL
  SELECT
    *
  FROM deduplicated_condo_mappings AS "pluto_condo"
  WHERE
    NOT COALESCE(
      (
        id IN (
          SELECT
            id
          FROM (
            SELECT
              id,
              ROW_NUMBER() OVER (PARTITION BY condo_base_bbl ORDER BY condo_base_bbl) AS row_num
            FROM deduplicated_condo_mappings AS pluto_condo
          ) AS t
          WHERE
            t.row_num > 1
        )
        AND condo_billing_bbl IS NULL
      ),
      FALSE
    )
),
deduplicated_billing_mappings AS NOT MATERIALIZED (
  -- pluto_build/sql/dedupecondotable.sql statement 6
  -- remove duplicate records where base bbl is the same but billing bbl is different
  SELECT
    *
  FROM condo_mappings_without_null_billing_duplicates AS "pluto_condo"
  WHERE
    NOT COALESCE(
      (
        id IN (
          SELECT
            id
          FROM (
            SELECT
              id,
              ROW_NUMBER() OVER (PARTITION BY condo_base_bbl ORDER BY condo_billing_bbl) AS row_num
            FROM condo_mappings_without_null_billing_duplicates AS pluto_condo
            WHERE
              condo_billing_bbl IS NOT NULL
          ) AS t
          WHERE
            t.row_num > 1
        )
      ),
      FALSE
    )
),
tax_lots_with_condo_prime_bbl AS MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 4
  -- Set the prime bbl as the billing bbl for condo lots
  -- using the pluto condo table
  SELECT
    "pluto_dtm".*
    REPLACE (
      CASE
        WHEN "pluto_condo".__matched
        THEN MOSES_TEXT(condo_billing_bbl)
        ELSE "pluto_dtm"."primebbl"
      END AS "primebbl"
    )
  FROM tax_lots_with_empty_prime_bbl AS "pluto_dtm"
  LEFT JOIN (
    SELECT
      "pluto_condo".*,
      TRUE AS __matched
    FROM deduplicated_billing_mappings AS pluto_condo
    WHERE
      (
        condo_billing_bbl IS NOT NULL
      )
    QUALIFY
      ROW_NUMBER() OVER (PARTITION BY condo_base_bbl) = 1
  ) AS "pluto_condo"
    ON (
      bbl = condo_base_bbl
    )
),
merged_condo_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 6
  SELECT
    primebbl,
    MOSES_UNION_AGG(geom) AS geom
  FROM tax_lots_with_condo_prime_bbl AS pluto_dtm
  WHERE
    primebbl IS NOT NULL
  GROUP BY
    primebbl
),
merged_noncondo_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 8
  SELECT
    bbl,
    MOSES_UNION_AGG(moses_makevalid(geom)) AS geom
  FROM tax_lots_with_condo_prime_bbl AS pluto_dtm
  WHERE
    bbl IS NOT NULL
    AND primebbl IS NULL /* AND st_isvalidreason(geom) <> 'IllegalArgumentException: Invalid number of points in LinearRing found 3 - must be 0 or >= 4' */
  GROUP BY
    bbl
),
unified_tax_lot_polygons AS NOT MATERIALIZED (
  -- pluto_build/sql/dtmmergepolygons.sql statement 10
  SELECT
    primebbl AS bbl,
    'Y' AS condo,
    geom
  FROM merged_condo_polygons AS pluto_dtm_condosmerged
  UNION ALL
  SELECT
    bbl,
    NULL AS condo,
    geom
  FROM merged_noncondo_polygons AS pluto_dtm_noncondosmerged
)
SELECT * FROM unified_tax_lot_polygons
