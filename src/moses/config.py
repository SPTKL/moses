"""Small helpers for configuration stored at a Moses warehouse root."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pyproj import CRS


_CONFIG_FILENAME = "config.json"


def _validate_crs(value: Any, *, label: str = "CRS") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty CRS string")
    try:
        return CRS.from_user_input(value).to_string()
    except Exception as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _config_path(root: str | Path) -> Path:
    return Path(root).expanduser() / _CONFIG_FILENAME


def load_config(root: str | Path) -> dict[str, Any]:
    """Load ``<root>/config.json``; a missing file means empty config.

    Malformed JSON, a non-object root, and an invalid stored default CRS fail
    clearly instead of silently discarding user configuration.
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
        value["default_crs"] = _validate_crs(value["default_crs"], label="stored default CRS")
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


def resolve_default_crs(root: str | Path) -> str | None:
    """Resolve CRS from non-empty ``MOSES_DEFAULT_CRS`` before stored config."""
    environment = os.environ.get("MOSES_DEFAULT_CRS", "").strip()
    if environment:
        return _validate_crs(environment, label="MOSES_DEFAULT_CRS")
    return load_config(root).get("default_crs")
