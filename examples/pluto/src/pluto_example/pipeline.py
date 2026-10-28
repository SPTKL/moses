"""Capture and import a published PLUTO release, with explicit readiness states.

Raw reconstructions use a separate namespace. Successful ingestion does not
establish historical normalized-input parity or full PLUTO build parity.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Callable

from .production import _digest, _write_json, download_url, release_inputs, acquire_release_sources


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def capture_seeds(metadata: dict, repository: str | Path, cache: str | Path) -> list[dict]:
    """Read seed blobs at the release commit without changing the checkout."""
    commit = metadata.get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Published build must identify a full Git commit")
    repository, cache = Path(repository).resolve(), Path(cache).resolve()
    def git(*args):
        return subprocess.run(["git", "-C", str(repository), *args], check=True, capture_output=True).stdout
    paths = git("ls-tree", "-r", "--name-only", commit, "products/pluto/seeds").decode().splitlines()
    paths = [path for path in paths if path.endswith((".csv", "/_seeds.yml"))]
    if sum(path.endswith(".csv") for path in paths) != 11:
        raise ValueError("Expected 11 seed CSVs at the published PLUTO source commit")
    records = []
    for path in paths:
        data = git("show", f"{commit}:{path}")
        destination = cache / "seeds" / Path(path).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"Cached seed differs from release commit: {destination.name}")
        destination.write_bytes(data)
        records.append({"path": str(destination), "upstream_path": path, "source_commit": commit,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    _write_json(cache / "seeds/manifest.json", records)
    return records


def capture_production(release: str, repository: str | Path, cache: str | Path) -> dict:
    """Download pinned recipe artifacts and discover public raw fallback captures."""
    if not re.fullmatch(r"[0-9]{2}v[0-9]+(?:\.[0-9]+)?", release):
        raise ValueError("Expected a published PLUTO release such as 26v2")
    cache = Path(cache).resolve()
    base = f"https://edm-publishing.nyc3.digitaloceanspaces.com/db-pluto/publish/{release}"
    capture = download_url(base + "/build_metadata.json", cache / "release/build_metadata.json")
    metadata = _read(capture["path"])
    if metadata.get("version") != release:
        raise ValueError("Published build metadata does not match requested release")
    release_inputs(metadata)
    download_url(base + "/source_data_versions.csv", cache / "release/source_data_versions.csv")
    seeds = capture_seeds(metadata, repository, cache)
    exact = acquire_release_sources(metadata, cache)
    from .raw import discover_raw_sources, acquire_raw_sources
    discovery = discover_raw_sources(metadata, cache)
    raw = acquire_raw_sources(discovery, cache)
    return {"target_release": release, "source_commit": metadata["commit"],
            "normalized_artifacts": exact, "raw_captures": raw, "seeds": seeds,
            "build_ready": False, "production_parity": False}


def _verified_capture(capture):
    path = Path(capture["path"])
    if path.stat().st_size != capture["bytes"] or _digest(path) != capture["sha256"]:
        raise ValueError(f"Capture checksum mismatch: {path}")
    return path


def ingest_production(catalog, cache: str | Path, *, extension_directory: str | Path,
                      progress: Callable[[str], None] | None = None) -> dict:
    """Sequential, checkpointed ingestion of full sources; no sampling or omissions.

    Failed sources are recorded and processing continues. Only fully ingested
    versions enter the lock. Raw candidates always retain provisional lineage.
    """
    from .legacy import normalize_legacy_dump
    from .raw_normalize import normalize_raw
    cache = Path(cache).resolve()
    metadata = _read(cache / "release/build_metadata.json")
    expected = release_inputs(metadata)
    exact = {row["name"]: row for row in _read(cache / "acquisition-report.json")["inputs"]}
    raw_path = cache / "raw-acquisition-report.json"
    raw = {row["name"]: row for row in _read(raw_path)["inputs"]} if raw_path.exists() else {}
    seeds = _read(cache / "seeds/manifest.json")
    report_path = cache / "production-ingestion.json"
    previous = _read(report_path) if report_path.exists() else {}
    prior = {row["catalog_name"]: row for row in previous.get("inputs", [])}
    records = []
    normalized_dir = cache / "normalized"
    normalized_dir.mkdir(exist_ok=True)
    normalization_reports = {}
    for name in ("pipeline-normalization.json", "raw-normalization.json", "legacy-normalization.json"):
        path = normalized_dir / name
        if path.exists():
            saved = _read(path)
            if "normalized_sources" in saved:
                normalization_reports.update({r["dataset"]: r for r in saved["normalized_sources"]})
            else:
                normalization_reports.update(saved)

    def checkpoint():
        successful = [r for r in records if r["status"] == "ingested"]
        report = {"target_release": metadata["version"], "source_commit": metadata["commit"],
                  "inputs": records, "expected_source_count": len(expected), "expected_seed_count": 11,
                  "source_count_ingested": sum(r["kind"] != "seed" for r in successful),
                  "seed_count_ingested": sum(r["kind"] == "seed" for r in successful),
                  "input_lock": {"versions": {r["catalog_name"]: r["catalog_version"] for r in successful}},
                  "build_ready": False, "production_parity": False,
                  "readiness_note": "Raw candidates require source contracts, pending recipe steps and historical lineage validation."}
        _write_json(report_path, report)
        return report

    def accept(record, path, provenance):
        digest = _digest(path)
        fingerprint = hashlib.sha256(json.dumps({"sha256": digest, "provenance": provenance}, sort_keys=True).encode()).hexdigest()
        old = prior.get(record["catalog_name"], {})
        if old.get("status") == "ingested" and old.get("fingerprint") == fingerprint:
            try:
                catalog.get_version(record["catalog_name"], old["catalog_version"])
                record.update(old, resumed=True)
                return
            except (KeyError, FileNotFoundError):
                pass
        result = catalog.ingest(path, name=record["catalog_name"], provenance=provenance)
        record.update(status="ingested", catalog_version=result["version"], rows=result["row_count"], fingerprint=fingerprint)

    def normalized(name, source, config=None):
        saved = normalization_reports.get(name)
        if saved and saved.get("normalized_path"):
            output = Path(saved["normalized_path"])
            source_hash = saved.get("source_sha256", saved.get("original_sha256"))
            code_path = Path(__file__).with_name("raw_normalize.py" if config else "legacy.py")
            code_matches = saved.get("code_sha256") == _digest(code_path)
            config_matches = config is None or saved.get("config_sha256") == hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
            if output.exists() and source_hash == _digest(source) and saved.get("normalized_sha256") == _digest(output) and code_matches and config_matches:
                return saved
        if config is None:
            result = normalize_legacy_dump(source, normalized_dir / f"{name}.parquet", dataset=name)
        else:
            result = normalize_raw(source, config, normalized_dir / f"raw__{name}.parquet", extension_directory=Path(extension_directory))
        normalization_reports[name] = result
        _write_json(normalized_dir / "pipeline-normalization.json", normalization_reports)
        return result

    for item in expected:
        artifact = exact.get(item["name"], {})
        is_exact = artifact.get("status") in {"downloaded", "acquired"}
        record = {"source_name": item["name"], "source_version": item["version"],
                  "catalog_name": item["alias"] if is_exact else "raw__" + item["alias"],
                  "kind": "normalized_archive" if is_exact else "raw_candidate", "status": "pending"}
        records.append(record)
        if progress:
            progress(f"Ingesting {record['catalog_name']}")
        try:
            provenance = {"target_release": metadata["version"], "source_commit": metadata["commit"], "source": item}
            if is_exact:
                source = _verified_capture(artifact["capture"])
                provenance.update(evidence="published_versioned_normalized_artifact", capture=artifact["capture"])
                if item["file_type"] == "pg_dump":
                    detail = normalized(item["name"], source)
                    provenance["normalization"] = detail
                    source = Path(detail["normalized_path"])
                record["normalization_pending"] = False
            else:
                capture = raw[item["name"]]
                if capture["status"] != "raw_downloaded":
                    raise ValueError("Raw source download is incomplete")
                source = _verified_capture(capture["raw_capture"])
                config_path = _verified_capture(capture["config_capture"])
                detail = normalized(item["name"], source, _read(config_path))
                record["normalization_pending"] = detail["normalization_pending"]
                record["recipe_steps_pending"] = detail["recipe_steps_pending"]
                record["geometry_status"] = detail["geometry_status"]
                provenance.update(evidence="provisional_historical_raw_candidate", raw_capture=capture["raw_capture"],
                                  config_capture=capture["config_capture"], selection=capture["selection"], normalization=detail)
                source = Path(detail["normalized_path"])
            accept(record, source, provenance)
        except Exception as exc:
            record.update(status="ingest_error", error_type=type(exc).__name__, error=str(exc)[:1000])
        checkpoint()
    for item in seeds:
        if not item["path"].endswith(".csv"):
            continue
        record = {"catalog_name": Path(item["path"]).stem, "kind": "seed", "status": "pending"}
        records.append(record)
        try:
            source = _verified_capture(item)
            accept(record, source, {"evidence": "release_commit_seed", **item,
                   "typing_policy": "CSV text preserved; dbt seed typing not yet applied"})
        except Exception as exc:
            record.update(status="ingest_error", error_type=type(exc).__name__, error=str(exc)[:1000])
        checkpoint()
    return checkpoint()
