{{ config(materialized='view') }}
-- Business process: qaqc_null
{{ pluto_qaqc_null(true, true) }}
UNION ALL
{{ pluto_qaqc_null(true, false) }}
UNION ALL
{{ pluto_qaqc_null(false, true) }}
UNION ALL
{{ pluto_qaqc_null(false, false) }}
