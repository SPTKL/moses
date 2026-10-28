import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pluto_example.cli import _lock, main


def test_plan_reports_unresolved_without_creating_catalog(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"release_type": "major", "target_release": "26v2"}))
    inventory = Path(__file__).parents[1] / "scripts/inventory.json"
    warehouse = tmp_path / "absent"
    report = tmp_path / "report.json"
    assert main(["-w", str(warehouse), "plan", "--inventory", str(inventory),
                 "--config", str(config), "--report", str(report)]) == 2
    assert not warehouse.exists()
    value = json.loads(capsys.readouterr().out)
    assert len(value["inputs"]) == 38 and len(value["seeds"]) == 11
    assert not value["build_ready"]
    assert json.loads(report.read_text()) == value


def test_compare_exit_codes_and_report_overwrite_prevention(tmp_path, capsys):
    path = tmp_path / "table.parquet"
    other = tmp_path / "other.parquet"
    pq.write_table(pa.table({"bbl": ["1000010001"], "value": ["a"]}), path)
    pq.write_table(pa.table({"bbl": ["1000010001"], "value": ["b"]}), other)
    assert main(["compare", str(path), str(path)]) == 0
    assert main(["compare", str(path), str(other)]) == 2
    report = tmp_path / "existing.json"
    report.write_text("do not overwrite")
    assert main(["compare", str(path), str(path), "--report", str(report)]) == 1
    assert report.read_text() == "do not overwrite"


def test_acquisition_lock_contains_seed_versions():
    versions = {"pluto_pts": "a", "pluto_input_landuse_bldgclass": "b"}
    assert _lock({"input_lock": {"versions": versions, "inputs": []}}) == versions


def test_combined_pluto_commands_retired_before_catalog_or_pipeline(tmp_path, capsys, monkeypatch):
    import moses

    def unexpected(*args, **kwargs):
        raise AssertionError("retired commands must not initialize a catalog")

    monkeypatch.setattr(moses, "Catalog", unexpected)
    for command in ("build", "run"):
        warehouse = tmp_path / command
        assert main(["-w", str(warehouse), command]) == 1
        assert not warehouse.exists()
        assert "standalone dbt project" in capsys.readouterr().err


def test_collection_prepare_uses_installed_moses_and_restores_runtime(tmp_path, monkeypatch, capsys):
    import os
    import moses
    import pluto_example.prepared

    warehouse = tmp_path / "warehouse"
    catalog = object()
    monkeypatch.setattr(moses, "Catalog", lambda path: catalog if path == str(warehouse) else None)
    monkeypatch.setenv("GEOSUPPORT_RUNTIME", "local")
    observed = {}

    def prepare(received_catalog, recipe, **options):
        observed.update(catalog=received_catalog, recipe=recipe, options=options,
                        runtime=os.environ["GEOSUPPORT_RUNTIME"])
        return {"status": "prepared", "input_id": "fixture"}

    monkeypatch.setattr(pluto_example.prepared, "prepare_collection", prepare)
    recipe = tmp_path / "collection.yml"
    lock = tmp_path / "lock.json"
    output = tmp_path / "prepared"
    assert main(["-w", str(warehouse), "prepare", str(recipe), "--lock", str(lock),
                 "--output-dir", str(output), "--geosupport-runtime", "docker"]) == 0
    assert observed["catalog"] is catalog
    assert observed["recipe"] == recipe
    assert observed["options"]["input_lock"] == str(lock)
    assert observed["options"]["output_dir"] == str(output)
    assert observed["runtime"] == "docker"
    assert os.environ["GEOSUPPORT_RUNTIME"] == "local"
    assert json.loads(capsys.readouterr().out)["status"] == "prepared"
