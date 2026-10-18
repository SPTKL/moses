from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely

from moses.catalog import Catalog
from moses.source_recipes import SourceRecipeError, load_recipe, prepare_recipe, validate_recipe


def rest_recipe():
    return {'schema_version': 1, 'name': 'api_points',
            'source': {'kind': 'dlt_rest_api', 'resource': 'points',
                       'config': {'client': {'base_url': 'https://fixture.invalid/', 'auth': {'type': 'bearer'}},
                                  'resource_defaults': {'endpoint': {'data_selector': 'data', 'paginator': {'type': 'json_link', 'next_url_path': 'next'}}},
                                  'resources': [{'name': 'unused', 'endpoint': {'path': 'unused'}},
                                                {'name': 'points', 'endpoint': {'path': 'points'}}]},
                       'secrets': {'client.auth.token': {'env': 'MOSES_FIXTURE_TOKEN'}}},
            'import': {'types': {'id': 'string', 'amount': 'int64'}, 'null_policy': {'tokens': [''], 'trim': False}}}


def mock_pages(monkeypatch, *, fail_second=False):
    import requests
    requested = []
    monkeypatch.setenv('MOSES_FIXTURE_TOKEN', 'fixture-secret-must-not-be-saved')
    def send(session, request, **kwargs):
        requested.append(request)
        assert request.headers['Authorization'] == 'Bearer fixture-secret-must-not-be-saved'
        if 'page=2' in request.url:
            if fail_second:
                raise ValueError('fixture-secret-must-not-be-saved')
            body = {'data': [{'id': '002', 'amount': '3'}], 'next': None}
        else:
            body = {'data': [{'id': '001', 'amount': '2'}], 'next': 'https://fixture.invalid/points?page=2'}
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response.request = request
        response.headers['Content-Type'] = 'application/json'
        response._content = json.dumps(body).encode()
        return response
    monkeypatch.setattr(requests.Session, 'send', send)
    return requested


def test_actual_dlt_pagination_selected_resource_and_offline_capture(tmp_path, monkeypatch):
    pytest.importorskip('dlt')
    requested = mock_pages(monkeypatch)
    catalog = Catalog(tmp_path / 'catalog')
    report = prepare_recipe(rest_recipe(), catalog)
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table['id'].to_pylist() == ['001', '002']
    assert table['amount'].to_pylist() == [2, 3]
    assert len(requested) == 2
    assert not any('unused' in request.url for request in requested)
    assert report['source']['extraction']['dlt_version'] == '1.31.0'
    assert report['source']['extraction']['incremental'] is False
    assert 'fixture-secret-must-not-be-saved' not in json.dumps(report)
    capture = catalog.root / report['source']['capture_path']
    assert report['source']['sha256'] == hashlib.sha256(capture.read_bytes()).hexdigest()
    replay = {'schema_version': 1, 'name': 'offline_points', 'source': {'kind': 'local', 'path': str(capture), 'sha256': report['source']['sha256']}, 'import': rest_recipe()['import']}
    monkeypatch.delenv('MOSES_FIXTURE_TOKEN')
    offline = prepare_recipe(replay, catalog)
    assert pq.read_table(offline['manifest']['parquet_path']).equals(table)
    assert len(requested) == 2


def test_actual_dlt_nullable_declared_field_across_more_than_1000_rows(tmp_path, monkeypatch):
    pytest.importorskip('dlt')
    import requests
    config = rest_recipe()
    config['source']['config']['client'].pop('auth')
    config['source'].pop('secrets')
    config['import']['rename'] = {'raw_note': 'note'}
    config['import']['types']['note'] = 'string'
    requests_seen = []
    def send(session, request, **kwargs):
        requests_seen.append(request.url)
        if 'page=2' in request.url:
            data = [{'id': '01001', 'amount': '3', 'raw_note': 'present'}]
            next_url = None
        else:
            data = [{'id': f'{index:05d}', 'amount': '2', 'raw_note': None} for index in range(1000)]
            next_url = 'https://fixture.invalid/points?page=2'
        response = requests.Response()
        response.status_code, response.url, response.request = 200, request.url, request
        response.headers['Content-Type'] = 'application/json'
        response._content = json.dumps({'data': data, 'next': next_url}).encode()
        return response
    monkeypatch.setattr(requests.Session, 'send', send)
    report = prepare_recipe(config, Catalog(tmp_path / 'catalog'))
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table.num_rows == 1001
    assert table['note'].type == pa.string()
    assert table['note'].null_count == 1000
    assert table['note'][1000].as_py() == 'present'
    assert len(requests_seen) == 2


