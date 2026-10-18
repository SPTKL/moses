"""Pure PLUTO source resolution and exact local-capture acquisition.

The planner never asks a live service what ``latest`` means. Callers provide an
explicit latest-version pointer and immutable, checksum-bearing artifacts.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any
import zipfile


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_READABLE = {".csv", ".tsv", ".parquet", ".geoparquet", ".geojson", ".json", ".gpkg", ".shp"}
_MAX_ARCHIVE_BYTES = 4 * 1024**3
_MAX_MEMBER_BYTES = 4 * 1024**3
_INGEST_OPTIONS = {"key", "types", "format", "layer", "x", "y", "crs"}
_ACTIONS = {
    "missing_previous_release": "Supply the latest published PLUTO source manifest in previous_release.inputs.",
    "missing_version_prev": "Set version_prev to the exact previous PLUTO version (VERSION_PREV).",
    "missing_release_metadata": "Supply available[name] with explicit version and artifact metadata.",
    "missing_latest_pointer": "Set available[name].latest_version to an explicit published version.",
    "missing_version": "Supply metadata for the exact selected source version.",
    "missing_artifact": "Supply a complete, exact local artifact with path and SHA256.",
    "missing_access": "Obtain an approved complete capture, then supply its local path and SHA256.",
    "sample": "Replace the bounded sample with the complete source artifact.",
    "alternate": "Replace the alternate representation with the exact recipe artifact.",
    "ambiguous_artifact": "Select one exact artifact; remove ambiguous complete candidates.",
    "adapter_unavailable": "Supply a local format Moses can ingest or implement the required adapter.",
    "raw_unstaged": "Normalize this raw capture to the exact upstream recipe artifact and pin that artifact.",
    "normalization_pending": "Complete and verify normalization, then mark the exact artifact ready.",
}


def _previous_versions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    inputs = value.get("inputs")
    if isinstance(inputs, dict):
        return {name: item.get("version") if isinstance(item, dict) else item for name, item in inputs.items()}
    if isinstance(inputs, list):
        return {item["name"]: item.get("version") for item in inputs if isinstance(item, dict) and isinstance(item.get("name"), str)}
    return {}


def _status(row: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    row.update(status=status, reason=reason, action=_ACTIONS[status])
    return row


def _format_for(artifact: dict[str, Any]) -> str:
    member = artifact.get("member")
    return str(artifact.get("format") or Path(member or artifact.get("path", "")).suffix).lower().lstrip(".")


def _ingest_options(capture: dict[str, Any]) -> dict[str, Any]:
    """Copy the small allowlist of operator-reviewed reader choices."""
    nested = capture.get("ingest_options") or {}
    if not isinstance(nested, dict) or set(nested) - _INGEST_OPTIONS:
        raise ValueError(f"ingest_options may contain only {sorted(_INGEST_OPTIONS)}")
    options = {name: capture[name] for name in _INGEST_OPTIONS if name in capture}
    options.update(nested)
    for name, value in options.items():
        if name == "types":
            if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
                raise ValueError("types must map field names to type names")
        elif not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a nonempty string")
    return options


def plan_sources(inventory: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Resolve all recipe inputs without network or filesystem access.

    ``available[name]`` has ``latest_version`` and ``versions[version].artifacts``.
    Each artifact needs ``kind: full``, an exact local ``path`` and ``sha256``;
    ZIP artifacts also need an exact ``member``. A minor release needs
    ``previous_release.inputs`` with name/version pairs. Explicit minor ``latest``
    entries refresh from the supplied latest pointer.
    """
    release_type = config.get("release_type")
    if release_type not in {"major", "minor"}:
        raise ValueError("release_type must be major or minor")
    target_release = config.get("target_release")
    if not isinstance(target_release, str) or not target_release.strip() or target_release.lower() == "latest":
        raise ValueError("target_release must identify the PLUTO release being planned")
    if config.get("version_prev") == target_release:
        raise ValueError("version_prev must identify a release before target_release")
    recipe = inventory.get("recipe", {})
    major = recipe.get("major", {}).get("inputs", {}).get("datasets", [])
    minor = recipe.get("minor", {}).get("inputs", {}).get("datasets", [])
    datasets = {item["name"]: item for item in inventory.get("datasets", [])}
    major_names = [item["name"] for item in major]
    aliases = [item.get("import_as") or datasets.get(item["name"], {}).get("build_import_name") or item["name"] for item in major]
    if len(major) != 38 or len(set(major_names)) != 38 or len(datasets) != 38 or set(major_names) != set(datasets):
        raise ValueError("inventory must contain the 38 PLUTO recipe inputs")
    if len(set(aliases)) != 38:
        raise ValueError("PLUTO recipe input aliases must be unique")
    local_seeds = inventory.get("local_seeds")
    if not isinstance(local_seeds, list) or len(local_seeds) != 11 or any(not isinstance(seed, dict) or not isinstance(seed.get("name"), str) or not seed["name"] for seed in local_seeds) or len({seed["name"] for seed in local_seeds}) != 11:
        raise ValueError("inventory must contain 11 uniquely named PLUTO local seeds")
    refresh = {item["name"] for item in minor if item.get("version") == "latest"}
    previous = _previous_versions(config.get("previous_release"))
    available = config.get("available") or {}
    if not isinstance(available, dict):
        raise ValueError("available must be a mapping of dataset names")
    rows: list[dict[str, Any]] = []
    for entry in major:
        name = entry["name"]
        description = datasets[name]
        alias = entry.get("import_as") or description.get("build_import_name") or name
        row = {"name": name, "alias": alias, "source_type": description.get("source_type"),
               "access": description.get("access"), "version_policy": "latest"}
        if entry.get("version_env_var") == "VERSION_PREV":
            row["version_policy"] = "VERSION_PREV"
            version = config.get("version_prev")
            if not isinstance(version, str) or not version.strip() or version.lower() == "latest":
                rows.append(_status(row, "missing_version_prev", "VERSION_PREV is required for previous_pluto"))
                continue
        elif release_type == "minor" and name not in refresh:
            row["version_policy"] = "previous_release"
            version = previous.get(name)
            if not isinstance(version, str) or not version.strip() or version.lower() == "latest":
                rows.append(_status(row, "missing_previous_release", f"{name} has no version in the previous PLUTO manifest"))
                continue
        else:
            source = available.get(name)
            if not isinstance(source, dict):
                rows.append(_status(row, "missing_release_metadata", f"No release metadata for {name}"))
                continue
            version = source.get("latest_version")
            if not isinstance(version, str) or not version or version.lower() == "latest":
                rows.append(_status(row, "missing_latest_pointer", f"No explicit latest version for {name}"))
                continue
        row["version"] = version
        source = available.get(name)
        if not isinstance(source, dict):
            rows.append(_status(row, "missing_release_metadata", f"No release metadata for {name}"))
            continue
        versions = source.get("versions") or {}
        selected = versions.get(version) if isinstance(versions, dict) else None
        if not isinstance(selected, dict):
            rows.append(_status(row, "missing_version", f"No artifact metadata for {name} version {version}"))
            continue
        artifacts = selected.get("artifacts") or []
        if not isinstance(artifacts, list) or not artifacts:
            status = "missing_access" if description.get("source_type") in {"axway", "s3", "edm.publishing.gis"} else "missing_artifact"
            rows.append(_status(row, status, f"No local artifact for {name} version {version}"))
            continue
        full = [item for item in artifacts if isinstance(item, dict) and item.get("kind") == "full"]
        if len(full) != 1:
            status = "ambiguous_artifact" if len(full) > 1 else ("sample" if any(isinstance(a, dict) and a.get("kind") == "sample" for a in artifacts) else "alternate")
            rows.append(_status(row, status, f"{name} version {version} has {len(full)} exact full artifacts"))
            continue
        artifact = dict(full[0])
        if artifact.get("representation") != "normalized_recipe":
            rows.append(_status(row, "raw_unstaged", f"{name} is not an exact normalized recipe artifact"))
            continue
        if artifact.get("normalization_status") != "ready":
            rows.append(_status(row, "normalization_pending", f"{name} normalization is not verified ready"))
            continue
        path = artifact.get("path")
        sha = artifact.get("sha256")
        if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            rows.append(_status(row, "missing_artifact", f"{name} needs an absolute local path and SHA256"))
            continue
        suffix = Path(path).suffix.lower()
        if suffix == ".zip":
            member = artifact.get("member")
            if not isinstance(member, str) or not _safe_member(member):
                rows.append(_status(row, "missing_artifact", f"{name} ZIP needs an exact safe member path"))
                continue
        elif artifact.get("member") is not None:
            rows.append(_status(row, "missing_artifact", f"{name} member is valid only for ZIP captures"))
            continue
        fmt = _format_for(artifact)
        if f".{fmt}" not in _READABLE or (suffix == ".shp" and artifact.get("member") is None):
            rows.append(_status(row, "adapter_unavailable", f"Moses has no local ingestion adapter for {fmt or suffix}"))
            continue
        _ingest_options(artifact)
        artifact["sha256"] = sha.lower()
        row.update(status="ready", reason="Exact full local artifact pinned", action=None,
                   artifact=artifact)
        rows.append(row)
    seeds = []
    supplied_seeds = config.get("seeds") or {}
    if not isinstance(supplied_seeds, dict):
        raise ValueError("seeds must be a mapping of seed names to local captures")
    for seed in local_seeds:
        name = seed["name"]
        supplied = supplied_seeds.get(name)
        if not isinstance(supplied, dict) or not isinstance(supplied.get("path"), str) or not Path(supplied["path"]).is_absolute() or not isinstance(supplied.get("sha256"), str) or not _SHA256.fullmatch(supplied["sha256"]):
            seeds.append({"name": name, "status": "missing_seed", "action": "Supply the exact local seed file and SHA256."})
        else:
            options = _ingest_options(supplied)
            seeds.append({"name": name, "status": "ready", "path": supplied["path"], "sha256": supplied["sha256"].lower(),
                          "upstream_path": seed.get("path"), "ingest_options": options})
    source_ready = all(row["status"] == "ready" for row in rows)
    return {"schema_version": 1, "release_type": release_type, "target_release": target_release,
            "inventory_source_commit": inventory.get("source_commit"),
            "ready": source_ready, "build_ready": source_ready and all(seed["status"] == "ready" for seed in seeds),
            "readiness_scope": "metadata_only; local files and SHA256 are verified by acquire_sources",
            "inputs": rows, "seeds": seeds}


