"""Small helpers for configuration stored at a Moses warehouse root."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from .dependencies import SpatialDependencyError, require_spatial


_CONFIG_FILENAME = "config.json"


def _validate_crs(value: Any, *, label: str = "CRS", defer_if_unavailable: bool = False) -> str:
    """Validate CRS shape, deferring semantics only when PyProj is unavailable.

    Reading existing settings must allow base-only tabular work. Spatial readers
    still require PyProj and validate the deferred string before publication.
    Explicit configuration writes keep semantic validation mandatory.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty CRS string")
    try:
        CRS = require_spatial("pyproj", "CRS validation").CRS
    except SpatialDependencyError:
        if defer_if_unavailable:
            return value.strip()
        raise
    try:
        return CRS.from_user_input(value).to_string()
    except Exception as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _config_path(root: str | Path) -> Path:
    return Path(root).expanduser() / _CONFIG_FILENAME


def load_config(root: str | Path) -> dict[str, Any]:
    """Load ``<root>/config.json``; a missing file means empty config.

    Malformed JSON, a non-object root, and malformed CRS values fail clearly.
    CRS semantics are checked when PyProj is available; a base-only installation
    retains a nonempty CRS string until a spatial operation can validate it.
    """
    path = _config_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read Moses config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Moses config must contain a JSON object")
    if "default_crs" in value and value["default_crs"] is not None:
        value["default_crs"] = _validate_crs(value["default_crs"], label="stored default CRS", defer_if_unavailable=True)
    return value


