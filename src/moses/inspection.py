"""Read-only source inspection helpers.

Inspection currently reads the complete source through :func:`read_vector`.
It is a full-file scan, not a sample or streaming metadata query; only the
returned preview is bounded.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import math
from pathlib import Path
from typing import Any

from .ingest import read_vector
from .config import resolve_column_names, resolve_default_crs, resolve_warehouse


_MAX_PREVIEW_ROWS = 100
_UNSET_DEFAULT_CRS = object()
_SUPPORTED_SUFFIXES = [".csv", ".tsv", ".parquet", ".geoparquet", ".geojson", ".json", ".gpkg", ".shp", ".zip", ".gdb", ".gdb.zip"]
_COORDINATE_PAIRS = (
    ("longitude", "latitude"),
    ("lon", "lat"),
    ("x", "y"),
    ("easting", "northing"),
)


def _json_safe(value: Any) -> Any:
    """Convert Arrow/Python values to stable JSON-compatible values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "0x" + bytes(value).hex()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    # Arrow scalars expose as_py; this also covers extension scalar wrappers.
    as_py = getattr(value, "as_py", None)
    if callable(as_py):
        return _json_safe(as_py())
    # Keep inspection serializable if a future Arrow type adds a new wrapper.
    return str(value)


def _coordinate_suggestions(names: list[str]) -> list[dict[str, str]]:
    by_folded_name = {name.casefold(): name for name in names}
    suggestions = []
    for x_name, y_name in _COORDINATE_PAIRS:
        x_actual = by_folded_name.get(x_name)
        y_actual = by_folded_name.get(y_name)
        if x_actual is not None and y_actual is not None:
            suggestions.append({"x": x_actual, "y": y_actual})
    return suggestions


def inspect_source(
    path: str | Path,
    *,
    layer: str | None = None,
    x: str | None = None,
    y: str | None = None,
    crs: str | None = None,
    default_crs: str | None = _UNSET_DEFAULT_CRS,
    infer_types: bool = False,
    types: dict[str, str] | None = None,
    format: str | None = None,
    column_names: str | None = None,
    preview_rows: int = 10,
) -> dict[str, Any]:
    """Inspect a supported source and return a JSON-safe summary.

    This performs a full-file scan by calling ``read_vector`` and materializing
    the complete Arrow table. It does not use sampling or streaming. Only the
    returned row preview is bounded, to between zero and 100 records.
    Format selection is based on the filename suffix supported by
    ``read_vector``; the selected reader then validates the file contents.
    Coordinate field candidates are suggestions and never create geometry.
    """
    if isinstance(preview_rows, bool) or not isinstance(preview_rows, int) or not 0 <= preview_rows <= _MAX_PREVIEW_ROWS:
        raise ValueError("preview_rows must be an integer from 0 to 100")
    column_names = resolve_column_names(explicit=column_names)["column_names"]
    if default_crs is _UNSET_DEFAULT_CRS:
        default_crs = resolve_default_crs(resolve_warehouse()["warehouse"])
    source = Path(path)
    table, metadata = read_vector(
        source,
        layer=layer,
        x=x,
        y=y,
        crs=crs,
        default_crs=default_crs,
        infer_types=infer_types,
        types=types,
        format=format,
        column_names=column_names,
    )
    schema = [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in table.schema
    ]
    columns = table.column_names
    preview = [
        {name: _json_safe(table[name][row].as_py()) for name in columns}
        for row in range(min(len(table), preview_rows))
    ]
    warnings = list(metadata.get("warnings") or [])
    candidates = _coordinate_suggestions(columns)
    if candidates:
        warnings.append("Coordinate field candidates are suggestions only; Moses does not select a coordinate pair automatically.")
    if len(candidates) > 1:
        warnings.append("Multiple coordinate field pairs match; select the intended pair explicitly.")
    suffix = source.suffix.lower()
    result = {
        "format": metadata["format"],
        "detection": {
            "method": "explicit_format" if format is not None else "filename_suffix",
            "suffix": suffix,
            "supported_suffixes": _SUPPORTED_SUFFIXES,
            "selected_format": metadata["format"],
        },
        "row_count": len(table),
        "schema": schema,
        "preview": preview,
        "crs": metadata.get("crs"),
        "crs_source": metadata.get("crs_source"),
        "geometry_column": metadata.get("geometry_column"),
        "coordinate_candidates": candidates,
        "layer": metadata.get("layer"),
        "warnings": warnings,
        "scan": "full_file",
    }
    if column_names == "snake_case":
        result["column_name_map"] = metadata["column_name_map"]
    return result
