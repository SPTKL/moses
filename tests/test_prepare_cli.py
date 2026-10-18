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


def test_combined_pluto_commands_retired_before_catalog_or_pipeline(tmp_path, capsys, monkeypatch):
    import moses.catalog

    def unexpected(*args, **kwargs):
        raise AssertionError("retired commands must not initialize a catalog")

    monkeypatch.setattr(moses.catalog, "Catalog", unexpected)
    for command in ("build", "run"):
        warehouse = tmp_path / command
        assert main(["-w", str(warehouse), "pluto", command]) == 1
        assert not warehouse.exists()
        assert "standalone dbt project" in capsys.readouterr().err


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
