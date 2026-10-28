"""Capture provisional raw sources linked to an exact published PLUTO release."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .production import _write_json, download_url, head_sources, release_inputs


_BUCKET = "https://edm-recipes.nyc3.digitaloceanspaces.com/"
_XML = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
_TIMEOUT = 30


def _object_url(key: str, name: str) -> str:
    parts = PurePosixPath(key).parts
    if len(parts) != 4 or parts[0] != "raw" or parts[1] != name or parts[2] in {"", ".", ".."} or parts[3] in {"", ".", ".."}:
        raise ValueError(f"Unsafe raw object key for {name}")
    return _BUCKET + quote(key, safe="/")


def _list_objects(prefix: str, *, delimiter: str | None = None) -> dict[str, Any]:
    """Page a public S3 ListObjectsV2 index without object-body downloads."""
    keys: list[dict[str, Any]] = []
    prefixes: list[str] = []
    token: str | None = None
    seen: set[str] = set()
    while True:
        query = {"list-type": "2", "prefix": prefix}
        if delimiter is not None:
            query["delimiter"] = delimiter
        if token is not None:
            query["continuation-token"] = token
        request = Request(_BUCKET + "?" + urlencode(query), headers={"User-Agent": "Moses-PLUTO-discovery/1.0"})
        with urlopen(request, timeout=_TIMEOUT) as response:
            root = ET.fromstring(response.read())
        for item in root.findall("s:Contents", _XML):
            key = item.findtext("s:Key", namespaces=_XML)
            size = item.findtext("s:Size", namespaces=_XML)
            if key is None or size is None or not size.isdecimal() or not key.startswith(prefix):
                raise ValueError("Invalid object entry in bucket listing")
            keys.append({"key": key, "size": int(size), "etag": item.findtext("s:ETag", namespaces=_XML),
                         "last_modified": item.findtext("s:LastModified", namespaces=_XML)})
        prefixes.extend(item.findtext("s:Prefix", namespaces=_XML) for item in root.findall("s:CommonPrefixes", _XML))
        if root.findtext("s:IsTruncated", namespaces=_XML) != "true":
            break
        token = root.findtext("s:NextContinuationToken", namespaces=_XML)
        if not token or token in seen:
            raise ValueError("Bucket listing pagination token missing or repeated")
        seen.add(token)
    return {"keys": keys, "prefixes": prefixes}


def _head_object(key: str, name: str) -> int | str:
    request = Request(_object_url(key, name), method="HEAD", headers={"User-Agent": "Moses-PLUTO-discovery/1.0"})
    try:
        with urlopen(request, timeout=_TIMEOUT) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except Exception as exc:
        return type(exc).__name__


def discover_raw_sources(metadata: dict[str, Any], cache_dir: str | Path, *, max_workers: int = 3) -> dict[str, Any]:
    """Find provisional raw predecessors of inaccessible normalized inputs.

    The published recipe fixes the version and object name. For each private
    normalized object, select the latest matching raw config at or before that
    object's archive time and the published build time. Listing metadata does
    not prove normalized lineage, so selections are explicitly provisional.
    """
    if not 1 <= max_workers <= 3:
        raise ValueError("max_workers must be 1..3")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    inputs = release_inputs(metadata)
    entry_by_name = {entry["id"]: entry for entry in metadata["recipe"]["inputs"]["datasets"]}
    heads = {row["name"]: row for row in head_sources(metadata, max_workers=max_workers)["inputs"]}
    build_time = datetime.fromisoformat(metadata["timestamp"])

    def discover(row: dict[str, Any]) -> dict[str, Any]:
        name = row["name"]
        head = heads[name]
        result = {"name": name, "version": row["version"], "file_type": row["file_type"],
                  "archive_date": entry_by_name[name].get("archive_date"),
                  "normalized_head": head["status"], "normalized_objects": [],
                  "candidate_raw_prefixes": [], "candidate_raw_objects": [], "candidate_raw_configs": []}
        try:
            normalized = _list_objects(f"datasets/{name}/{row['version']}/")
            result["normalized_objects"] = normalized["keys"]
            expected_key = f"datasets/{name}/{row['version']}/{Path(row['url']).name}"
            normalized_file = next((obj for obj in normalized["keys"] if obj["key"] == expected_key), None)
            if normalized_file is None or not normalized_file.get("last_modified"):
                result["selection_error"] = "Exact normalized object absent from bucket listing"
                return result
            if head["status"] not in {401, 403}:
                return result
            archive_time = datetime.fromisoformat(normalized_file["last_modified"].replace("Z", "+00:00"))
            raw_index = _list_objects(f"raw/{name}/", delimiter="/")
            result["raw_prefix_count"] = len(raw_index["prefixes"])
            eligible = []
            for prefix in raw_index["prefixes"]:
                parts = PurePosixPath(prefix).parts
                if len(parts) != 3 or parts[:2] != ("raw", name):
                    continue
                try:
                    stamp = datetime.fromisoformat(parts[2])
                except ValueError:
                    continue
                if stamp <= archive_time and stamp <= build_time:
                    eligible.append((stamp, prefix))
            for stamp, prefix in sorted(eligible, reverse=True):
                result["candidate_raw_prefixes"].append(prefix)
                listing = _list_objects(prefix)
                result["candidate_raw_objects"].extend(listing["keys"])
                config_key = prefix + "config.json"
                if not any(obj["key"] == config_key for obj in listing["keys"]):
                    continue
                config_path = cache / "discovery-configs" / name / stamp.isoformat() / "config.json"
                try:
                    capture = download_url(_object_url(config_key, name), config_path)
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    result["candidate_raw_configs"].append({"key": config_key, "error_type": type(exc).__name__})
                    continue
                candidate = {"key": config_key, "sha256": capture["sha256"], "id": config.get("id"),
                             "version": config.get("version"), "raw_filename": config.get("raw_filename"),
                             "timestamp": config.get("timestamp"),
                             "same_archive_date": stamp.date().isoformat() == result["archive_date"],
                             "version_match": config.get("version") == row["version"]}
                result["candidate_raw_configs"].append(candidate)
                if candidate["id"] != name or not candidate["version_match"] or candidate["timestamp"] != stamp.isoformat():
                    continue
                raw_name = candidate["raw_filename"]
                if (not isinstance(raw_name, str) or raw_name in {"", ".", ".."}
                        or "\\" in raw_name or PurePosixPath(raw_name).name != raw_name):
                    continue
                raw_key = prefix + raw_name
                raw_object = next((obj for obj in listing["keys"] if obj["key"] == raw_key), None)
                if raw_object is None or _head_object(raw_key, name) != 200:
                    continue
                result["selected_raw"] = {"key": raw_key, "size": raw_object["size"], "etag": raw_object["etag"],
                                          "raw_timestamp": candidate["timestamp"], "config_key": config_key,
                                          "config_sha256": capture["sha256"],
                                          "normalized_last_modified": normalized_file["last_modified"],
                                          "selection_policy": "latest matching id/version raw capture at or before exact normalized archive modification and published build timestamp; provisional until normalized lineage verified"}
                result["exact_date_version_match_count"] = sum(x.get("same_archive_date") and x.get("version_match") for x in result["candidate_raw_configs"])
                return result
            result["selection_error"] = "No public raw capture with matching id/version before normalized archive"
        except Exception as exc:
            result.update(selection_error=str(exc)[:300], error_type=type(exc).__name__)
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        rows = list(pool.map(discover, inputs))
    report = {"target_release": metadata["version"], "source_commit": metadata.get("commit"),
              "method": "public bucket listing and exact object HEAD", "inputs": rows}
    _write_json(cache / "public-source-discovery.json", report)
    return report


def acquire_raw_sources(discovery: dict[str, Any], cache_dir: str | Path, *, max_workers: int = 3) -> dict[str, Any]:
    """Download selected raw captures and configs, keeping normalization pending.

    ``selected_raw`` is derived from exact release version, archive object time,
    and matching raw config; it remains provisional until transformed output is
    compared against the historical normalized artifact.
    """
    if not 1 <= max_workers <= 3:
        raise ValueError("max_workers must be 1..3")
    rows = [row for row in discovery.get("inputs", []) if row.get("normalized_head") in {401, 403}]
    if any("selected_raw" not in row for row in rows):
        raise ValueError("Discovery must select every inaccessible normalized input")
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    report_path = cache / "raw-acquisition-report.json"

    def fetch(row: dict[str, Any]) -> dict[str, Any]:
        selected = row["selected_raw"]
        raw_key = selected["key"]
        config_key = selected["config_key"]
        raw_url = _object_url(raw_key, row["name"])
        config_url = _object_url(config_key, row["name"])
        if PurePosixPath(raw_key).parent != PurePosixPath(config_key).parent or PurePosixPath(config_key).name != "config.json":
            raise ValueError(f"Raw file and config are not from one snapshot: {row['name']}")
        target = cache / "raw" / row["name"] / PurePosixPath(raw_key).parts[2]
        result = {"name": row["name"], "version": row["version"], "selection": selected,
                  "normalization_status": "reconstruction_pending", "status": "pending"}
        try:
            result["config_capture"] = download_url(config_url, target / "config.json", expected_sha256=selected["config_sha256"])
            result["raw_capture"] = download_url(raw_url, target / PurePosixPath(raw_key).name)
            if result["raw_capture"]["bytes"] != selected["size"]:
                raise ValueError(f"Raw capture size differs from bucket listing for {row['name']}")
            expected_etag = selected.get("etag")
            actual_etag = result["raw_capture"].get("etag")
            if expected_etag and (not actual_etag or actual_etag.strip('"') != expected_etag.strip('"')):
                raise ValueError(f"Raw capture ETag changed after discovery for {row['name']}; rediscover before retrying")
            result["status"] = "raw_downloaded"
        except HTTPError as exc:
            result.update(status="access_blocked", http_status=exc.code)
        except Exception as exc:
            result.update(status="download_error", error_type=type(exc).__name__, error=str(exc)[:300])
        return result

    found: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch, row): row["name"] for row in rows}
        for future in as_completed(futures):
            result = future.result()
            found[result["name"]] = result
            ordered = [found[row["name"]] for row in rows if row["name"] in found]
            _write_json(report_path, {"target_release": discovery["target_release"], "source_commit": discovery["source_commit"],
                                      "inputs": ordered})
    ordered = [found[row["name"]] for row in rows]
    return {"target_release": discovery["target_release"], "source_commit": discovery["source_commit"],
            "inputs": ordered, "report_path": str(report_path)}
