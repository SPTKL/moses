{{ config(materialized='view', alias='qaqc_null') }}
-- Business process: qa_attribute_null_counts
{{ pluto_qaqc_null(true, true) }}
UNION ALL
{{ pluto_qaqc_null(true, false) }}
UNION ALL
{{ pluto_qaqc_null(false, true) }}
UNION ALL
{{ pluto_qaqc_null(false, false) }}