def test_record_capture_preserves_late_keys_and_rejects_nested_or_schema_change(tmp_path):
    from moses.source_recipes import _write_extracted
    output = tmp_path / 'capture.parquet'
    _write_extracted([{'id': 1}, {'id': 2, 'new_field': 'x'}], output, {})
    table = pq.read_table(output)
    assert table['new_field'].to_pylist() == [None, 'x']
    _write_extracted([{'id': 1}, {'id': '001'}], output, {'id': 'string'})
    assert pq.read_table(output)['id'].to_pylist() == ['1', '001']
    with pytest.raises(SourceRecipeError, match='Nested'):
        _write_extracted([{'id': 1, 'nested': {'a': 1}}, {'id': 2, 'nested': {'a': 2, 'late': 3}}], output, {})
    with pytest.raises(SourceRecipeError, match='schema changed'):
        _write_extracted([{'id': index} for index in range(1000)] + [{'id': 1000, 'late': 'x'}], output, {})


@pytest.mark.parametrize('key', ['token', 'api_key', 'password', 'signature', 'X-Amz-Signature'])
def test_url_credentials_are_rejected_before_provenance_can_capture_them(key):
    config = {'schema_version': 1, 'name': 'download', 'source': {'kind': 'url', 'url': f'https://fixture.invalid/file.csv?{key}=secret-value'}}
    with pytest.raises(SourceRecipeError, match='environment secret references') as caught:
        validate_recipe(config)
    assert 'secret-value' not in str(caught.value)
    config['source']['url'] = 'https://fixture.invalid/file.csv?download=1'
    assert validate_recipe(config)['source']['url'].endswith('?download=1')


def test_failed_dlt_pagination_is_redacted_and_never_publishes(tmp_path, monkeypatch):
    pytest.importorskip('dlt')
    catalog = Catalog(tmp_path / 'catalog')
    old = tmp_path / 'old.csv'
    old.write_text('id,amount\n000,1\n')
    manifest = catalog.ingest(old, name='api_points')
    requested = mock_pages(monkeypatch, fail_second=True)
    with pytest.raises(SourceRecipeError, match='suppressed') as caught:
        prepare_recipe(rest_recipe(), catalog)
    assert 'fixture-secret-must-not-be-saved' not in str(caught.value)
    assert len(requested) == 2
    assert catalog.get_version('api_points')['version'] == manifest['version']
    assert len(catalog.history('api_points')) == 1


@pytest.mark.parametrize('mutation', [
    lambda value: value['source']['config']['resources'][1]['endpoint'].update(incremental={'cursor_path': 'id'}),
    lambda value: value['source']['config']['resources'][1].update(processing_steps=[{'map': 'eval'}]),
    lambda value: value['source']['config']['client']['auth'].update(token='plaintext'),
    lambda value: value['source']['config']['client'].update(session='arbitrary'),
    lambda value: value['source'].update(resource='absent'),
    lambda value: value['source']['config']['resource_defaults']['endpoint'].pop('paginator'),
    lambda value: value['source']['config']['resource_defaults']['endpoint'].pop('data_selector'),
])
def test_rest_schema_rejects_implicit_or_executable_features(mutation):
    value = rest_recipe()
    mutation(value)
    with pytest.raises(SourceRecipeError):
        validate_recipe(value)


