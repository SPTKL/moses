{{ config(materialized='table') }}
-- Business process: pluto_removed_records
-- Corrected full rows, captured before each removal.
WITH lots_classified_for_removal AS (
{{ classified_corrected_lots(ref('parcel_mapping_flags'), ref('correction_decisions')) }}
)
SELECT * EXCLUDE (__removal_phase) FROM lots_classified_for_removal WHERE __removal_phase IS NOT NULL
