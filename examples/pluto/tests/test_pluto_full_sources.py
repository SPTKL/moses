"""Source preparation contracts; synthetic calls never claim native parity."""
import json
import hashlib
import os
from pathlib import Path

import duckdb
import pytest

from moses.catalog import Catalog
from pluto_example.full_sources import (
    FullSourceError, _geocode, _materialize_batches, _native_macros,
    _reset_native_macros, _shallow_json_merge, prepare_sources,
)


EXTENSIONS = Path(os.environ.get('MOSES_TEST_EXTENSIONS', Path(__file__).parents[1] / '.extensions'))
pytestmark = pytest.mark.skipif(not list(EXTENSIONS.glob('*/**/spatial.duckdb_extension')),
                                reason='requires installed local Spatial extension')


def _connection(path=':memory:'):
    con = duckdb.connect(str(path))
    con.execute("SET extension_directory='" + str(EXTENSIONS) + "'")
    con.execute('LOAD spatial')
    return con


def test_locked_streaming_sources_preserve_identifiers_and_geometry(tmp_path):
    con = _connection()
    source = tmp_path / 'source.parquet'
    con.execute("COPY (SELECT '001' id, 'NA' AS \"value\", ST_AsWKB(ST_Point(-74,40)) wkb_geometry) TO ? (FORMAT PARQUET)", [str(source)])
    con.close()
    catalog = Catalog(tmp_path / 'warehouse')
    first = catalog.ingest(source, name='raw__fixture', provenance={
        'normalization': {'csv_null_policy': {'upstream_pandas_compatibility': 'not_proven'}}})
    # Updating current version cannot change the supplied lock.
    newer = tmp_path / 'new.csv'
    newer.write_text('id,value\n999,new\n')
    catalog.ingest(newer, name='raw__fixture')
    database = tmp_path / 'prepared.duckdb'
    report = prepare_sources(catalog, {'versions': {'raw__fixture': first['version']}}, database, EXTENSIONS)
    assert report['status'] == 'prepared_provisional'
    assert report['production_parity'] is False
    assert report['input_lock']['versions']['raw__fixture'] == first['version']
    con = _connection(database)
    assert con.execute('SELECT id,value,ST_X(wkb_geometry) FROM sources.fixture').fetchone() == ('001', None, -74)
    con.close()
    assert json.loads(database.with_suffix('.sources.json').read_text())['fingerprint'] == report['fingerprint']


def test_conflicting_or_finished_sources_are_rejected_before_reading(tmp_path):
    class NoRead:
        def get_version(self, name, version):
            raise AssertionError('finished PLUTO must not be read')
    with pytest.raises(FullSourceError, match='finished-product'):
        prepare_sources(NoRead(), {'versions': {'pluto': 'v1'}}, tmp_path / 'out', EXTENSIONS)
    with pytest.raises(FullSourceError, match='nonempty explicit'):
        prepare_sources(NoRead(), {}, tmp_path / 'out', EXTENSIONS)


def test_batch_resume_does_not_reevaluate_completed_native_calls():
    con = _connection()
    con.execute('CREATE SCHEMA source_work')
    con.execute('CREATE TABLE keys AS SELECT range+1 source_row FROM range(5)')
    calls = []
    con.create_function('count_call', lambda value: calls.append(value) or value, ['BIGINT'], 'BIGINT', side_effects=True)
    args = (con, 'test', 'keys', 'count_call(source_row)', 'SELECT source_row,geo')
    _materialize_batches(*args, batch_size=2, progress=None)
    assert calls == [1, 2, 3, 4, 5]
    _materialize_batches(*args, batch_size=2, progress=None)
    assert calls == [1, 2, 3, 4, 5]
    assert con.execute('SELECT count(*) FROM source_work.test').fetchone()[0] == 5


