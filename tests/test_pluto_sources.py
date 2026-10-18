import hashlib
import json
from pathlib import Path
import zipfile
from copy import deepcopy

import pytest

from moses.pluto.sources import acquire_sources, plan_sources
from moses.catalog import Catalog


INVENTORY = json.loads((Path(__file__).parents[1] / "examples/pluto/inventory.json").read_text())
NAMES = [item["name"] for item in INVENTORY["recipe"]["major"]["inputs"]["datasets"]]
REFRESH = {item["name"] for item in INVENTORY["recipe"]["minor"]["inputs"]["datasets"] if item.get("version") == "latest"}
SHA = hashlib.sha256(b"id\n1\n").hexdigest()


def _artifact(path="/tmp/exact.csv", **overrides):
    return {"kind": "full", "representation": "normalized_recipe", "normalization_status": "ready",
            "path": path, "sha256": SHA, **overrides}


def _config(release_type="major"):
    return {"release_type": release_type, "target_release": "26v2", "version_prev": "26v1",
            "previous_release": {"inputs": [{"name": name, "version": "old"} for name in NAMES]},
            "available": {name: {"latest_version": "new", "versions": {
                "new": {"artifacts": [_artifact()]}, "old": {"artifacts": [_artifact()]},
                "26v1": {"artifacts": [_artifact()]}}} for name in NAMES}}


def test_major_resolves_all_38_and_previous_pluto():
    plan = plan_sources(INVENTORY, _config())
    assert plan["ready"] is True
    assert plan["build_ready"] is False  # Eleven local seeds remain to be pinned.
    assert len(plan["inputs"]) == 38
    assert len(plan["seeds"]) == 11
    assert all(item["version"] == "new" for item in plan["inputs"] if item["name"] != "dcp_pluto")
    previous = next(item for item in plan["inputs"] if item["name"] == "dcp_pluto")
    assert (previous["alias"], previous["version"], previous["version_policy"]) == ("previous_pluto", "26v1", "VERSION_PREV")
    assert plan["target_release"] == "26v2"


def test_minor_inherits_versions_except_explicit_refresh():
    plan = plan_sources(INVENTORY, _config("minor"))
    assert plan["ready"] is True
    assert len(REFRESH) == 9
    for row in plan["inputs"]:
        expected = "26v1" if row["name"] == "dcp_pluto" else "new" if row["name"] in REFRESH else "old"
        assert row["version"] == expected


def test_missing_previous_release_and_version_prev_are_actionable():
    config = _config("minor")
    del config["previous_release"]
    del config["version_prev"]
    plan = plan_sources(INVENTORY, config)
    assert plan["ready"] is False
    assert any(row["status"] == "missing_previous_release" for row in plan["inputs"])
    assert next(row for row in plan["inputs"] if row["name"] == "dcp_pluto")["status"] == "missing_version_prev"
    assert all(row.get("action") for row in plan["inputs"] if row["status"] != "ready")


@pytest.mark.parametrize("artifact,status", [
    ({"kind": "sample"}, "sample"),
    ({"kind": "alternate"}, "alternate"),
    (_artifact(representation="raw"), "raw_unstaged"),
    (_artifact(normalization_status="pending"), "normalization_pending"),
])
def test_non_exact_sources_do_not_pass_preflight(artifact, status):
    config = _config()
    config["available"][NAMES[0]]["versions"]["new"]["artifacts"] = [artifact]
    plan = plan_sources(INVENTORY, config)
    assert plan["ready"] is False
    assert plan["inputs"][0]["status"] == status


class _Catalog:
    def __init__(self, root):
        self.root = root
        self.calls = []

    def ingest(self, path, *, name, provenance):
        self.calls.append((Path(path).read_bytes(), name, provenance))
        return {"version": "catalog-v1"}


def _local_plan(tmp_path, artifact):
    config = _config()
    for name in NAMES:
        config["available"][name]["versions"]["new"]["artifacts"] = [artifact]
        config["available"][name]["versions"]["26v1"]["artifacts"] = [artifact]
    return plan_sources(INVENTORY, config)


def test_checksum_failure_precedes_any_ingestion(tmp_path):
    path = tmp_path / "exact.csv"
    path.write_bytes(b"changed")
    plan = _local_plan(tmp_path, _artifact(str(path)))
    catalog = _Catalog(tmp_path / "catalog")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        acquire_sources(catalog, plan)
    assert catalog.calls == []


