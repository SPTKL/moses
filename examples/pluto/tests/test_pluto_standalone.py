"""The product builds through ordinary dbt with a read-only prepared database."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import duckdb
import pytest
import yaml
from jinja2 import Environment

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'dbt'
CONTRACT=yaml.safe_load((PROJECT/'models/contract.yml').read_text())


def test_standalone_model_and_source_contract():
    models=list((PROJECT/'models').rglob('*.sql'))
    sources=CONTRACT['sources'][0]
    assert len(models)==38 and all(model.parent==PROJECT/'models' for model in models)
    assert len(sources['tables'])==42
    assert sum(len(table['columns']) for table in sources['tables'])==650
    assert sources['database']=="{{ var('input_database', 'prepared') }}"
    profile=yaml.safe_load((PROJECT/'profiles.yml').read_text())['pluto']['outputs']['local']
    assert profile['attach']==[{'path':"{{ env_var('PLUTO_INPUT_DATABASE') }}",'alias':'prepared','read_only':True}]
    assert not profile.get('extensions')
    assert profile['config_options']['autoinstall_known_extensions'] is False
    macro=(PROJECT/'macros/pluto_inputs.sql').read_text()
    branches=re.findall(r"\{% (?:if|elif) alias == '([^']+)' %\}\n(.*?)(?=\{% (?:elif|else)\b)",macro,re.S)
    raw=[body for name,body in branches if not name.startswith('stg__') and name!='pts_properties_base']
    assert len(raw)==33
    assert all('SELECT * FROM {{ source(' in body and 'NULLIF' not in body and 'CAST(' not in body for body in raw)
    assert len(branches)-len(raw)==32
    for path in PROJECT.rglob('*.py'):
        assert not re.search(r'\b(?:from|import)\s+moses\b',path.read_text())


@pytest.fixture
def standalone(tmp_path):
    extension=Path(os.environ.get('MOSES_TEST_EXTENSIONS', ROOT/'.extensions'))
    input_path=tmp_path/'prepared-input.duckdb'
    con=duckdb.connect(str(input_path))
    con.execute('SET extension_directory=?',[str(extension)])
    try:con.execute('LOAD spatial')
    except duckdb.Error:
        con.close();pytest.skip('Installed compatible spatial extension is required')
    con.execute('CREATE SCHEMA sources')
    con.execute('CREATE SCHEMA preparation')
    con.execute("CREATE TABLE preparation.identity AS SELECT 'fixture'::VARCHAR input_id, repeat('a',64)::VARCHAR descriptor_sha256")
    for table in CONTRACT['sources'][0]['tables']:
        columns=','.join('"'+column['name'].replace('"','""')+'" '+column['data_type'] for column in table['columns'])
        con.execute('CREATE TABLE sources."'+table['name']+'" ('+columns+')')
    con.close()
    project=tmp_path/'dbt';shutil.copytree(PROJECT,project)
    env=dict(os.environ,PLUTO_INPUT_DATABASE=str(input_path),PLUTO_OUTPUT_DATABASE=str(tmp_path/'result.duckdb'),PLUTO_SPATIAL_DIRECTORY=str(extension),DBT_SEND_ANONYMOUS_USAGE_STATS='false',DO_NOT_TRACK='1')
    def invoke(*arguments):
        return subprocess.run([sys.executable,'-m','dbt.cli.main',*arguments,'--project-dir',str(project),'--profiles-dir',str(project),'--no-use-colors'],env=env,capture_output=True,text=True,timeout=60)
    return project,input_path,env,invoke


@pytest.mark.integration
def test_plain_dbt_build_is_offline_and_input_is_read_only(standalone):
    project,input_path,env,invoke=standalone
    # Small prepared fixture rows exercise staging; physical source cleaning is
    # deliberately absent from the product project.
    con=duckdb.connect(str(input_path));con.execute("INSERT INTO sources.pluto_input_landuse_bldgclass (bldgclass,landuse) VALUES ('A0','01')");con.close()
    digest=hashlib.sha256(input_path.read_bytes()).hexdigest()
    parsed=invoke('parse');assert parsed.returncode==0,parsed.stdout+parsed.stderr
    result=invoke('build');assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((project/'target/run_results.json').read_text())
    assert len(report['results'])==48 and all(row['status']=='success' for row in report['results'])
    assert hashlib.sha256(input_path.read_bytes()).hexdigest()==digest
    output=duckdb.connect(env['PLUTO_OUTPUT_DATABASE']);output.execute("ATTACH '"+str(input_path).replace("'","''")+"' AS prepared (READ_ONLY)")
    with pytest.raises(duckdb.Error,match='read-only|read only'):
        output.execute("DELETE FROM prepared.sources.pluto_input_landuse_bldgclass")
    assert output.execute('SELECT count(*) FROM main.export_pluto').fetchone()[0]==0
    output.close()
    spec=importlib.util.spec_from_file_location('pluto_exports',PROJECT.parent/'export.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=module.export(env['PLUTO_OUTPUT_DATABASE'],project.parent/'exports',env['PLUTO_SPATIAL_DIRECTORY'],input_database=input_path)
    assert len(report['artifacts'])==13
    assert {row['crs'] for row in report['artifacts'] if 'crs' in row}=={'EPSG:2263'}
    assert hashlib.sha256(input_path.read_bytes()).hexdigest()==digest

    other_input=input_path.with_name('other-input.duckdb')
    shutil.copyfile(input_path,other_input)
    other=duckdb.connect(str(other_input))
    other.execute("UPDATE preparation.identity SET input_id='different-publication'")
    other.close()
    with pytest.raises(ValueError,match='identity differs'):
        module.export(env['PLUTO_OUTPUT_DATABASE'],project.parent/'wrong-exports',env['PLUTO_SPATIAL_DIRECTORY'],input_database=other_input)
    assert not (project.parent/'wrong-exports').exists()
    partial=invoke('build','--select','qa_expected_derived_values')
    assert partial.returncode==0,partial.stdout+partial.stderr
    with pytest.raises(ValueError,match='successful full PLUTO'):
        module.export(env['PLUTO_OUTPUT_DATABASE'],project.parent/'partial-exports',env['PLUTO_SPATIAL_DIRECTORY'],input_database=input_path)


@pytest.mark.integration
@pytest.mark.parametrize('defect,expected', [('missing','missing table sources.pluto_pts'),('type','type mismatch sources.pluto_pts.boro')])
def test_contract_fails_before_business_models(standalone,defect,expected):
    project,input_path,_,invoke=standalone
    con=duckdb.connect(str(input_path))
    if defect=='missing':con.execute('DROP TABLE sources.pluto_pts')
    else:con.execute('ALTER TABLE sources.pluto_pts ALTER COLUMN boro SET DATA TYPE INTEGER')
    con.close()
    result=invoke('build')
    assert result.returncode!=0 and expected in result.stdout+result.stderr
    con=duckdb.connect(standalone[2]['PLUTO_OUTPUT_DATABASE'])
    assert con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main'").fetchone()[0]==0
    con.close()


def test_true_staging_keeps_geometry_projection():
    environment=Environment();environment.globals['source']=lambda package,name:'sources.'+name
    macro=environment.from_string((PROJECT/'macros/pluto_inputs.sql').read_text()).make_module()
    query=macro.pluto_input('stg__dcp_cdboundaries_wi')
    assert 'wkb_geometry AS geom' in query
    assert 'NULLIF' not in macro.pluto_input('dcp_cb2010_wi')


@pytest.mark.integration
def test_contract_rejects_writable_input_attachment(standalone):
    project,_,_,invoke=standalone
    profile=project/'profiles.yml'
    profile.write_text(profile.read_text().replace('read_only: true','read_only: false'))
    result=invoke('build')
    assert result.returncode!=0
    assert 'must be attached read_only' in result.stdout+result.stderr
