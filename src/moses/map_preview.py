"""Bounded, display-only GeoJSON preview of an accepted Parquet snapshot."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
import json
import math
from pathlib import Path

import pyarrow.parquet as pq
from .dependencies import SpatialDependencyError, require_spatial


MAX_FEATURES = 1000
MAX_SCANNED_ROWS = 1000
MAX_BYTES = 2 * 1024 * 1024
MAX_GEOMETRY_BYTES = 1024 * 1024
MAX_COORDINATES = 100_000
MAX_FEATURE_COORDINATES = 20_000
MAX_PROPERTY_BYTES = 8192
MAX_CELL_BYTES = 4096
MAX_NESTED_ITEMS = 100
MAX_DEPTH = 8
_SUPPORTED = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"}
_MERCATOR_LATITUDE = 85.05112878


class MapPreviewError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))


def _safe_value(value: object, counts: Counter[str], depth: int = 0) -> object:
    if depth >= MAX_DEPTH:
        counts["nested_truncated"] += 1
        return {"truncated": True, "reason": "depth"}
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        size = len(value.encode("utf-8"))
        if size > MAX_CELL_BYTES:
            counts["large_cell"] += 1
            return {"truncated": True, "byte_length": size}
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        counts["binary_summarized"] += 1
        return {"byte_length": len(value), "binary": True}
    if isinstance(value, (date, datetime, time, Decimal)):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = [_safe_value(item, counts, depth + 1) for item in value[:MAX_NESTED_ITEMS]]
        if len(value) > MAX_NESTED_ITEMS:
            counts["nested_truncated"] += 1
            return {"items": items, "truncated": True, "omitted_count": len(value) - MAX_NESTED_ITEMS}
        return items
    if isinstance(value, dict):
        entries = list(value.items())
        if len(entries) > MAX_NESTED_ITEMS:
            counts["nested_truncated"] += 1
        result = {str(k): _safe_value(v, counts, depth + 1) for k, v in entries[:MAX_NESTED_ITEMS]}
        if len(entries) > MAX_NESTED_ITEMS:
            result["_truncated"] = {"omitted_count": len(entries) - MAX_NESTED_ITEMS}
        return result
    return _safe_value(str(value), counts, depth + 1)


def _properties(row: dict, geometry_column: str, counts: Counter[str]) -> dict:
    result: dict[str, object] = {}
    for key, value in row.items():
        if key == geometry_column:
            continue
        encoded = _safe_value(value, counts)
        candidate = {**result, str(key): encoded}
        if _json_size(candidate) > MAX_PROPERTY_BYTES:
            counts["properties_omitted"] += 1
            continue
        result[str(key)] = encoded
    return result


def _paths(coordinates: object):
    """Yield coordinate sequences, retaining ring/line boundaries."""
    if not isinstance(coordinates, (tuple, list)) or not coordinates:
        return
    if isinstance(coordinates[0], (int, float)):
        yield [coordinates]
    elif isinstance(coordinates[0], (tuple, list)) and coordinates[0] and isinstance(coordinates[0][0], (int, float)):
        yield coordinates
    else:
        for item in coordinates:
            yield from _paths(item)


def _display_geometry(geom, transformer) -> tuple[dict | None, str | None, bool]:
    if geom.is_empty:
        return None, "empty", False
    if geom.geom_type not in _SUPPORTED:
        return None, "unsupported", False
    if not geom.is_valid:
        return None, "invalid", False
    transform = require_spatial("shapely", "Map preview").transform
    mapping = require_spatial("shapely.geometry", "Map preview").mapping
    has_z = bool(geom.has_z)
    try:
        # Drop Z on the display copy. The accepted WKB is never rewritten.
        projected = transform(geom, transformer.transform, include_z=False, interleaved=False)
        coordinates = mapping(projected)["coordinates"]
        lons: list[float] = []
        lats: list[float] = []
        for path in _paths(coordinates):
            prior = None
            for point in path:
                lon, lat = point[:2]
                if not (math.isfinite(lon) and math.isfinite(lat)):
                    return None, "nonfinite", has_z
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    return None, "out_of_range", has_z
                if prior is not None and abs(lon - prior) > 180:
                    return None, "antimeridian", has_z
                prior = lon
                lons.append(lon)
                lats.append(lat)
        if not lons:
            return None, "empty", has_z
        if max(lons) - min(lons) > 180:
            return None, "antimeridian", has_z
        if any(abs(lat) > _MERCATOR_LATITUDE + 1e-8 for lat in lats):
            return None, "mercator_latitude", has_z
        return {"type": geom.geom_type, "coordinates": coordinates}, None, has_z
    except Exception:
        return None, "transform_failed", has_z


def build_map_preview(path: Path, manifest: dict, *, limit: int = 500) -> dict:
    """Build a bounded GeoJSON FeatureCollection from an immutable snapshot.

    ``limit`` controls returned features, while scanning stops after 1,000 rows.
    Invalid features are counted and omitted. The bounds and completeness fields
    refer only to emitted features and scanned rows respectively.
    """
    geometry_column = manifest.get("geometry_column")
    if not isinstance(geometry_column, str) or not geometry_column:
        raise MapPreviewError(422, "nonspatial", "This version has no geometry column")
    crs_text = manifest.get("crs")
    if not isinstance(crs_text, str) or not crs_text.strip():
        raise MapPreviewError(422, "unknown_crs", "A source CRS is required to display geometry")
    try:
        pyproj = require_spatial("pyproj", "Map preview")
        shapely = require_spatial("shapely", "Map preview")
    except SpatialDependencyError as exc:
        raise MapPreviewError(422, "spatial_dependencies_required", str(exc)) from exc
    try:
        source_crs = pyproj.CRS.from_user_input(crs_text)
        transformer = pyproj.Transformer.from_crs(source_crs, pyproj.CRS.from_epsg(4326), always_xy=True)
    except Exception as exc:
        raise MapPreviewError(422, "invalid_crs", "The source CRS cannot be transformed to EPSG:4326") from exc
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_FEATURES:
        raise ValueError("limit must be between 1 and 1000")

    parquet = pq.ParquetFile(path)
    if geometry_column not in parquet.schema_arrow.names:
        raise MapPreviewError(422, "invalid_geometry_column", "The geometry column is absent from this snapshot")
    total_rows = parquet.metadata.num_rows
    features: list[dict] = []
    omissions: Counter[str] = Counter()
    property_counts: Counter[str] = Counter()
    scanned = coordinate_work = used_bytes = 0
    bbox: list[float] | None = None
    z_dropped = False
    stop = False
    for batch in parquet.iter_batches(batch_size=16):
        for row in batch.to_pylist():
            if scanned >= MAX_SCANNED_ROWS or len(features) >= limit:
                stop = True
                break
            row_id = scanned
            scanned += 1
            raw = row[geometry_column]
            if raw is None:
                omissions["null"] += 1
                continue
            if not isinstance(raw, (bytes, bytearray, memoryview)):
                omissions["invalid"] += 1
                continue
            if len(raw) > MAX_GEOMETRY_BYTES:
                omissions["oversized_geometry"] += 1
                continue
            try:
                geom = shapely.from_wkb(raw, on_invalid="ignore")
            except Exception:
                geom = None
            if geom is None:
                omissions["invalid"] += 1
                continue
            coordinate_count = shapely.get_num_coordinates(geom)
            if coordinate_count > MAX_FEATURE_COORDINATES:
                omissions["oversized_coordinates"] += 1
                continue
            if coordinate_work + coordinate_count > MAX_COORDINATES:
                omissions["coordinate_budget"] += 1
                stop = True
                break
            coordinate_work += coordinate_count
            geojson, reason, has_z = _display_geometry(geom, transformer)
            if reason:
                omissions[reason] += 1
                continue
            assert geojson is not None
            properties = _properties(row, geometry_column, property_counts)
            feature = {"type": "Feature", "id": row_id, "properties": properties, "geometry": geojson}
            size = _json_size(feature)
            if size > MAX_BYTES - 8192:
                omissions["oversized_feature"] += 1
                continue
            if used_bytes + size > MAX_BYTES - 8192:
                omissions["byte_budget"] += 1
                stop = True
                break
            features.append(feature)
            used_bytes += size
            z_dropped |= has_z
            for path_coordinates in _paths(geojson["coordinates"]):
                for lon, lat in path_coordinates:
                    bbox = [lon, lat, lon, lat] if bbox is None else [
                        min(bbox[0], lon), min(bbox[1], lat), max(bbox[2], lon), max(bbox[3], lat)]
        if stop or scanned >= MAX_SCANNED_ROWS or len(features) >= limit:
            break

    warnings: list[str] = []
    crs_source = manifest.get("crs_source")
    if crs_source in {"default", "legacy_csv_default"}:
        warnings.append("Source CRS was assumed at ingestion")
    if z_dropped:
        warnings.append("Z coordinates were dropped for the 2D display preview")
    if property_counts:
        warnings.append("Some properties were summarized or omitted; see property_omissions")
    if omissions.get("antimeridian"):
        warnings.append("Geometries crossing the antimeridian were omitted")
    if omissions.get("mercator_latitude"):
        warnings.append("Web Mercator geometries outside its latitude limit were omitted")
    response = {
        "type": "FeatureCollection", "features": features, "bbox": bbox,
        "source_crs": source_crs.to_string(), "display_crs": "EPSG:4326", "crs_source": crs_source,
        "total_rows": total_rows, "scanned_rows": scanned, "returned_features": len(features),
        "omitted_features": scanned - len(features), "unscanned_rows": total_rows - scanned,
        "truncated": scanned < total_rows or bool(omissions), "omissions": dict(omissions),
        "property_omissions": dict(property_counts), "warnings": warnings,
        "limits": {"max_features": limit, "max_scanned_rows": MAX_SCANNED_ROWS,
                   "max_bytes": MAX_BYTES, "max_coordinates": MAX_COORDINATES,
                   "max_geometry_bytes": MAX_GEOMETRY_BYTES},
    }
    # The fixed reserve covers normal metadata; this final guard keeps the
    # contract exact even if an unusually long CRS label consumes that reserve.
    while features and _json_size(response) > MAX_BYTES:
        features.pop()
        omissions["byte_budget"] += 1
        response["returned_features"] = len(features)
        response["omitted_features"] = scanned - len(features)
        response["omissions"] = dict(omissions)
        response["truncated"] = True
        bbox = None
        for feature in features:
            for path_coordinates in _paths(feature["geometry"]["coordinates"]):
                for lon, lat in path_coordinates:
                    bbox = [lon, lat, lon, lat] if bbox is None else [
                        min(bbox[0], lon), min(bbox[1], lat), max(bbox[2], lon), max(bbox[3], lat)]
        response["bbox"] = bbox
    if _json_size(response) > MAX_BYTES:
        raise MapPreviewError(422, "preview_metadata_too_large", "Preview metadata exceeds the response size limit")
    return response
