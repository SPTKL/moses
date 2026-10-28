"""Preparation publishes typed source tables independently of product dbt."""
import os
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import duckdb
import pytest
import yaml

from pluto_example.prepared import PreparedError, _hash, _json_hash, _load, _normalization_query, prepare_collection


@pytest.fixture
def captured(tmp_path):
    extension=Path(os.environ.get('MOSES_TEST_EXTENSIONS', Path(__file__).resolve().parents[1]/'.extensions'))
    con=duckdb.connect();con.execute('SET extension_directory=?',[str(extension)])
    try:con.execute('LOAD spatial')
    except duckdb.Error:
        con.close();pytest.skip('Installed Spatial extension required')
    con.close()
    manifests={};inputs=[];versions={}
    for name,role in (('alpha','prepared_input'),('empty','prepared_input'),('kept','retained_source')):
        parquet=tmp_path/(name+'.parquet');parquet.write_bytes(b'bounded-fixture-catalog-capture')
        version='locked-'+name;versions[name]=version
        manifests[name]={'version':version,'content_sha256':hashlib.sha256(name.encode()).hexdigest(),'row_count':3 if name=='alpha' else 0,'parquet_path':str(parquet)}
        inputs.append({'name':name,'source':{'kind':'catalog','dataset':name,'version':'input_lock'},'role':role,'columns':{}})
    inputs[0]['columns']={'number':{'type':'decimal_38_12','numeric_grouping':True},'text':{'nulls':'trimmed_empty_or_null'},'exact':{'nulls':'empty'}}
    recipe={'schema_version':1,'kind':'source_collection','provider':'nyc_pluto_26v2','name':'fixture','release':'26v2','previous_release':'26v1','source_commit':'32bc98f632f15e7182933a17fb61ecf74e853518','inputs':inputs}
    class Catalog:
        def get_version(self,name,version):
            assert version==versions[name]
            return dict(manifests[name])
    build=tmp_path/'accepted';build.mkdir();archive=build/'implementation';archive.mkdir()
    code=archive/'full_sources.py';code.write_text('# old source adapter, never executed by migration\n')
    runtime={'release':'old-native','bundle_id':'old-bundle'}
    identity={'versions':versions,'content':{name:manifest['content_sha256'] for name,manifest in manifests.items()},'runtime':runtime,'code_sha256':_hash(code)}
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    report={'status':'prepared_provisional','code_sha256':_hash(code),'fingerprint':fingerprint,'native_runtime':runtime,'input_lock':{'versions':versions},'database_path':str(build/'pluto.duckdb'),'source_relations':{name:'sources."'+name+'"' for name in versions},'inputs':[{'catalog_name':name,'catalog_version':versions[name],'content_sha256':manifest['content_sha256'],'parquet_path':manifest['parquet_path'],'provisional':name=='alpha'} for name,manifest in manifests.items()]}
    database=duckdb.connect(str(build/'pluto.duckdb'));database.execute('CREATE SCHEMA sources');database.execute('CREATE SCHEMA source_work');database.execute('CREATE TABLE source_work.identity AS SELECT ?::VARCHAR AS fingerprint',[fingerprint])
    database.execute('CREATE TABLE sources.alpha(number VARCHAR,text VARCHAR,exact VARCHAR)')
    database.execute("INSERT INTO sources.alpha VALUES ('40,395',' NULL ',''),('1.234567','Code','  '),(NULL,'',NULL)")
    database.execute('CREATE TABLE sources.empty(id BIGINT,value VARCHAR)');database.execute('CREATE TABLE sources.kept(id BIGINT)');database.close()
    (build/'source-preparation.json').write_text(json.dumps(report))
    completed={'status':'completed','run_id':'completed-fixture','output':{'version':'accepted-output'},'upstream_commit':'32bc98f632f15e7182933a17fb61ecf74e853518','input_lock':versions,'sources':deepcopy(report),'implementation':{'full_sources.py':{'path':str(code),'sha256':_hash(code)}}}
    (build/'build-report.json').write_text(json.dumps(completed))
    return Catalog(),recipe,{'versions':versions},build,extension,report


def publish(captured,tmp_path,**options):
    catalog,recipe,lock,build,extension,_=captured
    return prepare_collection(catalog,recipe,input_lock=lock,output_dir=tmp_path/'published',extension_directory=extension,legacy_source_build=build,**options)


