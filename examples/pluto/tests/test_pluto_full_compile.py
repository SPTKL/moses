"""Cardinality, null writes and version references in immutable PLUTO models."""
import os
import re

import duckdb
import pytest
import sqlglot

from pluto_example.full_compile import SelectCompiler, ordered_steps, PINNED_COMMIT


@pytest.fixture
def compiler(tmp_path, monkeypatch):
    con = duckdb.connect()
    # Unit tests exercise the compiler without requiring the spatial extension.
    import pluto_example.full_compile as module
    numeric_macros=[s for s in module.compatibility_sql() if "MACRO moses_text" in s or "MACRO moses_census_tract_numeric_text" in s]
    monkeypatch.setattr(module, "compatibility_sql", lambda: numeric_macros)
    con.execute('CREATE TABLE source(bbl VARCHAR, val VARCHAR)')
    con.execute("INSERT INTO source VALUES ('1','old'),('2','retain'),('3',NULL)")
    con.execute('CREATE TABLE changes(bbl VARCHAR, val VARCHAR)')
    con.execute("INSERT INTO changes VALUES ('1',NULL),('1','duplicate'),('3','filled')")
    try:
        obj=SelectCompiler(con,tmp_path,{'pluto':'source','changes':'changes'})
        yield obj
    finally:
        con.close()


def execute_models(compiler):
    # Compiler placeholders carry schema only; execute SELECTs in model order.
    for row in compiler.models:
        text=(compiler.destination/'models'/(row['name']+'.sql')).read_text()
        text=re.sub(r'\{\{ config\([^\n]*\) \}\}', '', text)
        text=re.sub(r"\{\{ ref\('([^']+)'\) \}\}",r'\1',text)
        compiler.con.execute('DROP TABLE '+row['name'])
        compiler.con.execute('CREATE TABLE '+row['name']+' AS '+text)


