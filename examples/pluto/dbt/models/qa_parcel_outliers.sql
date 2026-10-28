{{ config(materialized='view', alias='qaqc_outlier') }}
-- Business process: qa_parcel_outliers
{{ pluto_qaqc_outlier(true, true) }}
UNION ALL
{{ pluto_qaqc_outlier(true, false) }}
UNION ALL
{{ pluto_qaqc_outlier(false, true) }}
UNION ALL
{{ pluto_qaqc_outlier(false, false) }}
