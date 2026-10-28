{% macro define_st_setsrid() %}
CREATE OR REPLACE MACRO ST_SetSRID(g, srid) AS g
{% endmacro %}

{% macro define_moses_text() %}
CREATE OR REPLACE MACRO moses_text(g) AS CASE WHEN typeof(g) IN ('DOUBLE','FLOAT','REAL') OR starts_with(typeof(g),'DECIMAL') THEN regexp_replace(regexp_replace(CAST(g AS VARCHAR), '(\.[0-9]*?)0+$', '\1'), '\.$', '') ELSE CAST(g AS VARCHAR) END
{% endmacro %}

{% macro define_moses_subdivide() %}
CREATE OR REPLACE MACRO moses_subdivide(g, maxvertices) AS ST_Collect(list_transform(ST_Dump(g), part -> ST_Subdivide(part.geom, maxvertices)))
{% endmacro %}

{% macro define_moses_transform_crs() %}
CREATE OR REPLACE MACRO moses_transform_crs(g, source_srid, target_srid) AS ST_Transform(g, 'EPSG:' || CAST(source_srid AS VARCHAR), 'EPSG:' || CAST(target_srid AS VARCHAR), always_xy := true)
{% endmacro %}

{% macro define_moses_geometrytype() %}
CREATE OR REPLACE MACRO moses_geometrytype(g) AS CASE CAST(ST_GeometryType(g) AS VARCHAR) WHEN 'POLYGON' THEN 'ST_Polygon' WHEN 'MULTIPOLYGON' THEN 'ST_MultiPolygon' WHEN 'POINT' THEN 'ST_Point' WHEN 'MULTIPOINT' THEN 'ST_MultiPoint' WHEN 'LINESTRING' THEN 'ST_LineString' WHEN 'MULTILINESTRING' THEN 'ST_MultiLineString' WHEN 'GEOMETRYCOLLECTION' THEN 'ST_GeometryCollection' END
{% endmacro %}

{% macro define_moses_makevalid() %}
CREATE OR REPLACE MACRO moses_makevalid(g) AS CASE WHEN CAST(ST_GeometryType(g) AS VARCHAR) IN ('MULTIPOINT','MULTILINESTRING','MULTIPOLYGON','GEOMETRYCOLLECTION') THEN ST_Multi(ST_MakeValid(g)) ELSE ST_MakeValid(g) END
{% endmacro %}

{% macro define_moses_census_tract_numeric_text() %}
CREATE OR REPLACE MACRO moses_census_tract_numeric_text(g) AS CASE WHEN contains(g, '.') THEN CAST(CAST(g AS DECIMAL(38,2)) AS VARCHAR) ELSE CAST(CAST(g AS DECIMAL(38,0)) AS VARCHAR) END
{% endmacro %}

{% macro define_moses_union_agg() %}
CREATE OR REPLACE MACRO moses_union_agg(g) AS CASE WHEN COUNT(g)=0 THEN NULL::GEOMETRY ELSE ST_Union_Agg(g) END
{% endmacro %}