def test_synthetic_native_recipe_merges_fields_falls_back_and_preserves_bin_grain():
    con = _connection()
    for schema in ('sources', 'source_work', 'source_raw'):
        con.execute('CREATE SCHEMA ' + schema)
    con.execute("CREATE TABLE source_raw.pluto_input_geocodes AS SELECT * FROM (VALUES ('1','00001','0001'),('1','00001','0001'),('1','00001','0002')) t(boro,block,lot)")
    con.execute("CREATE TABLE source_raw.pluto_input_numbldgs AS SELECT * FROM (VALUES ('1000001'),('1000001'),('1000002')) t(bin)")
    # Extension-compatible typed result; every branch is synthetic evidence.
    con.execute('''CREATE MACRO gs_call(fn,inputs,release,mode) AS struct_pack(
        grc := CASE WHEN fn='1A' AND json_extract_string(inputs,'$.house_number')='2' THEN '02' WHEN fn='BN' AND mode='regular' AND json_extract_string(inputs,'$.bin')='1000002' THEN '02' ELSE '00' END,
        bbl := '1000010001',
        raw := CASE
          WHEN fn='BL' THEN to_json({'BOROUGH BLOCK LOT (BBL)': {'BOROUGH BLOCK LOT (BBL)': json_extract_string(inputs,'$.bbl')}, 'COMMUNITY DISTRICT': {'COMMUNITY DISTRICT':'101'}, 'ZIP Code':'BL-ZIP', 'Latitude':'40.7', 'Longitude':'-74.0', 'Number of Existing Structures on Lot':'0002', 'LIST OF GEOGRAPHIC IDENTIFIERS': [{'Low House Number': right(json_extract_string(inputs,'$.bbl'),1), '5-Digit Street Code':'45490', 'Borough Code':'1'}]})
          WHEN fn='D' THEN '{"First Street Name Normalized":"WORTH STREET"}'
          WHEN fn='1A' THEN '{"ZIP Code":"", "BOROUGH BLOCK LOT (BBL)":{"BOROUGH BLOCK LOT (BBL)":"1000010001"}, "Latitude":"40.7", "Longitude":"-74.0"}'
          ELSE '{"ZIP Code":"10013", "2020 Census Tract":"001000"}' END)''')
    report = _geocode(con, {'bundle_id': 'synthetic'}, batch_size=1, progress=None)
    rows = con.execute('SELECT lot,zipcode,ct2020,numberofexistingstructures,ST_X(geom),ST_Y(geom) FROM sources.pluto_input_geocodes ORDER BY lot').fetchall()
    assert rows == [('0001', '', '001000', '0002', 40.7, -74), ('0002', 'BL-ZIP', None, '0002', 40.7, -74)]
    assert con.execute('SELECT * FROM sources.pluto_input_numbldgs').fetchall() == [('1000010001', 3)]
    assert report['calls'] == {'bl': 2, 'street': 1, 'regular': 2, 'extended': 1, 'bin_regular': 2, 'bin_tpad': 1}


@pytest.mark.parametrize('regular', [
    {'nested': {}}, {'nested': None}, {}, {'nested': {'x': ''}}, {'nested': {'x': None}},
])
def test_shallow_merge_replaces_nested_objects_and_retains_explicit_nulls(regular):
    extended = {'nested': {'x': 'extended', 'other': 'removed'}, 'carry': 'kept'}
    con = duckdb.connect()
    con.execute('CREATE TABLE inputs(extended JSON, regular JSON)')
    con.execute('INSERT INTO inputs VALUES (?,?)', [json.dumps(extended), json.dumps(regular)])
    result = con.execute('SELECT ' + _shallow_json_merge('extended', 'regular') + ' FROM inputs').fetchone()[0]
    assert json.loads(result) == {**extended, **regular}
    if regular == {'nested': {}}:
        assert con.execute("SELECT json_extract_string(" + _shallow_json_merge('extended', 'regular') + ", '$.nested.x') FROM inputs").fetchone()[0] is None
    con.close()


