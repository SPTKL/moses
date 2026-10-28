{{ config(materialized='view') }}
-- Business process: qaqc_mismatch
{{ pluto_qaqc_mismatch(true, true) }}
UNION ALL
{{ pluto_qaqc_mismatch(true, false) }}
UNION ALL
{{ pluto_qaqc_mismatch(false, true) }}
UNION ALL
{{ pluto_qaqc_mismatch(false, false) }}
