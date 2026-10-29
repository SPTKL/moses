import json

import pyarrow.parquet as pq
import pytest

from moses.catalog import Catalog
from moses.cli import main
from moses.column_names import snake_case
from moses.ingest import read_vector
from moses.inspection import inspect_source
from moses.source_recipes import prepare_recipe


@pytest.mark.parametrize(('source', 'expected'), [
    ('TaxLotID', 'tax_lot_id'), ('camelCase', 'camel_case'),
    ('Lot # / Name', 'lot_name'), ('  12 Acres ', 'column_12_acres'),
    ('_UPPER__CASE_', 'upper_case'),
])
def test_snake_case_rules(source, expected):
    assert snake_case(source) == expected


def test_inspect_load_and_unchanged_with_source_options(tmp_path):
    source = tmp_path / 'points.csv'
    source.write_text('Parcel ID,TaxLotID,Longitude X,Latitude Y,12 Floors\n001,7,-73.9,40.7,3\n')
    kwargs = {'x': 'Longitude X', 'y': 'Latitude Y', 'types': {'12 Floors': 'int64'},
              'column_names': 'snake_case'}
    inspected = inspect_source(source, **kwargs)
    assert inspected['column_name_map'] == {'Parcel ID': 'parcel_id', 'TaxLotID': 'tax_lot_id',
        'Longitude X': 'longitude_x', 'Latitude Y': 'latitude_y', '12 Floors': 'column_12_floors'}
    assert inspected['preview'][0]['column_12_floors'] == 3
    catalog = Catalog(tmp_path / 'warehouse')
    manifest = catalog.ingest(source, name='points', key='Parcel ID', **kwargs)
    assert manifest['key'] == 'parcel_id'
    assert manifest['recipe']['column_name_map'] == inspected['column_name_map']
    table = pq.read_table(manifest['parquet_path'])
    assert table.column_names == [*inspected['column_name_map'].values(), 'geometry']
    assert json.loads(table.schema.metadata[b'geo'])['primary_column'] == 'geometry'
    assert manifest['crs'] == 'EPSG:4326'
    assert catalog.ingest(source, name='points', key='Parcel ID', **kwargs)['unchanged']
    assert read_vector(source)[0].column_names[:2] == ['Parcel ID', 'TaxLotID']


def test_reject_empty_and_colliding_names(tmp_path):
    source = tmp_path / 'input.csv'
    source.write_text('Value!,Value?\n1,2\n')
    with pytest.raises(ValueError, match='collide'):
        read_vector(source, column_names='snake_case')
    source.write_text('é,ok\n1,2\n')
    with pytest.raises(ValueError, match='no usable ASCII'):
        read_vector(source, column_names='snake_case')
    source.write_text('Geometry,X,Y\nfoo,1,2\n')
    with pytest.raises(ValueError, match='collide'):
        read_vector(source, x='X', y='Y', column_names='snake_case')


def test_invalid_mode_and_collision_keep_current_version(tmp_path):
    source = tmp_path / 'input.csv'
    source.write_text('Value!,Other\n1,2\n')
    catalog = Catalog(tmp_path / 'catalog')
    with pytest.raises(ValueError, match='column_names'):
        read_vector(source, column_names='camelCase')
    with pytest.raises(ValueError, match='column_names'):
        catalog.ingest(source, name='values', column_names='camelCase')
    original = catalog.ingest(source, name='values', column_names='snake_case')
    source.write_text('Value!,Value?\n1,2\n')
    with pytest.raises(ValueError, match='collide'):
        catalog.ingest(source, name='values', column_names='snake_case')
    assert catalog.get_version('values')['version'] == original['version']


def test_recipe_rename_then_snake_case_with_final_types_and_key(tmp_path):
    source = tmp_path / 'source.csv'
    source.write_text('Raw ID,Old Value\n001,4\n')
    recipe = {'schema_version': 1, 'name': 'renamed',
              'source': {'kind': 'local', 'path': str(source)},
              'import': {'rename': {'Old Value': 'NewValue'}, 'column_names': 'snake_case',
                         'types': {'new_value': 'int64'}}, 'key': 'raw_id'}
    report = prepare_recipe(recipe, Catalog(tmp_path / 'catalog'))
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table.column_names == ['raw_id', 'new_value']
    assert table['new_value'].to_pylist() == [4]
    assert report['manifest']['key'] == 'raw_id'
    assert report['normalization']['column_name_map'] == {'Raw ID': 'raw_id', 'Old Value': 'new_value'}


def test_python_record_capture_uses_final_type_name_without_phantom_column(tmp_path, monkeypatch):
    module = tmp_path / 'normalized_source.py'
    module.write_text("def records():\n    yield {'Parcel ID': '001', 'Amount Value': 1}\n"
                      "    yield {'Parcel ID': '002', 'Amount Value': '2'}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    recipe = {'schema_version': 1, 'name': 'record_names',
              'source': {'kind': 'python', 'callable': 'normalized_source:records'},
              'import': {'column_names': 'snake_case',
                         'types': {'parcel_id': 'string', 'amount_value': 'int64'}},
              'key': 'parcel_id'}
    report = prepare_recipe(recipe, Catalog(tmp_path / 'catalog'))
    table = pq.read_table(report['manifest']['parquet_path'])
    assert table.column_names == ['amount_value', 'parcel_id']
    assert table['amount_value'].to_pylist() == [1, 2]
    assert table['parcel_id'].to_pylist() == ['001', '002']


def test_cli_inspect_and_load_accept_source_names(tmp_path, capsys):
    source = tmp_path / 'input.csv'
    source.write_text('Parcel ID,AmountValue\n001,5\n')
    warehouse = tmp_path / 'warehouse'
    assert main(['--warehouse', str(warehouse), 'inspect', str(source),
                 '--column-names', 'snake_case', '--type', 'AmountValue=int64']) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected['column_name_map']['AmountValue'] == 'amount_value'
    assert inspected['preview'][0]['amount_value'] == 5
    assert main(['--warehouse', str(warehouse), 'load', str(source), '--name', 'csv_names',
                 '--column-names', 'snake_case', '--key', 'Parcel ID',
                 '--type', 'AmountValue=int64']) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded['key'] == 'parcel_id'
    assert pq.read_table(loaded['parquet_path'])['amount_value'].to_pylist() == [5]