def test_legacy_publication_is_physical_typed_immutable_and_preserves_identity(captured,tmp_path):
    _,_,_,build,_,old=captured
    before=_hash(build/'pluto.duckdb')
    result=publish(captured,tmp_path)
    assert result['status']=='ready' and result['input_count']==3 and result['prepared_input_count']==2 and result['retained_source_count']==1
    assert result['provenance']['archived_code_sha256']==old['code_sha256']
    assert result['provenance']['native_runtime']==old['native_runtime']
    assert result['provenance']['source_database_sha256_before']==result['provenance']['source_database_sha256_after']==before
    assert result['descriptor_sha256']==_json_hash(result['descriptor'])
    database=Path(result['database_path']);assert result['database_sha256']==_hash(database)
    con=duckdb.connect(str(database),read_only=True)
    assert con.execute('SELECT * FROM preparation.identity').fetchall()==[(result['input_id'],result['descriptor_sha256'])]
    assert con.execute('SELECT * FROM sources.alpha ORDER BY number NULLS LAST').fetchall()==[(Decimal('1.234567000000'),'Code','  '),(Decimal('40395.000000000000'),None,None),(None,None,None)]
    assert con.execute('DESCRIBE sources.empty').fetchall()[0][1]=='BIGINT'
    assert con.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='sources' ORDER BY table_name").fetchall()==[('alpha','BASE TABLE'),('empty','BASE TABLE')]
    con.close()
    assert _hash(build/'pluto.duckdb')==before
    with pytest.raises(FileExistsError):publish(captured,tmp_path)


def test_migration_rejects_changed_catalog_or_archive_or_cache(captured,tmp_path):
    _,_,_,build,extension,_=captured
    archive=build/'implementation/full_sources.py';archive.write_text('different current code must not replace cached implementation')
    with pytest.raises(PreparedError,match='implementation hash'):
        publish(captured,tmp_path)
    assert not (tmp_path/'published/prepared.duckdb').exists()
    assert not (tmp_path/'published/manifest.json').exists()


def test_migration_rejects_database_identity_mismatch(captured,tmp_path):
    _,_,_,build,_,_=captured
    con=duckdb.connect(str(build/'pluto.duckdb'));con.execute("UPDATE source_work.identity SET fingerprint='wrong'");con.close()
    with pytest.raises(PreparedError,match='database identity'):
        publish(captured,tmp_path)
    assert not (tmp_path/'published/manifest.json').exists()


def test_failed_numeric_normalization_is_never_published(captured,tmp_path):
    _,_,_,build,_,_=captured
    con=duckdb.connect(str(build/'pluto.duckdb'));con.execute("UPDATE sources.alpha SET number='1,,2' WHERE number='40,395'");con.close()
    with pytest.raises(duckdb.Error,match='Invalid numeric grouping'):
        publish(captured,tmp_path)
    assert not (tmp_path/'published/prepared.duckdb').exists()
    assert not (tmp_path/'published/manifest.json').exists()
    assert json.loads((tmp_path/'published/failed.json').read_text())['status']=='failed'


def test_normal_source_adapter_branch_without_business_runner(captured,tmp_path,monkeypatch):
    catalog,recipe,lock,build,extension,report=captured
    from pluto_example import full_sources
    called=[]
    def adapter(catalog_arg,lock_arg,database_path,extension_arg,**kwargs):
        import shutil
        called.append(kwargs)
        shutil.copyfile(build/'pluto.duckdb',database_path)
        return deepcopy(report)
    monkeypatch.setattr(full_sources,'prepare_sources',adapter)
    result=prepare_collection(catalog,recipe,input_lock=lock,output_dir=tmp_path/'normal',extension_directory=extension,geosupport_release='explicit')
    assert result['status']=='ready' and result['provenance']['mode']=='source_adapters'
    assert called[0]['geosupport_release']=='explicit'


