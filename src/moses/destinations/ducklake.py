"""Explicit DuckLake publication; no extensions are downloaded by default."""
from __future__ import annotations

import json
import uuid

import duckdb


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _ident(value):
    return '"' + str(value).replace('"', '""') + '"'


class DuckLakePublisher:
    """Publish WKB tables and CRS/provenance in a single DuckLake transaction.

    Supply a configured connection for PostgreSQL/S3 secrets. Its extension
    directory and credentials remain caller-managed. Geometry is BLOB WKB,
    not a native spatial column; metadata lives in ``_moses.versions``.
    """

    def __init__(self, catalog_uri, data_path=None, *, connection=None, install_extensions=False):
        self.catalog_uri = str(catalog_uri)
        self.data_path = data_path
        self.connection = connection
        self.install_extensions = install_extensions

    def publish(self, catalog, name, version=None):
        manifest = catalog.get_version(name, version)
        table = catalog.read(name, manifest["version"])
        owned = self.connection is None
        con = self.connection if self.connection is not None else duckdb.connect()
        alias = "moses_" + uuid.uuid4().hex
        relation = "input_" + uuid.uuid4().hex
        attached = False
        registered = False
        previous_autoinstall = con.execute("SELECT current_setting('autoinstall_known_extensions')").fetchone()[0]
        try:
            if not self.install_extensions:
                con.execute("SET autoinstall_known_extensions = false")
            # Caller opts in to each required download. Local-first operations
            # never enter this module.
            extensions = ["ducklake"]
            if self.catalog_uri.removeprefix("ducklake:").startswith("postgres:"):
                extensions.append("postgres")
            if self.catalog_uri.removeprefix("ducklake:").startswith("sqlite:"):
                extensions.append("sqlite")
            if str(self.data_path or "").startswith("s3://"):
                extensions.append("httpfs")
            for extension in extensions:
                if self.install_extensions:
                    con.execute(f"INSTALL {extension}")
                con.execute(f"LOAD {extension}")
            uri = self.catalog_uri if self.catalog_uri.startswith("ducklake:") else "ducklake:" + self.catalog_uri
            options = f" (DATA_PATH {_literal(self.data_path)})" if self.data_path else ""
            con.execute(f"ATTACH {_literal(uri)} AS {_ident(alias)}{options}")
            attached = True
            # Strip Arrow extension metadata for portable WKB BLOB storage.
            import pyarrow as pa
            clean = pa.Table.from_arrays(table.columns, names=table.column_names)
            con.register(relation, clean)
            registered = True
            prefix = _ident(alias)
            con.execute("BEGIN")
            try:
                con.execute(f"CREATE SCHEMA IF NOT EXISTS {prefix}._moses")
                con.execute(f"CREATE TABLE IF NOT EXISTS {prefix}._moses.versions (dataset VARCHAR, version VARCHAR, manifest JSON, published_at TIMESTAMPTZ)")
                con.execute(f"CREATE OR REPLACE TABLE {prefix}.main.{_ident(name)} AS SELECT * FROM {_ident(relation)}")
                portable = {k: v for k, v in manifest.items() if k not in {"parquet_path", "raw_files"}}
                con.execute(f"INSERT INTO {prefix}._moses.versions VALUES (?, ?, ?, current_timestamp)", [name, manifest["version"], json.dumps(portable)])
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            snapshot = con.execute(f"SELECT * FROM {prefix}.last_committed_snapshot()").fetchone()
            return {"dataset": name, "version": manifest["version"], "ducklake_snapshot": snapshot[0] if snapshot else None, "geometry_encoding": "WKB", "metadata_table": "_moses.versions"}
        finally:
            if owned:
                con.close()
            else:
                if registered:
                    con.unregister(relation)
                if attached:
                    con.execute(f"DETACH {_ident(alias)}")
                con.execute(f"SET autoinstall_known_extensions = {'true' if previous_autoinstall else 'false'}")