def test_update_preserves_rows_and_null_assignment(compiler):
    compiler.statement(sqlglot.parse_one('UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl=c.bbl',read='postgres'),'test')
    execute_models(compiler)
    rows=compiler.con.execute('SELECT * FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()
    assert len(rows)==3
    assert rows[0][1] is None
    assert rows[1]==('2','retain')
    assert rows[2]==('3','filled')


def test_insert_delete_and_type_changes(compiler):
    statements='''CREATE TABLE result (id serial, bbl text, val text DEFAULT 'default');
    INSERT INTO result (bbl) SELECT bbl FROM pluto;
    UPDATE result SET val=NULL WHERE bbl='1';
    DELETE FROM result WHERE bbl='2';
    ALTER TABLE result RENAME COLUMN val TO value;'''
    for statement in sqlglot.parse(statements,read='postgres'):
        compiler.statement(statement,'test')
    execute_models(compiler)
    rows=compiler.con.execute('SELECT id,bbl,value FROM '+compiler.current['result']+' ORDER BY bbl').fetchall()
    assert rows==[(1,'1',None),(3,'3','default')]
    for row in compiler.models:
        text=(compiler.destination/'models'/(row['name']+'.sql')).read_text()
        assert not re.search(r'\b(UPDATE|INSERT|DELETE|ALTER|CREATE)\b',text.replace('-- test',''))


def test_pinned_commit():
    assert PINNED_COMMIT=='32bc98f632f15e7182933a17fb61ecf74e853518'


def test_spatial_render_preserves_crs_and_geography(compiler):
    rendered=compiler.render(sqlglot.parse_one('SELECT ST_Transform(ST_SetSRID(ST_MakePoint(1000000,200000),2263),4326), ST_Area(g::geography)',read='postgres'))
    assert '2263, 4326' in rendered
    assert 'ST_AREA_SPHEROID(ST_FLIPCOORDINATES(G))' in rendered.upper()
    subdivide=compiler.render(sqlglot.parse_one('SELECT ST_Subdivide(g)',read='postgres'))
    assert '256' in subdivide and 'UNNEST' in subdivide and '.geom' in subdivide


@pytest.mark.integration
def test_spatial_compatibility_matches_nyc_coordinates(tmp_path):
    from pathlib import Path
    from pyproj import Geod, Transformer
    from pluto_example.full_compile import compatibility_sql
    ext=Path(os.environ.get('MOSES_TEST_EXTENSIONS', Path(__file__).resolve().parents[1]/'.extensions'))
    con=duckdb.connect()
    try:
        con.execute('SET extension_directory='+repr(str(ext)))
        try:con.execute('LOAD spatial')
        except duckdb.Error:pytest.skip('Local spatial extension not installed')
        compiler=SelectCompiler(con,tmp_path,{})
        query=compiler.render(sqlglot.parse_one('SELECT ST_AsText(ST_Transform(ST_SetSRID(ST_MakePoint(1000000,200000),2263),4326))',read='postgres'))
        point=con.execute(query).fetchone()[0]
        from shapely import from_wkt
        actual=from_wkt(point)
        lon,lat=Transformer.from_crs(2263,4326,always_xy=True).transform(1000000,200000)
        assert actual.x==pytest.approx(lon,abs=1e-8)
        assert actual.y==pytest.approx(lat,abs=1e-8)
        wkt='POLYGON((-74 40.7,-73.999 40.7,-73.999 40.701,-74 40.701,-74 40.7))'
        query=compiler.render(sqlglot.parse_one("SELECT ST_Area(ST_GeomFromText('"+wkt+"')::geography)",read='postgres'))
        area=con.execute(query).fetchone()[0]
        expected=abs(Geod(ellps='WGS84').polygon_area_perimeter([-74,-73.999,-73.999,-74,-74],[40.7,40.7,40.701,40.701,40.7])[0])
        assert area==pytest.approx(expected,rel=1e-8)
        # GEOS collapses an invalid duplicate MultiPolygon to Polygon. PostGIS
        # restores MULTI for collection inputs, retaining zoning-filter matches.
        duplicate='MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)),((0 0,2 0,2 2,0 2,0 0)))'
        raw=con.execute("SELECT ST_GeometryType(ST_MakeValid(ST_GeomFromText(?)))::VARCHAR",[duplicate]).fetchone()[0]
        assert raw=='POLYGON'
        rendered=compiler.render(sqlglot.parse_one("SELECT ST_GeometryType(ST_MakeValid(ST_GeomFromText('"+duplicate+"')))",read='postgres'))
        assert con.execute(rendered).fetchone()[0]=='ST_MultiPolygon'
        assert con.execute("SELECT ST_Area(moses_makevalid(ST_GeomFromText(?)))",[duplicate]).fetchone()[0]==4
        for wkt in ('POLYGON EMPTY','MULTIPOLYGON EMPTY','GEOMETRYCOLLECTION EMPTY','GEOMETRYCOLLECTION(POINT(0 0),LINESTRING(0 0,1 1))'):
            assert con.execute('SELECT ST_Equals(moses_makevalid(ST_GeomFromText(?)),ST_MakeValid(ST_GeomFromText(?)))',[wkt,wkt]).fetchone()[0]
        assert con.execute('SELECT moses_makevalid(NULL::GEOMETRY)').fetchone()[0] is None
        assert con.execute("SELECT ST_GeometryType(moses_makevalid(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))')))::VARCHAR").fetchone()[0]=='POLYGON'
        empty=compiler.render(sqlglot.parse_one("SELECT ST_Subdivide(ST_GeomFromText('GEOMETRYCOLLECTION EMPTY')) AS geom",read='postgres'))
        assert con.execute(empty).fetchall()==[]
        assert con.execute("SELECT moses_geometrytype(ST_GeomFromText('MULTIPOLYGON(((0 0,1 0,1 1,0 0)))'))").fetchone()[0]=='ST_MultiPolygon'
    finally:con.close()


def test_numeric_precision_and_text_zero_branches(compiler):
    from decimal import Decimal
    query=compiler.render(sqlglot.parse_one("SELECT '1.12345678901'::numeric AS numfloors, '0.0000001'::numeric > 0 AS nonzero, '0'::numeric::text AS lotarea, '00005'::numeric::text AS condono, '005.20'::text AS original_text",read='postgres'))
    row=compiler.con.execute(query).fetchone()
    assert row==(Decimal('1.123456789010'),True,'0','5','005.20')
    # Lotarea zero checks and condo-number joins must remain textual matches.
    assert compiler.con.execute('SELECT moses_text(0.0::DOUBLE)=\'0\', moses_text(5::DECIMAL(38,12))=\'5\'').fetchone()==(True,True)


def test_varchar_cast_retains_postgres_width(compiler):
    query=compiler.render(sqlglot.parse_one("SELECT 'abcdef'::varchar(2)",read='postgres'))
    assert compiler.con.execute(query).fetchone()[0]=='ab'


def test_numeric_ratio_rounds_decimal_half_up(compiler):
    from decimal import Decimal
    query=compiler.render(sqlglot.parse_one("SELECT round('1005'::numeric / '1000'::numeric, 2) AS builtfar",read='postgres'))
    assert compiler.con.execute(query).fetchone()[0]==Decimal('1.01')


def test_maintained_project_is_portable_and_hashes_match():
    import hashlib
    import json
    from pathlib import Path
    import yaml
    from pluto_example import full_compile
    root=Path(full_compile.__file__).with_name('dbt_full')
    manifest=json.loads((root/'full_manifest.json').read_text())
    project=yaml.safe_load((root/'dbt_project.yml').read_text())
    assert manifest['source_commit']==PINNED_COMMIT
    assert project['vars']['pluto_version']=='26v2m4'
    assert project['vars']['previous_pluto_version']=='26v1'
    assert len(manifest['source_files'])==192
    assert manifest['model_count']==len(manifest['models'])==38
    assert manifest['qa_factoring_verification']['passed']==12
    for row in manifest['models']:
        path=root/row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    for name,digest in manifest['macro_hashes'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
    for path in root.rglob('*'):
        if path.is_file():
            content=path.read_text()
            assert '/tmp/' not in content and '/Users/' not in content
            assert 'previous_locked' not in content
    create=next((root/'models').rglob('parcel_base.sql')).read_text()
    assert '{{ var("pluto_version") }}' in create
    assert "source('pluto_inputs'" in (root/'macros'/'pluto_inputs.sql').read_text()
    assert not list((root/'models').rglob('input__*.sql'))


def test_equality_update_deduplicates_once(compiler):
    compiler.statement(sqlglot.parse_one('UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl=c.bbl',read='postgres'),'test')
    sql=(compiler.destination/'models'/(compiler.current['pluto']+'.sql')).read_text()
    assert 'LEFT JOIN' in sql and 'QUALIFY' in sql
    assert 'LATERAL' not in sql
    execute_models(compiler)
    assert compiler.con.execute('SELECT count(*) FROM '+compiler.current['pluto']).fetchone()[0]==3


def test_copy_input_empty_null_policy_and_strict_date_guards(compiler):
    compiler.con.execute('DELETE FROM source')
    compiler.con.execute("INSERT INTO source VALUES ('1',''),('2',NULL),('3','12/20/86'),('4','not-a-date'),('5',' ')")
    compiler.emit('pluto',"SELECT * REPLACE (NULLIF(val,'') AS val) FROM pluto",'input_copy/pluto.sql',model_name='input__pluto')
    compiler.statement(sqlglot.parse_one("UPDATE pluto SET val=to_char(to_date(val,'MM/DD/YY'),'MM/DD/YYYY') WHERE val IS NOT NULL AND bbl IN ('1','2','3')",read='postgres'),'test')
    assert compiler.current['pluto'].startswith('__m_0000_')
    execute_models(compiler)
    rows=compiler.con.execute('SELECT * FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()
    assert rows==[('1',None),('2',None),('3','12/20/1986'),('4','not-a-date'),('5',' ')]


def test_null_safe_join_and_separate_source_target_filters(compiler):
    statement=sqlglot.parse_one("UPDATE pluto p SET val=c.bbl FROM changes c WHERE p.val IS NOT DISTINCT FROM c.val AND c.bbl='1' AND p.bbl='3'",read='postgres')
    compiler.statement(statement,'test')
    execute_models(compiler)
    assert compiler.con.execute('SELECT * FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()==[('1','old'),('2','retain'),('3','1')]


def test_target_guard_uses_hash_join_and_keeps_false_unknown_rows(compiler):
    compiler.con.execute("INSERT INTO source VALUES (NULL,NULL)")
    compiler.con.execute("INSERT INTO changes VALUES (NULL,'null-key')")
    statement=sqlglot.parse_one("UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl IS NOT DISTINCT FROM c.bbl AND p.bbl <> '2'",read='postgres')
    compiler.statement(statement,'test')
    text=(compiler.destination/'models'/(compiler.current['pluto']+'.sql')).read_text()
    text=re.sub(r'\{\{ config\([^\n]*\) \}\}','',text)
    plan=compiler.con.execute('EXPLAIN '+text).fetchone()[1]
    assert 'HASH_JOIN' in plan and 'BLOCKWISE_NL_JOIN' not in plan
    execute_models(compiler)
    rows=compiler.con.execute('SELECT * FROM '+compiler.current['pluto']+' ORDER BY bbl NULLS LAST').fetchall()
    assert rows==[('1',None),('2','retain'),('3','filled'),(None,None)]


def test_geocode_style_guard_is_a_hashable_independent_key(compiler):
    compiler.con.execute('ALTER TABLE source ADD COLUMN lot VARCHAR')
    compiler.con.execute("UPDATE source SET lot=CASE bbl WHEN '1' THEN '0001' WHEN '2' THEN '7501' END")
    compiler.statement(sqlglot.parse_one("UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl=c.bbl AND p.lot NOT LIKE '75%'",read='postgres'),'test')
    text=(compiler.destination/'models'/(compiler.current['pluto']+'.sql')).read_text()
    text=re.sub(r'\{\{ config\([^\n]*\) \}\}','',text)
    plan=compiler.con.execute('EXPLAIN '+text).fetchone()[1]
    assert 'HASH_JOIN' in plan and 'BLOCKWISE_NL_JOIN' not in plan
    execute_models(compiler)
    assert compiler.con.execute('SELECT * FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()==[('1',None,'0001'),('2','retain','7501'),('3',None,None)]


def test_chained_numeric_multiplication_resets_scale(compiler):
    from decimal import Decimal
    cases=[("40", "21", "4", Decimal('3360')), ("10.125", "20.25", "2.5", Decimal('512.578125')), ("-40", "21", "4", Decimal('-3360'))]
    for x,y,z,expected in cases:
        query=compiler.render(sqlglot.parse_one(f"SELECT '{x}'::numeric * '{y}'::numeric * '{z}'::numeric",read='postgres'))
        assert compiler.con.execute(query).fetchone()[0]==expected
    query=compiler.render(sqlglot.parse_one('SELECT 40::numeric * NULL::numeric * 4::numeric',read='postgres'))
    assert compiler.con.execute(query).fetchone()[0] is None
    query=compiler.render(sqlglot.parse_one('SELECT typeof(40 * 21 * 4)',read='postgres'))
    assert compiler.con.execute(query).fetchone()[0]=='INTEGER'


def test_seed_inference_restores_grouped_numbers_and_text_codes(compiler, monkeypatch):
    from decimal import Decimal
    import pluto_example.full_compile as module
    content={
        'seeds/_seeds.yml': 'seeds:\n  - name: example\n    config:\n      column_types:\n        code: text\n',
        'seeds/example.csv': 'code,area,description\n001,"40,395", keep \n002,"19,174",null\n003,,NULL\n004,12.125, \n',
    }
    monkeypatch.setattr(module,'read_pinned',lambda repository,path:content[path])
    assert module.seed_column_types('fixture')=={'example':{'code':'Text','area':'Number','description':'Text'}}
    compiler.con.execute('CREATE TABLE seed(code VARCHAR, area VARCHAR, description VARCHAR)')
    compiler.con.execute("INSERT INTO seed VALUES ('001','40,395',' keep '),('002','19,174','null'),('003',NULL,'NULL'),('004','12.125',' ')")
    fields=[module.seed_input_expression(c,k)+' AS '+module.quote(c) for c,k in module.seed_column_types('fixture')['example'].items()]
    rows=compiler.con.execute('SELECT '+','.join(fields)+' FROM seed ORDER BY code').fetchall()
    assert rows==[('001',Decimal('40395'),' keep '),('002',Decimal('19174'),None),('003',None,None),('004',Decimal('12.125'),None)]


def test_spatial_fallback_materializes_small_matched_patch(compiler):
    compiler.con.execute('ALTER TABLE source ADD COLUMN id BIGINT')
    compiler.con.execute('UPDATE source SET id=CAST(bbl AS BIGINT)')
    compiler.serials['pluto']=['id']  # The pinned CREATE/INSERT serial lineage.
    statement=sqlglot.parse_one('UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl=c.bbl OR p.val=c.val',read='postgres')
    compiler.statement(statement,'pluto_build/sql/spatialjoins.sql statement 3')
    assert [row['name'] for row in compiler.models]==['check__pluto_spatial_ids','patch__0000_spatialjoins','__m_0000_spatialjoins__pluto']
    assert compiler.models[1]['materialized']=='table'
    execute_models(compiler)
    assert [row[0] for row in compiler.con.execute('DESCRIBE patch__0000_spatialjoins').fetchall()]==['id','__matched','val']
    rows=compiler.con.execute('SELECT bbl,val,id FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()
    assert rows==[('1',None,1),('2','retain',2),('3','filled',3)]


@pytest.mark.parametrize('ids',[(1,1,3),(1,None,3)])
def test_spatial_patch_rejects_duplicate_or_null_serial_ids(compiler,ids):
    compiler.con.execute('ALTER TABLE source ADD COLUMN id BIGINT')
    for bbl,value in enumerate(ids,1):
        compiler.con.execute('UPDATE source SET id=? WHERE bbl=?',[value,str(bbl)])
    compiler.serials['pluto']=['id']
    compiler.statement(sqlglot.parse_one('UPDATE pluto p SET val=c.val FROM changes c WHERE p.bbl=c.bbl OR p.val=c.val',read='postgres'),'pluto_build/sql/spatialjoins.sql statement 3')
    with pytest.raises(duckdb.InvalidInputException,match='unique non-null serial ids'):
        execute_models(compiler)


def test_census_numeric_text_preserves_nonzero_suffix_scale(compiler):
    compiler.con.execute('ALTER TABLE source ADD COLUMN ct2010 VARCHAR')
    compiler.con.execute("UPDATE source SET ct2010=CASE bbl WHEN '1' THEN '0170.10' WHEN '2' THEN '0170' ELSE '0170.01' END")
    statement=sqlglot.parse_one("UPDATE pluto a SET ct2010=a.ct2010::numeric WHERE a.ct2010 ~ '[0-9]'",read='postgres')
    compiler.statement(statement,'pluto_build/sql/numericfields_geomfields.sql statement 3')
    execute_models(compiler)
    assert compiler.con.execute('SELECT ct2010 FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall()==[('170.10',),('170',),('170.01',)]


def test_replacement_formatter_preserves_tokens_and_array_indices(compiler):
    from pluto_example.full_compile import format_replacements
    from sqlglot.dialects.duckdb import DuckDB
    query = "SELECT * REPLACE(/* keep CASE ( ) */ CASE WHEN n IS NOT NULL THEN array[10,20][1] ELSE 0 END AS n, CASE WHEN n=1 THEN 'CASE' ELSE '(' END AS label) FROM example"
    formatted = format_replacements(query)
    signature = lambda sql: [(token.token_type, token.text) for token in DuckDB.Tokenizer().tokenize(sql)]
    assert signature(query) == signature(formatted)
    assert '[1]' in formatted
    assert "THEN 'CASE'" in formatted and "ELSE '('" in formatted
    assert '\n    WHEN' in formatted and '\n  CASE' in formatted
    assert '/* keep CASE ( ) */' in formatted
    assert format_replacements(formatted) == formatted
    rendered = compiler.render(sqlglot.parse_one('SELECT ARRAY[10,20][1] AS first_item', read='postgres'))
    assert compiler.con.execute(rendered).fetchone()[0] == 10


@pytest.mark.integration
@pytest.mark.parametrize('inputs,expected',[([],None),([None,None],None),([None,'GEOMETRYCOLLECTION EMPTY'],'GEOMETRYCOLLECTION EMPTY'),([None,'POINT(1 2)'],'POINT (1 2)')])
def test_union_aggregate_preserves_sql_null_and_explicit_empty(tmp_path,inputs,expected):
    from pathlib import Path
    con=duckdb.connect()
    try:
        con.execute('SET extension_directory='+repr(str(Path(os.environ.get('MOSES_TEST_EXTENSIONS', Path(__file__).resolve().parents[1]/'.extensions')))))
        try:con.execute('LOAD spatial')
        except duckdb.Error:pytest.skip('Local spatial extension not installed')
        obj=SelectCompiler(con,tmp_path,{})
        con.execute('CREATE TABLE features(g GEOMETRY)')
        for value in inputs:con.execute('INSERT INTO features VALUES(ST_GeomFromText(?))',[value])
        query=obj.render(sqlglot.parse_one('SELECT ST_AsText(ST_Union(g)) FROM features',read='postgres'))
        assert con.execute(query).fetchone()[0]==expected
        binary=obj.render(sqlglot.parse_one("SELECT ST_Union(ST_Point(1,2),ST_Point(3,4))",read='postgres'))
        assert 'moses_union_agg' not in binary.lower()
    finally:con.close()


def test_process_projection_fusion_preserves_arrays_and_rejects_dependencies():
    from pluto_example.full_process import fuse_projection_pair
    first="SELECT a.* REPLACE(CAST(a.x+1 AS DECIMAL(38,12)) AS x) FROM {{ ref('base') }} AS a"
    second="SELECT b.* REPLACE(ARRAY[10,20][1] AS y) FROM {{ ref('first') }} AS b"
    fused=fuse_projection_pair(first,second)
    assert fused is not None and "{{ ref('base') }}" in fused
    con=duckdb.connect()
    try:
        con.execute('CREATE TABLE base(x DECIMAL(38,12),y INTEGER)')
        con.execute('INSERT INTO base VALUES(1,0),(NULL,9)')
        actual=con.execute(fused.replace("{{ ref('base') }}",'base')).fetchall()
        assert actual==[(2,10),(None,10)]
    finally:con.close()
    dependent="SELECT b.* REPLACE(CASE WHEN b.x>0 THEN 5 ELSE b.y END AS y) FROM {{ ref('first') }} AS b"
    assert fuse_projection_pair(first,dependent) is None
    assert fuse_projection_pair(first,dependent.replace('b.x','x')) is None
    assert fuse_projection_pair(first,second.replace('ARRAY[10,20][1]','random()')) is None
    assert fuse_projection_pair(first,second.replace('AS y','AS x')) is None
    assert fuse_projection_pair(first,second+' ORDER BY b.x') is None
    assert fuse_projection_pair(first,second.replace('ARRAY[10,20][1]','ROW_NUMBER() OVER ()')) is None


def test_process_graph_rejects_cycles_and_dangling_edges():
    from pluto_example.full_process import validate_process_graph
    validate_process_graph([{'name':'base','depends_on':[]},{'name':'final','depends_on':['base']}])
    with pytest.raises(ValueError,match='Dangling'):
        validate_process_graph([{'name':'final','depends_on':['missing']}])
    with pytest.raises(ValueError,match='Cycle'):
        validate_process_graph([{'name':'a','depends_on':['b']},{'name':'b','depends_on':['a']}])


def test_spatial_process_uses_stable_base_and_rejects_cross_field_reads():
    from pluto_example.full_process import spatial_process_queries
    rows={};queries={}
    for offset in range(5):
        name=f'patch__{196+offset:04d}_spatialjoins'
        rows[name]={'name':name}
        queries[name]=f"SELECT a.id,TRUE AS __matched,a.field{offset} AS field{offset} FROM {{{{ ref('__m_{195+offset:04d}_spatialjoins__pluto') }}}} a"
    queries['check__pluto_spatial_ids']='SELECT TRUE AS valid'
    result=spatial_process_queries('political_geography','__m_0200_spatialjoins__pluto',rows,queries)
    for name in rows:
        assert "ref('__m_0195_spatialjoins__pluto')" in result[name]
    assert result['__m_0200_spatialjoins__pluto'].count('LEFT JOIN')==5
    assert 'required_ids.valid' in result['__m_0200_spatialjoins__pluto']
    queries['patch__0197_spatialjoins']=queries['patch__0197_spatialjoins'].replace('a.field1','a.field0')
    with pytest.raises(ValueError,match='earlier changed field'):
        spatial_process_queries('political_geography','__m_0200_spatialjoins__pluto',rows,queries)


def test_factored_qa_variants_preserve_results_types_and_tokens():
    from jinja2 import Environment
    from pluto_example.full_process import mismatch_diagnostic, outlier_diagnostic, verify_diagnostic_variants
    con=duckdb.connect()
    con.execute('CREATE TABLE current_rows(bbl VARCHAR, geom INTEGER, value INTEGER)')
    con.execute("INSERT INTO current_rows VALUES ('10007501',1,NULL),('10000001',NULL,2),('20007501',NULL,3),('20000001',1,4)")
    con.execute('CREATE TABLE previous_rows AS SELECT bbl,10 AS value FROM current_rows')
    try:
        for family in ('qaqc_mismatch','qaqc_null','qaqc_outlier'):
            rows={};queries={}
            for mapped,condo in ((True,True),(True,False),(False,True),(False,False)):
                suffix=str(mapped).lower()+'_'+str(condo).lower();name=family+'_'+suffix
                predicates=(['a.geom IS NOT NULL'] if mapped else [])+(["RIGHT(a.bbl,4) LIKE '75%' "] if condo else [])
                where=' WHERE '+' AND '.join(predicates) if predicates else ''
                if family=='qaqc_outlier':
                    query=f"(WITH pluto_filtered AS (SELECT * FROM {{{{ ref('current') }}}} a{where}), building_area_increase AS (SELECT count(*) AS n FROM pluto_filtered) SELECT 'candidate' AS v,{str(condo)} AS condo,{str(mapped)} AS mapped,to_json(list(n)) AS outlier FROM building_area_increase)"
                else:
                    expression='COUNT(*) FILTER(WHERE a.value!=b.value)' if family=='qaqc_mismatch' else 'SUM(CASE WHEN a.value IS NULL AND b.value IS NOT NULL THEN 1 ELSE 0 END)'
                    query=f"(SELECT 'candidate - previous' AS pair,{str(condo)} AS condo,{str(mapped)} AS mapped,COUNT(*) AS total,{expression} AS value FROM {{{{ ref('current') }}}} a JOIN {{{{ ref('previous') }}}} b ON a.bbl=b.bbl{where})"
                query=query.replace(str(condo)+' AS condo',str(condo).upper()+' AS condo').replace(str(mapped)+' AS mapped',str(mapped).upper()+' AS mapped')
                rows[name]={'name':name,'relation':name};queries[name]=query
            external={'current':'current_rows','previous':'previous_rows'}
            generator=outlier_diagnostic if family=='qaqc_outlier' else mismatch_diagnostic
            args=() if family=='qaqc_outlier' else (family,)
            _,macro=generator(rows,queries,external,{},*args)
            assert len(verify_diagnostic_variants(family,rows,queries,macro,external,{}))==4
            environment=Environment();environment.globals['ref']=lambda name:name
            for name,query in queries.items():
                mapped,condo=(value=='true' for value in name.removeprefix(family+'_').split('_'))
                original=environment.from_string(query).render(ref=lambda name:external[name])
                rendered=environment.from_string(macro+'{{ pluto_'+family+'(mapped,condo) }}').render(mapped=mapped,condo=condo)
                expected=con.execute(original);schema=expected.description;values=expected.fetchall()
                actual=con.execute(rendered)
                assert actual.description==schema and actual.fetchall()==values
    finally:con.close()


@pytest.mark.parametrize('family', ['cama', 'zipcode'])
def test_scoped_canonical_matching_is_permutation_invariant(compiler, family):
    compiler.con.execute('DELETE FROM changes')
    compiler.con.execute('ALTER TABLE changes ADD COLUMN bldgnum VARCHAR')
    compiler.con.execute('ALTER TABLE changes ADD COLUMN ogc_fid INTEGER')
    compiler.con.execute('ALTER TABLE source ADD COLUMN zipcode VARCHAR')
    compiler.con.execute("UPDATE source SET zipcode='retain'")
    options=[('1','zeta','1',7),('1','alpha','1',7),('3',None,'1',9)]
    origin='pluto_build/sql/cama_bldgarea_2.sql statement 1' if family=='cama' else 'pluto_build/sql/spatialjoins.sql statement 16'
    column='val' if family=='cama' else 'zipcode'
    predicate='p.bbl=c.bbl' if family=='cama' else 'contains(c.bbl,p.bbl)'
    statement=sqlglot.parse_one(f'UPDATE pluto p SET {column}=c.val FROM changes c WHERE {predicate}',read='postgres')
    outputs=[]
    for rows in (options,list(reversed(options)),[options[1],options[2],options[0]]):
        compiler.con.execute('DELETE FROM changes')
        compiler.con.executemany('INSERT INTO changes VALUES (?,?,?,?)',rows)
        compiler.current['pluto']='source'
        compiler.statement(statement,origin)
        model=compiler.models[-1]
        assert model['match_selection']['canonical']
        text=(compiler.destination/'models'/(model['name']+'.sql')).read_text()
        assert 'ORDER BY' in text and 'NULLS LAST' in text
        execute_models(compiler)
        outputs.append(compiler.con.execute('SELECT bbl,'+column+' FROM '+compiler.current['pluto']+' ORDER BY bbl').fetchall())
    assert outputs[0]==outputs[1]==outputs[2]==[('1','alpha'),('2','retain' if family=='zipcode' else 'retain'),('3',None)]


def test_canonical_geometry_order_uses_payload_and_explicit_nulls():
    from pluto_example.full_compile import SelectCompiler
    order,columns=SelectCompiler.canonical_match_order('b',[('geom','GEOMETRY'),('value','VARCHAR'),('bbl','VARCHAR')],('bbl','bldgnum'))
    assert columns==['bbl','geom','value']
    assert 'hex(ST_AsWKB("b"."geom")) ASC NULLS LAST' in order
    assert order.count('NULLS LAST')==3


def test_review_comment_cleanup_preserves_tokens_and_business_explanation():
    from pluto_example.full_process import _body
    original="-- Source: pinned.sql statement 1\n-- Allocate billing lots.\n-- DROP TABLE old;\n-- CREATE TABLE old AS (\n-- SELECT discarded FROM source\n-- );\nSELECT 'CREATE TABLE remains text' AS value"
    cleaned=_body(original)
    assert 'Allocate billing lots.' in cleaned and "'CREATE TABLE remains text'" in cleaned
    assert '-- Source:' not in cleaned and 'discarded' not in cleaned
