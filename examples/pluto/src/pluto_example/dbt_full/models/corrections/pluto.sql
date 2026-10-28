{{ config(materialized='table') }}
-- Business process: pluto
-- Final corrected lots after both ordered unit-lot removals.
WITH corrected AS (
{{ corrected_lot_rows(ref('map_flags'), ref('correction_decisions')) }}
)
-- The first DELETE uses its predicate; the final DELETE uses BBLs
-- from the removed-record table, rather than just target serial ids.
SELECT a.* FROM corrected AS a
WHERE NOT COALESCE((CAST(lot AS DECIMAL(38,12)) >= 1000
  AND lot NOT LIKE '75%' AND CAST(unitstotal AS DECIMAL(38,12)) > 1
  AND geom IS NULL), FALSE)
AND NOT EXISTS (SELECT 1 FROM {{ ref('pluto_removed_records') }} AS r WHERE r.bbl = a.bbl)
