import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from moses.cli import main
from moses.pluto.cli import _lock


def test_plan_reports_unresolved_without_creating_catalog(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"release_type": "major", "target_release": "26v2"}))
    inventory = Path(__file__).parents[1] / "examples/pluto/inventory.json"
    warehouse = tmp_path / "absent"
    report = tmp_path / "report.json"
    assert main(["-w", str(warehouse), "pluto", "plan", "--inventory", str(inventory),
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
    assert main(["pluto", "compare", str(path), str(path)]) == 0
    assert main(["pluto", "compare", str(path), str(other)]) == 2
    report = tmp_path / "existing.json"
    report.write_text("do not overwrite")
    assert main(["pluto", "compare", str(path), str(path), "--report", str(report)]) == 1
    assert report.read_text() == "do not overwrite"


def test_acquisition_lock_contains_seed_versions():
    versions = {"pluto_pts": "a", "pluto_input_landuse_bldgclass": "b"}
    assert _lock({"input_lock": {"versions": versions, "inputs": []}}) == versions
