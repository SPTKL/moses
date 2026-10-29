"""Base workflows run in fresh interpreters that cannot import native GIS libs."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


_BLOCK_NATIVE = """
import importlib.abc
import sys

class BlockNativeGIS(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'shapely', 'pyogrio', 'pyproj'}:
            raise ModuleNotFoundError(f'blocked optional dependency: {fullname}', name=fullname)

sys.meta_path.insert(0, BlockNativeGIS())
"""


def _run_without_spatial(script, tmp_path):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('MOSES_')}
    environment['XDG_CONFIG_HOME'] = str(tmp_path / 'user-config')
    # Keep source-tree runs and installed-wheel runs equally usable.
    environment['PYTHONPATH'] = os.pathsep.join(str(Path(path).resolve()) for path in sys.path if path)
    result = subprocess.run(
        [sys.executable, '-c', _BLOCK_NATIVE + textwrap.dedent(script)],
        cwd=tmp_path, env=environment, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_base_import_help_and_empty_crs_config(tmp_path):
    _run_without_spatial('''
        import importlib
        for name in ('cli', 'config', 'ingest', 'exports', 'map_preview', 'source_recipes', 'service'):
            importlib.import_module('moses.' + name)
        from moses.cli import main
        from moses.config import load_config, resolve_default_crs
        assert load_config('warehouse') == {}
        assert resolve_default_crs('warehouse') is None
        try:
            main(['--help'])
        except SystemExit as exc:
            assert exc.code == 0
        assert main(['--warehouse', 'warehouse', 'config', 'show']) == 0
        assert main(['--warehouse', 'warehouse', 'init']) == 0
        assert not {'shapely', 'pyogrio', 'pyproj'} & sys.modules.keys()
    ''', tmp_path)


@pytest.mark.parametrize('suffix', ['csv', 'parquet'])
def test_base_tabular_inspect_load_query_export_and_recipe(tmp_path, suffix):
    _run_without_spatial('''
        from pathlib import Path
        import pyarrow as pa
        import pyarrow.parquet as pq
        from moses.catalog import Catalog
        from moses.cli import main
        from moses.inspection import inspect_source
        from moses import source_recipes
        source = Path('rows.SUFFIX')
        if source.suffix == '.csv':
            source.write_text('id,value\\n001,hello\\n002,world\\n')
        else:
            pq.write_table(pa.table({'id': ['001', '002'], 'value': ['hello', 'world']}), source)
        assert inspect_source(source)['row_count'] == 2
        args = ['--warehouse', 'warehouse']
        assert main(args + ['inspect', str(source)]) == 0
        assert main(args + ['load', str(source), '--name', 'rows', '--key', 'id']) == 0
        catalog = Catalog('warehouse')
        assert catalog.query('select id from rows order by id')['id'].to_pylist() == ['001', '002']
        assert main(args + ['export', 'rows', 'delivery.parquet', '--format', 'Parquet']) == 0
        assert pq.read_table('delivery.parquet')['id'].to_pylist() == ['001', '002']
        # An import blocker alone does not remove installed package metadata.
        original_version = source_recipes.package_metadata.version
        def base_version(name):
            if name in {'shapely', 'pyproj', 'pyogrio'}:
                raise source_recipes.package_metadata.PackageNotFoundError(name)
            return original_version(name)
        source_recipes.package_metadata.version = base_version
        report = source_recipes.prepare_recipe({
            'schema_version': 1, 'name': 'prepared',
            'source': {'kind': 'local', 'path': str(source)}, 'key': 'id',
        }, catalog)
        assert report['manifest']['row_count'] == 2
        assert set(report['engine']['dependencies']) == {'pyarrow', 'duckdb'}
        assert not {'shapely', 'pyogrio', 'pyproj'} & sys.modules.keys()
    '''.replace('SUFFIX', suffix), tmp_path)


@pytest.mark.parametrize('setting_source', ['project', 'global', 'legacy', 'environment'])
def test_base_workflows_with_existing_default_crs(tmp_path, setting_source):
    _run_without_spatial('''
        import json
        import os
        from pathlib import Path
        from moses.cli import main
        from moses.config import resolve_default_crs, show_config
        setting_source = 'SETTING_SOURCE'
        warehouse = Path('warehouse')
        warehouse.mkdir()
        if setting_source == 'legacy':
            (warehouse / 'config.json').write_text(json.dumps({'default_crs': 'EPSG:4326'}))
        elif setting_source == 'environment':
            os.environ['MOSES_DEFAULT_CRS'] = 'EPSG:4326'
        else:
            target = (Path('config.toml') if setting_source == 'project'
                      else Path(os.environ['XDG_CONFIG_HOME']) / 'moses' / 'config.toml')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('[moses.spatial]\\ndefault_crs = "EPSG:4326"\\n')
        assert resolve_default_crs(warehouse) == 'EPSG:4326'
        assert show_config(warehouse=warehouse)['settings']['spatial']['default_crs'] == 'EPSG:4326'
        Path('rows.csv').write_text('id,value\\n001,hello\\n002,world\\n')
        args = ['--warehouse', str(warehouse)]
        for command in [
            ['config', 'show'], ['list'], ['inspect', 'rows.csv'],
            ['load', 'rows.csv', '--name', 'rows', '--key', 'id'],
            ['query', 'select id from rows order by id'], ['list'],
        ]:
            assert main(args + command) == 0, command
        assert not {'shapely', 'pyogrio', 'pyproj'} & sys.modules.keys()
    '''.replace('SETTING_SOURCE', setting_source), tmp_path)


def test_base_crs_deferral_preserves_configuration_shape_errors(tmp_path):
    _run_without_spatial('''
        import json
        import os
        from pathlib import Path
        from moses.config import load_config, resolve_default_crs, resolve_warehouse, set_default_crs
        from moses.dependencies import SpatialDependencyError
        warehouse = Path('warehouse')
        warehouse.mkdir()
        def fails(operation, expected=ValueError):
            try:
                operation()
            except expected:
                return
            raise AssertionError('expected configuration error')
        for value in (False, 4326, [], {}, '', '   '):
            (warehouse / 'config.json').write_text(json.dumps({'default_crs': value}))
            fails(lambda: load_config(warehouse))
        for value in ('false', '4326', '[]', '{}', '""', '"   "'):
            Path('config.toml').write_text('[moses.spatial]\\ndefault_crs = ' + value + '\\n')
            fails(resolve_warehouse)
        Path('config.toml').unlink()
        # Semantic deferral is narrowly bounded to the missing-dependency case.
        (warehouse / 'config.json').write_text(json.dumps({'default_crs': ' unknown-crs '}))
        assert resolve_default_crs(warehouse) == 'unknown-crs'
        os.environ['MOSES_DEFAULT_CRS'] = ' another-unknown-crs '
        assert resolve_default_crs(warehouse) == 'another-unknown-crs'
        fails(lambda: set_default_crs(warehouse, 'EPSG:4326'), SpatialDependencyError)
        assert json.loads((warehouse / 'config.json').read_text())['default_crs'] == ' unknown-crs '
    ''', tmp_path)


def test_missing_spatial_dependency_is_actionable_at_feature_boundary(tmp_path):
    _run_without_spatial('''
        from pathlib import Path
        from moses.config import set_default_crs
        from moses.dependencies import SpatialDependencyError
        from moses.ingest import read_vector
        from moses.exports import export_filegdb
        from moses.map_preview import build_map_preview, MapPreviewError
        from moses.source_recipes import validate_recipe
        Path('points.csv').write_text('x,y\\n-74,40.7\\n')
        Path('points.geojson').write_text('{"type":"FeatureCollection","features":[]}')
        operations = [
            lambda: set_default_crs('warehouse', 'EPSG:4326'),
            lambda: read_vector('points.csv', x='x', y='y'),
            lambda: read_vector('points.geojson'),
            lambda: export_filegdb(None, 'points', 'out.gdb', version='exact-version', layer='points'),
            lambda: validate_recipe({'schema_version': 1, 'name': 'points',
                'source': {'kind': 'local', 'path': 'points.csv'},
                'geometry': {'x': 'x', 'y': 'y', 'crs': 'EPSG:4326', 'on_null': 'error', 'on_invalid': 'error'}}),
        ]
        for operation in operations:
            try:
                operation()
            except SpatialDependencyError as exc:
                assert "uv add 'moses-geo[spatial]'" in str(exc), str(exc)
            else:
                raise AssertionError('spatial operation should require the spatial extra')
        try:
            build_map_preview(Path('unused.parquet'), {'geometry_column': 'geometry', 'crs': 'EPSG:4326'})
        except MapPreviewError as exc:
            assert exc.code == 'spatial_dependencies_required'
            assert "uv add 'moses-geo[spatial]'" in str(exc)
        else:
            raise AssertionError('map preview should require the spatial extra')
    ''', tmp_path)
