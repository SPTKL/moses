import json
from pathlib import Path

import duckdb
import pytest

from moses.pluto.full import compare_release


def test_audit_diagnosis_keeps_business_text_history_nulls_and_duplicate_counts(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / 'examples/pluto/diagnose_consolidation_audits.py'
    spec = importlib.util.spec_from_file_location('pluto_audit_diagnosis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline, candidate = tmp_path / 'baseline', tmp_path / 'candidate'
    applied_header = 'bbl,field,old_value,new_value,type,reason,version\n'
    duplicate = '4,ownername,A,B,text,Research,24v1\n'
    for directory, version, historical, old, copies, serial, quoted in (
            (baseline, 'm2', '24v1', '1.0', 2, '1', '""'),
            (candidate, 'm3', '24v2', '1', 1, '20', '')):
        directory.mkdir()
        (directory / 'build-report.json').write_text(json.dumps({
            'status': 'completed', 'input_lock': {'pinned': 'same'},
            'upstream_commit': 'same', 'run_id': version, 'candidate_version': version}))
        (directory / 'pluto_changes_applied.csv').write_text(
            applied_header + f'1,lotarea,0,100,numeric,Zero lot area,{version}\n'
            + f'2,lotarea,0,200,numeric,Zero lot area,{historical}\n'
            + f'3,bldgarea,{old},10,numeric,Research,24v1\n' + duplicate * copies)
        # A quoted owner comma and quoted empty string exercise the explicitly
        # fixed dialect and NULL policy instead of relying on auto-detection.
        (directory / 'pluto_changes_not_applied.csv').write_text(
            applied_header.rstrip('\n') + ',found_value\n'
            + '5,ownername,"OWNER, LLC",B,text,Research,24v1,' + quoted + '\n')
        (directory / 'pluto_removed_records.csv').write_text(
            f'id,bbl,ownername,version\n{serial},6,"OWNER, LLC",{version}\n')
    report = module.diagnose(baseline, candidate)
    applied = report['audits']['pluto_changes_applied']
    assert applied['raw_exact']['baseline_only']['rows'] == 4
    assert applied['raw_exact']['candidate_only']['rows'] == 3
    diagnostic = applied['diagnostic_normalization']
    # Only the one automatic current-release label is normalized: historical
    # labels, numeric spellings and duplicate multiplicity remain differences.
    assert diagnostic['baseline_only']['rows'] == 3
    assert diagnostic['candidate_only']['rows'] == 2
    rejected = report['audits']['pluto_changes_not_applied']
    assert rejected['raw_exact']['baseline_only']['rows'] == 1
    assert rejected['raw_exact']['candidate_only']['rows'] == 1
    removed = report['audits']['pluto_removed_records']
    assert removed['raw_exact']['matches'] is False
    assert removed['keyed_removed_comparison']['column_difference_counts'] == {'id': 1, 'version': 1}
    assert removed['diagnostic_normalization']['excluded_columns'] == ['id']
    assert removed['diagnostic_normalization']['baseline_only']['rows'] == 0
    assert removed['diagnostic_normalization']['candidate_only']['rows'] == 0
    assert report['numeric_equivalence_used'] is False


def test_ambiguity_diagnosis_preserves_target_eligibility_and_actual_values(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / 'examples/pluto/diagnose_ambiguous_matches.py'
    spec = importlib.util.spec_from_file_location('pluto_match_diagnosis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    compiled = tmp_path / 'parcel_cama.sql'
    compiled.write_text('''WITH cama_bldgarea_4_pluto AS (
      SELECT a.* REPLACE (CASE WHEN b.__matched THEN CAST(b.grossarea AS BIGINT)
        ELSE a.bldgarea END AS bldgarea)
      FROM parcel_base a LEFT JOIN (
        SELECT b.*, TRUE AS __matched FROM raw_cama b WHERE b.bldgnum='1'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY b.primebbl)=1
      ) b ON a.bbl=b.primebbl AND (a.bldgarea=0)=b.__matched
    ) SELECT * FROM cama_bldgarea_4_pluto''')
    con = duckdb.connect()
    con.execute('CREATE MACRO moses_text(x) AS CAST(x AS VARCHAR)')
    con.execute("CREATE TABLE parcel_base AS SELECT * FROM (VALUES (1,'5024500160',0::BIGINT),(2,'2000000001',50),(3,'3002080304',0)) t(id,bbl,bldgarea)")
    con.execute("""CREATE TABLE raw_cama AS SELECT bbl,'1' AS bldgnum,LEFT(bbl,10) AS primebbl,
      NULL::VARCHAR AS billingbbl,grossarea FROM (VALUES
      ('5024500160','10382'),('5024500160E','0'),
      ('2000000001','20'),('2000000001E','30'),
      ('3002080304','10'),('3002080304E','10')) t(bbl,grossarea)""")
    con.execute('CREATE TABLE parcel_cama AS SELECT * REPLACE(777::BIGINT AS bldgarea) FROM parcel_base')
    con.execute("CREATE TABLE pluto AS SELECT *,0 AS comarea,0 AS resarea,0 AS otherarea,0 AS builtfar,'7' AS areasource FROM parcel_cama")
    try:
        report = module.cama_diagnosis(con, compiled, 50)
    finally:
        con.close()
    rule = report['rules'][0]
    assert rule['multiple_match_targets'] == 2
    assert rule['conflicting_assignment_targets'] == 1
    assert report['conflicting_target_bbls'] == ['5024500160']
    known = next(group for group in rule['detailed_groups'] if group['target_bbl'] == '5024500160')
    assert [option['source_payload']['bbl'] for option in known['options']] == ['5024500160', '5024500160E']
    assert known['actual_final_cama_values'] == [{'bldgarea': 777}]
    assert 'recomputed_stage_values' in known


def test_zip_ambiguity_counts_matched_null_and_retains_removed_target(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / 'examples/pluto/diagnose_ambiguous_matches.py'
    spec = importlib.util.spec_from_file_location('pluto_zip_diagnosis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    con = duckdb.connect(config={'extension_directory': str(Path('.extensions').resolve())})
    try:
        con.execute('LOAD spatial')
    except duckdb.Error:
        con.close()
        pytest.skip('Installed DuckDB Spatial required')
    try:
        con.execute('CREATE MACRO moses_text(x) AS CAST(x AS VARCHAR)')
        con.execute('CREATE SCHEMA sources')
        con.execute("CREATE TABLE political_geography AS SELECT 1 id,'1012650040' bbl,NULL::VARCHAR zipcode,1 xcoord,ST_Point(-74,41) centroid")
        con.execute("CREATE TABLE sources.doitt_zipcodeboundaries AS SELECT *,ST_GeomFromText('POLYGON((-75 40,-73 40,-73 42,-75 42,-75 40))') wkb_geometry FROM (VALUES ('10020',1),(NULL,2)) t(zipcode,ogc_fid)")
        con.execute("CREATE TABLE service_geography AS SELECT * REPLACE('10020' AS zipcode) FROM political_geography")
        con.execute('CREATE TABLE pluto AS SELECT * FROM service_geography WHERE FALSE')
        report = module.zip_diagnosis(con, 50)
    finally:
        con.close()
    assert report['eligible_targets'] == 1
    assert report['conflicting_zipcode_targets'] == 1
    group = report['detailed_groups'][0]
    assert [row['option_zipcode'] for row in group['options']] == ['10020', None]
    assert group['actual_selected_service_zipcode'] == '10020'
    assert group['actual_final_pluto_rows'] == []


def test_release_comparison_preserves_nulls_and_reports_key_changes(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE candidate AS SELECT * FROM (VALUES (1000010001::DECIMAL(10,0), 2.0::DECIMAL(5,1), 'A'), (1000010002, NULL, ''), (1000010003, 4, 'C')) AS t(bbl, area, name)")
    reference = tmp_path / 'reference.csv'
    reference.write_text('bbl,area,name\n1000010001.000000,2,A\n1000010002,0,\n1000010004,4,D\n')
    report = compare_release(con, 'candidate', reference, tmp_path)
    assert (report['added_bbls'], report['removed_bbls'], report['matched_bbls']) == (1, 1, 2)
    counts = {r['column']: r['mismatched_rows'] for r in report['columns']}
    assert counts == {'bbl': 0, 'area': 1, 'name': 1}
    assert not report['all_compared_values_equal']
    assert not report['production_parity']
    assert json.loads((tmp_path / 'reference-comparison.json').read_text()) == report


def test_comparison_rejects_duplicate_reference_keys(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE candidate AS SELECT 1000010001::BIGINT bbl")
    reference = tmp_path / 'reference.csv'
    reference.write_text('bbl\n1000010001\n1000010001\n')
    with pytest.raises(ValueError, match='unique canonical BBLs'):
        compare_release(con, 'candidate', reference, tmp_path)


def test_spatial_export_records_state_plane_crs(tmp_path):
    from moses.pluto.full import export_spatial
    import pyarrow.parquet as pq
    con = duckdb.connect(config={'extension_directory': str(Path('.extensions').resolve())})
    try:
        con.execute('LOAD spatial')
    except duckdb.Error:
        pytest.skip('Installed DuckDB Spatial required')
    con.execute("CREATE TABLE mappluto AS SELECT '1000010001' bbl, ST_Point(980000,190000) geom")
    paths, result = export_spatial(con, {'mappluto': 'mappluto'}, tmp_path)
    geo = json.loads(pq.read_schema(paths[0]).metadata[b'geo'])
    assert geo['columns']['geom']['crs']['id'] == {'authority': 'EPSG', 'code': 2263}
    assert result['mappluto']['crs'] == 'EPSG:2263'
    # A repeated export atomically replaces the file, supporting finalization.
    assert export_spatial(con, {'mappluto': 'mappluto'}, tmp_path)[1] == result


def test_resume_rebuilds_changed_or_failed_models_and_descendants(tmp_path):
    from moses.pluto.full import _resume_selection
    project = {'project_dir': str(tmp_path), 'manifest': {'compatibility_macros': [], 'models': [{'name':'base','sha256':'a'}, {'name':'derived','sha256':'new'}, {'name':'failed','sha256':'f'}]}, 'outputs': {'export_pluto': 'export_pluto'}}
    old = {'project': project, 'execution_ledger': {'base':{'status':'success','sha256':'a'}, 'derived':{'status':'success','sha256':'old'}, 'failed':{'status':'error','sha256':'f'}}}
    selection, ledger = _resume_selection(old, project)
    assert selection == ['derived+', 'failed+', 'export_pluto']
    assert ledger['base']['status'] == 'success'


def test_resume_rejects_cached_outputs_from_changed_engines():
    from moses.pluto.full import _validate_resume_engines
    engines = {'duckdb': '1.5.6', 'dbt-core': '1.12.6'}
    _validate_resume_engines({'engines': engines}, engines)
    with pytest.raises(ValueError, match='unchanged engine versions'):
        _validate_resume_engines({'engines': {**engines, 'duckdb': '1.5.5'}}, engines)


def test_candidate_database_clone_preserves_parent(tmp_path):
    from moses.pluto.full import _clone_database
    parent, child = tmp_path / 'parent.duckdb', tmp_path / 'child.duckdb'
    with duckdb.connect(str(parent)) as con:
        con.execute('CREATE TABLE parcels AS SELECT 1 id')
    _clone_database(parent, child)
    with duckdb.connect(str(child)) as con:
        con.execute('UPDATE parcels SET id=2')
    with duckdb.connect(str(parent), read_only=True) as con:
        assert con.execute('SELECT id FROM parcels').fetchone() == (1,)
    with pytest.raises(FileExistsError):
        _clone_database(parent, child)


def test_resume_rebuilds_retargeted_output_alias(tmp_path):
    from moses.pluto.full import _resume_selection
    manifest = {'compatibility_macros': [], 'models': []}
    old = {'project': {'project_dir': str(tmp_path), 'manifest': manifest,
                       'outputs': {'pluto': 'old_model'}},
           'execution_ledger': {'pluto': {'status': 'success'}}}
    selection, _ = _resume_selection(old, {'manifest': manifest,
                                         'outputs': {'pluto': 'new_model'}})
    assert selection == ['pluto']


def test_resume_rebuilds_when_shared_macro_changes(tmp_path):
    from moses.pluto.full import _resume_selection
    manifest = {'compatibility_macros': [],
                'macro_hashes': {'macros/inputs.sql': 'original'},
                'models': [{'name': 'parcels', 'sha256': 'same-call'}]}
    old = {'project': {'project_dir': str(tmp_path), 'manifest': manifest},
           'execution_ledger': {'parcels': {'status': 'success', 'sha256': 'same-call'}}}
    changed = {**manifest, 'macro_hashes': {'macros/inputs.sql': 'new-null-policy'}}
    selection, ledger = _resume_selection(old, {'manifest': changed})
    assert selection == []  # Empty selection means a full dbt build.
    assert ledger == {}


def test_prune_removes_only_obsolete_manifest_models_from_child(tmp_path):
    from moses.pluto.full import _clone_database, _prune_obsolete_models
    parent, child = tmp_path / 'parent.duckdb', tmp_path / 'child.duckdb'
    with duckdb.connect(str(parent)) as con:
        con.execute('CREATE SCHEMA sources')
        con.execute('CREATE TABLE sources.old_model AS SELECT 7 AS id')
        con.execute('CREATE TABLE old_model AS SELECT 1 AS id')
        con.execute('CREATE VIEW old_view AS SELECT * FROM old_model')
        con.execute('CREATE VIEW old_export AS SELECT * FROM old_view')
        con.execute('CREATE TABLE retained AS SELECT 2 AS id')
        con.execute('CREATE TABLE unlisted AS SELECT 3 AS id')
    old = {'project': {'manifest': {'models': [
        {'name': 'old_model'}, {'name': 'old_view'}, {'name': 'retained'}]},
        'outputs': {'old_export': 'old_view'}}}
    new = {'manifest': {'models': [{'name': 'retained'}]}, 'outputs': {}}
    _clone_database(parent, child)
    with duckdb.connect(str(child)) as con:
        removed = _prune_obsolete_models(con, old, new)
        assert removed == [{'name': 'old_export', 'type': 'VIEW'},
                           {'name': 'old_view', 'type': 'VIEW'},
                           {'name': 'old_model', 'type': 'TABLE'}]
        for relation, expected in [('retained', 2), ('unlisted', 3), ('sources.old_model', 7)]:
            assert con.execute(f'SELECT id FROM {relation}').fetchone() == (expected,)
    with duckdb.connect(str(parent), read_only=True) as con:
        assert con.execute('SELECT id FROM old_export').fetchone() == (1,)


def test_consolidation_audits_distinguish_null_empty_and_duplicate_rows(tmp_path):
    import runpy
    verify = runpy.run_path(str(Path(__file__).parents[1] / 'examples/pluto/verify_full_consolidation.py'))['verify']
    baseline, candidate = tmp_path / 'before', tmp_path / 'after'
    build = {'status': 'completed', 'input_lock': {'source': 'locked'}, 'upstream_commit': 'pinned'}
    for directory in (baseline, candidate):
        directory.mkdir()
        (directory / 'build-report.json').write_text(json.dumps(build))
    (baseline / 'pluto.csv').write_text('bbl,amount\n1000010001,1\n')
    with duckdb.connect() as con:
        con.execute(f"COPY (SELECT 1000010001::BIGINT AS bbl, 1 AS amount) TO '{candidate / 'pluto.parquet'}' (FORMAT PARQUET)")
    for name in ('pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records'):
        # Quoted text can occur after DuckDB's default sniffing sample.
        tail = '1000010003,plain\n' * 21000 + '1000010004,"Owner, ""quoted"""\n'
        (baseline / f'{name}.csv').write_text('bbl,value\n1000010001,\n1000010002,A\n1000010002,A\n' + tail)
        (candidate / f'{name}.csv').write_text('bbl,value\n1000010001,""\n1000010002,A\n' + tail)
    result = verify(baseline, candidate, tmp_path / 'evidence')
    assert result['parcel_comparison']['all_compared_values_equal']
    for audit in result['correction_audits'].values():
        assert audit['added_rows'] == 1  # The quoted empty value.
        assert audit['removed_rows'] == 2  # NULL and the missing duplicate.
        assert not audit['equal_multiset']
    (candidate / 'build-report.json').write_text(json.dumps({**build, 'input_lock': {'source': 'changed'}}))
    with pytest.raises(ValueError, match='different input_lock'):
        verify(baseline, candidate, tmp_path / 'different-inputs')