@pytest.mark.parametrize('mutate,match',[
    (lambda recipe:recipe.update(provider='unknown'),'Unsupported collection provider'),
    (lambda recipe:recipe.update(schema_version=True),'schema_version'),
    (lambda recipe:recipe.update(unrecognized=True),'Unknown collection fields'),
    (lambda recipe:recipe['inputs'][0].update(unrecognized=True),'Unknown input fields'),
    (lambda recipe:recipe['inputs'][0]['source'].update(unrecognized=True),'unsupported source fields'),
    (lambda recipe:recipe['inputs'][0]['columns']['number'].update(unrecognized=True),'unsupported column policy'),
])
def test_strict_recipe_schema(captured,tmp_path,mutate,match):
    catalog,recipe,lock,_,extension,_=captured;mutate(recipe)
    with pytest.raises(PreparedError,match=match):prepare_collection(catalog,recipe,input_lock=lock,output_dir=tmp_path/'invalid',extension_directory=extension)
    assert not (tmp_path/'invalid').exists()


def test_duplicate_recipe_keys_and_legacy_runtime_arguments_are_rejected(captured,tmp_path):
    path=tmp_path/'duplicate.yml';path.write_text('schema_version: 1\nschema_version: 2\n')
    with pytest.raises(PreparedError,match='Duplicate'):_load(path)
    with pytest.raises(PreparedError,match='cannot be combined'):
        publish(captured,tmp_path,geosupport_release='new-runtime')


def test_catalog_hash_drift_is_rejected(captured,tmp_path,monkeypatch):
    catalog,*_=captured;original=catalog.get_version
    monkeypatch.setattr(catalog,'get_version',lambda name,version:{**original(name,version),'content_sha256':'changed-catalog-content'})
    with pytest.raises(PreparedError,match='cached source version/content hash'):
        publish(captured,tmp_path)
    assert not (tmp_path/'published/manifest.json').exists()


def test_incomplete_legacy_build_is_rejected(captured,tmp_path):
    build=captured[3];path=build/'build-report.json';report=json.loads(path.read_text());report['status']='running';path.write_text(json.dumps(report))
    with pytest.raises(PreparedError,match='completed build report'):
        publish(captured,tmp_path)


def test_legacy_hash_change_during_extraction_prevents_publication(captured,tmp_path,monkeypatch):
    from pluto_example import prepared
    original=prepared._hash;source=captured[3]/'pluto.duckdb';calls=[]
    def digest(path):
        if Path(path)==source:
            calls.append(str(path))
            if len(calls)==2:return 'changed-source-database'
        return original(path)
    monkeypatch.setattr(prepared,'_hash',digest)
    with pytest.raises(PreparedError,match='changed the source database'):
        publish(captured,tmp_path)
    assert len(calls)==2
    assert not (tmp_path/'published/manifest.json').exists()


def test_numeric_grouping_strict_cast_and_null_spelling():
    con=duckdb.connect();con.execute('CREATE TABLE numbers(value VARCHAR)')
    con.execute("INSERT INTO numbers VALUES ('+40,395.125'),('-1,234'),('1e3'),(' NULL '),(''),(NULL)")
    query=_normalization_query('numbers',[('value','VARCHAR')],{'value':{'nulls':'trimmed_empty_or_null','type':'decimal_38_12','numeric_grouping':True}})
    assert con.execute(query).fetchall()==[(Decimal('40395.125000000000'),),(Decimal('-1234.000000000000'),),(Decimal('1000.000000000000'),),(None,),(None,),(None,)]
    con.execute("INSERT INTO numbers VALUES ('not-numeric')")
    with pytest.raises(duckdb.Error,match='Could not convert'):
        con.execute(query).fetchall()
    con.close()


@pytest.mark.parametrize('field,value',[('release','different'),('previous_release','different'),('source_commit','different')])
def test_provider_revision_contract_is_explicit(captured,tmp_path,field,value):
    catalog,recipe,lock,_,extension,_=captured;recipe[field]=value
    with pytest.raises(PreparedError,match='requires '+field):
        prepare_collection(catalog,recipe,input_lock=lock,output_dir=tmp_path/'invalid',extension_directory=extension)


@pytest.mark.parametrize('field',['adapter','runtime','axis_policy'])
def test_native_preparation_declarations_cannot_claim_different_execution(field):
    from pluto_example.prepared import _validate_recipe
    recipe=yaml.safe_load((Path(__file__).resolve().parents[1]/'recipes/26v2.yml').read_text())
    versions={item['source']['dataset']:'fixed-version' for item in recipe['inputs']}
    native=next(item for item in recipe['inputs'] if item['name']=='pluto_input_geocodes')
    native['preparation'][field]='unsupported'
    with pytest.raises(PreparedError,match='pinned native adapter'):_validate_recipe(recipe,versions)
