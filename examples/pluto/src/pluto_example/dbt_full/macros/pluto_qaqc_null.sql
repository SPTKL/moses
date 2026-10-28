{% macro pluto_qaqc_null(mapped, condo) %}
{% set fields = [
  [
    "borough",
    "SUM(CASE WHEN a.borough IS NULL AND b.borough IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "block",
    "SUM(CASE WHEN a.block IS NULL AND b.block IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "lot",
    "SUM(CASE WHEN a.lot IS NULL AND b.lot IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "cd",
    "SUM(CASE WHEN a.cd IS NULL AND b.cd IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ct2010",
    "SUM(CASE WHEN a.ct2010 IS NULL AND b.ct2010 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "cb2010",
    "SUM(CASE WHEN a.cb2010 IS NULL AND b.cb2010 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "schooldist",
    "SUM(CASE WHEN a.schooldist IS NULL AND b.schooldist IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "council",
    "SUM(CASE WHEN a.council IS NULL AND b.council IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zipcode",
    "SUM(CASE WHEN a.zipcode IS NULL AND b.zipcode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "firecomp",
    "SUM(CASE WHEN a.firecomp IS NULL AND b.firecomp IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "policeprct",
    "SUM(CASE WHEN a.policeprct IS NULL AND b.policeprct IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "healtharea",
    "SUM(CASE WHEN a.healtharea IS NULL AND b.healtharea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "sanitboro",
    "SUM(CASE WHEN a.sanitboro IS NULL AND b.sanitboro IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "sanitsub",
    "SUM(CASE WHEN a.sanitsub IS NULL AND b.sanitsub IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "address",
    "SUM(CASE WHEN a.address IS NULL AND b.address IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zonedist1",
    "SUM(CASE WHEN a.zonedist1 IS NULL AND b.zonedist1 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zonedist2",
    "SUM(CASE WHEN a.zonedist2 IS NULL AND b.zonedist2 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zonedist3",
    "SUM(CASE WHEN a.zonedist3 IS NULL AND b.zonedist3 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zonedist4",
    "SUM(CASE WHEN a.zonedist4 IS NULL AND b.zonedist4 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "overlay1",
    "SUM(CASE WHEN a.overlay1 IS NULL AND b.overlay1 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "overlay2",
    "SUM(CASE WHEN a.overlay2 IS NULL AND b.overlay2 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "spdist1",
    "SUM(CASE WHEN a.spdist1 IS NULL AND b.spdist1 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "spdist2",
    "SUM(CASE WHEN a.spdist2 IS NULL AND b.spdist2 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "spdist3",
    "SUM(CASE WHEN a.spdist3 IS NULL AND b.spdist3 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ltdheight",
    "SUM(CASE WHEN a.ltdheight IS NULL AND b.ltdheight IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "splitzone",
    "SUM(CASE WHEN a.splitzone IS NULL AND b.splitzone IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bldgclass",
    "SUM(CASE WHEN a.bldgclass IS NULL AND b.bldgclass IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "landuse",
    "SUM(CASE WHEN a.landuse IS NULL AND b.landuse IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "easements",
    "SUM(CASE WHEN a.easements IS NULL AND b.easements IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ownertype",
    "SUM(CASE WHEN a.ownertype IS NULL AND b.ownertype IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ownername",
    "SUM(CASE WHEN a.ownername IS NULL AND b.ownername IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "lotarea",
    "SUM(CASE WHEN a.lotarea IS NULL AND b.lotarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bldgarea",
    "SUM(CASE WHEN a.bldgarea IS NULL AND b.bldgarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "comarea",
    "SUM(CASE WHEN a.comarea IS NULL AND b.comarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "resarea",
    "SUM(CASE WHEN a.resarea IS NULL AND b.resarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "officearea",
    "SUM(CASE WHEN a.officearea IS NULL AND b.officearea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "retailarea",
    "SUM(CASE WHEN a.retailarea IS NULL AND b.retailarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "garagearea",
    "SUM(CASE WHEN a.garagearea IS NULL AND b.garagearea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "strgearea",
    "SUM(CASE WHEN a.strgearea IS NULL AND b.strgearea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "factryarea",
    "SUM(CASE WHEN a.factryarea IS NULL AND b.factryarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "otherarea",
    "SUM(CASE WHEN a.otherarea IS NULL AND b.otherarea IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "areasource",
    "SUM(CASE WHEN a.areasource IS NULL AND b.areasource IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "numbldgs",
    "SUM(CASE WHEN a.numbldgs IS NULL AND b.numbldgs IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "numfloors",
    "SUM(CASE WHEN a.numfloors IS NULL AND b.numfloors IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "unitsres",
    "SUM(CASE WHEN a.unitsres IS NULL AND b.unitsres IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "unitstotal",
    "SUM(CASE WHEN a.unitstotal IS NULL AND b.unitstotal IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "lotfront",
    "SUM(CASE WHEN a.lotfront IS NULL AND b.lotfront IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "lotdepth",
    "SUM(CASE WHEN a.lotdepth IS NULL AND b.lotdepth IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bldgfront",
    "SUM(CASE WHEN a.bldgfront IS NULL AND b.bldgfront IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bldgdepth",
    "SUM(CASE WHEN a.bldgdepth IS NULL AND b.bldgdepth IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ext",
    "SUM(CASE WHEN a.ext IS NULL AND b.ext IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "proxcode",
    "SUM(CASE WHEN a.proxcode IS NULL AND b.proxcode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "irrlotcode",
    "SUM(CASE WHEN a.irrlotcode IS NULL AND b.irrlotcode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "lottype",
    "SUM(CASE WHEN a.lottype IS NULL AND b.lottype IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bsmtcode",
    "SUM(CASE WHEN a.bsmtcode IS NULL AND b.bsmtcode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "assessland",
    "SUM(CASE WHEN a.assessland IS NULL AND b.assessland IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "assesstot",
    "SUM(CASE WHEN a.assesstot IS NULL AND b.assesstot IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "exempttot",
    "SUM(CASE WHEN a.exempttot IS NULL AND b.exempttot IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "yearbuilt",
    "SUM(CASE WHEN a.yearbuilt IS NULL AND b.yearbuilt IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "yearalter1",
    "SUM(CASE WHEN a.yearalter1 IS NULL AND b.yearalter1 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "yearalter2",
    "SUM(CASE WHEN a.yearalter2 IS NULL AND b.yearalter2 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "histdist",
    "SUM(CASE WHEN a.histdist IS NULL AND b.histdist IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "landmark",
    "SUM(CASE WHEN a.landmark IS NULL AND b.landmark IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "builtfar",
    "SUM(CASE WHEN a.builtfar IS NULL AND b.builtfar IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "residfar",
    "SUM(CASE WHEN a.residfar IS NULL AND b.residfar IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "commfar",
    "SUM(CASE WHEN a.commfar IS NULL AND b.commfar IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "facilfar",
    "SUM(CASE WHEN a.facilfar IS NULL AND b.facilfar IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "borocode",
    "SUM(CASE WHEN a.borocode IS NULL AND b.borocode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "bbl",
    "SUM(CASE WHEN a.bbl IS NULL AND b.bbl IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "condono",
    "SUM(CASE WHEN a.condono IS NULL AND b.condono IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "tract2010",
    "SUM(CASE WHEN a.tract2010 IS NULL AND b.tract2010 IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "xcoord",
    "SUM(CASE WHEN a.xcoord IS NULL AND b.xcoord IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "ycoord",
    "SUM(CASE WHEN a.ycoord IS NULL AND b.ycoord IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "longitude",
    "SUM(CASE WHEN a.longitude IS NULL AND b.longitude IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "latitude",
    "SUM(CASE WHEN a.latitude IS NULL AND b.latitude IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zonemap",
    "SUM(CASE WHEN a.zonemap IS NULL AND b.zonemap IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "zmcode",
    "SUM(CASE WHEN a.zmcode IS NULL AND b.zmcode IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "sanborn",
    "SUM(CASE WHEN a.sanborn IS NULL AND b.sanborn IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "taxmap",
    "SUM(CASE WHEN a.taxmap IS NULL AND b.taxmap IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "edesignum",
    "SUM(CASE WHEN a.edesignum IS NULL AND b.edesignum IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "appbbl",
    "SUM(CASE WHEN a.appbbl IS NULL AND b.appbbl IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "appdate",
    "SUM(CASE WHEN a.appdate IS NULL AND b.appdate IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "plutomapid",
    "SUM(CASE WHEN a.plutomapid IS NULL AND b.plutomapid IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "version",
    "SUM(CASE WHEN a.version IS NULL AND b.version IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "sanitdistrict",
    "SUM(\n      CASE WHEN a.sanitdistrict IS NULL AND b.sanitdistrict IS NOT NULL THEN 1 ELSE 0 END\n    )"
  ],
  [
    "healthcenterdistrict",
    "SUM(\n      CASE\n        WHEN a.healthcenterdistrict IS NULL AND b.healthcenterdistrict IS NOT NULL\n        THEN 1\n        ELSE 0\n      END\n    )"
  ],
  [
    "firm07_flag",
    "SUM(CASE WHEN a.firm07_flag IS NULL AND b.firm07_flag IS NOT NULL THEN 1 ELSE 0 END)"
  ],
  [
    "pfirm15_flag",
    "SUM(\n      CASE WHEN a.pfirm15_flag IS NULL AND b.pfirm15_flag IS NOT NULL THEN 1 ELSE 0 END\n    )"
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
