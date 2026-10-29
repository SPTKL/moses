"""Offline capture and ingestion boundaries for published PLUTO releases."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from pluto_example import pipeline


def _capture(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class _Catalog:
    def __init__(self):
        self.calls = []
        self.versions = {}

    def ingest(self, path, *, name, provenance):
        self.calls.append((name, Path(path).read_bytes(), provenance))
        version = f"version-{name}"
        self.versions[name, version] = {"version": version}
        return {"version": version, "row_count": 1}

    def get_version(self, name, version):
        return self.versions[name, version]


def _ingestion_fixture(tmp_path, monkeypatch, *, corrupt_exact=False, fail_raw=False):
    cache = tmp_path / "capture"
    _write(cache / "release/build_metadata.json", {"version": "26v2", "commit": "a" * 40})
    monkeypatch.setattr(pipeline, "release_inputs", lambda _metadata: [
        {"name": "exact", "alias": "exact_input", "version": "v1", "file_type": "parquet"},
        {"name": "alternate", "alias": "alternate_input", "version": "v2", "file_type": "parquet"},
    ])
    exact = cache / "sources/exact.parquet"
    exact.parent.mkdir(parents=True)
    exact.write_bytes(b"exact published parquet")
    exact_receipt = _capture(exact)
    if corrupt_exact:
        exact.write_bytes(b"tampered published parquet")
    raw = cache / "raw/alternate.csv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"id\n001\n")
    config = cache / "raw/config.json"
    _write(config, {"dataset": "alternate", "version": "v2"})
    _write(cache / "acquisition-report.json", {"inputs": [
        {"name": "exact", "status": "downloaded", "capture": exact_receipt},
        {"name": "alternate", "status": "access_blocked"},
    ]})
    _write(cache / "raw-acquisition-report.json", {"inputs": [{
        "name": "alternate", "status": "raw_downloaded", "raw_capture": _capture(raw),
        "config_capture": _capture(config), "selection": {"status": "provisional"},
    }]})
    _write(cache / "seeds/manifest.json", [])
    normalized = cache / "normalized/raw__alternate.parquet"

    def normalize(source, options, destination, *, extension_directory):
        if fail_raw:
            raise RuntimeError("normalizer failed")
        assert Path(source).read_bytes() == b"id\n001\n"
        assert options["version"] == "v2"
        assert Path(extension_directory) == tmp_path / "extensions"
        normalized.parent.mkdir(parents=True, exist_ok=True)
        normalized.write_bytes(b"normalized alternate")
        return {"normalized_path": str(normalized), "normalization_pending": True,
                "recipe_steps_pending": ["historical parity"], "geometry_status": "pending"}

    monkeypatch.setattr("pluto_example.raw_normalize.normalize_raw", normalize)
    return cache


def test_exact_and_raw_ingest_have_separate_lineage_and_never_claim_readiness(tmp_path, monkeypatch):
    cache = _ingestion_fixture(tmp_path, monkeypatch)
    catalog = _Catalog()
    report = pipeline.ingest_production(catalog, cache, extension_directory=tmp_path / "extensions")
    assert [r["catalog_name"] for r in report["inputs"]] == ["exact_input", "raw__alternate_input"]
    assert [r["kind"] for r in report["inputs"]] == ["normalized_archive", "raw_candidate"]
    assert [r["status"] for r in report["inputs"]] == ["ingested", "ingested"]
    assert report["inputs"][1]["normalization_pending"] is True
    assert report["input_lock"]["versions"] == {
        "exact_input": "version-exact_input", "raw__alternate_input": "version-raw__alternate_input"}
    assert report["build_ready"] is False and report["production_parity"] is False
    assert catalog.calls[0][2]["evidence"] == "published_versioned_normalized_artifact"
    assert catalog.calls[1][2]["evidence"] == "provisional_historical_raw_candidate"
    # A completed checkpoint resumes without reingesting either input.
    again = pipeline.ingest_production(catalog, cache, extension_directory=tmp_path / "extensions")
    assert len(catalog.calls) == 2
    assert all(r.get("resumed") for r in again["inputs"])


@pytest.mark.parametrize("corrupt_exact,fail_raw,locked", [
    (True, False, {"raw__alternate_input"}),
    (False, True, {"exact_input"}),
])
def test_failed_sources_are_checkpointed_and_excluded_from_lock(
    tmp_path, monkeypatch, corrupt_exact, fail_raw, locked
):
    cache = _ingestion_fixture(tmp_path, monkeypatch, corrupt_exact=corrupt_exact, fail_raw=fail_raw)
    report = pipeline.ingest_production(_Catalog(), cache, extension_directory=tmp_path / "extensions")
    persisted = json.loads((cache / "production-ingestion.json").read_text())
    assert persisted == report
    assert {r["catalog_name"] for r in report["inputs"] if r["status"] == "ingest_error"} == (
        {"exact_input", "raw__alternate_input"} - locked)
    assert set(report["input_lock"]["versions"]) == locked
    assert not report["build_ready"]


def test_capture_seeds_reads_release_commit_without_switching_checkout(tmp_path):
    repo = tmp_path / "data-engineering"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    seed_dir = repo / "products/pluto/seeds"
    seed_dir.mkdir(parents=True)
    for number in range(11):
        (seed_dir / f"seed_{number}.csv").write_text(f"code\n00{number}\n")
    (seed_dir / "_seeds.yml").write_text("version: 2\n")
    subprocess.run(["git", "-C", str(repo), "add", "products/pluto/seeds"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.test", "commit", "-qm", "seeds"], check=True)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (seed_dir / "seed_0.csv").write_text("working tree changed\n")
    cache = tmp_path / "cache"
    records = pipeline.capture_seeds({"commit": commit}, repo, cache)
    csv_records = [row for row in records if row["path"].endswith(".csv")]
    assert len(csv_records) == 11 and len(records) == 12
    assert (cache / "seeds/seed_0.csv").read_text() == "code\n000\n"
    assert (seed_dir / "seed_0.csv").read_text() == "working tree changed\n"
    assert {row["source_commit"] for row in records} == {commit}
    assert json.loads((cache / "seeds/manifest.json").read_text()) == records
    (cache / "seeds/seed_0.csv").write_text("corrupt\n")
    with pytest.raises(ValueError, match="Cached seed differs"):
        pipeline.capture_seeds({"commit": commit}, repo, cache)


def test_capture_production_rejects_wrong_published_release_before_other_capture(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, destination):
        calls.append(url)
        _write(Path(destination), {"version": "26v1", "commit": "a" * 40})
        return {"path": str(destination)}

    monkeypatch.setattr(pipeline, "download_url", fake_download)
    with pytest.raises(ValueError, match="does not match requested release"):
        pipeline.capture_production("26v2", tmp_path / "unused-repo", tmp_path / "cache")
    assert len(calls) == 1 and calls[0].endswith("/26v2/build_metadata.json")
