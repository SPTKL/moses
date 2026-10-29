{{ config(materialized='table') }}
-- Business process: pluto_changes_applied
-- Preserve every upstream applied INSERT event, including lots later removed.
-- Audit DISTINCT excludes internal target ids and found values.
SELECT "bbl", "field", "old_value", "new_value", "Type", "reason", "version" FROM (SELECT DISTINCT phase, "bbl", "field", "old_value", "new_value", "Type", "reason", "version" FROM {{ ref('correction_decisions') }} WHERE audit_status = 'applied') AS audit_events