def test_trusted_python_source_processing_identity_order_and_failure(tmp_path, monkeypatch):
    module = tmp_path / 'recipe_fixture_hooks.py'
    module.write_text('''from decimal import Decimal
import pyarrow as pa
def records():
    return pa.table({'ID':['001'], 'amount':['2'], 'price':pa.array([Decimal('100.20')],type=pa.decimal128(8,2))})
def multiply(table, factor):
    assert table.column_names == ['id','amount','price']
    assert table['amount'].type == pa.int64()
    return table.set_column(1,'amount',pa.array([table['amount'][0].as_py()*factor]))
def broken(table, value):
    raise ValueError(value)
''')
    monkeypatch.syspath_prepend(str(tmp_path))
    config = {'schema_version': 1, 'name': 'python_points', 'source': {'kind': 'python', 'callable': 'recipe_fixture_hooks:records'},
              'import': {'rename': {'ID': 'id'}, 'types': {'id': 'string', 'amount': 'int64'}},
              'processing': [{'callable': 'recipe_fixture_hooks:multiply', 'parameters': {'factor': 3}}]}
    catalog = Catalog(tmp_path / 'catalog')
    report = prepare_recipe(config, catalog)
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table['amount'].to_pylist() == [6]
    assert table['id'].to_pylist() == ['001']
    assert str(table['price'][0].as_py()) == '100.20'
    expected = hashlib.sha256(module.read_bytes()).hexdigest()
    assert report['source']['extraction']['code_sha256'] == expected
    assert report['normalization']['processing'][0]['code_sha256'] == expected
    assert report['source']['extraction']['trusted_python_not_sandboxed'] is True
    config['processing'] = [{'callable': 'recipe_fixture_hooks:broken', 'secrets': {'value': {'env': 'MOSES_FIXTURE_SECRET'}}}]
    monkeypatch.setenv('MOSES_FIXTURE_SECRET', 'do-not-echo-this-value')
    with pytest.raises(SourceRecipeError, match='suppressed') as caught:
        prepare_recipe(config, catalog)
    assert 'do-not-echo-this-value' not in str(caught.value)
    assert catalog.get_version('python_points')['version'] == report['manifest']['version']
    config['processing'] = []
    config['source']['code_sha256'] = '0' * 64
    with pytest.raises(SourceRecipeError, match='SHA256'):
        prepare_recipe(config, catalog)


def recipe(path='points.csv'):
    return {'schema_version': 1, 'name': 'points',
            'source': {'kind': 'local', 'path': path},
            'import': {'rename': {'ID': 'id'}, 'types': {'id': 'string', 'amount': 'int64'},
                       'null_policy': {'tokens': ['', 'NA'], 'trim': True}},
            'geometry': {'x': 'lon', 'y': 'lat', 'crs': 'EPSG:4326', 'on_null': 'null', 'on_invalid': 'error'},
            'key': 'id'}


def points(tmp_path):
    source = tmp_path / 'points.csv'
    source.write_text('ID,lon,lat,amount,name\n001,-74,40.7,2, NA \n002,,,NA,kept\n')
    return source


