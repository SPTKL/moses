{% macro pluto_qaqc_mismatch(mapped, condo) %}
{% set fields = [
  [
    "borough",
    "COUNT(*) FILTER(WHERE\n      a.borough IS DISTINCT FROM b.borough)"
  ],
  [
    "block",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.block) IS DISTINCT FROM MOSES_TEXT(b.block))"
  ],
  [
    "lot",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.lot) IS DISTINCT FROM MOSES_TEXT(b.lot))"
  ],
  [
    "cd",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.cd) IS DISTINCT FROM MOSES_TEXT(b.cd))"
  ],
  [
    "ct2010",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.ct2010) IS DISTINCT FROM MOSES_TEXT(b.ct2010))"
  ],
  [
    "cb2010",
    "COUNT(*) FILTER(WHERE\n      a.cb2010 IS DISTINCT FROM b.cb2010)"
  ],
  [
    "schooldist",
    "COUNT(*) FILTER(WHERE\n      a.schooldist IS DISTINCT FROM b.schooldist)"
  ],
  [
    "council",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.council) IS DISTINCT FROM MOSES_TEXT(b.council))"
  ],
  [
    "zipcode",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.zipcode) IS DISTINCT FROM MOSES_TEXT(b.zipcode))"
  ],
  [
    "firecomp",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.firecomp) IS DISTINCT FROM MOSES_TEXT(b.firecomp))"
  ],
  [
    "policeprct",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.policeprct) IS DISTINCT FROM MOSES_TEXT(b.policeprct))"
  ],
  [
    "healtharea",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.healtharea) IS DISTINCT FROM MOSES_TEXT(b.healtharea))"
  ],
  [
    "sanitboro",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.sanitboro) IS DISTINCT FROM MOSES_TEXT(b.sanitboro))"
  ],
  [
    "sanitsub",
    "COUNT(*) FILTER(WHERE\n      MOSES_TEXT(a.sanitsub) IS DISTINCT FROM MOSES_TEXT(b.sanitsub))"
  ],
  [
    "address",
    "COUNT(*) FILTER(WHERE\n      TRIM(a.address) IS DISTINCT FROM TRIM(b.address))"
  ],
  [
    "zonedist1",
    "COUNT(*) FILTER(WHERE\n      a.zonedist1 IS DISTINCT FROM b.zonedist1)"
  ],
  [
    "zonedist2",
    "COUNT(*) FILTER(WHERE\n      a.zonedist2 IS DISTINCT FROM b.zonedist2)"
  ],
  [
    "zonedist3",
    "COUNT(*) FILTER(WHERE\n      a.zonedist3 IS DISTINCT FROM b.zonedist3)"
  ],
  [
    "zonedist4",
    "COUNT(*) FILTER(WHERE\n      a.zonedist4 IS DISTINCT FROM b.zonedist4)"
  ],
  [
    "overlay1",
    "COUNT(*) FILTER(WHERE\n      a.overlay1 IS DISTINCT FROM b.overlay1)"
  ],
  [
    "overlay2",
    "COUNT(*) FILTER(WHERE\n      a.overlay2 IS DISTINCT FROM b.overlay2)"
  ],
  [
    "spdist1",
    "COUNT(*) FILTER(WHERE\n      a.spdist1 IS DISTINCT FROM b.spdist1)"
  ],
  [
    "spdist2",
    "COUNT(*) FILTER(WHERE\n      a.spdist2 IS DISTINCT FROM b.spdist2)"
  ],
  [
    "spdist3",
    "COUNT(*) FILTER(WHERE\n      a.spdist3 IS DISTINCT FROM b.spdist3)"
  ],
  [
    "ltdheight",
    "COUNT(*) FILTER(WHERE\n      a.ltdheight IS DISTINCT FROM b.ltdheight)"
  ],
  [
    "splitzone",
    "COUNT(*) FILTER(WHERE\n      a.splitzone IS DISTINCT FROM b.splitzone)"
  ],
  [
    "bldgclass",
    "COUNT(*) FILTER(WHERE\n      a.bldgclass IS DISTINCT FROM b.bldgclass)"
  ],
  [
    "landuse",
    "COUNT(*) FILTER(WHERE\n      a.landuse IS DISTINCT FROM b.landuse)"
  ],
  [
    "easements",
    "COUNT(*) FILTER(WHERE\n      CAST(a.easements AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.easements AS DECIMAL(38, 12)))"
  ],
  [
    "ownertype",
    "COUNT(*) FILTER(WHERE\n      a.ownertype IS DISTINCT FROM b.ownertype)"
  ],
  [
    "ownername",
    "COUNT(*) FILTER(WHERE\n      a.ownername IS DISTINCT FROM b.ownername)"
  ],
  [
    "lotarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.lotarea AS DECIMAL(38, 12)) - CAST(b.lotarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.lotarea IS NULL\n        ) AS INT) + CAST((\n          b.lotarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "bldgarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.bldgarea AS DECIMAL(38, 12)) - CAST(b.bldgarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.bldgarea IS NULL\n        ) AS INT) + CAST((\n          b.bldgarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "comarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.comarea AS DECIMAL(38, 12)) - CAST(b.comarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.comarea IS NULL\n        ) AS INT) + CAST((\n          b.comarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "resarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.resarea AS DECIMAL(38, 12)) - CAST(b.resarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.resarea IS NULL\n        ) AS INT) + CAST((\n          b.resarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "officearea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.officearea AS DECIMAL(38, 12)) - CAST(b.officearea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.officearea IS NULL\n        ) AS INT) + CAST((\n          b.officearea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "retailarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.retailarea AS DECIMAL(38, 12)) - CAST(b.retailarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.retailarea IS NULL\n        ) AS INT) + CAST((\n          b.retailarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "garagearea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.garagearea AS DECIMAL(38, 12)) - CAST(b.garagearea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.garagearea IS NULL\n        ) AS INT) + CAST((\n          b.garagearea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "strgearea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.strgearea AS DECIMAL(38, 12)) - CAST(b.strgearea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.strgearea IS NULL\n        ) AS INT) + CAST((\n          b.strgearea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "factryarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.factryarea AS DECIMAL(38, 12)) - CAST(b.factryarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.factryarea IS NULL\n        ) AS INT) + CAST((\n          b.factryarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "otherarea",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.otherarea AS DECIMAL(38, 12)) - CAST(b.otherarea AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.otherarea IS NULL\n        ) AS INT) + CAST((\n          b.otherarea IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "areasource",
    "COUNT(*) FILTER(WHERE\n      a.areasource IS DISTINCT FROM b.areasource)"
  ],
  [
    "numbldgs",
    "COUNT(*) FILTER(WHERE\n      CAST(a.numbldgs AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.numbldgs AS DECIMAL(38, 12)))"
  ],
  [
    "numfloors",
    "COUNT(*) FILTER(WHERE\n      CAST(a.numfloors AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.numfloors AS DECIMAL(38, 12)))"
  ],
  [
    "unitsres",
    "COUNT(*) FILTER(WHERE\n      CAST(a.unitsres AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.unitsres AS DECIMAL(38, 12)))"
  ],
  [
    "unitstotal",
    "COUNT(*) FILTER(WHERE\n      CAST(a.unitstotal AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.unitstotal AS DECIMAL(38, 12)))"
  ],
  [
    "lotfront",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.lotfront AS DECIMAL(38, 12)) - CAST(b.lotfront AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.lotfront IS NULL\n        ) AS INT) + CAST((\n          b.lotfront IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "lotdepth",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.lotdepth AS DECIMAL(38, 12)) - CAST(b.lotdepth AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.lotdepth IS NULL\n        ) AS INT) + CAST((\n          b.lotdepth IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "bldgfront",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.bldgfront AS DECIMAL(38, 12)) - CAST(b.bldgfront AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.bldgfront IS NULL\n        ) AS INT) + CAST((\n          b.bldgfront IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "bldgdepth",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.bldgdepth AS DECIMAL(38, 12)) - CAST(b.bldgdepth AS DECIMAL(38, 12))) >= 5\n      OR (\n        CAST((\n          a.bldgdepth IS NULL\n        ) AS INT) + CAST((\n          b.bldgdepth IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "ext",
    "COUNT(*) FILTER(WHERE\n      a.ext IS DISTINCT FROM b.ext)"
  ],
  [
    "proxcode",
    "COUNT(*) FILTER(WHERE\n      a.proxcode IS DISTINCT FROM b.proxcode)"
  ],
  [
    "irrlotcode",
    "COUNT(*) FILTER(WHERE\n      a.irrlotcode IS DISTINCT FROM b.irrlotcode)"
  ],
  [
    "lottype",
    "COUNT(*) FILTER(WHERE\n      a.lottype IS DISTINCT FROM b.lottype)"
  ],
  [
    "bsmtcode",
    "COUNT(*) FILTER(WHERE\n      a.bsmtcode IS DISTINCT FROM b.bsmtcode)"
  ],
  [
    "assessland",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.assessland AS DECIMAL(38, 12)) - CAST(b.assessland AS DECIMAL(38, 12))) >= 10\n      OR (\n        CAST((\n          a.assessland IS NULL\n        ) AS INT) + CAST((\n          b.assessland IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "assesstot",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.assesstot AS DECIMAL(38, 12)) - CAST(b.assesstot AS DECIMAL(38, 12))) >= 10\n      OR (\n        CAST((\n          a.assesstot IS NULL\n        ) AS INT) + CAST((\n          b.assesstot IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "exempttot",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.exempttot AS DECIMAL(38, 12)) - CAST(b.exempttot AS DECIMAL(38, 12))) >= 10\n      OR (\n        CAST((\n          a.exempttot IS NULL\n        ) AS INT) + CAST((\n          b.exempttot IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "yearbuilt",
    "COUNT(*) FILTER(WHERE\n      CAST(a.yearbuilt AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.yearbuilt AS DECIMAL(38, 12)))"
  ],
  [
    "yearalter1",
    "COUNT(*) FILTER(WHERE\n      CAST(a.yearalter1 AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.yearalter1 AS DECIMAL(38, 12)))"
  ],
  [
    "yearalter2",
    "COUNT(*) FILTER(WHERE\n      CAST(a.yearalter2 AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.yearalter2 AS DECIMAL(38, 12)))"
  ],
  [
    "histdist",
    "COUNT(*) FILTER(WHERE\n      a.histdist IS DISTINCT FROM b.histdist)"
  ],
  [
    "landmark",
    "COUNT(*) FILTER(WHERE\n      a.landmark IS DISTINCT FROM b.landmark)"
  ],
  [
    "builtfar",
    "COUNT(*) FILTER(WHERE\n      CAST(a.builtfar AS DOUBLE) IS DISTINCT FROM CAST(b.builtfar AS DOUBLE))"
  ],
  [
    "residfar",
    "COUNT(*) FILTER(WHERE\n      CAST(a.residfar AS DOUBLE) IS DISTINCT FROM CAST(b.residfar AS DOUBLE))"
  ],
  [
    "commfar",
    "COUNT(*) FILTER(WHERE\n      CAST(a.commfar AS DOUBLE) IS DISTINCT FROM CAST(b.commfar AS DOUBLE))"
  ],
  [
    "facilfar",
    "COUNT(*) FILTER(WHERE\n      CAST(a.facilfar AS DOUBLE) IS DISTINCT FROM CAST(b.facilfar AS DOUBLE))"
  ],
  [
    "borocode",
    "COUNT(*) FILTER(WHERE\n      CAST(a.borocode AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.borocode AS DECIMAL(38, 12)))"
  ],
  [
    "bbl",
    "0"
  ],
  [
    "condono",
    "/* can't have bbl changes when we're joining on bbl. But included for backwards compatibility */\n    COUNT(*) FILTER(WHERE\n      CAST(a.condono AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.condono AS DECIMAL(38, 12)))"
  ],
  [
    "tract2010",
    "COUNT(*) FILTER(WHERE\n      a.tract2010 IS DISTINCT FROM b.tract2010)"
  ],
  [
    "xcoord",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.xcoord AS DECIMAL(38, 12)) - CAST(b.xcoord AS DECIMAL(38, 12))) >= 1\n      OR (\n        CAST((\n          a.xcoord IS NULL\n        ) AS INT) + CAST((\n          b.xcoord IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "ycoord",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.ycoord AS DECIMAL(38, 12)) - CAST(b.ycoord AS DECIMAL(38, 12))) >= 1\n      OR (\n        CAST((\n          a.ycoord IS NULL\n        ) AS INT) + CAST((\n          b.ycoord IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "latitude",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.latitude AS DECIMAL(38, 12)) - CAST(b.latitude AS DECIMAL(38, 12))) >= 0.0001\n      OR (\n        CAST((\n          a.latitude IS NULL\n        ) AS INT) + CAST((\n          b.latitude IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "longitude",
    "COUNT(*) FILTER(WHERE\n      ABS(CAST(a.longitude AS DECIMAL(38, 12)) - CAST(b.longitude AS DECIMAL(38, 12))) >= 0.0001\n      OR (\n        CAST((\n          a.longitude IS NULL\n        ) AS INT) + CAST((\n          b.longitude IS NULL\n        ) AS INT)\n      ) = 1)"
  ],
  [
    "zonemap",
    "COUNT(*) FILTER(WHERE\n      a.zonemap IS DISTINCT FROM b.zonemap)"
  ],
  [
    "zmcode",
    "COUNT(*) FILTER(WHERE\n      a.zmcode IS DISTINCT FROM b.zmcode)"
  ],
  [
    "sanborn",
    "COUNT(*) FILTER(WHERE\n      a.sanborn IS DISTINCT FROM b.sanborn)"
  ],
  [
    "taxmap",
    "COUNT(*) FILTER(WHERE\n      a.taxmap IS DISTINCT FROM b.taxmap)"
  ],
  [
    "edesignum",
    "COUNT(*) FILTER(WHERE\n      a.edesignum IS DISTINCT FROM b.edesignum)"
  ],
  [
    "appbbl",
    "COUNT(*) FILTER(WHERE\n      CAST(a.appbbl AS DOUBLE) IS DISTINCT FROM CAST(b.appbbl AS DOUBLE))"
  ],
  [
    "appdate",
    "COUNT(*) FILTER(WHERE\n      a.appdate IS DISTINCT FROM b.appdate)"
  ],
  [
    "plutomapid",
    "COUNT(*) FILTER(WHERE\n      a.plutomapid IS DISTINCT FROM b.plutomapid)"
  ],
  [
    "sanitdistrict",
    "COUNT(*) FILTER(WHERE\n      a.sanitdistrict IS DISTINCT FROM b.sanitdistrict)"
  ],
  [
    "healthcenterdistrict",
    "COUNT(*) FILTER(WHERE\n      CAST(a.healthcenterdistrict AS DECIMAL(38, 12)) IS DISTINCT FROM CAST(b.healthcenterdistrict AS DECIMAL(38, 12)))"
  ],
  [
    "firm07_flag",
    "COUNT(*) FILTER(WHERE\n      a.firm07_flag IS DISTINCT FROM b.firm07_flag)"
  ],
  [
    "pfirm15_flag",
    "COUNT(*) FILTER(WHERE\n      a.pfirm15_flag IS DISTINCT FROM b.pfirm15_flag)"
  ]
] %}

  SELECT
'{{ var("pluto_version") }}' || ' - ' || '{{ var("previous_pluto_version") }}' AS pair,
{{ 'TRUE' if condo else 'FALSE' }} AS condo,
{{ 'TRUE' if mapped else 'FALSE' }} AS mapped,
COUNT(*) AS total,
{% for field, expression in fields %}
{{ expression }} AS {{ field }}{% if not loop.last %},{% endif %}
{% endfor %}
FROM {{ ref('archive_pluto') }} AS a
  INNER JOIN ({{ pluto_input('previous_pluto') }}) AS b
    ON (
      CAST(CAST(a.bbl AS DOUBLE) AS BIGINT) = CAST(CAST(b.bbl AS DOUBLE) AS BIGINT)
    )

{% if mapped or condo %}
WHERE
{% if mapped %}a.geom IS NOT NULL{% endif %}
{% if mapped and condo %}AND{% endif %}
{% if condo %}RIGHT(MOSES_TEXT(CAST(a.bbl AS BIGINT)), 4) LIKE '75%%'{% endif %}
{% endif %}
{% endmacro %}
