"""Offline acceptance of the case-study workflow against an actual PLUTO seed.

The adjacent NYCPlanning checkout is optional; no fabricated fixture stands in
for production input when it is absent. The full live run is opt-in via runner.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pluto_case_study", ROOT / "examples/pluto/run_case_study.py")
case_study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(case_study)


def test_real_pluto_seed_lifecycle_offline(tmp_path, monkeypatch):
    source_repo = ROOT.parent / "data-engineering"
    if not (source_repo / case_study.SEED).exists():
        pytest.skip("requires adjacent NYCPlanning/data-engineering checkout for the real PLUTO seed")
    original_revision = case_study.git_revision
    monkeypatch.setattr(case_study, "ROOT", tmp_path)
    monkeypatch.setattr(case_study, "git_revision", lambda path: original_revision(ROOT if path == tmp_path else path))
    args = SimpleNamespace(data_engineering=source_repo, limit=100, output=tmp_path / "results.json",
                           offline_from=None, seed_only=True)
    assert case_study.run(args) == 0
    report = json.loads(args.output.read_text())
    assert report["status"] == "passed"
    assert report["full_build"] is False
    assert len(report["datasets"]) == 1
    seed = report["datasets"][0]
    assert seed["name"] == "pluto_input_landuse_bldgclass"
    assert seed["query_row_count"] > 100
    assert seed["repeat_unchanged"] and seed["observations"] == 2
    assert seed["export_verified"]
    assert report["seed_identifier_check"] == {"landuse_arrow_type": "string", "leading_zero_codes_preserved": True}
    assert report["lock_replay"]["same_result"]

    # Cached capture replay verifies recorded raw bytes before normalization.
    captures = Path(report["work_directory"]) / "captures"
    args.offline_from = captures
    assert case_study.run(args) == 0
    path = captures / "pluto_input_landuse_bldgclass.csv"
    path.write_bytes(path.read_bytes() + b"\n")
    assert case_study.run(args) == 1
    failed = json.loads(args.output.read_text())
    assert "hash does not match" in failed["datasets"][0]["error"]