def set_default_crs(root: str | Path, crs: str) -> dict[str, Any]:
    """Set a validated default CRS, preserving other config keys atomically."""
    canonical = _validate_crs(crs, label="default CRS")
    config = load_config(root)
    config["default_crs"] = canonical
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temp_name = stream.name
            json.dump(config, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return config


def _column_mode(value: Any, label: str) -> str:
    if value not in ("preserve", "snake_case") or not isinstance(value, str):
        raise ValueError(f"{label} must be 'preserve' or 'snake_case'")
    return value


def _export_mode(value: Any, label: str) -> str:
    modes = {"parquet": "Parquet", "geoparquet": "GeoParquet", "filegdb": "FileGDB"}
    if not isinstance(value, str) or value.lower() not in modes:
        raise ValueError(f"{label} must be Parquet, GeoParquet, or FileGDB")
    return modes[value.lower()]


def _toml_settings(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"could not read Moses TOML config {path}: {exc}") from exc
    if "moses" not in data:
        return None
    settings = data["moses"]
    if not isinstance(settings, dict):
        raise ValueError(f"Moses TOML config {path}: [moses] must be a table")
    unknown = set(settings) - {"config_version", "input", "project", "normalization", "spatial", "export"}
    if unknown:
        raise ValueError(f"Moses TOML config {path}: unknown [moses] settings: {sorted(unknown)}")
    if "config_version" in settings and (type(settings["config_version"]) is not int or settings["config_version"] != 1):
        raise ValueError(f"Moses TOML config {path}: config_version must be 1")
    allowed = {"input": {"column_names"}, "project": {"warehouse"},
               "normalization": {"column_names"}, "spatial": {"default_crs"},
               "export": {"format"}}
    groups: dict[str, dict[str, Any]] = {}
    for group, keys in allowed.items():
        section = settings.get(group, {})
        if not isinstance(section, dict):
            raise ValueError(f"Moses TOML config {path}: [moses.{group}] must be a table")
        extra = set(section) - keys
        if extra:
            raise ValueError(f"Moses TOML config {path}: unknown [moses.{group}] settings: {sorted(extra)}")
        groups[group] = section
    if "column_names" in groups["input"]:
        _column_mode(groups["input"]["column_names"], f"Moses TOML config {path} input.column_names")
    if "column_names" in groups["normalization"]:
        _column_mode(groups["normalization"]["column_names"], f"Moses TOML config {path} normalization.column_names")
    if ("column_names" in groups["input"] and "column_names" in groups["normalization"]
            and groups["input"]["column_names"] != groups["normalization"]["column_names"]):
        raise ValueError(f"Moses TOML config {path}: [moses.input] and [moses.normalization] set conflicting column_names")
    flat: dict[str, Any] = {}
    naming = groups["normalization"].get("column_names", groups["input"].get("column_names"))
    if naming is not None:
        flat["column_names"] = _column_mode(naming, f"Moses TOML config {path} column_names")
    if "warehouse" in groups["project"]:
        value = groups["project"]["warehouse"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Moses TOML config {path}: project.warehouse must be a nonempty path")
        flat["warehouse"] = value
    if "default_crs" in groups["spatial"]:
        flat["default_crs"] = _validate_crs(groups["spatial"]["default_crs"], label=f"Moses TOML config {path} spatial.default_crs", defer_if_unavailable=True)
    if "format" in groups["export"]:
        flat["export_format"] = _export_mode(groups["export"]["format"], f"Moses TOML config {path} export.format")
    return flat


def _discover(cwd: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any], Path | None, Path | None, Path]:
    current = Path(cwd or Path.cwd()).expanduser().resolve()
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and not Path(xdg).expanduser().is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be an absolute path")
    global_path = (Path(xdg).expanduser() if xdg else Path.home() / ".config") / "moses" / "config.toml"
    global_settings = _toml_settings(global_path)
    project_path = None
    project_settings = None
    for directory in (current, *current.parents):
        candidate = directory / "config.toml"
        found = _toml_settings(candidate)
        if found is not None:
            project_path, project_settings = candidate, found
            break
    return global_settings or {}, project_settings or {}, global_path if global_settings is not None else None, project_path, current


def _from_files(setting: str, cwd: str | Path | None = None) -> tuple[Any, str, Path | None, Path | None, Path]:
    global_settings, project_settings, global_path, project_path, current = _discover(cwd)
    if setting in project_settings:
        return project_settings[setting], "project", global_path, project_path, current
    if setting in global_settings:
        return global_settings[setting], "global", global_path, project_path, current
    return None, "built_in", global_path, project_path, current


def resolve_column_names(*, explicit: str | None = None, recipe: str | None = None,
                         cwd: str | Path | None = None) -> dict[str, Any]:
    """Resolve naming policy and report its origin without creating any files."""
    file_value, file_origin, global_path, project_path, _ = _from_files("column_names", cwd)
    environment = os.environ.get("MOSES_COLUMN_NAMES", "").strip()
    if environment:
        _column_mode(environment, "MOSES_COLUMN_NAMES")
    if recipe is not None:
        _column_mode(recipe, "recipe import.column_names")
    if explicit is not None:
        _column_mode(explicit, "column_names")
    if explicit is not None:
        value, origin = explicit, "explicit"
    elif recipe is not None:
        value, origin = recipe, "recipe"
    elif environment:
        value, origin = environment, "environment"
    elif file_value is not None:
        value, origin = file_value, file_origin
    else:
        value, origin = "preserve", "built_in"
    return {"column_names": value, "origin": origin,
            "project_path": str(project_path) if project_path else None,
            "global_path": str(global_path) if global_path else None}


def resolve_warehouse(*, explicit: str | Path | None = None, cwd: str | Path | None = None) -> dict[str, Any]:
    value, origin, global_path, project_path, current = _from_files("warehouse", cwd)
    if explicit is not None:
        value, origin = str(explicit), "explicit"
    elif value is None:
        value, origin = ".moses", "built_in"
    path = Path(value).expanduser()
    base = (project_path.parent if origin == "project" and project_path else
            project_path.parent if origin in {"global", "built_in"} and project_path else current)
    resolved = (path if path.is_absolute() else base / path).resolve()
    return {"warehouse": str(resolved), "origin": origin,
            "project_path": str(project_path) if project_path else None,
            "global_path": str(global_path) if global_path else None}


def resolve_default_crs(root: str | Path, *, explicit: str | None = None) -> str | None:
    """Resolve fallback CRS; defer semantic validation if PyProj is unavailable."""
    file_value, _, _, _, _ = _from_files("default_crs")
    environment = os.environ.get("MOSES_DEFAULT_CRS", "").strip()
    if explicit is not None:
        return _validate_crs(explicit, label="default CRS", defer_if_unavailable=True)
    if environment:
        return _validate_crs(environment, label="MOSES_DEFAULT_CRS", defer_if_unavailable=True)
    if file_value is not None:
        return file_value
    return load_config(root).get("default_crs")


def resolve_export_format(*, explicit: str | None = None) -> dict[str, str]:
    value, origin, _, _, _ = _from_files("export_format")
    if explicit is not None:
        return {"format": _export_mode(explicit, "export format"), "origin": "explicit"}
    return {"format": value or "Parquet", "origin": origin}


def show_config(*, warehouse: str | Path | None = None) -> dict[str, Any]:
    naming = resolve_column_names()
    project = resolve_warehouse(explicit=warehouse)
    export = resolve_export_format()
    file_crs, file_origin, _, _, _ = _from_files("default_crs")
    environment = os.environ.get("MOSES_DEFAULT_CRS", "").strip()
    if environment:
        spatial_value, spatial_origin = _validate_crs(environment, label="MOSES_DEFAULT_CRS", defer_if_unavailable=True), "environment"
    elif file_crs is not None:
        spatial_value, spatial_origin = file_crs, file_origin
    else:
        spatial_value = load_config(project["warehouse"]).get("default_crs")
        spatial_origin = "legacy_warehouse" if spatial_value is not None else "built_in"
    return {"settings": {"project": {"warehouse": project["warehouse"]},
                         "normalization": {"column_names": naming["column_names"]},
                         "spatial": {"default_crs": spatial_value},
                         "export": {"format": export["format"]}},
            "origins": {"project.warehouse": project["origin"],
                        "normalization.column_names": naming["origin"],
                        "spatial.default_crs": spatial_origin,
                        "export.format": export["origin"]},
            "project_path": naming["project_path"], "global_path": naming["global_path"]}
