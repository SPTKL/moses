"""Bounded local raw-format normalization using DuckDB for data operations.

This is an acquisition adapter, not the PLUTO build. Unsupported recipe steps
are reported and subsequent steps remain pending. No geometry is repaired.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

import duckdb
from pyproj import CRS


class RawNormalizationError(ValueError):
    pass


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _identifier(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RawNormalizationError("Column names must be nonempty strings")
    return '"' + value.replace('"', '""') + '"'


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _columns(con, query):
    return [(row[0], row[1]) for row in con.execute("DESCRIBE " + query).fetchall()]


def _project(query, columns):
    names = [name.lower() for _, name in columns]
    if len(set(names)) != len(names):
        raise RawNormalizationError("Recipe would create colliding column names")
    return "SELECT " + ", ".join(f"{expression} AS {_identifier(name)}" for expression, name in columns) + f" FROM ({query}) AS source"


def _zip_member(path, fmt, temporary):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise RawNormalizationError("ZIP contains duplicate member paths")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                raise RawNormalizationError(f"Unsafe ZIP member {name!r}")
        wanted = fmt.get("unzipped_filename")
        suffixes = (".shp",) if fmt["type"] == "shapefile" else (".csv", ".txt", ".tsv")
        candidates = [name for name in names if name.lower().endswith(suffixes)]
        if wanted:
            if wanted not in names:
                raise RawNormalizationError(f"Configured ZIP member {wanted!r} is absent")
            chosen = wanted
        elif len(candidates) == 1:
            chosen = candidates[0]
        else:
            raise RawNormalizationError(f"ZIP member selection ambiguous: {candidates}")
        if fmt["type"] == "shapefile":
            return "/vsizip/" + str(path) + "/" + chosen, chosen
        extracted = Path(temporary) / "source.csv"
        with archive.open(chosen) as source, extracted.open("wb") as target:
            shutil.copyfileobj(source, target)
        return str(extracted), chosen


def normalize_raw(path, config, output, *, extension_directory: Path) -> dict:
    """Convert one captured archive with fixed DuckDB SELECT operations.

    Config may be the full capture config (its matching id is selected), or one
    dataset config. CSV values default to text, preserving source lexical values;
    unspecified pandas inference is explicitly pending rather than emulated.
    """
    source = Path(path).resolve(strict=True)
    output = Path(output).resolve()
    if output == source:
        raise RawNormalizationError("Output cannot replace raw capture")
    if "datasets" in config:
        selected = [item for item in config["datasets"] if item["id"] == config["id"]]
        if len(selected) != 1:
            raise RawNormalizationError("Full config needs exactly one dataset matching its id")
        dataset = selected[0]
    else:
        dataset = config
    fmt = dataset["file_format"]
    kind = fmt["type"].lower()
    if kind not in {"csv", "shapefile", "geojson"}:
        raise RawNormalizationError(f"Unsupported captured format {kind!r}")
    original_hash = _hash(source)
    applied, pending = [], []
    source_crs = None
    target_crs = None
    geom = None
    member = None
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="moses-raw-", dir=output.parent) as temporary:
        con = duckdb.connect(str(Path(temporary) / "work.duckdb"))
        try:
            con.execute("SET memory_limit='1GB'")
            con.execute("SET threads=1")
            con.execute("SET preserve_insertion_order=true")
            con.execute("SET temp_directory=" + _literal(str(Path(temporary) / "spill")))
            con.execute("SET extension_directory=" + _literal(str(Path(extension_directory).resolve())))
            con.execute("SET autoinstall_known_extensions=false")
            con.execute("SET autoload_known_extensions=false")
            con.execute("LOAD spatial")
            location = str(source)
            if zipfile.is_zipfile(source):
                location, member = _zip_member(source, fmt, temporary)
            if kind in {"shapefile", "geojson"}:
                query = f"SELECT * FROM ST_Read({_literal(location)})"
                columns = _columns(con, query)
                geometry_columns = [name for name, dtype in columns if dtype.startswith("GEOMETRY")]
                if len(geometry_columns) != 1:
                    raise RawNormalizationError("Spatial input requires exactly one native geometry column")
                geom = geometry_columns[0]
                metadata = con.execute(f"SELECT * FROM ST_Read_Meta({_literal(location)})").fetchone()
                layer = metadata[3][0]
                crs = layer["geometry_fields"][0].get("crs")
                embedded_crs = None
                if crs:
                    embedded_crs = (crs["auth_name"] + ":" + crs["auth_code"]) if crs.get("auth_name") and crs.get("auth_code") else crs.get("wkt")
                source_crs = fmt.get("crs") or embedded_crs or ("EPSG:4326" if kind == "geojson" else None)
                if fmt.get("crs") and embedded_crs and not CRS.from_user_input(fmt["crs"]).equals(CRS.from_user_input(embedded_crs), ignore_axis_order=True):
                    raise RawNormalizationError("Configured source CRS differs from embedded CRS")
                applied.append({"name": "read_spatial", "engine": "DuckDB ST_Read", "embedded_crs": embedded_crs})
            else:
                options = ["header=" + ("false" if fmt.get("names") else "true"), "all_varchar=true", "sample_size=20480", "strict_mode=true", "null_padding=false"]
                options += ["delim=" + _literal(fmt.get("delimiter", ",")), "nullstr=['']", "allow_quoted_nulls=false"]
                if fmt.get("quoting") == 3:
                    options += ["quote=''", "escape=''"]
                if fmt.get("encoding", "utf-8").lower() not in {"utf-8", "utf8"}:
                    raise RawNormalizationError("Only declared UTF-8 CSV is supported")
                query = f"SELECT * FROM read_csv({_literal(location)}, {', '.join(options)})"
                columns = _columns(con, query)
                usecols, names = fmt.get("usecols"), fmt.get("names")
                selected_names = [name for name, _ in columns]
                if usecols:
                    selected_names = [selected_names[index] if isinstance(index, int) else index for index in usecols]
                    if any(name not in dict(columns) for name in selected_names):
                        raise RawNormalizationError("Configured CSV usecols is missing")
                output_names = names or selected_names
                if len(output_names) != len(selected_names):
                    raise RawNormalizationError("Configured CSV names do not match selected field count")
                query = _project(query, [(_identifier(name), renamed) for name, renamed in zip(selected_names, output_names)])
                applied.append({"name": "read_csv", "all_varchar": True, "null_policy": "unquoted empty is NULL; quoted empty remains empty string"})
                pending.append({"name": "csv_null_policy_compatibility", "reason": "DuckDB preserves quoted empty strings and literal NA tokens; upstream pandas default NA parsing compatibility is not proven"})
                if fmt.get("dtype") != "str":
                    pending.append({"name": "implicit_csv_type_inference", "reason": "Preserved lexical values as VARCHAR; unspecified pandas inference is not reproduced"})
                geometry_config = fmt.get("geometry")
                if geometry_config:
                    source_crs = geometry_config.get("crs")
                    column = geometry_config["geom_column"]
                    if isinstance(column, dict):
                        x, y = _identifier(column["x"]), _identifier(column["y"])
                        expression = f"CASE WHEN TRY_CAST({x} AS DOUBLE) IS NOT NULL AND TRY_CAST({y} AS DOUBLE) IS NOT NULL THEN ST_Point(CAST({x} AS DOUBLE), CAST({y} AS DOUBLE)) ELSE NULL END"
                    elif geometry_config.get("format") == "wkb":
                        expression = f"ST_GeomFromWKB(from_hex({_identifier(column)}))"
                    else:
                        raise RawNormalizationError("Unsupported declared CSV geometry format")
                    columns = _columns(con, query)
                    query = _project(query, [(_identifier(name), name) for name, _ in columns if not isinstance(column, str) or name != column] + [(expression, "geom")])
                    geom = "geom"
                    applied.append({"name": "convert_declared_geometry", "source_crs": source_crs, "axis_policy": "configured x/y; no swap"})
            target_crs = source_crs
            steps = dataset.get("processing_steps", [])
            for index, step in enumerate(steps):
                name, args = step["name"], step.get("args", {})
                columns = _columns(con, query)
                expressions = [(_identifier(column), column) for column, _ in columns]
                if name == "clean_column_names":
                    cleaned = []
                    for column, _ in columns:
                        renamed = column
                        for old, new in args.get("replace", {}).items():
                            renamed = renamed.replace(old, new)
                        if args.get("lower"):
                            renamed = renamed.lower()
                        if column == geom:
                            geom = renamed
                        cleaned.append((_identifier(column), renamed))
                    expressions = cleaned
                elif name == "rename_columns":
                    mapping = args.get("map", {})
                    expressions = [(_identifier(column), mapping.get(column, column)) for column, _ in columns]
                    geom = mapping.get(geom, geom)
                elif name == "multi" and geom:
                    expressions = [(f"ST_Multi({_identifier(column)})" if column == geom else _identifier(column), column) for column, _ in columns]
                elif name == "strip_columns":
                    chosen = args.get("cols", args.get("columns", [column for column, dtype in columns if dtype == "VARCHAR"]))
                    expressions = [(f"trim({_identifier(column)})" if column in chosen else _identifier(column), column) for column, _ in columns]
                elif name == "coerce_column_types":
                    mapping = args.get("column_types", {})
                    missing = set(mapping) - dict(columns).keys()
                    if missing:
                        raise RawNormalizationError(f"Declared type columns missing: {sorted(missing)}")
                    types = {"string": "VARCHAR", "str": "VARCHAR", "int": "BIGINT", "int64": "BIGINT", "integer": "INTEGER", "bigint": "BIGINT", "numeric": "DOUBLE", "float": "DOUBLE", "float64": "DOUBLE", "date": "DATE"}
                    if any(dtype not in types for dtype in mapping.values()):
                        pending.extend([{**remaining, "reason": "unsupported declared coercion"} for remaining in steps[index:]])
                        break
                    cast = "TRY_CAST" if args.get("errors") == "coerce" else "CAST"
                    expressions = []
                    for column, _ in columns:
                        expression = _identifier(column)
                        if column in mapping and mapping[column] == "date":
                            text = f"CAST({_identifier(column)} AS VARCHAR)"
                            date = f"CAST(coalesce(TRY_CAST({text} AS TIMESTAMP), try_strptime({text}, ['%m/%d/%Y %H:%M:%S.%f','%m/%d/%Y %H:%M:%S','%m/%d/%Y','%Y%m%d'])) AS DATE)"
                            expression = date if args.get("errors") == "coerce" else f"CASE WHEN {_identifier(column)} IS NOT NULL AND {date} IS NULL THEN error('Invalid declared date field') ELSE {date} END"
                        elif column in mapping:
                            expression = f"{cast}({_identifier(column)} AS {types[mapping[column]]})"
                        expressions.append((expression, column))
                elif name == "pd_series_func" and args.get("function_name") == "str.replace" and args.get("pat") == "\r\n" and args.get("repl") == "\n":
                    expressions = [(f"replace({_identifier(column)}, {_literal(chr(13)+chr(10))}, {_literal(chr(10))})" if column == args["column_name"] else _identifier(column), column) for column, _ in columns]
                else:
                    pending.extend([{**remaining, "reason": "unsupported step; raw row grain retained"} for remaining in steps[index:]])
                    break
                query = _project(query, expressions)
                applied.append(step)
            requested_crs = dataset.get("target_crs")
            if geom and requested_crs:
                if not source_crs:
                    raise RawNormalizationError("target_crs requires known source CRS")
                columns = _columns(con, query)
                query = _project(query, [(f"ST_Transform({_identifier(column)}, {_literal(source_crs)}, {_literal(requested_crs)}, always_xy := true)" if column == geom else _identifier(column), column) for column, _ in columns])
                target_crs = requested_crs
                applied.append({"name": "target_crs", "source": source_crs, "target": target_crs, "always_xy": True})
            status, invalid, null_geometry, geometry_types = "nonspatial", 0, 0, []
            if geom:
                stats = con.execute(f"SELECT count(*), count(*) FILTER (WHERE {_identifier(geom)} IS NOT NULL AND NOT ST_IsValid({_identifier(geom)})), count(*) FILTER (WHERE {_identifier(geom)} IS NULL), list(DISTINCT CAST(ST_GeometryType({_identifier(geom)}) AS VARCHAR)) FROM ({query}) AS final").fetchone()
                rows, invalid, null_geometry, geometry_types = stats
                status = "raw_invalid_topology" if invalid else "valid_spatial" if target_crs else "raw_unknown_crs"
                columns = _columns(con, query)
                query = _project(query, [(f"CAST(ST_AsWKB({_identifier(column)}) AS BLOB)" if column == geom else _identifier(column), "wkb_geometry" if column == geom else column) for column, _ in columns])
                geom = "wkb_geometry"
            else:
                rows = con.execute(f"SELECT count(*) FROM ({query}) AS final").fetchone()[0]
            kv = {}
            if status == "valid_spatial":
                types = {"POINT": "Point", "LINESTRING": "LineString", "POLYGON": "Polygon", "MULTIPOINT": "MultiPoint", "MULTILINESTRING": "MultiLineString", "MULTIPOLYGON": "MultiPolygon", "GEOMETRYCOLLECTION": "GeometryCollection"}
                geo = {"version": "1.1.0", "primary_column": geom, "columns": {geom: {"encoding": "WKB", "geometry_types": [types[value] for value in geometry_types if value is not None], "crs": CRS.from_user_input(target_crs).to_json_dict()}}}
                kv["geo"] = json.dumps(geo)
            elif geom:
                kv["moses_raw_geometry"] = json.dumps({"column": geom, "crs": target_crs, "status": status, "invalid_geometries": invalid})
            staging = Path(temporary) / "output.parquet"
            kv_sql = ", KV_METADATA {" + ", ".join(_identifier(key) + ": " + _literal(value) for key, value in kv.items()) + "}" if kv else ""
            con.execute(f"COPY ({query}) TO {_literal(staging)} (FORMAT PARQUET, COMPRESSION ZSTD{kv_sql})")
            if original_hash != _hash(source):
                raise RawNormalizationError("Raw capture changed while normalizing")
            os.replace(staging, output)
        finally:
            con.close()
    return {"dataset": dataset["id"], "source_path": str(source), "source_sha256": original_hash,
            "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            "normalized_path": str(output), "normalized_sha256": _hash(output), "rows": rows,
            "geometry_column": geom, "source_crs": source_crs, "crs": target_crs,
            "geometry_status": status, "invalid_geometries": invalid, "null_geometries": null_geometry,
            "recipe_steps_applied": applied, "recipe_steps_pending": pending, "normalization_pending": bool(pending),
            "archive_member": member, "engine": {"duckdb": duckdb.__version__, "spatial": "installed local extension; no downloads"},
            "resource_limits": {"memory_limit": "1GB", "threads": 1, "spill": True},
            "transform_engine": "DuckDB SELECT and COPY only", "geometry_repairs": False,
            "date_policy": "DuckDB ISO timestamp/date or explicit US month-first formats; invalid dates follow declared errors policy",
            "csv_null_policy": {"unquoted_empty": "NULL", "quoted_empty": "empty string", "NA_tokens": "literal strings", "upstream_pandas_compatibility": "not_proven"} if kind == "csv" else None,
            "code_sha256": _hash(Path(__file__))}
