import json

import pyarrow.parquet as pq
import pytest

from moses.catalog import Catalog
from moses.cli import main
from moses.config import resolve_column_names
from moses.ingest import read_vector
from moses.inspection import inspect_source
from moses.source_recipes import prepare_recipe


def _config(path, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[other]\nvalue = 1\n\n[moses]\nconfig_version = 1\n'
                    f'\n[moses.input]\ncolumn_names = "{mode}"\n')


def test_global_project_parent_env_and_explicit_precedence(tmp_path, monkeypatch):
    xdg = tmp_path / 'xdg'
    _config(xdg / 'moses' / 'config.toml', 'snake_case')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(xdg))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    project = tmp_path / 'project'
    subdir = project / 'nested' / 'deep'
    subdir.mkdir(parents=True)
    (subdir / 'config.toml').write_text('[unrelated]\nvalue = true\n')
    monkeypatch.chdir(subdir)
    assert resolve_column_names()['origin'] == 'global'
    _config(project / 'config.toml', 'preserve')
    assert resolve_column_names() == {
        'column_names': 'preserve', 'origin': 'project',
        'project_path': str(project / 'config.toml'),
        'global_path': str(xdg / 'moses' / 'config.toml')}
    monkeypatch.setenv('MOSES_COLUMN_NAMES', 'snake_case')
    assert resolve_column_names()['origin'] == 'environment'
    assert resolve_column_names(recipe='preserve')['origin'] == 'recipe'
    assert resolve_column_names(explicit='snake_case', recipe='preserve')['origin'] == 'explicit'
    monkeypatch.setenv('MOSES_COLUMN_NAMES', '   ')
    assert resolve_column_names()['origin'] == 'project'


def test_high_level_uses_config_low_level_stays_pure(tmp_path, monkeypatch):
    xdg = tmp_path / 'xdg'
    _config(xdg / 'moses' / 'config.toml', 'snake_case')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(xdg))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'input.csv'
    source.write_text('Parcel ID,AmountValue\n001,2\n')
    assert read_vector(source)[0].column_names == ['Parcel ID', 'AmountValue']
    assert inspect_source(source)['schema'][0]['name'] == 'parcel_id'
    catalog = Catalog(tmp_path / 'catalog')
    selected = catalog.ingest(source, name='input', key='Parcel ID')
    assert selected['key'] == 'parcel_id'
    assert pq.read_table(selected['parquet_path']).column_names == ['parcel_id', 'amount_value']
    preserved = catalog.ingest(source, name='original', key='Parcel ID', column_names='preserve')
    assert pq.read_table(preserved['parquet_path']).column_names == ['Parcel ID', 'AmountValue']


def test_recipe_precedence_and_prepared_snapshot_preserved(tmp_path, monkeypatch):
    xdg = tmp_path / 'xdg'
    _config(xdg / 'moses' / 'config.toml', 'snake_case')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(xdg))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'input.csv'
    source.write_text('Parcel ID,RawValue\n001,5\n')
    recipe = {'schema_version': 1, 'name': 'prepared',
              'source': {'kind': 'local', 'path': str(source)},
              'import': {'column_names': 'preserve'}, 'key': 'Parcel ID'}
    catalog = Catalog(tmp_path / 'catalog')
    preserved = prepare_recipe(recipe, catalog)
    assert pq.read_table(preserved['manifest']['parquet_path']).column_names == ['Parcel ID', 'RawValue']
    assert preserved['manifest']['key'] == 'Parcel ID'
    assert preserved['normalization']['import']['column_names'] == 'preserve'
    snake = prepare_recipe({**recipe, 'name': 'snake', 'import': {}, 'key': 'parcel_id'}, catalog)
    assert pq.read_table(snake['manifest']['parquet_path']).column_names == ['parcel_id', 'raw_value']
    assert snake['normalization']['import']['column_names'] == 'snake_case'
    override = prepare_recipe({**recipe, 'name': 'override', 'key': 'parcel_id'}, catalog, column_names='snake_case')
    assert pq.read_table(override['manifest']['parquet_path']).column_names == ['parcel_id', 'raw_value']
    explicit_preserve = prepare_recipe({**recipe, 'name': 'explicit_preserve', 'import': {}},
                                       catalog, column_names='preserve')
    recorded = explicit_preserve['manifest']['provenance']['source_recipe']['recipe']
    assert recorded['import']['column_names'] == 'preserve'
    replay = prepare_recipe({**recorded, 'name': 'explicit_preserve_replay'}, catalog)
    assert pq.read_table(replay['manifest']['parquet_path']).column_names == ['Parcel ID', 'RawValue']