@pytest.fixture
def native_macro_fixture(tmp_path):
    setting = os.environ.get('MOSES_TEST_GEOSUPPORT_EXTENSION')
    if not setting:
        pytest.skip('set MOSES_TEST_GEOSUPPORT_EXTENSION to test extension registration without native calls')
    binary = Path(setting).resolve(strict=True)
    runtime = {'extension_path': str(binary), 'extension_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    database = tmp_path / 'native_macros.duckdb'
    def connect():
        return duckdb.connect(str(database), config={'allow_unsigned_extensions': True})
    def load(con):
        con.execute("LOAD '" + str(binary).replace("'", "''") + "'")
    con = connect()
    con.execute('CREATE SCHEMA source_work')
    con.execute("CREATE TABLE source_work.identity AS SELECT 'fixture-identity' fingerprint")
    con.execute("CREATE TABLE source_work.checkpoint_fixture AS SELECT 10000 completed")
    assert _reset_native_macros(con, runtime, 'fixture-identity') == []
    load(con)
    assert len(_native_macros(con)) == 4
    con.close()
    return connect, load, runtime


def test_shallow_merge_two_empty_objects_returns_json_object():
    con = duckdb.connect()
    expression = _shallow_json_merge("'{}'::JSON", "'{}'::JSON")
    result, result_type = con.execute('SELECT ' + expression + ', typeof(' + expression + ')').fetchone()
    assert json.loads(result) == {}
    assert result_type == 'JSON'
    con.close()


def test_native_macro_reopen_reset_and_reload_preserve_checkpoint_and_other_schema(native_macro_fixture):
    connect, load, runtime = native_macro_fixture
    con = connect()
    assert con.execute("SELECT count(*) FROM duckdb_functions() WHERE function_name IN ('_gs_call','gs_load')").fetchone()[0] == 0
    con.execute('CREATE SCHEMA user_macros')
    con.execute('CREATE MACRO user_macros.gs_call(value) AS value+1')
    assert _reset_native_macros(con, runtime, 'fixture-identity') == ['gs_address', 'gs_bbl', 'gs_bin', 'gs_call']
    assert _native_macros(con) == []
    assert con.execute('SELECT user_macros.gs_call(2)').fetchone()[0] == 3
    assert con.execute('SELECT completed FROM source_work.checkpoint_fixture').fetchone()[0] == 10000
    load(con)
    assert len(_native_macros(con)) == 4
    con.close()


@pytest.mark.parametrize('macro_name', ['gs_call', 'GS_CALL'])
def test_native_macro_cleanup_rejects_unknown_same_name_without_dropping_anything(native_macro_fixture, macro_name):
    connect, _, runtime = native_macro_fixture
    con = connect()
    con.execute('CREATE OR REPLACE MACRO main."' + macro_name + '"(value) AS value+99')
    before = _native_macros(con)
    with pytest.raises(FullSourceError, match='unexpected definition or signature'):
        _reset_native_macros(con, runtime, 'fixture-identity')
    assert _native_macros(con) == before
    assert con.execute('SELECT main.gs_call(1)').fetchone()[0] == 100
    con.close()


def test_native_macro_cleanup_requires_verified_identity_and_extension(native_macro_fixture):
    connect, _, runtime = native_macro_fixture
    con = connect()
    before = _native_macros(con)
    with pytest.raises(FullSourceError, match='source identity'):
        _reset_native_macros(con, runtime, 'wrong-identity')
    with pytest.raises(FullSourceError, match='extension checksum'):
        _reset_native_macros(con, {**runtime, 'extension_sha256': '0'*64}, 'fixture-identity')
    assert _native_macros(con) == before
    con.close()


def test_failed_native_load_requires_fresh_connection_before_cleanup(native_macro_fixture):
    connect, load, runtime = native_macro_fixture
    con = connect()
    with pytest.raises(duckdb.Error, match='already exists'):
        load(con)
    with pytest.raises(FullSourceError, match='reopen the connection'):
        _reset_native_macros(con, runtime, 'fixture-identity')
    con.close()
    con = connect()
    assert len(_reset_native_macros(con, runtime, 'fixture-identity')) == 4
    load(con)
    assert len(_native_macros(con)) == 4
    con.close()
