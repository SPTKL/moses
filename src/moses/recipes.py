"""Validated, portable choices that explain an accepted import."""

from __future__ import annotations

import codecs
import math
from pathlib import Path
import re
from typing import Any

import pyarrow as pa


RECIPE_VERSION = 1
_SUFFIX_FORMATS = {
    ".csv": "CSV", ".tsv": "TSV", ".parquet": "Parquet",
    ".geoparquet": "Parquet", ".geojson": "GeoJSON", ".json": "GeoJSON",
    ".gpkg": "GeoPackage", ".shp": "Shapefile", ".zip": "Shapefile", ".gdb": "FileGDB",
}
_TYPE_ALIASES = {
    "string": "string", "text": "string", "bool": "bool", "boolean": "bool",
    "int64": "int64", "integer": "int64", "float64": "float64", "float": "float64",
}
_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_FLOAT = re.compile(r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\Z")


def canonical_types(types: dict[str, str] | None) -> dict[str, str]:
    if types is None:
        return {}
    if not isinstance(types, dict):
        raise TypeError("types must be a mapping from field names to primitive types")
    normalized = {}
    for field, choice in types.items():
        if not isinstance(field, str) or not field:
            raise ValueError("type override field names must be nonempty strings")
        if not isinstance(choice, str) or choice.lower() not in _TYPE_ALIASES:
            raise ValueError(f"unsupported type for field {field!r}: {choice!r}; choose string, bool, int64, or float64")
        normalized[field] = _TYPE_ALIASES[choice.lower()]
    return dict(sorted(normalized.items()))


def selected_format(path: Path, explicit: str | None = None) -> tuple[str, str]:
    """Select an allowlisted reader and reject contradictory strong signatures."""
    suffix = path.suffix.lower()
    if path.name.lower().endswith(".gdb.zip"):
        suffix = ".gdb.zip"
    if explicit is None:
        if suffix == ".gdb.zip":
            selected = "FileGDB"
        elif suffix not in _SUFFIX_FORMATS:
            raise ValueError(f"unsupported vector source extension: {suffix or '(none)'}")
        else:
            selected = _SUFFIX_FORMATS[suffix]
    else:
        if not isinstance(explicit, str):
            raise ValueError("format must name an explicitly supported reader")
        names = {"csv": "CSV", "tsv": "TSV", "parquet": "Parquet", "geoparquet": "Parquet",
                 "geojson": "GeoJSON", "geopackage": "GeoPackage", "gpkg": "GeoPackage",
                 "shapefile": "Shapefile", "filegdb": "FileGDB"}
        selected = names.get(explicit.lower())
        if selected is None:
            raise ValueError(f"unsupported format {explicit!r}")
    if selected == "FileGDB":
        from .filegdb import directory_files, reject_symlink_path
        reject_symlink_path(path)
        if path.is_dir():
            directory_files(path)
            return selected, ".gdb"
        with path.open("rb") as stream:
            if stream.read(4) != b"PK\x03\x04":
                raise ValueError("FileGDB source must be a .gdb directory or ZIP archive")
        return selected, ".gdb.zip"
    if path.is_dir():
        raise ValueError("directory sources require the FileGDB reader")
    with path.open("rb") as stream:
        head = stream.read(4096)
        if selected == "Parquet":
            stream.seek(-4, 2) if path.stat().st_size >= 4 else None
            tail = stream.read(4)
        else:
            tail = b""
    if selected == "Parquet" and head.startswith(b"PAR1") and tail != b"PAR1":
        raise ValueError("Parquet source has an invalid footer signature")
    if head.startswith(b"PAR1"):
        detected = "Parquet"
    elif head.startswith(b"SQLite format 3\x00"):
        detected = "GeoPackage"
    elif head.startswith(b"PK\x03\x04"):
        detected = "Shapefile"
    elif len(head) >= 4 and head[:4] == b"\x00\x00\x27\x0a":
        detected = "Shapefile"
    elif head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith((b"{", b"[")):
        detected = "GeoJSON"
    else:
        detected = "tabular"
    if selected in {"CSV", "TSV"}:
        if detected != "tabular" or b"\x00" in head:
            raise ValueError(f"content signature does not match selected {selected} reader")
        try:
            codecs.getincrementaldecoder("utf-8-sig")().decode(head, final=False)
        except UnicodeError as exc:
            raise ValueError(f"content is not UTF-8 text for selected {selected} reader") from exc
    elif detected != selected:
        if detected == "tabular":
            detail = {"GeoJSON": "GeoJSON source is not valid JSON",
                      "GeoPackage": "GeoPackage source has an invalid SQLite header",
                      "Shapefile": "Shapefile source has an invalid Shapefile header",
                      "Parquet": "Parquet source has an invalid signature"}.get(selected)
            if detail:
                raise ValueError(detail)
        raise ValueError(f"content signature does not match selected {selected} reader")
    # A shapefile ZIP is identified by its suffix; never feed an arbitrary ZIP
    # to GDAL merely because its bytes begin with PK.
    if selected == "Shapefile" and detected == "Shapefile":
        kind = ".zip" if head.startswith(b"PK\x03\x04") else ".shp"
    elif selected == "Parquet":
        kind = ".parquet"
    else:
        kind = {"CSV": ".csv", "TSV": ".tsv", "GeoJSON": ".geojson", "GeoPackage": ".gpkg"}.get(selected, suffix)
    return selected, kind


def apply_types(table: pa.Table, types: dict[str, str] | None, *, first_row: int) -> pa.Table:
    choices = canonical_types(types)
    for name in choices:
        if name not in table.column_names:
            raise ValueError(f"type override field {name!r} does not exist")
    result = table
    targets = {"string": pa.string(), "bool": pa.bool_(), "int64": pa.int64(), "float64": pa.float64()}
    for name, choice in choices.items():
        values = table[name].to_pylist()
        converted = []
        for offset, value in enumerate(values):
            if value is None or (value == "" and choice != "string"):
                converted.append(None)
                continue
            try:
                if choice == "string":
                    parsed = value if isinstance(value, str) else str(value)
                elif choice == "bool":
                    if isinstance(value, bool):
                        parsed = value
                    elif isinstance(value, str) and value.casefold() in {"true", "false"}:
                        parsed = value.casefold() == "true"
                    else:
                        raise ValueError("expected true or false")
                elif choice == "int64":
                    if isinstance(value, bool):
                        raise ValueError("boolean is not an integer")
                    if isinstance(value, int):
                        parsed = value
                    elif isinstance(value, str) and _INTEGER.fullmatch(value):
                        parsed = int(value)
                    else:
                        raise ValueError("expected an integer")
                    if not -(2**63) <= parsed <= 2**63 - 1:
                        raise ValueError("integer outside int64 range")
                else:
                    if isinstance(value, bool):
                        raise ValueError("boolean is not a float")
                    if isinstance(value, str) and not _FLOAT.fullmatch(value):
                        raise ValueError("expected a decimal number")
                    parsed = float(value)
                    if not math.isfinite(parsed):
                        raise ValueError("float must be finite")
                    if isinstance(value, int) and int(parsed) != value:
                        raise ValueError("integer cannot be represented exactly as float64")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"invalid {choice} in field {name!r} at row {first_row + offset}: {exc}") from exc
            converted.append(parsed)
        result = result.set_column(result.column_names.index(name), name, pa.array(converted, type=targets[choice]))
    return result


def import_recipe(*, metadata: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    result = {
        "version": RECIPE_VERSION,
        "format": metadata.get("format"),
        "layer": metadata.get("layer"),
        "coordinates": {"x": options.get("x"), "y": options.get("y")},
        "types": canonical_types(options.get("types")),
        "type_blank_policy": "empty_to_null_for_non_string_overrides",
        "infer_types": bool(options.get("infer_types", False)),
        "crs": {"value": metadata.get("crs"), "source": metadata.get("crs_source")},
    }
    if options.get("column_names") == "snake_case":
        result["column_names"] = "snake_case"
        result["column_name_map"] = metadata["column_name_map"]
    return result