def _safe_member(member: str) -> bool:
    path = PurePosixPath(member)
    return bool(member) and not path.is_absolute() and ".." not in path.parts and "\\" not in member and not member.endswith("/") and member == path.as_posix()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _materialize_member(archive: zipfile.ZipFile, member: str, root: Path) -> Path:
    matching = [info for info in archive.infolist() if info.filename == member and not info.is_dir()]
    if len(matching) != 1:
        raise ValueError(f"ZIP member {member!r} must occur exactly once")
    if matching[0].file_size > _MAX_MEMBER_BYTES:
        raise ValueError(f"ZIP member {member!r} exceeds size limit")
    target = root / Path(member).name
    with archive.open(matching[0]) as source, target.open("wb") as output:
        while block := source.read(1024 * 1024):
            output.write(block)
    return target


def _stage_capture(path: Path, sha256: str, destination: Path) -> Path:
    """Snapshot and hash one capture before any parser can reopen its bytes."""
    if not path.is_file():
        raise FileNotFoundError(f"Pinned source missing: {path}")
    if path.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ValueError(f"Pinned source exceeds size limit: {path}")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source, destination.open("xb") as staged:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            total += len(block)
            if total > _MAX_ARCHIVE_BYTES:
                raise ValueError(f"Pinned source exceeds size limit while copying: {path}")
            digest.update(block)
            staged.write(block)
        staged.flush()
        os.fsync(staged.fileno())
    actual = digest.hexdigest()
    if actual != sha256:
        raise ValueError(f"SHA256 mismatch for {path}: expected {sha256}, found {actual}")
    return destination


