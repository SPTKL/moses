"""Exact 26v2-style release captures from a published upstream build manifest.

This module downloads version-addressed objects and freezes their captured
bytes locally. Upstream keys can be overwritten; a version label alone is not
proof of build-time byte identity. It never resolves a ``latest`` pointer or
assumes an HTTP 403 means a source does not exist.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


_BASE = "https://edm-recipes.nyc3.digitaloceanspaces.com/datasets"
_EXT = {"parquet": "parquet", "pg_dump": "sql", "csv": "csv"}
_MAX_WORKERS = 3
_TIMEOUT = 60
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".part", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def release_inputs(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Build exact object keys from the published build's resolved recipe."""
    recipe = metadata.get("recipe") or {}
    entries = (recipe.get("inputs") or {}).get("datasets")
    if not isinstance(entries, list) or len(entries) != 38 or metadata.get("version") != recipe.get("version"):
        raise ValueError("Expected a published PLUTO manifest with 38 resolved inputs")
    rows = []
    for item in entries:
        name, version, file_type = item.get("id"), item.get("version"), item.get("file_type")
        if (not isinstance(name, str) or not _NAME.fullmatch(name)
                or not isinstance(version, str) or not _VERSION.fullmatch(version)
                or version == "latest" or ".." in version or file_type not in _EXT):
            raise ValueError(f"Unresolved or unsupported source in release manifest: {name!r}")
        if item.get("source") != "edm.recipes.datasets":
            raise ValueError(f"Unsupported source connector for {name}: {item.get('source')}")
        base = f"{_BASE}/{quote(name, safe='')}/{quote(version, safe='')}"
        alias = item.get("import_as") or name
        if not isinstance(alias, str) or not _NAME.fullmatch(alias):
            raise ValueError(f"Unsafe source alias in release manifest: {alias!r}")
        rows.append({"name": name, "alias": alias, "version": version,
                     "file_type": file_type, "url": f"{base}/{quote(name, safe='')}.{_EXT[file_type]}",
                     "config_url": f"{base}/config.json"})
    if len({row["name"] for row in rows}) != 38 or len({row["alias"] for row in rows}) != 38:
        raise ValueError("Published PLUTO manifest has duplicate input names or aliases")
    return rows


