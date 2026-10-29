"""Bounded, local vector and tabular ingestion for Moses.

CSV/TSV attributes default to strings, with conservative inference opt-in. This avoids losing
identifier formatting (for example leading zeroes) before the caller applies a
domain-specific schema.
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
import shutil
import struct
import tempfile
import zipfile
from typing import Any

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from .dependencies import require_spatial

from .recipes import apply_types, canonical_types, selected_format
from .column_names import column_name_map


_GEO_METADATA_KEY = b"geo"
_GEOPARQUET_GEOMETRY_TYPES = {
    "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString",
    "MultiPolygon", "GeometryCollection",
}


def _json_crs(crs: Any) -> dict[str, Any] | None:
    if crs is None:
        return None
    CRS = require_spatial("pyproj", "Geometry CRS metadata").CRS
    parsed = CRS.from_user_input(crs)
    return parsed.to_json_dict()


def _geo_metadata(
    table: pa.Table,
    geom_name: str,
    crs: Any,
    declared_geometry_types: list[str] | None = None,
) -> dict[str, str]:
    shapely = require_spatial("shapely", "Geometry metadata")
    # GeoParquet 1.1 requires CRS to be explicit; null means unknown CRS.
    geom_types: set[str] = set()
    values = table[geom_name].to_pylist()
    for value in values:
        if value is None:
            continue
        geom = shapely.from_wkb(value)
        kind = geom.geom_type
        if kind not in _GEOPARQUET_GEOMETRY_TYPES:
            raise ValueError(f"unsupported GeoParquet geometry type: {kind}")
        if getattr(geom, "has_z", False):
            kind += " Z"
        geom_types.add(kind)
    if not geom_types and declared_geometry_types:
        # An all-null/empty geometry column has no observable types, so retain
        # the source declaration rather than erasing useful schema metadata.
        geom_types.update(declared_geometry_types)
    payload = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": sorted(geom_types),
                "crs": _json_crs(crs),
                "edges": "planar",
            }
        },
    }
    return {"geo": json.dumps(payload, separators=(",", ":"), sort_keys=True)}


def _with_canonical_geometry(
    table: pa.Table,
    source_geometry: str,
    crs: Any,
    declared_geometry_types: list[str] | None = None,
) -> pa.Table:
    shapely = require_spatial("shapely", "Geometry ingestion")
    names = table.column_names
    geom_fields = [name for name in names if name == source_geometry]
    if len(geom_fields) != 1:
        raise ValueError("source must have exactly one geometry column")
    values = table[source_geometry].to_pylist()
    canonical_values: list[bytes | None] = []
    for i, value in enumerate(values):
        if value is None:
            canonical_values.append(None)
            continue
        try:
            geom = shapely.from_wkb(value)
        except Exception as exc:
            raise ValueError(f"malformed WKB geometry at row {i}") from exc
        if getattr(geom, "has_m", False):
            raise ValueError(f"measured (M) geometries are unsupported at row {i}")
        if not shapely.is_valid(geom):
            raise ValueError(f"invalid geometry at row {i}")
        # GeoParquet 1.1 defines OGC WKB. ISO flavor represents Z dimensions
        # portably instead of relying on EWKB high-bit flags.
        canonical_values.append(shapely.to_wkb(geom, flavor="iso"))
    geom_array = pa.array(canonical_values, type=pa.binary())
    if source_geometry in names:
        idx = names.index(source_geometry)
        if source_geometry != "geometry" and "geometry" in names:
            raise ValueError("attribute column 'geometry' conflicts with canonical geometry name")
        table = table.set_column(idx, "geometry", geom_array)
    else:
        table = table.append_column("geometry", geom_array)
    # Rebuild schema metadata only; retain field-level metadata from the reader.
    geo = _geo_metadata(table, "geometry", crs, declared_geometry_types)
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **{k.encode(): v.encode() for k, v in geo.items()}})
    return table


def _read_csv(
    path: Path,
    x: str | None,
    y: str | None,
    *,
    delimiter: str = ",",
    infer_types: bool = False,
    types: dict[str, str] | None = None,
) -> tuple[pa.Table, Any, str | None]:
    if (x is None) != (y is None):
        raise ValueError("x and y must be supplied together")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        try:
            headers = next(csv.reader(stream, delimiter=delimiter))
        except StopIteration as exc:
            raise ValueError("CSV source is empty") from exc
    if any(not name.strip() for name in headers):
        raise ValueError("tabular source has an empty column name")
    if len(headers) != len(set(headers)):
        raise ValueError("tabular source has duplicate column names")
    table = pacsv.read_csv(
        path,
        parse_options=pacsv.ParseOptions(delimiter=delimiter),
        convert_options=pacsv.ConvertOptions(
            column_types={name: pa.string() for name in headers},
            strings_can_be_null=False,
        ),
    )
    if infer_types:
        table = _infer_tabular_types(table, exclude=set(types or {}))
    table = apply_types(table, types, first_row=2)
    if x is None:
        return table, None, None
    if x not in table.column_names or y not in table.column_names:
        raise ValueError(f"coordinate columns {x!r} and {y!r} must exist")
    if "geometry" in table.column_names:
        raise ValueError("CSV already has a geometry column")
    shapely = require_spatial("shapely", "CSV/TSV coordinate ingestion")
    coords: list[bytes | None] = []
    for rowno, (raw_x, raw_y) in enumerate(zip(table[x].to_pylist(), table[y].to_pylist()), 2):
        sx = "" if raw_x is None else str(raw_x).strip()
        sy = "" if raw_y is None else str(raw_y).strip()
        if not sx and not sy:
            coords.append(None)
            continue
        if not sx or not sy:
            raise ValueError(f"partial missing coordinates on CSV row {rowno}")
        try:
            xx, yy = float(sx), float(sy)
        except ValueError as exc:
            raise ValueError(f"malformed coordinates on CSV row {rowno}") from exc
        if not math.isfinite(xx) or not math.isfinite(yy):
            raise ValueError(f"non-finite coordinates on CSV row {rowno}")
        coords.append(shapely.to_wkb(shapely.Point(xx, yy)))
    table = table.append_column("geometry", pa.array(coords, type=pa.binary()))
    return table, None, "geometry"


def _infer_tabular_types(table: pa.Table, *, exclude: set[str] | None = None) -> pa.Table:
    """Infer only unambiguous primitive types from complete string columns.

    Empty cells, leading-zero identifiers, dates, mixed values, and integers
    outside int64 remain strings. Empty strings therefore remain unchanged.
    """
    import re

    bool_values = {"true", "false"}
    int_pattern = re.compile(r"[+-]?(?:0|[1-9][0-9]*)\Z")
    float_pattern = re.compile(r"[+-]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+)\Z")
    result = table
    for index, field in enumerate(table.schema):
        if field.name in (exclude or set()):
            continue
        if not pa.types.is_string(field.type):
            continue
        values = table.column(index).to_pylist()
        # Empty strings are meaningful in the default reader. Keep the whole
        # column as text whenever any occur, rather than turning them into null.
        if not values or any(value == "" for value in values):
            continue
        lowered = [value.casefold() for value in values]
        if all(value in bool_values for value in lowered):
            cast_type = pa.bool_()
            cast_values = [value == "true" for value in lowered]
        elif all(int_pattern.fullmatch(value) for value in values):
            # Leading zeroes commonly encode identifiers, including signed
            # values such as -001. Do not reinterpret them as numbers.
            try:
                cast_values = [int(value) for value in values]
                if any(value < -(2**63) or value > 2**63 - 1 for value in cast_values):
                    continue
            except ValueError:
                continue
            cast_type = pa.int64()
        elif all(float_pattern.fullmatch(value) for value in values):
            # Preserve formatting that could identify a code even when a
            # decimal point or exponent makes the token numeric-looking.
            if any(
                (mantissa := value.lstrip("+-").split("e")[0].split("E")[0]).split(".")[0].startswith("0")
                and len(mantissa.split(".")[0]) > 1
                for value in values
            ):
                continue
            try:
                cast_values = [float(value) for value in values]
            except ValueError:
                continue
            if not all(math.isfinite(value) for value in cast_values):
                continue
            try:
                if any(Decimal(str(parsed)) != Decimal(original) for original, parsed in zip(values, cast_values)):
                    continue
            except InvalidOperation:
                continue
            cast_type = pa.float64()
        else:
            continue
        # Build from parsed values so a failed conversion never partially
        # changes the source table.
        result = result.set_column(index, field.name, pa.array(cast_values, type=cast_type))
    return result


def _source_layers(path: Path) -> list[str]:
    pyogrio = require_spatial("pyogrio", "Vector layer inspection")
    try:
        layers = pyogrio.list_layers(path)
    except Exception as exc:
        raise ValueError(f"could not inspect vector source {path}") from exc
    return [str(row[0]) for row in layers]


def _shapefile_sources(path: Path) -> list[str]:
    if path.suffix.lower() == ".zip":
        return [str(path.resolve())]
    stem = path.stem.lower()
    # Include all existing same-stem sidecars; GDAL may need .shx/.dbf/.prj,
    # while encoding and spatial-index sidecars can affect interpretation.
    return sorted(str(p.resolve()) for p in path.parent.iterdir() if p.is_file() and p.stem.lower() == stem)


def _validate_shapefile_zip(path: Path) -> None:
    """Reject archives that GDAL could interpret as another vector driver."""
    allowed_extensions = {
        ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx",
        ".fbn", ".fbx", ".ain", ".aih", ".atx", ".ixs", ".mxs", ".xml",
    }
    try:
        with zipfile.ZipFile(path) as archive:
            files = [name for name in archive.namelist() if not name.endswith("/")]
            entries = {info.filename.casefold(): info for info in archive.infolist() if not info.is_dir()}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(".zip source is not a valid Shapefile archive") from exc
    if not files:
        raise ValueError(".zip source contains no Shapefile files")
    if len(entries) != len(files):
        raise ValueError(".zip source contains duplicate member names")
    for name in files:
        member_path = PurePosixPath(name)
        if "\\" in name or member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(".zip source contains an unsafe member path")
    suffixes = {Path(name).suffix.lower() for name in files}
    if ".vrt" in suffixes:
        raise ValueError("VRT content is not supported in Shapefile archives")
    if not suffixes <= allowed_extensions:
        raise ValueError(".zip source contains non-Shapefile content")
    names = {name.casefold() for name in files}
    shp_files = [name for name in files if Path(name).suffix.lower() == ".shp"]
    if not shp_files:
        raise ValueError(".zip source contains no .shp file")
    for shp_name in shp_files:
        stem = str(Path(shp_name).with_suffix(""))
        if f"{stem}.shx".casefold() not in names or f"{stem}.dbf".casefold() not in names:
            raise ValueError("each archived .shp requires matching .shx and .dbf files")
        info = entries[shp_name.casefold()]
        with zipfile.ZipFile(path) as archive, archive.open(info) as stream:
            _validate_shapefile_header(stream, info.file_size, shp_name)


def _validate_shapefile_header(stream: Any, file_size: int, label: str) -> None:
    header = stream.read(100)
    if len(header) < 100 or struct.unpack(">i", header[:4])[0] != 9994:
        raise ValueError(f"{label} has an invalid Shapefile header")
    declared_size = struct.unpack(">i", header[24:28])[0] * 2
    if declared_size < 100 or declared_size > file_size:
        raise ValueError(f"{label} has an invalid declared file size")


def _validate_geojson(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("GeoJSON source is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("GeoJSON root must be an object")
    if document.get("type") == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list):
            raise ValueError("GeoJSON FeatureCollection must contain a features array")
        candidates = features
    elif document.get("type") == "Feature":
        candidates = [document]
    else:
        raise ValueError("GeoJSON root must be a Feature or FeatureCollection")

    def valid_geometry(geometry: Any) -> bool:
        if geometry is None:
            return True
        if not isinstance(geometry, dict):
            return False
        kind = geometry.get("type")
        if kind == "GeometryCollection":
            members = geometry.get("geometries")
            return isinstance(members, list) and all(valid_geometry(member) for member in members)
        return kind in {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"} and isinstance(geometry.get("coordinates"), list)

    for index, feature in enumerate(candidates):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"GeoJSON feature at index {index} is invalid")
        if "geometry" not in feature or "properties" not in feature:
            raise ValueError(f"GeoJSON feature at index {index} is missing required members")
        geometry = feature.get("geometry")
        properties = feature.get("properties")
        if not valid_geometry(geometry):
            raise ValueError(f"GeoJSON geometry at index {index} is invalid")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError(f"GeoJSON properties at index {index} must be an object or null")


def _validate_gpkg(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            header = stream.read(72)
    except OSError as exc:
        raise ValueError("could not read GeoPackage header") from exc
    if not header.startswith(b"SQLite format 3\x00"):
        raise ValueError("GeoPackage source has an invalid SQLite header")
    if len(header) < 72 or header[68:72] != b"GPKG":
        raise ValueError("SQLite source is not a GeoPackage")


def read_vector(
    path: str | Path,
    *,
    layer: str | None = None,
    x: str | None = None,
    y: str | None = None,
    crs: str | None = None,
    default_crs: str | None = None,
    infer_types: bool = False,
    types: dict[str, str] | None = None,
    format: str | None = None,
    column_names: str = "preserve",
) -> tuple[pa.Table, dict[str, Any]]:
    """Read a local source into Arrow, with canonical WKB for spatial data.

    This function never reprojects or repairs data. ``crs`` assigns a CRS only
    when the source has none. CSV/TSV attributes remain strings unless
    ``infer_types`` opts into conservative full-column inference.
    """
    source = Path(path)
    if column_names not in {"preserve", "snake_case"}:
        raise ValueError("column_names must be 'preserve' or 'snake_case'")
    if not source.exists():
        raise FileNotFoundError(source)
    types = canonical_types(types)
    _, ext = selected_format(source, format)
    warnings: list[str] = []
    declared_geometry_types: list[str] | None = None
    if ext in {".gdb", ".gdb.zip"}:
        pyogrio = require_spatial("pyogrio", "FileGDB ingestion")
        from .filegdb import directory_files, reader_directory
        if x is not None or y is not None:
            raise ValueError("x and y are only supported for CSV/TSV sources")
        with reader_directory(source) as reader_source:
            layers = _source_layers(reader_source)
            if layer is None:
                if len(layers) != 1:
                    raise ValueError(f"source has {len(layers)} layers; specify layer explicitly; available layers: {layers}")
                selected = layers[0]
            elif layer not in layers:
                raise ValueError(f"layer {layer!r} not found; available layers: {layers}")
            else:
                selected = layer
            try:
                info = pyogrio.read_info(reader_source, layer=selected)
                if info.get("driver") not in {"OpenFileGDB", "FileGDB"}:
                    raise ValueError("source is not a File Geodatabase")
                metadata, table = pyogrio.read_arrow(reader_source, layer=selected)
            except Exception as exc:
                raise ValueError(f"could not read FileGDB layer {selected!r}: {exc}") from exc
        geom_name = metadata.get("geometry_name") or None
        if info.get("geometry_type") is not None:
            if geom_name not in table.column_names:
                attributes = set(metadata.get("fields", []))
                candidates = [field.name for field in table.schema
                              if field.name not in attributes and pa.types.is_binary(field.type)]
                if len(candidates) != 1:
                    raise ValueError("source must contain exactly one supported geometry column")
                geom_name = candidates[0]
            kind = info.get("geometry_type")
            if kind and kind != "Unknown":
                declared_geometry_types = [kind.replace(" ZM", " M").replace("25D", " Z")]
                if kind.endswith((" M", " ZM")):
                    raise ValueError("measured (M) geometries are unsupported")
        else:
            geom_name = None
        src_crs = metadata.get("crs") if geom_name is not None else None
        fmt = "FileGDB"
        warnings.append("FileGDB conversion preserves selected-layer features and field types; domains, relationships, attachments, and other geodatabase behavior are not reproduced.")
        files = ([str(member.resolve()) for member in directory_files(source)]
                 if source.is_dir() else [str(source.resolve())])
    elif ext in {".csv", ".tsv"}:
        if layer is not None:
            raise ValueError("layer is not applicable to CSV/TSV sources")
        if (x is None or y is None) and crs is not None:
            raise ValueError("crs can only be used for CSV/TSV with x and y coordinates")
        table, src_crs, geom_name = _read_csv(
            source, x, y, delimiter="\t" if ext == ".tsv" else ",", infer_types=infer_types, types=types
        )
        files = [str(source.resolve())]
        fmt = "TSV" if ext == ".tsv" else "CSV"
    elif ext in {".parquet", ".geoparquet"}:
        if layer is not None:
            raise ValueError("layer is not applicable to Parquet sources")
        if x is not None or y is not None:
            raise ValueError("x and y are only supported for CSV sources")
        table = pq.read_table(source)
        raw_geo = (table.schema.metadata or {}).get(_GEO_METADATA_KEY)
        if raw_geo is None:
            if crs is not None:
                raise ValueError("crs requires a geometry column")
            geom_name = None
            src_crs = None
            fmt, files = "Parquet", [str(source.resolve())]
        else:
            CRS = require_spatial("pyproj", "GeoParquet ingestion").CRS
            try:
                geo = json.loads(raw_geo)
                columns = geo["columns"]
                if len(columns) != 1:
                    raise ValueError("multiple geometry columns are unsupported")
                geom_name = geo.get("primary_column")
                if geom_name not in columns or geom_name not in table.column_names:
                    raise ValueError("invalid GeoParquet primary geometry column")
                if not pa.types.is_binary(table.schema.field(geom_name).type):
                    raise ValueError("GeoParquet WKB geometry column must use binary storage")
                column_metadata = columns[geom_name]
                if column_metadata.get("encoding") != "WKB":
                    raise ValueError("only GeoParquet WKB geometry encoding is supported")
                if column_metadata.get("edges", "planar") != "planar":
                    raise ValueError("only planar GeoParquet edges are supported")
                if "epoch" in column_metadata:
                    raise ValueError("GeoParquet coordinate epochs are unsupported")
                declared_geometry_types = column_metadata.get("geometry_types", [])
                allowed_types = _GEOPARQUET_GEOMETRY_TYPES | {f"{item} Z" for item in _GEOPARQUET_GEOMETRY_TYPES}
                if not isinstance(declared_geometry_types, list) or not all(item in allowed_types for item in declared_geometry_types):
                    raise ValueError("invalid GeoParquet geometry_types metadata")
                # GeoParquet's omitted crs member means OGC:CRS84; an explicit
                # null member means the CRS is unknown.
                src_crs = columns[geom_name].get("crs", "OGC:CRS84")
                if src_crs is not None:
                    src_crs = CRS.from_user_input(src_crs)
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid GeoParquet metadata") from exc
            fmt, files = "GeoParquet", [str(source.resolve())]
    else:
        pyogrio = require_spatial("pyogrio", "Vector ingestion")
        if x is not None or y is not None:
            raise ValueError("x and y are only supported for CSV/TSV sources")
        if ext == ".zip":
            _validate_shapefile_zip(source)
        elif ext == ".shp":
            try:
                with source.open("rb") as stream:
                    _validate_shapefile_header(stream, source.stat().st_size, str(source))
            except OSError as exc:
                raise ValueError("could not read Shapefile source") from exc
        elif ext == ".gpkg":
            _validate_gpkg(source)
        elif ext in {".geojson", ".json"}:
            _validate_geojson(source)
        # GDAL may dispatch by suffix even after our signature validation.
        # Give an explicitly selected vector reader a local, correctly named
        # copy so the allowlisted choice governs both layer discovery and read.
        reader_source = source
        reader_copy = None
        if source.suffix.lower() not in {ext, ".json" if ext == ".geojson" else ext}:
            if ext == ".shp":
                raise ValueError("explicit Shapefile reader requires a .shp source with its sidecars")
            reader_copy = tempfile.TemporaryDirectory(prefix="moses-reader-")
            reader_source = Path(reader_copy.name) / f"source{ext}"
            shutil.copy2(source, reader_source)
        try:
            layers = _source_layers(reader_source)
            if layer is None:
                if len(layers) != 1:
                    raise ValueError(f"source has {len(layers)} layers; specify layer explicitly; available layers: {layers}")
                selected = layers[0]
            else:
                if layer not in layers:
                    raise ValueError(f"layer {layer!r} not found; available layers: {layers}")
                selected = layer
            try:
                metadata, table = pyogrio.read_arrow(reader_source, layer=selected)
            except Exception as exc:
                raise ValueError(f"could not read vector source {source}") from exc
        finally:
            if reader_copy is not None:
                reader_copy.cleanup()
        geom_name = metadata.get("geometry_name") or None
        # Some OGR drivers (notably ESRI Shapefile) report an empty geometry
        # name even though read_arrow exposes the WKB field as wkb_geometry.
        if geom_name not in table.column_names:
            attribute_names = set(metadata.get("fields", []))
            candidates = [
                field.name for field in table.schema
                if field.name not in attribute_names and pa.types.is_binary(field.type)
            ]
            if len(candidates) == 1:
                geom_name = candidates[0]
        if not geom_name or geom_name not in table.column_names:
            raise ValueError("source does not contain a supported geometry column")
        # Driver metadata reports a single geometry column; reject any extras.
        if len([field for field in table.schema if field.name not in set(metadata.get("fields", [])) and pa.types.is_binary(field.type)]) > 1:
            raise ValueError("multiple geometry columns are unsupported")
        src_crs = metadata.get("crs")
        if ext == ".zip":
            fmt, files = "Shapefile", [str(source.resolve())]
        elif ext == ".shp":
            fmt, files = "Shapefile", _shapefile_sources(source)
        elif ext == ".gpkg":
            fmt, files = "GeoPackage", [str(source.resolve())]
        elif ext in {".geojson", ".json"}:
            fmt, files = "GeoJSON", [str(source.resolve())]
        else:
            fmt, files = (source.suffix.lstrip(".").upper() or "Vector"), [str(source.resolve())]
    source_columns = [name for name in table.column_names if name != "geometry"] if ext in {".csv", ".tsv"} and geom_name == "geometry" else table.column_names[:]
    source_geometry = geom_name
    if geom_name is not None and geom_name in types:
        raise ValueError("geometry cannot receive a primitive type override")
    if ext not in {".csv", ".tsv"}:
        table = apply_types(table, types, first_row=1)
    if geom_name is None and crs is not None:
        raise ValueError("crs requires a geometry column")
    crs_source: str | None = "source" if src_crs is not None else ("unknown" if geom_name is not None else None)
    if geom_name is not None:
        CRS = require_spatial("pyproj", "Geometry ingestion").CRS
    if src_crs is not None and crs is not None:
        if not CRS.from_user_input(src_crs).equals(CRS.from_user_input(crs)):
            raise ValueError("supplied crs conflicts with the source CRS")
    elif src_crs is None and crs is not None:
        src_crs = crs
        crs_source = "explicit"
    elif src_crs is None and geom_name is not None and default_crs is not None:
        src_crs = default_crs
        crs_source = "default"
        warnings.append("Assigned default CRS because the source has no CRS")
    elif src_crs is None and ext in {".csv", ".tsv"} and geom_name is not None:
        src_crs = "EPSG:4326"
        crs_source = "legacy_csv_default"
        warnings.append("CSV/TSV coordinates have no CRS; using the legacy EPSG:4326 fallback")
    if geom_name is not None:
        table = _with_canonical_geometry(
            table,
            geom_name,
            src_crs,
            declared_geometry_types,
        )
    if column_names == "snake_case":
        # The generated/canonical geometry participates in collision checks.
        names = column_name_map(table.column_names, column_names)
        metadata = table.schema.metadata
        table = table.rename_columns([names[name] for name in table.column_names]).replace_schema_metadata(metadata)
        source_map = {name: ("geometry" if name == source_geometry else names[name])
                      for name in source_columns}
    provenance = {
        "format": fmt,
        "layer": layer if layer is not None else (selected if ext not in {".csv", ".tsv", ".parquet", ".geoparquet"} else None),
        "crs": CRS.from_user_input(src_crs).to_string() if src_crs is not None else None,
        "crs_source": crs_source,
        "warnings": warnings,
        "geometry_column": "geometry" if geom_name is not None else None,
        "source_files": files,
    }
    if column_names == "snake_case":
        provenance["column_name_map"] = source_map
    return table, provenance
