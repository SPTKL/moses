{{ config(materialized='table') }}
-- Business process: pluto_removed_records
-- Corrected full rows, captured before each removal.
WITH classified AS (
{{ classified_corrected_lots(ref('map_flags'), ref('correction_decisions')) }}
)
SELECT * EXCLUDE (__removal_phase) FROM classified WHERE __removal_phase IS NOT NULL
