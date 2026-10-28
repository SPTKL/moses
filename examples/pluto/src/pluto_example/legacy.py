"""Data-only normalization of the bounded ogr2ogr PostgreSQL COPY dump format.

SQL is parsed, never executed. Supported declarations are SERIAL, VARCHAR and
FLOAT8 plus one AddGeometryColumn MULTIPOLYGON/2D declaration. Other statements
or types fail explicitly. Invalid topology is preserved and reported, not fixed.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS
import shapely


class LegacyDumpError(ValueError):
    """The dump is outside the explicitly supported data-only format."""


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _copy_text(value: str) -> str | None:
    if value == r"\N":
        return None
    data = value.encode("utf-8")
    output = bytearray()
    index = 0
    escaped = {ord("b"): 8, ord("f"): 12, ord("n"): 10, ord("r"): 13,
               ord("t"): 9, ord("v"): 11, ord("\\"): 92}
    while index < len(data):
        char = data[index]
        index += 1
        if char != 92:
            output.append(char)
            continue
        if index == len(data):
            raise LegacyDumpError("COPY text field ends with an incomplete escape")
        char = data[index]
        index += 1
        if char in escaped:
            output.append(escaped[char])
        elif 48 <= char <= 55:
            digits = bytes([char])
            while index < len(data) and len(digits) < 3 and 48 <= data[index] <= 55:
                digits += bytes([data[index]])
                index += 1
            number = int(digits, 8)
            if number > 255:
                raise LegacyDumpError("COPY octal escape is outside one byte")
            output.append(number)
        elif char == ord("x"):
            digits = b""
            while index < len(data) and len(digits) < 2 and chr(data[index]) in "0123456789abcdefABCDEF":
                digits += bytes([data[index]])
                index += 1
            if not digits:
                raise LegacyDumpError("COPY hex escape has no digits")
            output.append(int(digits, 16))
        else:
            output.append(char)
    if 0 in output:
        raise LegacyDumpError("PostgreSQL text cannot contain a zero byte")
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LegacyDumpError("COPY text is not valid UTF-8 after escape decoding") from exc


def normalize_legacy_dump(path: Path, output: Path, *, dataset: str) -> dict:
    """Normalize one captured ogr2ogr dump without ingestion or SQL execution.

    The original SQL is the authoritative raw capture. The returned provenance
    records its hash/path and all interpretation choices. The output is replaced
    atomically only after the whole dump has passed syntax/schema checks.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", dataset):
        raise LegacyDumpError("dataset must be a lowercase SQL identifier")
    source = Path(path).resolve(strict=True)
    output = Path(output).resolve()
    if source == output:
        raise LegacyDumpError("Normalized output cannot replace the original dump")
    identifier = re.escape(dataset)
    table = rf'"public"\."{identifier}"'
    serial_create = rf'CREATE TABLE {table} \( "ogc_fid" SERIAL, CONSTRAINT "{identifier}_pk" PRIMARY KEY \("ogc_fid"\) \);'
    column_pattern = re.compile(rf'ALTER TABLE {table} ADD COLUMN "([a-z_][a-z0-9_]*)" (VARCHAR|FLOAT8|SERIAL(?: CONSTRAINT "{identifier}_pk" PRIMARY KEY)?);')
    geometry_pattern = re.compile(rf"SELECT AddGeometryColumn\('public','{identifier}','([a-z_][a-z0-9_]*)',([0-9]+),'MULTIPOLYGON',2\);")
    copy_pattern = re.compile(rf'COPY {table} \(("[a-z_][a-z0-9_]*"(?:, "[a-z_][a-z0-9_]*")*)\) FROM STDIN;')
    ignored = [rf'DROP TABLE IF EXISTS {table} CASCADE;',
               rf'CREATE INDEX "{identifier}_[a-z0-9_]+" ON {table} USING GIST \("[a-z_][a-z0-9_]*"\);',
               rf'COMMENT ON TABLE {table} IS NULL;']
    fields = []
    values = {}
    declared = {}
    geometry = None
    srid = None
    copy_columns = None
    in_copy = False
    completed_copy = False
    created = False
    rows = 0
    invalid = []
    invalid_count = 0
    null_geometry = 0
    standard_strings = None
    terminated = False
    with source.open(encoding="utf-8", newline="") as stream:
        for line_number, raw in enumerate(stream, 1):
            line = raw.rstrip("\r\n")
            if in_copy:
                if line == r"\.":
                    in_copy = False
                    completed_copy = True
                    continue
                cells = line.split("\t")
                if len(cells) != len(copy_columns):
                    raise LegacyDumpError(f"line {line_number}: COPY has {len(cells)} values; expected {len(copy_columns)}")
                rows += 1
                values["ogc_fid"].append(rows)
                for name, cell in zip(copy_columns, cells):
                    try:
                        value = _copy_text(cell)
                        kind = declared[name]
                        if kind == "geometry" and value is not None:
                            encoded = bytes.fromhex(value)
                            shape = shapely.from_wkb(encoded, on_invalid="raise")
                            if int(shapely.get_srid(shape)) != srid:
                                raise LegacyDumpError(f"EWKB SRID differs from declared EPSG:{srid}")
                            if shape.geom_type != "MultiPolygon" or int(shapely.get_coordinate_dimension(shape)) != 2:
                                raise LegacyDumpError("EWKB geometry type/dimension differs from MULTIPOLYGON/2D declaration")
                            if not bool(shapely.is_valid(shape)):
                                invalid_count += 1
                                if len(invalid) < 20:
                                    invalid.append({"ogc_fid": rows, "reason": str(shapely.is_valid_reason(shape))})
                            value = shapely.to_wkb(shape, include_srid=False, flavor="iso")
                        elif kind == "geometry":
                            null_geometry += 1
                        elif kind == "FLOAT8" and value is not None:
                            if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?(?:Infinity|inf)|NaN", value, re.IGNORECASE):
                                raise LegacyDumpError("invalid FLOAT8 literal")
                            number = float(value)
                            if math.isinf(number) and "inf" not in value.lower():
                                raise LegacyDumpError("FLOAT8 overflow")
                            if number == 0 and not Decimal(value).is_zero():
                                raise LegacyDumpError("FLOAT8 underflow")
                            value = number
                        values[name].append(value)
                    except (ValueError, shapely.errors.GEOSException) as exc:
                        raise LegacyDumpError(f"line {line_number}, {name}: {exc}") from exc
                continue
            if not line:
                continue
            setting = re.fullmatch(r"SET standard_conforming_strings = (ON|OFF);", line)
            if setting and not created:
                standard_strings = setting.group(1)
                continue
            if line in {"BEGIN;", "END;", "COMMIT;"}:
                if line == "BEGIN;" and (created or completed_copy):
                    raise LegacyDumpError(f"line {line_number}: unexpected BEGIN")
                if line in {"END;", "COMMIT;"}:
                    if not completed_copy:
                        raise LegacyDumpError(f"line {line_number}: transaction ends before completed COPY")
                    terminated = True
                continue
            if any(re.fullmatch(pattern, line) for pattern in ignored):
                if line.startswith("DROP TABLE") and created:
                    raise LegacyDumpError(f"line {line_number}: DROP after CREATE is unsupported")
                continue
            if re.fullmatch(serial_create, line) or re.fullmatch(rf'CREATE TABLE {table}\(\);', line):
                if created or completed_copy:
                    raise LegacyDumpError(f"line {line_number}: repeated CREATE TABLE")
                created = True
                if re.fullmatch(serial_create, line):
                    fields.append(pa.field("ogc_fid", pa.int32(), nullable=False))
                    declared["ogc_fid"] = "SERIAL"
                    values["ogc_fid"] = []
                continue
            match = column_pattern.fullmatch(line)
            geometry_match = geometry_pattern.fullmatch(line)
            if match or geometry_match:
                if not created or copy_columns is not None:
                    raise LegacyDumpError(f"line {line_number}: declaration outside pre-COPY schema")
                if geometry_match:
                    name, srid_text = geometry_match.groups()
                    if geometry is not None:
                        raise LegacyDumpError("Only one declared geometry is supported")
                    geometry, srid = name, int(srid_text)
                    CRS.from_epsg(srid)
                    kind, arrow_type = "geometry", pa.binary()
                else:
                    name, kind = match.groups()
                    kind = "SERIAL" if kind.startswith("SERIAL") else kind
                    if kind == "SERIAL" and name != "ogc_fid":
                        raise LegacyDumpError("Only ogc_fid SERIAL is supported")
                    arrow_type = {"SERIAL": pa.int32(), "VARCHAR": pa.string(), "FLOAT8": pa.float64()}[kind]
                if name in declared:
                    raise LegacyDumpError(f"Duplicate column declaration {name}")
                fields.append(pa.field(name, arrow_type, nullable=kind != "SERIAL"))
                declared[name], values[name] = kind, []
                continue
            match = copy_pattern.fullmatch(line)
            if match:
                if copy_columns is not None or not created or geometry is None or declared.get("ogc_fid") != "SERIAL":
                    raise LegacyDumpError(f"line {line_number}: unsupported/repeated COPY or missing schema")
                copy_columns = re.findall(r'"([a-z_][a-z0-9_]*)"', match.group(1))
                if len(set(copy_columns)) != len(copy_columns) or set(copy_columns) != set(declared) - {"ogc_fid"}:
                    raise LegacyDumpError("COPY must supply each non-SERIAL declared column exactly once")
                in_copy = True
                continue
            raise LegacyDumpError(f"line {line_number}: unsupported SQL statement {line[:120]!r}")
    if in_copy or not completed_copy or standard_strings is None or not terminated:
        raise LegacyDumpError("Incomplete COPY dump or missing standard_conforming_strings declaration")
    metadata = {"version": "1.1.0", "primary_column": geometry, "columns": {geometry: {
        "encoding": "WKB", "geometry_types": ["MultiPolygon"], "crs": CRS.from_epsg(srid).to_json_dict(), "edges": "planar"}}}
    arrow = pa.Table.from_pydict(values, schema=pa.schema(fields, metadata={b"geo": json.dumps(metadata).encode()}))
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(prefix="legacy-", suffix=".parquet", dir=output.parent)
    os.close(handle)
    try:
        pq.write_table(arrow, staging)
        os.replace(staging, output)
    finally:
        Path(staging).unlink(missing_ok=True)
    return {"dataset": dataset, "original_path": str(source), "original_sha256": _digest(source),
            "normalized_path": str(output), "normalized_sha256": _digest(output), "rows": rows,
            "columns": list(declared), "declared_types": declared, "schema": str(arrow.schema),
            "format": "ogr2ogr PostgreSQL COPY text", "parser": "data-only; no SQL executed",
            "standard_conforming_strings": standard_strings, "encoding": "UTF-8",
            "numeric_policy": "VARCHAR kept as string; FLOAT8 parsed as IEEE float64; no blank-to-null coercion",
            "null_policy": r"COPY unescaped \N only is NULL; escaped literal and empty strings preserved",
            "serial_policy": "ogc_fid generated 1-based in COPY row order, as fresh PostgreSQL SERIAL restore",
            "geometry_column": geometry, "crs": f"EPSG:{srid}",
            "geometry_conversion": "EWKB to ISO WKB; SRID moved to GeoParquet CRS metadata; coordinates/order unchanged; no repair/reprojection",
            "invalid_geometries": invalid_count, "invalid_examples": invalid, "null_geometries": null_geometry,
            "engines": {"pyarrow": pa.__version__, "shapely": shapely.__version__},
            "code_sha256": _digest(Path(__file__))}
