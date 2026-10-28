"""A small, local, immutable vector dataset catalog.

The catalog keeps complete source-file captures and GeoParquet releases under
``root``. SQLite is only an index: file paths in it are relative to ``root`` so
the whole directory can be moved. Tables and diffs are materialized in memory.
"""

from __future__ import annotations

import base64
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_value(value: Any) -> Any:
    """Encode Arrow/Python scalars without losing bytes or temporal types."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (datetime, date, time)):
        return {"__temporal__": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, float):
        return {"__float__": value.hex()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Cannot encode metadata value of type {type(value).__name__}")


def _encoded(value: Any) -> bytes:
    return json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _row_tokens(table: pa.Table) -> list[bytes]:
    # In-memory MVP: Arrow's Python conversion is deliberate and keeps WKB bytes.
    return [_encoded(row) for row in table.to_pylist()]


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_versions() -> dict[str, str]:
    versions = {"pyarrow": pa.__version__, "sqlite": sqlite3.sqlite_version}
    for package in ("duckdb", "pyogrio", "shapely", "pyproj"):
        try:
            versions[package] = package_version(package)
        except PackageNotFoundError:
            pass
    return versions


class Catalog:
    """Versioned local catalog for datasets small enough to inspect in memory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "raw").mkdir(exist_ok=True)
        (self.root / "snapshots").mkdir(exist_ok=True)
        (self.root / ".staging").mkdir(exist_ok=True)
        self.db_path = self.root / "catalog.sqlite3"
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    name TEXT PRIMARY KEY,
                    current_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS versions (
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    PRIMARY KEY (name, version)
                );
                CREATE INDEX IF NOT EXISTS versions_by_dataset
                    ON versions (name, created_at, version);
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    raw_files_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
        finally:
            conn.close()

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError("Dataset name must match [A-Za-z_][A-Za-z0-9_]*")

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _public_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Expose usable paths while keeping the SQLite manifest relocatable."""
        result = dict(manifest)
        result["parquet_path"] = str(self.root / result["parquet_path"])
        result["raw_files"] = [str(self.root / item) for item in result["raw_files"]]
        return result

    def _manifest(self, conn: sqlite3.Connection, name: str, version: str | None = None) -> dict[str, Any]:
        if version is None:
            row = conn.execute("SELECT current_version FROM datasets WHERE name = ?", (name,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown dataset: {name}")
            version = row["current_version"]
        row = conn.execute(
            "SELECT manifest_json FROM versions WHERE name = ? AND version = ?", (name, version)
        ).fetchone()
        if row is None:
            if conn.execute("SELECT 1 FROM datasets WHERE name = ?", (name,)).fetchone() is None:
                raise KeyError(f"Unknown dataset: {name}")
            raise KeyError(f"Unknown version {version} of dataset {name}")
        return json.loads(row["manifest_json"])

    @staticmethod
    def _source_paths(path: Path, meta: dict[str, Any]) -> list[Path]:
        reported = meta.get("source_files") or [str(path)]
        if isinstance(reported, (str, Path)):
            reported = [reported]
        files: list[Path] = []
        for item in reported:
            candidate = Path(item)
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            candidate = candidate.resolve(strict=True)
            if not candidate.is_file():
                raise ValueError(f"Source is not a regular file: {candidate}")
            if candidate not in files:
                files.append(candidate)
        if path not in files:
            files.insert(0, path)
        return files

    @staticmethod
    def _validate_key(table: pa.Table, key: str | None) -> None:
        if key is None:
            return
        if key not in table.column_names:
            raise ValueError(f"Key column {key!r} is missing")
        values = table.column(key).to_pylist()
        if any(value is None for value in values):
            raise ValueError(f"Key column {key!r} contains null values")
        tokens = [_encoded(value) for value in values]
        if len(set(tokens)) != len(tokens):
            raise ValueError(f"Key column {key!r} contains duplicate values")

    def ingest(
        self,
        path: str | Path,
        *,
        name: str,
        key: str | None = None,
        layer: str | None = None,
        x: str | None = None,
        y: str | None = None,
        crs: str | None = None,
        infer_types: bool = False,
        types: dict[str, str] | None = None,
        format: str | None = None,
        column_names: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Capture source files and publish a release if logical content changed.

        SQLite serializes writers. Files are published first, then the current
        version pointer commits; failed imports therefore leave the previous
        release readable. Orphaned immutable files after a failure are harmless.
        """
        from .ingest import read_vector
        from .config import resolve_column_names, resolve_default_crs
        from .recipes import canonical_types, import_recipe, selected_format

        self._validate_name(name)
        if key is not None and (not isinstance(key, str) or not key):
            raise ValueError("key must be a nonempty column name")
        if provenance is None:
            provenance = {}
        if not isinstance(provenance, dict):
            raise TypeError("provenance must be a dictionary")
        # Validate JSON compatibility before staging any files.
        provenance_json = _encoded(provenance).decode("utf-8")
        provenance = json.loads(provenance_json)
        from .filegdb import copy_directory, directory_files, reject_symlink_path
        source = Path(path).expanduser().absolute()
        if source.is_dir() or source.name.lower().endswith((".gdb", ".gdb.zip")) or (isinstance(format, str) and format.lower() in {"filegdb", "openfilegdb"}):
            reject_symlink_path(source)
        source = source.resolve(strict=True)
        if not source.is_file() and not source.is_dir():
            raise ValueError(f"Source is not a regular file or FileGDB directory: {source}")
        options = {"layer": layer, "x": x, "y": y, "crs": crs}
        column_names = resolve_column_names(explicit=column_names)["column_names"]
        if column_names == "snake_case":
            options["column_names"] = column_names
        type_choices = canonical_types(types)
        if type_choices:
            options["types"] = type_choices
        chosen, _ = selected_format(source, format)
        if format is not None:
            try:
                inferred, _ = selected_format(source)
            except ValueError:
                inferred = None
            if chosen != inferred:
                options["format"] = chosen
        # Keep the legacy options unchanged when no new behavior is requested,
        # so an existing warehouse does not create releases merely on upgrade.
        default_crs = resolve_default_crs(self.root)
        if default_crs is not None:
            options["default_crs"] = default_crs
        # Only CSV/TSV readers infer types. Inapplicable flags must not change
        # the effective recipe or create a release of identical native data.
        if infer_types and chosen in {"CSV", "TSV"}:
            options["infer_types"] = True

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stage = Path(tempfile.mkdtemp(prefix="import-", dir=self.root / ".staging"))
            try:
                collision = conn.execute(
                    "SELECT name FROM datasets WHERE lower(name) = lower(?) AND name != ?",
                    (name, name),
                ).fetchone()
                if collision:
                    raise ValueError(f"Dataset name {name!r} conflicts with {collision['name']!r}")
                # The first read discovers every constituent file; the second
                # reads exclusively from the captured, immutable copy.
                if chosen == "FileGDB" and source.is_dir():
                    source_files = directory_files(source)
                    discovered = None
                else:
                    _, discovered = read_vector(source, **options)
                    source_files = self._source_paths(source, discovered)
                # An unused fallback is not part of the interpretation. Changing
                # it must not release identical nonspatial/embedded-CRS data.
                if discovered is not None and discovered.get("crs_source") != "default":
                    options.pop("default_crs", None)
                before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in source_files}
                raw_stage = stage / "raw"
                raw_stage.mkdir()
                copies: dict[Path, Path] = {}
                if source.is_dir():
                    copy_directory(source, raw_stage / source.name)
                    copies = {original: raw_stage / source.name / original.relative_to(source)
                              for original in source_files}
                else:
                    for original in source_files:
                        target = raw_stage / original.name
                        if target in copies.values():
                            raise ValueError("Source files have colliding names")
                        shutil.copy2(original, target)
                        copies[original] = target
                after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in source_files}
                if before != after or (source.is_dir() and directory_files(source) != source_files):
                    raise RuntimeError("Source files changed while being captured; retry import")
                # This hashes the *bundle* (names and bytes). Including names
                # ensures an existing raw directory has the files referenced by
                # its manifest even if a later import renames the source.
                source_fingerprint = hashlib.sha256()
                for original in source_files:
                    name_bytes = copies[original].relative_to(raw_stage).as_posix().encode("utf-8")
                    source_fingerprint.update(len(name_bytes).to_bytes(8, "big"))
                    source_fingerprint.update(name_bytes)
                    source_fingerprint.update(bytes.fromhex(_digest_file(copies[original])))
                source_sha256 = source_fingerprint.hexdigest()
                raw_dir = self.root / "raw" / source_sha256
                captured_source = raw_stage / source.name if source.is_dir() else copies[source]
                table, meta = read_vector(captured_source, **options)
                if not isinstance(table, pa.Table) or not isinstance(meta, dict):
                    raise TypeError("read_vector must return an Arrow Table and metadata dictionary")
                if meta.get("crs_source") != "default":
                    options.pop("default_crs", None)
                if key is not None and column_names == "snake_case":
                    if key not in meta["column_name_map"]:
                        raise ValueError(f"Key source column {key!r} is missing")
                    accepted_key = meta["column_name_map"][key]
                else:
                    accepted_key = key
                self._validate_key(table, accepted_key)
                recipe = import_recipe(metadata=meta, options=options)
                current = conn.execute(
                    "SELECT current_version FROM datasets WHERE name = ?", (name,)
                ).fetchone()
                old_manifest = self._manifest(conn, name) if current else None
                if old_manifest and old_manifest["key"] != accepted_key:
                    raise ValueError(f"Key for {name} cannot change from {old_manifest['key']!r} to {accepted_key!r}")

                # Include schema, values and interpretation options. Source bytes
                # and provenance are observations, not logical dataset identity.
                row_hashes = sorted(_row_tokens(table))
                logical = hashlib.sha256()
                # Arrow's display string may abbreviate long metadata values;
                # serialized schema bytes keep the full field and GeoParquet metadata.
                schema_bytes = table.schema.serialize().to_pybytes()
                logical.update(len(schema_bytes).to_bytes(8, "big"))
                logical.update(schema_bytes)
                logical.update(_encoded({
                    "geometry_column": meta.get("geometry_column"),
                    "crs": meta.get("crs"),
                    "key": accepted_key,
                    "options": options,
                }))
                logical.update(b"\x00")
                for token in row_hashes:
                    logical.update(len(token).to_bytes(8, "big"))
                    logical.update(token)
                content_sha256 = logical.hexdigest()
                old_content = None
                if current:
                    old_content = conn.execute(
                        "SELECT content_sha256 FROM versions WHERE name = ? AND version = ?",
                        (name, current["current_version"]),
                    ).fetchone()["content_sha256"]

                if not raw_dir.exists():
                    raw_stage.rename(raw_dir)
                raw_files = [self._relative_path(raw_dir / copies[p].relative_to(raw_stage)) for p in source_files]
                observed_at = _utc_now()
                if content_sha256 == old_content:
                    assert old_manifest is not None
                    conn.execute(
                        "INSERT INTO observations (name, version, observed_at, source_sha256, raw_files_json, provenance_json) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (name, old_manifest["version"], observed_at, source_sha256,
                         json.dumps(raw_files), provenance_json),
                    )
                    conn.commit()
                    return {**self._public_manifest(old_manifest), "unchanged": True, "observed_at": observed_at,
                            "observation_source_sha256": source_sha256}

                version = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}"
                snapshot_dir = self.root / "snapshots" / name
                snapshot_dir.mkdir(exist_ok=True)
                parquet_path = snapshot_dir / f"{version}.parquet"
                parquet_stage = stage / "snapshot.parquet"
                pq.write_table(table, parquet_stage)
                parquet_stage.rename(parquet_path)
                manifest = {
                    "dataset": name,
                    "version": version,
                    "created_at": observed_at,
                    "row_count": table.num_rows,
                    "schema": str(table.schema),
                    "geometry_column": meta.get("geometry_column"),
                    "crs": meta.get("crs"),
                    "crs_source": meta.get("crs_source"),
                    "warnings": meta.get("warnings", []),
                    "source_sha256": source_sha256,
                    "content_sha256": content_sha256,
                    "key": accepted_key,
                    "parquet_path": self._relative_path(parquet_path),
                    "format": meta.get("format"),
                    "layer": meta.get("layer"),
                    "source_files": [str(p) for p in source_files],
                    "raw_files": raw_files,
                    "options": options,
                    "recipe": recipe,
                    "provenance": provenance,
                    "runtime_versions": _runtime_versions(),
                }
                if column_names == "snake_case":
                    manifest["column_name_map"] = meta["column_name_map"]
                manifest_json = _encoded(manifest).decode("utf-8")
                conn.execute(
                    "INSERT INTO versions (name, version, created_at, content_sha256, manifest_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (name, version, observed_at, content_sha256, manifest_json),
                )
                conn.execute(
                    "INSERT INTO datasets (name, current_version) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET current_version = excluded.current_version",
                    (name, version),
                )
                conn.execute(
                    "INSERT INTO observations (name, version, observed_at, source_sha256, raw_files_json, provenance_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name, version, observed_at, source_sha256, json.dumps(raw_files), provenance_json),
                )
                conn.commit()
                return self._public_manifest(manifest)
            except BaseException:
                conn.rollback()
                raise
            finally:
                shutil.rmtree(stage, ignore_errors=True)

    def history(self, name: str) -> list[dict[str, Any]]:
        self._validate_name(name)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT manifest_json FROM versions WHERE name = ? ORDER BY created_at, version", (name,)
            ).fetchall()
        return [self._public_manifest(json.loads(row["manifest_json"])) for row in rows]

    def datasets(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT v.manifest_json FROM datasets d JOIN versions v "
                "ON d.name = v.name AND d.current_version = v.version ORDER BY d.name"
            ).fetchall()
        return [self._public_manifest(json.loads(row["manifest_json"])) for row in rows]

    def lock(self) -> dict[str, str]:
        """Capture the current dataset versions for a reproducible query."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, current_version FROM datasets ORDER BY name"
            ).fetchall()
        return {row["name"]: row["current_version"] for row in rows}

    def get_version(self, name: str, version: str | None = None) -> dict[str, Any]:
        self._validate_name(name)
        with self._connect() as conn:
            return self._public_manifest(self._manifest(conn, name, version))

    def observations(self, name: str) -> list[dict[str, Any]]:
        """Return source captures, including imports with unchanged content."""
        self._validate_name(name)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT version, observed_at, source_sha256, raw_files_json, provenance_json "
                "FROM observations WHERE name = ? ORDER BY id", (name,)
            ).fetchall()
        return [
            {
                "dataset": name,
                "version": row["version"],
                "observed_at": row["observed_at"],
                "source_sha256": row["source_sha256"],
                "raw_files": [str(self.root / path) for path in json.loads(row["raw_files_json"])],
                "provenance": json.loads(row["provenance_json"]),
            }
            for row in rows
        ]

    def read(self, name: str, version: str | None = None) -> pa.Table:
        self._validate_name(name)
        with self._connect() as conn:
            manifest = self._manifest(conn, name, version)
        return pq.read_table(self.root / manifest["parquet_path"])

    def diff(self, name: str, old: str, new: str) -> dict[str, Any]:
        self._validate_name(name)
        with self._connect() as conn:
            old_manifest = self._manifest(conn, name, old)
            new_manifest = self._manifest(conn, name, new)
        old_table = self.read(name, old)
        new_table = self.read(name, new)
        key = old_manifest["key"]
        if key != new_manifest["key"]:
            raise ValueError("Cannot diff versions with different keys")
        schema_changed = not old_table.schema.equals(new_table.schema, check_metadata=True)
        if key is None:
            before = Counter(_row_tokens(old_table))
            after = Counter(_row_tokens(new_table))
            added = sum((after - before).values())
            removed = sum((before - after).values())
            changed = 0
        else:
            before = dict(zip((_encoded(v) for v in old_table[key].to_pylist()), _row_tokens(old_table)))
            after = dict(zip((_encoded(v) for v in new_table[key].to_pylist()), _row_tokens(new_table)))
            added = len(after.keys() - before.keys())
            removed = len(before.keys() - after.keys())
            changed = sum(before[k] != after[k] for k in before.keys() & after.keys())
        return {
            "added": added, "removed": removed, "changed": changed,
            "old_version": old, "new_version": new, "key": key,
            "schema_changed": schema_changed,
            "old_schema": old_manifest["schema"] if schema_changed else None,
            "new_schema": new_manifest["schema"] if schema_changed else None,
        }

    def query(self, sql: str, *, versions: dict[str, str] | None = None) -> pa.Table:
        """Query current snapshots with DuckDB, without extension/network access."""
        import duckdb

        if not isinstance(sql, str) or not re.match(r"^\s*(SELECT|WITH)\b", sql, re.IGNORECASE):
            raise ValueError("Only SELECT queries are supported")
        if ";" in sql.rstrip().rstrip(";"):
            raise ValueError("Only one query is supported")
        if versions is None:
            # The join in datasets() is one SQLite snapshot. Each subsequent
            # read must use that manifest's version, even if a writer publishes
            # a newer release while this query is registering tables.
            selected = {item["dataset"]: item["version"] for item in self.datasets()}
        else:
            if not isinstance(versions, dict):
                raise TypeError("versions must be a mapping of dataset names to version strings")
            selected = {}
            for name, version in versions.items():
                self._validate_name(name)
                if not isinstance(version, str) or not version:
                    raise ValueError("Each locked version must be a nonempty string")
                selected[name] = version
        con = duckdb.connect(database=":memory:")
        try:
            for name, version in selected.items():
                con.register(name, self.read(name, version))
            con.execute("SET enable_external_access = false")
            return con.execute(sql).to_arrow_table()
        finally:
            con.close()
