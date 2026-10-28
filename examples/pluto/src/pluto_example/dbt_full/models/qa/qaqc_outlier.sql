{{ config(materialized='view') }}
-- Business process: qaqc_outlier
{{ pluto_qaqc_outlier(true, true) }}
UNION ALL
{{ pluto_qaqc_outlier(true, false) }}
UNION ALL
{{ pluto_qaqc_outlier(false, true) }}
UNION ALL
{{ pluto_qaqc_outlier(false, false) }}
