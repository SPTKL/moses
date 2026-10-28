{{ config(materialized='view', alias='qaqc_mismatch') }}
-- Business process: qa_attribute_mismatches
{{ pluto_qaqc_mismatch(true, true) }}
UNION ALL
{{ pluto_qaqc_mismatch(true, false) }}
UNION ALL
{{ pluto_qaqc_mismatch(false, true) }}
UNION ALL
{{ pluto_qaqc_mismatch(false, false) }}