def head_sources(metadata: dict[str, Any], *, max_workers: int = _MAX_WORKERS) -> dict[str, Any]:
    """Probe exact release objects without downloading their bodies."""
    if not 1 <= max_workers <= _MAX_WORKERS:
        raise ValueError("max_workers must be 1..3")

    def probe(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        request = Request(row["url"], method="HEAD", headers={"User-Agent": "Moses-PLUTO/1.0"})
        try:
            with urlopen(request, timeout=_TIMEOUT) as response:
                result.update(status=response.status, content_length=response.headers.get("Content-Length"), etag=response.headers.get("ETag"))
        except HTTPError as exc:
            result.update(status=exc.code, content_length=exc.headers.get("Content-Length"), etag=exc.headers.get("ETag"))
        except Exception as exc:
            result.update(status="error", error_type=type(exc).__name__)
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        rows = list(pool.map(probe, release_inputs(metadata)))
    return {"target_release": metadata["version"], "source_commit": metadata.get("commit"), "method": "HEAD", "inputs": rows}


def download_url(url: str, path: str | Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    """Stream a versioned object into an atomic, hash-verified local cache.

    A rerun rehashes completed files against the saved receipt. A missing or
    invalid receipt forces a fresh transfer. Partial files are never reused.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt = destination.with_name(destination.name + ".capture.json")
    if expected_sha256 is not None and (len(expected_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)):
        raise ValueError("expected_sha256 must be a 64-character hexadecimal digest")
    expected_sha256 = expected_sha256.lower() if expected_sha256 else None
    if destination.is_file() and receipt.is_file():
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            actual = _digest(destination)
            if saved.get("url") == url and saved.get("sha256") == actual and destination.stat().st_size == saved.get("bytes") and (expected_sha256 is None or actual == expected_sha256):
                return {**saved, "path": str(destination), "cached": True}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    partial = destination.with_name(destination.name + ".partial")
    request = Request(url, method="GET", headers={"User-Agent": "Moses-PLUTO/1.0"})
    try:
        with urlopen(request, timeout=_TIMEOUT) as response, partial.open("wb") as output:
            if response.status != 200:
                raise ValueError(f"GET returned HTTP {response.status} for {url}")
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdecimal() or int(declared) <= 0):
                raise ValueError(f"Invalid Content-Length for {url}")
            digest = hashlib.sha256()
            count = 0
            for block in iter(lambda: response.read(1024 * 1024), b""):
                output.write(block)
                digest.update(block)
                count += len(block)
            output.flush()
            os.fsync(output.fileno())
            if count == 0 or (declared is not None and count != int(declared)):
                raise ValueError(f"Incomplete transfer for {url}: {count} of {declared} bytes")
            sha256 = digest.hexdigest()
            if expected_sha256 is not None and sha256 != expected_sha256:
                raise ValueError(f"SHA256 mismatch for {url}")
            result = {"url": url, "sha256": sha256, "bytes": count, "etag": response.headers.get("ETag"),
                      "retrieved_at": datetime.now(timezone.utc).isoformat(),
                      "last_modified": response.headers.get("Last-Modified"),
                      "content_length": int(declared) if declared else None}
        os.replace(partial, destination)
        _write_json(receipt, result)
        return {**result, "path": str(destination), "cached": False}
    finally:
        partial.unlink(missing_ok=True)


def acquire_release_sources(
    metadata: dict[str, Any], cache_dir: str | Path, *,
    ingest_adapter: Callable[[dict[str, Any], Path, dict[str, Any]], dict[str, Any]] | None = None,
    max_workers: int = _MAX_WORKERS,
) -> dict[str, Any]:
    """Checkpoint each exact artifact; an adapter may ingest it into Moses.

    HTTP 403/404 and parser failures remain per-source blocked statuses. A
    verified data artifact stays downloaded even if its config.json is private.
    """
    if not 1 <= max_workers <= _MAX_WORKERS:
        raise ValueError("max_workers must be 1..3")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    rows = release_inputs(metadata)
    report_path = cache / "acquisition-report.json"

    def fetch(row: dict[str, Any]) -> dict[str, Any]:
        target = cache / "sources" / row["name"] / row["version"]
        artifact = target / Path(row["url"]).name
        result = dict(row)
        try:
            result["capture"] = download_url(row["url"], artifact)
            try:
                result["config_capture"] = download_url(row["config_url"], target / "config.json")
            except HTTPError as exc:
                result["config_status"] = exc.code
            except Exception as exc:
                result["config_status"] = type(exc).__name__
            result["status"] = "downloaded"
        except HTTPError as exc:
            result.update(status="access_blocked" if exc.code in {401, 403} else "http_error", http_status=exc.code)
        except Exception as exc:
            result.update(status="download_error", error_type=type(exc).__name__, error=str(exc)[:300])
        return result

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch, row): row["name"] for row in rows}
        for future in as_completed(futures):
            row = future.result()
            if row["status"] == "downloaded" and ingest_adapter is not None:
                try:
                    row["ingest"] = ingest_adapter(row, Path(row["capture"]["path"]), row["capture"])
                    row["status"] = "acquired"
                except Exception as exc:
                    row.update(status="adapter_error", error_type=type(exc).__name__, error=str(exc)[:300])
            results[row["name"]] = row
            ordered = [results[item["name"]] for item in rows if item["name"] in results]
            _write_json(report_path, {"target_release": metadata["version"], "source_commit": metadata.get("commit"),
                                      "inputs": ordered})
    ordered = [results[item["name"]] for item in rows]
    return {"target_release": metadata["version"], "source_commit": metadata.get("commit"), "inputs": ordered,
            "report_path": str(report_path)}