def test_xy_import_is_typed_null_explicit_and_versioned(tmp_path):
    source = points(tmp_path)
    catalog = Catalog(tmp_path / 'catalog')
    config = recipe()
    config['source']['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    report = prepare_recipe(config, catalog, base_directory=tmp_path)
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table['id'].to_pylist() == ['001', '002']
    assert table['amount'].type == pa.int64()
    assert table['amount'].to_pylist() == [2, None]
    assert table['name'].to_pylist() == [None, 'kept']
    assert shapely.from_wkb(table['geometry'][0].as_py()).coords[:] == [(-74, 40.7)]
    assert table['geometry'][1].as_py() is None
    assert json.loads(table.schema.metadata[b'geo'])['columns']['geometry']['crs']['id']['code'] == 4326
    assert report['normalization']['geometry']['null_input_rows'] == 1
    retained = catalog.root / report['source']['capture_path']
    assert retained.read_bytes() == source.read_bytes()
    again = prepare_recipe(config, catalog, base_directory=tmp_path)
    assert again['manifest']['version'] == report['manifest']['version']
    assert again['manifest']['unchanged'] is True


@pytest.mark.parametrize('mutation', [
    lambda value: value.update(sql='DROP TABLE points'),
    lambda value: value.update(schema_version=True),
    lambda value: value['source'].update(version='latest'),
    lambda value: value['source'].update(sha256='wrong'),
    lambda value: value['import'].update(python='pass'),
    lambda value: value['import'].update(types={'id': 'arbitrary_expression'}),
    lambda value: value['import'].update(null_policy={'tokens': [], 'trim': 'yes'}),
    lambda value: value['geometry'].update(on_invalid='repair'),
    lambda value: value['geometry'].pop('y'),
    lambda value: value['source'].update(archive_member='../escape.csv'),
])
def test_unknown_or_unsafe_declarations_are_rejected(mutation):
    value = recipe()
    mutation(value)
    with pytest.raises((SourceRecipeError, ValueError)):
        validate_recipe(value)


def test_yaml_loader_rejects_duplicate_keys_and_executable_tags(tmp_path):
    source = tmp_path / 'recipe.yml'
    source.write_text('schema_version: 1\nname: first\nname: second\nsource: {kind: local, path: points.csv}\n')
    with pytest.raises(SourceRecipeError, match='unique'):
        load_recipe(source)
    source.write_text('!!python/object/apply:os.system ["touch unwanted"]')
    with pytest.raises(SourceRecipeError, match='unsupported YAML'):
        load_recipe(source)


def test_catalog_source_is_exact_even_after_current_changes(tmp_path):
    source = points(tmp_path)
    catalog = Catalog(tmp_path / 'catalog')
    original = catalog.ingest(source, name='raw_points')
    source.write_text('ID,lon,lat,amount,name\n999,-73,41,3,new\n')
    catalog.ingest(source, name='raw_points')
    config = recipe()
    config['source'] = {'kind': 'catalog', 'name': 'raw_points', 'version': original['version']}
    report = prepare_recipe(config, catalog)
    assert pq.read_table(report['manifest']['parquet_path'])['id'].to_pylist() == ['001', '002']
    assert report['source']['catalog_content_sha256'] == original['content_sha256']
    for version in ('latest', 'current', '*'):
        config['source']['version'] = version
        with pytest.raises(SourceRecipeError, match='exact immutable'):
            validate_recipe(config)


def test_url_archive_download_hash_and_member_are_pinned(tmp_path, monkeypatch):
    source = points(tmp_path)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('nested/points.csv', source.read_bytes())
        stream.writestr('other.csv', 'unselected\nvalue\n')
    data = archive.getvalue()
    observed = []
    def download(url, timeout):
        observed.append((url, timeout))
        return io.BytesIO(data)
    monkeypatch.setattr('moses.source_recipes.urlopen', download)
    config = recipe()
    config['source'] = {'kind': 'url', 'url': 'https://example.test/release.zip',
                        'archive_member': 'nested/points.csv', 'sha256': hashlib.sha256(data).hexdigest()}
    report = prepare_recipe(config, Catalog(tmp_path / 'catalog'))
    assert report['manifest']['row_count'] == 2
    assert report['source']['member_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert observed == [('https://example.test/release.zip', 60)]


@pytest.mark.parametrize('failure', ['hash', 'cast', 'geometry', 'rename', 'key'])
def test_failure_never_changes_current_catalog_release(tmp_path, failure):
    points(tmp_path)
    catalog = Catalog(tmp_path / 'catalog')
    first = prepare_recipe(recipe(), catalog, base_directory=tmp_path)['manifest']
    config = recipe()
    if failure == 'hash':
        config['source']['sha256'] = '0' * 64
    elif failure == 'cast':
        config['import']['types']['name'] = 'int64'
    elif failure == 'geometry':
        config['geometry']['on_null'] = 'error'
    elif failure == 'rename':
        config['import']['rename']['name'] = 'id'
    else:
        config['key'] = 'absent'
    with pytest.raises(ValueError):
        prepare_recipe(config, catalog, base_directory=tmp_path)
    assert catalog.get_version('points')['version'] == first['version']
    assert len(catalog.history('points')) == 1


def test_invalid_coordinates_can_be_nulled_without_swapping_axes(tmp_path):
    source = tmp_path / 'points.csv'
    source.write_text('ID,lon,lat,amount,name\n001,nan,40,1,A\n002,40,-74,2,B\n003,bad,40,3,C\n')
    config = recipe()
    config['geometry']['on_invalid'] = 'null'
    result = prepare_recipe(config, Catalog(tmp_path / 'catalog'), base_directory=tmp_path)
    table = pq.read_table(result['manifest']['parquet_path'])
    assert table['geometry'][0].as_py() is None
    assert shapely.from_wkb(table['geometry'][1].as_py()).coords[:] == [(40, -74)]
    assert table['geometry'][2].as_py() is None
    assert result['normalization']['geometry']['invalid_input_rows'] == 2


def geocode_recipe():
    return {'schema_version': 1, 'name': 'addresses', 'source': {'kind': 'local', 'path': 'addresses.csv'},
            'geosupport': {'adapter': 'address_points', 'fields': {'borough': 'boro', 'house_number': 'number', 'street': 'street'},
                          'runtime': {'extension': 'extension.duckdb_extension', 'extension_sha256': '1' * 64,
                                      'home': 'store', 'bundle_id': '2' * 64, 'release': '26c', 'mode': 'local'},
                          'function': '1A', 'mode': 'regular', 'on_failure': 'record'}}


def test_named_geosupport_adapter_retains_every_status_raw_and_coordinate(tmp_path):
    (tmp_path / 'addresses.csv').write_text('boro,number,street\n1,1,CENTRE STREET\n1,99,FAKE STREET\n1,2,CENTRE STREET\n')
    received = []
    @contextmanager
    def adapter(config, base):
        assert config['runtime']['bundle_id'] == '2' * 64
        assert base == tmp_path
        def call(inputs):
            received.extend(inputs)
            return [{'grc': '00', 'raw': {'Longitude': '-74', 'Latitude': '40.7', 'Message': 'good'}},
                    {'grc': '02', 'raw': {'Message': 'not found', 'Longitude': '-74', 'Latitude': '40.7'}},
                    {'grc': '00', 'raw': {'Message': 'coordinates absent'}}]
        yield call
    catalog = Catalog(tmp_path / 'catalog')
    report = prepare_recipe(geocode_recipe(), catalog, base_directory=tmp_path, adapters={'address_points': adapter})
    table = pq.read_table(report['manifest']['parquet_path'])
    assert received[0] == {'borough_code': '1', 'house_number': '1', 'street_name': 'CENTRE STREET'}
    assert table['geosupport_grc'].to_pylist() == ['00', '02', '00']
    assert table['geosupport_ok'].to_pylist() == [True, False, False]
    assert table['geosupport_error'].to_pylist() == [None, 'return_code', 'invalid_coordinates']
    assert table['geosupport_longitude'].to_pylist() == [-74, None, None]
    assert table['geometry'].null_count == 2
    assert json.loads(table['geosupport_raw'][1].as_py())['Message'] == 'not found'
    assert report['normalization']['geosupport']['failed_rows'] == 2
    strict = geocode_recipe()
    strict['geosupport']['on_failure'] = 'error'
    with pytest.raises(SourceRecipeError, match='GRC='):
        prepare_recipe(strict, catalog, base_directory=tmp_path, adapters={'address_points': adapter})
    assert catalog.get_version('addresses')['version'] == report['manifest']['version']


def test_native_extension_hash_is_checked_before_loading(tmp_path):
    from moses.source_recipes import native_address_adapter
    binary = tmp_path / 'extension.duckdb_extension'
    binary.write_bytes(b'not a binary')
    (tmp_path / 'store').mkdir()
    before = {key: os.environ.get(key) for key in ('GEOSUPPORT_HOME', 'GEOSUPPORT_RUNTIME')}
    with pytest.raises(SourceRecipeError, match='SHA256'):
        with native_address_adapter(geocode_recipe()['geosupport'], tmp_path):
            raise AssertionError('Unverified native binary must never be loaded')
    assert before == {key: os.environ.get(key) for key in before}


def test_installed_native_extension_can_register_without_native_calls():
    setting = os.environ.get('MOSES_TEST_GEOSUPPORT_EXTENSION')
    if not setting:
        pytest.skip('Set MOSES_TEST_GEOSUPPORT_EXTENSION for optional registration-only check')
    binary = Path(setting).resolve(strict=True)
    con = duckdb.connect(config={'allow_unsigned_extensions': True})
    try:
        con.execute("LOAD '" + str(binary).replace("'", "''") + "'")
        assert con.execute("SELECT count(*) FROM duckdb_functions() WHERE function_name='gs_call'").fetchone()[0] == 1
    finally:
        con.close()
