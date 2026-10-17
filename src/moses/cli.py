"""A small CLI; each command is also available through the Python API."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

from .catalog import Catalog


def _json(value):
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _type_overrides(values):
    from .recipes import canonical_types

    choices = {}
    for item in values:
        field, separator, kind = item.partition("=")
        if not separator or not field or not kind:
            raise ValueError("--type must use FIELD=TYPE")
        if field in choices:
            raise ValueError(f"duplicate --type for field {field!r}")
        choices[field] = kind
    return canonical_types(choices)


def parser():
    p = argparse.ArgumentParser(prog="moses", description="Local-first, versioned geospatial ELT")
    p.add_argument("--warehouse", "-w", default=".moses", help="Warehouse directory (default: .moses)")
    p.add_argument("--version", action="version", version="moses 0.1.0")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a local warehouse")
    init.add_argument("--default-crs", help="Fallback CRS for geometry without a source CRS")
    sub.add_parser("demo", help="Load a tiny bundled synthetic NYC example, offline")
    load = sub.add_parser("load", help="Capture a local vector or tabular file as a versioned table")
    load.add_argument("source")
    load.add_argument("--name", required=True)
    load.add_argument("--key")
    load.add_argument("--layer")
    load.add_argument("--x")
    load.add_argument("--y")
    load.add_argument("--crs")
    load.add_argument("--infer-types", action="store_true", help="Conservatively infer CSV/TSV types using all rows")
    load.add_argument("--type", dest="types", action="append", default=[], metavar="FIELD=TYPE",
                      help="Override one column with string, bool, int64, or float64; repeatable")
    load.add_argument("--format", help="Explicit supported reader: CSV, TSV, Parquet, GeoJSON, GeoPackage, Shapefile")
    inspect = sub.add_parser("inspect", help="Inspect a local file without publishing a version (full-file read)")
    inspect.add_argument("source")
    inspect.add_argument("--layer")
    inspect.add_argument("--x")
    inspect.add_argument("--y")
    inspect.add_argument("--crs")
    inspect.add_argument("--infer-types", action="store_true")
    inspect.add_argument("--type", dest="types", action="append", default=[], metavar="FIELD=TYPE")
    inspect.add_argument("--format")
    inspect.add_argument("--preview-rows", type=int, default=10)
    sub.add_parser("list", help="List current datasets")
    history = sub.add_parser("history", help="List accepted dataset versions")
    history.add_argument("name")
    diff = sub.add_parser("diff", help="Compare two accepted versions")
    diff.add_argument("name")
    diff.add_argument("old")
    diff.add_argument("new")
    query = sub.add_parser("query", help="Run SQL against current datasets; geometry is WKB")
    query.add_argument("sql")
    query.add_argument("--lock", help="Read exact dataset versions from a JSON lockfile")
    lock = sub.add_parser("lock", help="Save exact current input versions for reproducible SQL")
    lock.add_argument("destination")
    export = sub.add_parser("export", help="Export an exact version as GeoParquet")
    export.add_argument("name")
    export.add_argument("destination")
    export.add_argument("--version", dest="dataset_version")
    nyc = sub.add_parser("nyc", help="Download a NYC Open Data GeoJSON dataset (network required)")
    nyc.add_argument("dataset_id")
    nyc.add_argument("--name", required=True)
    nyc.add_argument("--key")
    nyc.add_argument("--limit", type=int, help="Explicit sample limit; omitted downloads all pages")
    s3 = sub.add_parser("publish-s3", help="Publish an immutable version bundle to S3-compatible storage")
    s3.add_argument("name")
    s3.add_argument("bucket")
    s3.add_argument("--prefix", default="moses")
    s3.add_argument("--endpoint-url")
    s3.add_argument("--version", dest="dataset_version")
    lake = sub.add_parser("publish-ducklake", help="Publish into an optional DuckLake destination")
    lake.add_argument("name")
    lake.add_argument("catalog_uri", help="Local catalog filename or DuckLake metadata URI")
    lake.add_argument("--data-path")
    lake.add_argument("--version", dest="dataset_version")
    lake.add_argument("--install-extensions", action="store_true", help="Allow explicit extension downloads")
    return p


def resolve_version(catalog, name, version=None):
    versions = catalog.history(name)
    if version is None and versions:
        return versions[-1]
    for item in versions:
        if item["version"] == version:
            return item
    raise ValueError(f"Unknown dataset/version: {name}/{version or 'latest'}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        # Inspection must not create a catalog or warehouse as a side effect.
        if args.command == "inspect":
            from .config import resolve_default_crs
            from .inspection import inspect_source
            result = inspect_source(
                args.source, layer=args.layer, x=args.x, y=args.y, crs=args.crs,
                default_crs=resolve_default_crs(args.warehouse),
                infer_types=args.infer_types, preview_rows=args.preview_rows,
                types=_type_overrides(args.types), format=args.format,
            )
            print(json.dumps(result, indent=2, default=_json, allow_nan=False))
            return 0
        if args.command == "init" and args.default_crs is not None:
            from .config import set_default_crs
            set_default_crs(args.warehouse, args.default_crs)
        catalog = Catalog(args.warehouse)
        match args.command:
            case "init":
                from .config import resolve_default_crs
                result = {"warehouse": str(Path(args.warehouse).resolve()),
                          "default_crs": resolve_default_crs(args.warehouse)}
            case "demo":
                fixture = files("moses").joinpath("examples/places.geojson")
                result = catalog.ingest(str(fixture), name="places", key="id", provenance={"description": "Synthetic NYC example; not official city data"})
            case "load":
                result = catalog.ingest(args.source, name=args.name, key=args.key, layer=args.layer, x=args.x, y=args.y, crs=args.crs, infer_types=args.infer_types, types=_type_overrides(args.types), format=args.format)
            case "list":
                result = catalog.datasets()
            case "history":
                result = catalog.history(args.name)
            case "diff":
                result = catalog.diff(args.name, args.old, args.new)
            case "query":
                versions = json.loads(Path(args.lock).read_text()) if args.lock else None
                result = catalog.query(args.sql, versions=versions).to_pylist()
            case "lock":
                versions = catalog.lock()
                with Path(args.destination).open("x", encoding="utf-8") as stream:
                    json.dump(versions, stream, indent=2)
                    stream.write("\n")
                result = {"path": str(Path(args.destination).resolve()), "versions": versions}
            case "export":
                manifest = resolve_version(catalog, args.name, args.dataset_version)
                destination = Path(args.destination)
                if destination.exists():
                    raise ValueError(f"Destination already exists: {destination}")
                source = Path(manifest["parquet_path"])
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents overwriting another process's export.
                with source.open("rb") as src, destination.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
                result = {"path": str(destination.resolve()), "version": manifest["version"]}
            case "nyc":
                from .sources import download_socrata
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "source.geojson"
                    provenance = download_socrata("data.cityofnewyork.us", args.dataset_id, path, limit=args.limit)
                    result = catalog.ingest(path, name=args.name, key=args.key, provenance=provenance)
            case "publish-s3":
                from .destinations.s3 import S3Publisher
                result = S3Publisher(args.bucket, prefix=args.prefix, endpoint_url=args.endpoint_url).publish(catalog, args.name, args.dataset_version)
            case "publish-ducklake":
                from .destinations.ducklake import DuckLakePublisher
                result = DuckLakePublisher(args.catalog_uri, data_path=args.data_path, install_extensions=args.install_extensions).publish(catalog, args.name, args.dataset_version)
        print(json.dumps(result, indent=2, default=_json, allow_nan=False))
        return 0
    except Exception as exc:
        # Library calls preserve their exception types; the CLI provides a concise error.
        print(f"moses: {exc}", file=sys.stderr)
        return 1
