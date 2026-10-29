import json

import pyarrow.parquet as pq
import pyogrio
import pytest

from moses.catalog import Catalog
from moses.cli import main
from moses.config import resolve_column_names, resolve_default_crs, resolve_export_format, resolve_warehouse, show_config
from moses.inspection import inspect_source


def _write(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)


def test_category_merge_alias_and_paths(tmp_path, monkeypatch):
    global_path = tmp_path / 'xdg' / 'moses' / 'config.toml'
    _write(global_path, '[moses]\nconfig_version = 1\n'
           '[moses.project]\nwarehouse = "shared-data"\n'
           '[moses.normalization]\ncolumn_names = "snake_case"\n'
           '[moses.spatial]\ndefault_crs = "EPSG:2263"\n'
           '[moses.export]\nformat = "gEoPaRqUeT"\n')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.delenv('MOSES_DEFAULT_CRS', raising=False)
    project = tmp_path / 'project'
    nested = project / 'a' / 'b'
    nested.mkdir(parents=True)
    _write(project / 'config.toml', '[moses.project]\nwarehouse = "warehouse"\n'
           '[moses.input]\ncolumn_names = "preserve"\n')
    monkeypatch.chdir(nested)
    assert resolve_column_names()['column_names'] == 'preserve'
    assert resolve_column_names()['origin'] == 'project'
    assert resolve_default_crs(project / 'old-warehouse') == 'EPSG:2263'
    assert resolve_export_format() == {'format': 'GeoParquet', 'origin': 'global'}
    assert resolve_warehouse()['warehouse'] == str(project / 'warehouse')
    _write(project / 'config.toml', '[moses.input]\ncolumn_names = "preserve"\n')
    assert resolve_warehouse()['warehouse'] == str(project / 'shared-data')
    assert resolve_warehouse(explicit='manual')['warehouse'] == str(nested / 'manual')
    report = show_config()
    assert report['settings']['normalization']['column_names'] == 'preserve'
    assert report['settings']['spatial']['default_crs'] == 'EPSG:2263'
    assert report['settings']['export']['format'] == 'GeoParquet'
    assert report['origins']['spatial.default_crs'] == 'global'
    assert report['project_path'] == str(project / 'config.toml')
    assert report['global_path'] == str(global_path)


def test_global_absolute_warehouse_and_legacy_crs_fallback(tmp_path, monkeypatch):
    shared = tmp_path / 'shared'
    _write(tmp_path / 'xdg' / 'moses' / 'config.toml',
           f'[moses.project]\nwarehouse = "{shared}"\n')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('MOSES_DEFAULT_CRS', raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_warehouse()['warehouse'] == str(shared)
    shared.mkdir()
    _write(shared / 'config.json', '{"default_crs": "EPSG:3857"}')
    assert resolve_default_crs(shared) == 'EPSG:3857'
    assert show_config()['origins']['spatial.default_crs'] == 'legacy_warehouse'
    _write(tmp_path / 'config.toml', '[moses.spatial]\ndefault_crs = "EPSG:2263"\n')
    assert resolve_default_crs(shared) == 'EPSG:2263'
    monkeypatch.setenv('MOSES_DEFAULT_CRS', 'EPSG:4326')
    assert resolve_default_crs(shared) == 'EPSG:4326'


def test_cli_project_warehouse_subdir_and_explicit_override(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'empty-xdg'))
    project = tmp_path / 'project'
    subdir = project / 'nested'
    subdir.mkdir(parents=True)
    _write(project / 'config.toml', '[moses.project]\nwarehouse = "store"\n')
    monkeypatch.chdir(subdir)
    source = tmp_path / 'input.csv'
    source.write_text('id\na\n')
    assert main(['load', str(source), '--name', 'configured', '--key', 'id']) == 0
    assert json.loads(capsys.readouterr().out)['dataset'] == 'configured'
    assert (project / 'store' / 'catalog.sqlite3').exists()
    assert not (subdir / '.moses').exists()
    assert main(['--warehouse', 'manual', 'load', str(source), '--name', 'explicit']) == 0
    capsys.readouterr()
    assert (subdir / 'manual' / 'catalog.sqlite3').exists()
    assert main(['config', 'show']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['settings']['project']['warehouse'] == str(project / 'store')
    assert shown['origins']['project.warehouse'] == 'project'


def test_spatial_fallback_does_not_override_embedded_crs(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    _write(tmp_path / 'xdg' / 'moses' / 'config.toml',
           '[moses.spatial]\ndefault_crs = "EPSG:2263"\n')
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'points.geojson'
    source.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': 'a'},
         'geometry': {'type': 'Point', 'coordinates': [-73.9, 40.7]}}]}))
    # GeoJSON's embedded CRS defaults to OGC:CRS84, so the fallback is unused.
    manifest = Catalog(tmp_path / 'warehouse').ingest(source, name='points', key='id')
    assert manifest['crs'] != 'EPSG:2263'
    assert manifest['crs_source'] == 'source'
    assert pq.read_table(manifest['parquet_path']).schema.metadata[b'geo']