def test_config_show_is_read_only_and_legacy_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'missing-xdg'))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.chdir(tmp_path)
    warehouse = tmp_path / 'warehouse'
    assert main(['--warehouse', str(warehouse), 'config', 'show']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['settings']['normalization']['column_names'] == 'preserve'
    assert report['origins']['normalization.column_names'] == 'built_in'
    assert not warehouse.exists()
    source = tmp_path / 'data.csv'
    source.write_text('MixedCase\na\n')
    assert inspect_source(source)['schema'][0]['name'] == 'MixedCase'


@pytest.mark.parametrize('contents,match', [
    ('[moses.input\ncolumn_names = "snake_case"\n', 'could not read'),
    ('[moses.input]\ncolumn_names = "camelCase"\n', 'column_names'),
    ('[moses]\nconfig_version = 2\n', 'config_version'),
    ('[moses]\nfuture = true\n', 'unknown'),
    ('[moses.input]\nfuture = true\n', 'unknown'),
])
def test_invalid_config_has_path_and_clear_error(tmp_path, monkeypatch, contents, match):
    xdg = tmp_path / 'xdg'
    path = xdg / 'moses' / 'config.toml'
    path.parent.mkdir(parents=True)
    path.write_text(contents)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(xdg))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match=match) as caught:
        resolve_column_names()
    assert str(path) in str(caught.value)


def test_relative_xdg_config_home_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', 'relative')
    with pytest.raises(ValueError, match='absolute path'):
        resolve_column_names()


def test_cli_global_default_and_prepare_override(tmp_path, monkeypatch, capsys):
    xdg = tmp_path / 'xdg'
    _config(xdg / 'moses' / 'config.toml', 'snake_case')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(xdg))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'source.csv'
    source.write_text('Parcel ID,RawValue\n001,5\n')
    warehouse = tmp_path / 'warehouse'
    assert main(['--warehouse', str(warehouse), 'inspect', str(source)]) == 0
    assert json.loads(capsys.readouterr().out)['schema'][0]['name'] == 'parcel_id'
    assert main(['--warehouse', str(warehouse), 'load', str(source), '--name', 'configured',
                 '--key', 'Parcel ID']) == 0
    configured = json.loads(capsys.readouterr().out)
    assert pq.read_table(configured['parquet_path']).column_names == ['parcel_id', 'raw_value']
    assert main(['--warehouse', str(warehouse), 'load', str(source), '--name', 'explicit',
                 '--key', 'Parcel ID', '--column-names', 'preserve']) == 0
    explicit = json.loads(capsys.readouterr().out)
    assert pq.read_table(explicit['parquet_path']).column_names == ['Parcel ID', 'RawValue']
    recipe = tmp_path / 'recipe.yml'
    recipe.write_text(json.dumps({'schema_version': 1, 'name': 'prepared_cli',
                                  'source': {'kind': 'local', 'path': str(source)},
                                  'key': 'Parcel ID'}))
    assert main(['--warehouse', str(warehouse), 'prepare', str(recipe),
                 '--column-names', 'preserve']) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared['normalization']['import']['column_names'] == 'preserve'
    assert pq.read_table(prepared['manifest']['parquet_path']).column_names == ['Parcel ID', 'RawValue']


def test_home_fallback_when_xdg_unset(tmp_path, monkeypatch):
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'home' / '.config' / 'moses' / 'config.toml'
    _config(path, 'snake_case')
    assert resolve_column_names()['global_path'] == str(path)
    assert resolve_column_names()['column_names'] == 'snake_case'


def test_same_policy_from_different_project_paths_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'empty-xdg'))
    monkeypatch.delenv('MOSES_COLUMN_NAMES', raising=False)
    source = tmp_path / 'source.csv'
    source.write_text('Parcel ID\n001\n')
    catalog = Catalog(tmp_path / 'catalog')
    first_dir = tmp_path / 'first'
    second_dir = tmp_path / 'second'
    _config(first_dir / 'config.toml', 'snake_case')
    _config(second_dir / 'config.toml', 'snake_case')
    monkeypatch.chdir(first_dir)
    first = catalog.ingest(source, name='stable', key='Parcel ID')
    monkeypatch.chdir(second_dir)
    second = catalog.ingest(source, name='stable', key='Parcel ID')
    assert second['unchanged'] is True
    assert second['version'] == first['version']
