import argparse
import json
import subprocess
import sys

from moses.catalog import Catalog
from moses.cli import main


def test_prepare_recipe_cli_preserves_identifiers_and_constructs_geometry(tmp_path, capsys):
    (tmp_path / "points.csv").write_text("id,lon,lat\n001,-73.9,40.7\n")
    recipe = tmp_path / "points.yml"
    recipe.write_text("""schema_version: 1
name: points
source:
  kind: local
  path: points.csv
import:
  format: CSV
  types:
    id: string
    lon: float64
    lat: float64
geometry:
  x: lon
  y: lat
  crs: EPSG:4326
  on_null: error
  on_invalid: error
key: id
""")
    warehouse = tmp_path / "warehouse"
    assert main(["-w", str(warehouse), "prepare", str(recipe)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["manifest"]["dataset"] == "points"
    table = Catalog(warehouse).query('SELECT id FROM points')
    assert table.to_pylist() == [{"id": "001"}]


def test_local_preparation_needs_no_dlt_dbt_or_sql_compiler(tmp_path):
    (tmp_path / "data.csv").write_text("id\n001\n")
    recipe = tmp_path / "source.yml"
    recipe.write_text("schema_version: 1\nname: identifiers\nsource:\n  kind: local\n  path: data.csv\n")
    code = """
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in ('dlt', 'dbt', 'sqlglot'):
        raise AssertionError('Unexpected optional runtime dependency: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from moses.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run([sys.executable, "-c", code, "-w", str(tmp_path / "warehouse"),
                             "prepare", str(recipe)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["manifest"]["dataset"] == "identifiers"


def test_core_cli_exposes_generic_preparation_without_pluto_commands():
    from moses.cli import parser

    help_text = parser().format_help()
    assert "prepare" in help_text
    assert "pluto" not in help_text
    recipe_help = next(action for action in parser()._actions
                       if isinstance(action, argparse._SubParsersAction)).choices["prepare"].format_help()
    assert "--lock" not in recipe_help
    assert "--legacy-source-build" not in recipe_help


def test_core_prepare_rejects_product_collection_without_publication(tmp_path, capsys):
    recipe = tmp_path / "collection.yml"
    recipe.write_text("schema_version: 1\nkind: source_collection\nname: pluto\ninputs: []\n")
    warehouse = tmp_path / "warehouse"
    assert main(["-w", str(warehouse), "prepare", str(recipe)]) == 1
    assert "Unknown recipe keys" in capsys.readouterr().err
    assert Catalog(warehouse).datasets() == []
