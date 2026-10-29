{{ config(materialized='table') }}
-- Business process: pluto_changes_not_applied
-- Only specific research mismatches were recorded upstream.
SELECT "bbl", "field", "old_value", "new_value", "Type", "reason", "version", found_value FROM (SELECT DISTINCT phase, "bbl", "field", "old_value", "new_value", "Type", "reason", "version", found_value FROM {{ ref('correction_decisions') }} WHERE audit_status = 'not_applied') AS audit_events