def test_inspection_api_uses_configured_crs_fallback_and_explicit_override(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('MOSES_DEFAULT_CRS', raising=False)
    _write(tmp_path / 'xdg' / 'moses' / 'config.toml',
           '[moses.spatial]\ndefault_crs = "EPSG:2263"\n')
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'points.csv'
    source.write_text('X,Y\n1000,2000\n')
    configured = inspect_source(source, x='X', y='Y')
    assert configured['crs'] == 'EPSG:2263'
    assert configured['crs_source'] == 'default'
    overridden = inspect_source(source, x='X', y='Y', default_crs='EPSG:3857')
    assert overridden['crs'] == 'EPSG:3857'
    assert overridden['crs_source'] == 'default'
    embedded = tmp_path / 'embedded.geojson'
    embedded.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {},
         'geometry': {'type': 'Point', 'coordinates': [-73.9, 40.7]}}]}))
    assert inspect_source(embedded)['crs'] != 'EPSG:2263'


def test_inspection_explicit_none_does_not_reresolve_other_warehouse(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'empty-xdg'))
    monkeypatch.delenv('MOSES_DEFAULT_CRS', raising=False)
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / '.moses' / 'config.json', '{"default_crs": "EPSG:3857"}')
    source = tmp_path / 'coords.csv'
    source.write_text('X,Y\n-73.9,40.7\n')
    assert inspect_source(source, x='X', y='Y')['crs'] == 'EPSG:3857'
    assert inspect_source(source, x='X', y='Y', default_crs=None)['crs'] == 'EPSG:4326'
    other = tmp_path / 'other'
    assert main(['--warehouse', str(other), 'inspect', str(source), '--x', 'X', '--y', 'Y']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['crs'] == 'EPSG:4326'
    assert result['crs_source'] == 'legacy_csv_default'
    assert not other.exists()


def test_configured_filegdb_export_uses_existing_writer(tmp_path, monkeypatch, capsys):
    if pyogrio.list_drivers().get('OpenFileGDB') not in {'rw', 'raw'}:
        pytest.skip('OpenFileGDB writer unavailable')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    _write(tmp_path / 'xdg' / 'moses' / 'config.toml',
           '[moses.export]\nformat = "filegdb"\n')
    monkeypatch.chdir(tmp_path)
    warehouse = tmp_path / 'warehouse'
    source = tmp_path / 'table.csv'
    source.write_text('id,amount\na,2\n')
    manifest = Catalog(warehouse).ingest(source, name='table', key='id')
    destination = tmp_path / 'table.gdb'
    assert main(['-w', str(warehouse), 'export', 'table', str(destination),
                 '--version', manifest['version'], '--layer', 'exported']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['format'] == 'FileGDB'
    assert pyogrio.list_layers(destination).tolist() == [['exported', None]]


@pytest.mark.parametrize('contents,match', [
    ('[moses.input]\ncolumn_names = "preserve"\n[moses.normalization]\ncolumn_names = "snake_case"\n', 'conflicting'),
    ('[moses.project]\nunknown = 1\n', 'unknown'),
    ('[moses.spatial]\ndefault_crs = "bogus"\n', 'invalid'),
    ('[moses.export]\nformat = "csv"\n', 'Parquet'),
])
def test_invalid_grouped_config(tmp_path, monkeypatch, contents, match):
    path = tmp_path / 'xdg' / 'moses' / 'config.toml'
    _write(path, contents)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=match) as caught:
        resolve_column_names()
    assert str(path) in str(caught.value)


def test_identical_alias_and_canonical_are_accepted(tmp_path, monkeypatch):
    path = tmp_path / 'xdg' / 'moses' / 'config.toml'
    _write(path, '[moses.input]\ncolumn_names = "snake_case"\n'
           '[moses.normalization]\ncolumn_names = "snake_case"\n')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.chdir(tmp_path)
    assert resolve_column_names()['column_names'] == 'snake_case'
