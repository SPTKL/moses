{% macro pluto_qaqc_outlier(mapped, condo) %}
(
  WITH selected_current_parcels AS (
    SELECT
      *
    FROM {{ ref('archive_pluto') }} AS a

{% if mapped or condo %}
WHERE
{% if mapped %}a.geom IS NOT NULL{% endif %}
{% if mapped and condo %}AND{% endif %}
{% if condo %}RIGHT(MOSES_TEXT(CAST(a.bbl AS BIGINT)), 4) LIKE '75%%'{% endif %}
{% endif %}
), building_area_increase /* building area has more than doubled in size */ AS (
    SELECT
      TO_JSON(
        LIST(
          JSON_OBJECT(
            'pair',
            '{{ var("pluto_version") }}' || ' - ' || '{{ var("previous_pluto_version") }}',
            'bbl',
            current.bbl,
            'building_area_current',
            CAST(current.bldgarea AS DOUBLE),
            'building_area_previous',
            CAST(prev.bldgarea AS DOUBLE),
            'percent_change',
            (
              CAST(current.bldgarea AS DOUBLE) - CAST(prev.bldgarea AS DOUBLE)
            ) / CAST(prev.bldgarea AS DOUBLE) * 100
          )
        )
      ) AS values,
      'building_area_increase' AS field
    FROM selected_current_parcels AS current
    INNER JOIN ({{ pluto_input('previous_pluto') }}) AS prev
      ON CAST(current.bbl AS DOUBLE) = CAST(prev.bbl AS DOUBLE)
    WHERE
      CAST(current.bldgarea AS DOUBLE) > 2 * CAST(prev.bldgarea AS DOUBLE)
      AND CAST(prev.bldgarea AS DOUBLE) <> 0
  ), small_apartments /* unreasonably small apartments based on area/unit ratio */ AS (
    SELECT
      TO_JSON(
        LIST(
          JSON_OBJECT(
            'bbl',
            bbl,
            'ownername',
            ownername,
            'unitsres',
            unitsres,
            'resarea',
            resarea,
            'res_unit_ratio',
            CAST(resarea AS DOUBLE) / CAST(unitsres AS DOUBLE)
          )
        )
      ) AS values,
      'unitsres_resarea' AS field
    FROM selected_current_parcels
    WHERE
      CAST(unitsres AS DOUBLE) > 50
      AND CAST(resarea AS DOUBLE) / CAST(unitsres AS DOUBLE) < 300
      AND CAST(resarea AS DOUBLE) <> 0
  ), floor_area_outliers /* building area over lot area is more than double the number of floors */ AS (
    SELECT
      TO_JSON(
        LIST(
          JSON_OBJECT(
            'bbl',
            current.bbl,
            'bldgarea',
            current.bldgarea,
            'lotarea',
            current.lotarea,
            'numfloors',
            current.numfloors,
            'blog_lot_ratio',
            CAST(current.bldgarea AS DOUBLE) / CAST(current.lotarea AS DOUBLE),
            'new_flag',
            prev.bbl IS NULL
          )
        )
      ) AS values,
      'lotarea_numfloor' AS field
    FROM selected_current_parcels AS current
    LEFT JOIN ({{ pluto_input('previous_pluto') }}) AS prev
      ON CAST(current.bbl AS DOUBLE) = CAST(prev.bbl AS DOUBLE)
      AND CAST(prev.lotarea AS DOUBLE) <> 0
      AND CAST(prev.numfloors AS DOUBLE) <> 0
      AND CAST(prev.bldgarea AS DOUBLE) / CAST(prev.lotarea AS DOUBLE) > CAST(prev.numfloors AS DOUBLE) * 2
    WHERE
      CAST(current.bldgarea AS DOUBLE) / CAST(current.lotarea AS DOUBLE) > CAST(current.numfloors AS DOUBLE) * 2
      AND CAST(current.lotarea AS DOUBLE) <> 0
      AND current.numfloors <> 0
  ), combined_outlier_checks AS (
    SELECT
      *
    FROM building_area_increase
    UNION ALL
    SELECT
      *
    FROM small_apartments
    UNION ALL
    SELECT
      *
    FROM floor_area_outliers
  )
  SELECT
    '{{ var("pluto_version") }}' AS v,
    {{ 'TRUE' if condo else 'FALSE' }} AS condo,
    {{ 'TRUE' if mapped else 'FALSE' }} AS mapped,
    TO_JSON(LIST(combined_outlier_checks)) AS outlier
  FROM combined_outlier_checks
)
{% endmacro %}