def test_zip_member_is_exact_and_archive_is_retained(tmp_path):
    path = tmp_path / "capture.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data/selected.csv", b"id\n1\n")
        archive.writestr("data/other.csv", b"id\n2\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    artifact = _artifact(str(path), sha256=sha, member="data/selected.csv")
    plan = _local_plan(tmp_path, artifact)
    catalog = _Catalog(tmp_path / "catalog")
    report = acquire_sources(catalog, plan)
    assert len(catalog.calls) == 38
    assert all(payload == b"id\n1\n" for payload, _, _ in catalog.calls)
    assert all(item["stored_archive"] for item in report["inputs"])
    assert (catalog.root / "pluto_archives" / f"{sha}.zip").read_bytes() == path.read_bytes()
    assert report["input_lock"]["inputs"][0]["archive_member"] == "data/selected.csv"


def test_missing_or_unsafe_zip_member_blocks_acquisition(tmp_path):
    path = tmp_path / "capture.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("only.csv", b"id\n1\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    config = _config()
    config["available"][NAMES[0]]["versions"]["new"]["artifacts"] = [_artifact(str(path), sha256=sha, member="../only.csv")]
    assert plan_sources(INVENTORY, config)["inputs"][0]["status"] == "missing_artifact"
    plan = _local_plan(tmp_path, _artifact(str(path), sha256=sha, member="missing.csv"))
    catalog = _Catalog(tmp_path / "catalog")
    with pytest.raises(ValueError, match="must occur exactly once"):
        acquire_sources(catalog, plan)
    assert catalog.calls == []


def test_pinned_plan_does_not_reresolve_latest(tmp_path):
    path = tmp_path / "exact.csv"
    path.write_bytes(b"id\n1\n")
    config = _config()
    for name in NAMES:
        config["available"][name]["versions"]["new"]["artifacts"] = [_artifact(str(path))]
        config["available"][name]["versions"]["26v1"]["artifacts"] = [_artifact(str(path))]
    plan = plan_sources(INVENTORY, config)
    for name in NAMES:
        config["available"][name]["latest_version"] = "changed-after-plan"
    catalog = _Catalog(tmp_path / "catalog")
    report = acquire_sources(catalog, plan)
    assert report["ready"] is True
    assert all(item["upstream_version"] in {"new", "26v1"} for item in report["inputs"])


def test_unresolved_plan_blocks_catalog_changes(tmp_path):
    plan = plan_sources(INVENTORY, {"release_type": "major", "target_release": "26v2"})
    catalog = _Catalog(tmp_path / "catalog")
    with pytest.raises(ValueError, match="unresolved"):
        acquire_sources(catalog, plan)
    assert catalog.calls == []


def test_real_catalog_acquires_sources_and_seeds_with_types_and_lock(tmp_path):
    source = tmp_path / "capture.csv"
    source.write_text("parcel,quantity\n00123,2\n", encoding="utf-8")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = _artifact(str(source), sha256=sha, ingest_options={"types": {"parcel": "string", "quantity": "int64"}, "key": "parcel"})
    config = _config()
    for name in NAMES:
        version = "26v1" if name == "dcp_pluto" else "new"
        config["available"][name]["versions"][version]["artifacts"] = [artifact]
    config["seeds"] = {seed["name"]: {"path": str(source), "sha256": sha,
                                       "types": {"parcel": "string", "quantity": "int64"}}
                       for seed in INVENTORY["local_seeds"]}
    plan = plan_sources(INVENTORY, config)
    assert plan["ready"] and plan["build_ready"]
    catalog = Catalog(tmp_path / "catalog")
    report = acquire_sources(catalog, plan)
    assert report["build_ready"]
    assert len(report["inputs"]) == 38 and len(report["seeds"]) == 11
    assert len(report["input_lock"]["versions"]) == 49
    assert report["input_lock"]["versions"]["previous_pluto"] == catalog.get_version("previous_pluto")["version"]
    assert catalog.read("pluto_pts").to_pylist() == [{"parcel": "00123", "quantity": 2}]
    seed_name = INVENTORY["local_seeds"][0]["name"]
    assert catalog.read(seed_name).to_pylist()[0]["parcel"] == "00123"
    provenance = catalog.get_version("pluto_pts")["provenance"]["pluto_source"]
    assert provenance["representation"] == "normalized_recipe"
    assert provenance["target_release"] == "26v2"
    assert provenance["ingest_options"]["types"] == {"parcel": "string", "quantity": "int64"}


def test_source_changed_after_plan_is_rejected(tmp_path):
    source = tmp_path / "capture.csv"
    source.write_bytes(b"id\n1\n")
    plan = _local_plan(tmp_path, _artifact(str(source)))
    source.write_bytes(b"id\n2\n")
    catalog = _Catalog(tmp_path / "catalog")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        acquire_sources(catalog, plan)
    assert catalog.calls == []


def test_mutable_original_cannot_change_staged_ingestion(tmp_path):
    source = tmp_path / "capture.csv"
    source.write_bytes(b"id\n1\n")
    plan = _local_plan(tmp_path, _artifact(str(source)))

    class MutatingCatalog(_Catalog):
        def ingest(self, path, *, name, provenance):
            result = super().ingest(path, name=name, provenance=provenance)
            if len(self.calls) == 1:
                source.write_bytes(b"id\n999\n")
            return result

    catalog = MutatingCatalog(tmp_path / "catalog")
    acquire_sources(catalog, plan)
    assert len(catalog.calls) == 38
    assert all(payload == b"id\n1\n" for payload, _, _ in catalog.calls)


def test_plain_shapefile_requires_archive_and_import_options_are_restricted():
    config = _config()
    config["available"][NAMES[0]]["versions"]["new"]["artifacts"] = [_artifact("/tmp/shape.shp")]
    plan = plan_sources(INVENTORY, config)
    assert plan["inputs"][0]["status"] == "adapter_unavailable"
    config["available"][NAMES[0]]["versions"]["new"]["artifacts"] = [_artifact(ingest_options={"infer_types": True})]
    with pytest.raises(ValueError, match="ingest_options"):
        plan_sources(INVENTORY, config)


@pytest.mark.parametrize("change", ["missing", "empty", "duplicate"])
def test_malformed_seed_inventory_never_claims_build_ready(change):
    inventory = deepcopy(INVENTORY)
    if change == "missing":
        inventory.pop("local_seeds")
    elif change == "empty":
        inventory["local_seeds"] = []
    else:
        inventory["local_seeds"][-1]["name"] = inventory["local_seeds"][0]["name"]
    with pytest.raises(ValueError, match="11 uniquely named"):
        plan_sources(inventory, _config())


def test_duplicate_input_alias_rejected():
    inventory = deepcopy(INVENTORY)
    inventory["recipe"]["major"]["inputs"]["datasets"][0]["import_as"] = "previous_pluto"
    with pytest.raises(ValueError, match="aliases must be unique"):
        plan_sources(inventory, _config())