def _retain_archive(catalog: Any, staged: Path, sha256: str) -> Path:
    archive_dir = catalog.root / "pluto_archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    retained = archive_dir / f"{sha256}.zip"
    if retained.exists():
        if _digest(retained) != sha256:
            raise ValueError(f"Stored PLUTO archive checksum mismatch: {retained}")
        return retained
    with tempfile.NamedTemporaryFile(dir=archive_dir, prefix=f".{sha256}.", suffix=".part", delete=False) as stream:
        candidate = Path(stream.name)
    try:
        shutil.copyfile(staged, candidate)
        if _digest(candidate) != sha256:
            raise ValueError(f"Staged PLUTO archive checksum mismatch: {staged}")
        os.replace(candidate, retained)
    finally:
        candidate.unlink(missing_ok=True)
    return retained


def acquire_sources(catalog: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Verify every pinned capture before ingestion; never re-resolve versions.

    A failed preflight leaves the catalog untouched. Each successful catalog
    ingestion keeps its own immutable raw capture; the returned lock retains
    both selected-member and original archive SHA256 provenance.
    """
    rows = plan.get("inputs")
    if not plan.get("ready") or not isinstance(rows, list) or any(row.get("status") != "ready" for row in rows):
        raise ValueError("Source plan has unresolved required inputs; complete preflight first")
    seeds = plan.get("seeds", [])
    with tempfile.TemporaryDirectory(prefix="moses-pluto-captures-") as directory:
        staging = Path(directory)
        snapshots: dict[tuple[str, str], Path] = {}

        def snapshot(path_text: str, sha256: str) -> Path:
            key = (path_text, sha256)
            if key not in snapshots:
                suffix = Path(path_text).suffix
                snapshots[key] = _stage_capture(Path(path_text), sha256, staging / f"capture-{len(snapshots)}{suffix}")
            return snapshots[key]

        # Preflight every requested file and ZIP member before the first catalog write.
        for row in rows:
            artifact = row["artifact"]
            staged = snapshot(artifact["path"], artifact["sha256"])
            member = artifact.get("member")
            if member is not None:
                if not _safe_member(member):
                    raise ValueError(f"Unsafe ZIP member for {row['name']}")
                with zipfile.ZipFile(staged) as archive:
                    infos = archive.infolist()
                    if sum(info.filename == member and not info.is_dir() for info in infos) != 1:
                        raise ValueError(f"ZIP member {member!r} must occur exactly once")
                    if any(info.file_size > _MAX_MEMBER_BYTES for info in infos):
                        raise ValueError(f"ZIP contains a member exceeding the size limit: {artifact['path']}")
        for seed in seeds:
            if seed.get("status") == "ready":
                snapshot(seed["path"], seed["sha256"])

        acquired = []
        for index, row in enumerate(rows):
            artifact = row["artifact"]
            member = artifact.get("member")
            staged = snapshot(artifact["path"], artifact["sha256"])
            selected = staged
            if member is not None:
                member_dir = staging / f"member-{index}"
                member_dir.mkdir()
                with zipfile.ZipFile(staged) as archive:
                    selected = _materialize_member(archive, member, member_dir)
                    if selected.suffix.lower() == ".shp":
                        stem = str(PurePosixPath(member).with_suffix(""))
                        for suffix in (".shx", ".dbf", ".prj", ".cpg"):
                            sidecar = stem + suffix
                            if sidecar in archive.namelist():
                                _materialize_member(archive, sidecar, member_dir)
            selected_hash = _digest(selected)
            stored_archive = _retain_archive(catalog, staged, artifact["sha256"]) if member is not None else None
            options = _ingest_options(artifact)
            provenance = {"pluto_source": {"name": row["name"], "alias": row["alias"],
                          "target_release": plan["target_release"], "upstream_version": row["version"],
                          "version_policy": row["version_policy"], "capture_path": artifact["path"],
                          "capture_sha256": artifact["sha256"], "stored_archive": str(stored_archive) if stored_archive else None,
                          "archive_member": member, "selected_sha256": selected_hash,
                          "artifact_kind": "full", "representation": artifact["representation"],
                          "normalization_status": artifact["normalization_status"], "ingest_options": options}}
            result = catalog.ingest(selected, name=row["alias"], provenance=provenance, **options)
            acquired.append({"name": row["name"], "alias": row["alias"], "upstream_version": row["version"],
                             "catalog_version": result["version"], "capture_path": artifact["path"],
                             "capture_sha256": artifact["sha256"], "archive_member": member,
                             "selected_sha256": selected_hash, "ingest_options": options,
                             "representation": artifact["representation"],
                             "normalization_status": artifact["normalization_status"],
                             "stored_archive": str(stored_archive) if stored_archive else None})
        acquired_seeds = []
        for seed in seeds:
            if seed.get("status") != "ready":
                acquired_seeds.append({"name": seed["name"], "status": seed["status"]})
                continue
            selected = snapshot(seed["path"], seed["sha256"])
            options = _ingest_options(seed)
            provenance = {"pluto_seed": {"name": seed["name"], "target_release": plan["target_release"],
                          "upstream_path": seed.get("upstream_path"), "capture_path": seed["path"],
                          "capture_sha256": seed["sha256"], "ingest_options": options}}
            result = catalog.ingest(selected, name=seed["name"], provenance=provenance, **options)
            acquired_seeds.append({"name": seed["name"], "status": "ready", "catalog_version": result["version"],
                                   "capture_path": seed["path"], "capture_sha256": seed["sha256"],
                                   "upstream_path": seed.get("upstream_path"), "ingest_options": options})
    versions = {row["alias"]: row["catalog_version"] for row in acquired}
    versions.update({seed["name"]: seed["catalog_version"] for seed in acquired_seeds if seed["status"] == "ready"})
    build_ready = all(seed["status"] == "ready" for seed in acquired_seeds) and len(acquired_seeds) == 11
    lock = {"schema_version": 1, "target_release": plan["target_release"],
            "inventory_source_commit": plan.get("inventory_source_commit"),
            "versions": versions, "inputs": acquired, "seeds": acquired_seeds}
    return {"ready": True, "build_ready": build_ready,
            "release_type": plan["release_type"], "target_release": plan["target_release"],
            "inputs": acquired, "seeds": acquired_seeds, "input_lock": lock}
