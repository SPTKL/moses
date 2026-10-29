"""Explicit, offline-safe lifecycle for DuckDB's Spatial extension."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path

import duckdb


class SpatialError(RuntimeError):
    """A Spatial setup failure with a stable code and actionable guidance."""

    def __init__(self, code: str, detail: str, remedy: str):
        self.code = code
        self.detail = detail
        self.remedy = remedy
        super().__init__(f"Spatial {code}: {detail}. {remedy}")

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail, "remedy": self.remedy}


def _directory(extension_directory: str | Path | None) -> Path | None:
    value = extension_directory if extension_directory is not None else os.environ.get("MOSES_EXTENSION_DIRECTORY")
    return Path(value).expanduser().resolve() if value else None


def _connect(database: str, extension_directory: str | Path | None):
    config = {
        "autoinstall_known_extensions": "false",
        "autoload_known_extensions": "false",
    }
    if extension_directory is not None:
        config["extension_directory"] = str(extension_directory)
    try:
        return duckdb.connect(database=database, config=config)
    except duckdb.Error as exc:
        raise SpatialError(
            "connection_failed", str(exc),
            "Check the DuckDB database and --extension-directory path and permissions",
        ) from exc


def _extension_row(con) -> dict:
    row = con.execute(
        "SELECT installed, loaded, install_path, extension_version, install_mode, installed_from "
        "FROM duckdb_extensions() WHERE extension_name = 'spatial'"
    ).fetchone()
    if row is None:
        raise SpatialError(
            "unsupported", f"DuckDB {duckdb.__version__} does not list the Spatial extension",
            "Use a DuckDB build that supports Spatial",
        )
    return dict(zip(
        ("installed", "loaded", "install_path", "extension_version", "install_mode", "installed_from"), row,
    ))


def _identity(row: dict, extension_directory: str | Path | None) -> dict:
    return {
        "duckdb_version": duckdb.__version__,
        "extension_name": "spatial",
        "extension_version": row["extension_version"] or None,
        "install_path": row["install_path"] or None,
        "install_mode": row["install_mode"],
        "installed_from": row["installed_from"] or None,
        "extension_directory": str(extension_directory) if extension_directory is not None else None,
    }


def _check_version(row: dict, expected_version: str | None) -> None:
    if expected_version is None:
        return
    actual = row["extension_version"] or None
    if actual != expected_version:
        raise SpatialError(
            "version_mismatch",
            f"Expected Spatial extension version {expected_version!r}, found {actual!r}",
            "Provide a cache with the pinned Spatial version using --extension-directory "
            "or MOSES_EXTENSION_DIRECTORY",
        )


def _load(con) -> None:
    try:
        con.execute("LOAD spatial")
    except duckdb.Error as exc:
        raise SpatialError(
            "load_failed", str(exc),
            "Repair the cached extension with `moses spatial install --force` "
            "(add --extension-directory for a custom cache)",
        ) from exc


def spatial_status(extension_directory: str | Path | None = None, *, expected_version: str | None = None) -> dict:
    """Inspect and verify the installed extension without downloading anything."""
    extension_directory = _directory(extension_directory)
    con = _connect(":memory:", extension_directory)
    try:
        row = _extension_row(con)
        result = _identity(row, extension_directory)
        if not row["installed"]:
            return {
                **result, "state": "missing", "loaded": False,
                "remedy": "Run `moses spatial install` to download Spatial explicitly "
                "(add --extension-directory for a custom cache)",
            }
        try:
            _check_version(row, expected_version)
            _load(con)
            row = _extension_row(con)
            _check_version(row, expected_version)
        except SpatialError as exc:
            return {**result, "state": "incompatible", "loaded": False, "error": exc.as_dict()}
        return {**_identity(row, extension_directory), "state": "ready", "loaded": True}
    finally:
        con.close()


def install_spatial(extension_directory: str | Path | None = None, *, expected_version: str | None = None,
                    force: bool = False) -> dict:
    """Download Spatial only when called explicitly, then verify it loads."""
    extension_directory = _directory(extension_directory)
    con = _connect(":memory:", extension_directory)
    try:
        try:
            con.execute("FORCE INSTALL spatial" if force else "INSTALL spatial")
        except duckdb.Error as exc:
            raise SpatialError(
                "install_failed", str(exc),
                "Check network access and the extension cache permissions, then retry "
                "`moses spatial install` (use --force to replace a bad cached copy)",
            ) from exc
        row = _extension_row(con)
        _check_version(row, expected_version)
        _load(con)
        row = _extension_row(con)
        _check_version(row, expected_version)
        return {**_identity(row, extension_directory), "state": "ready", "loaded": True}
    finally:
        con.close()


@contextmanager
def spatial_connection(database: str = ":memory:", *, extension_directory: str | Path | None = None,
                       expected_version: str | None = None):
    """Open a Spatial-enabled DuckDB connection from an already installed copy."""
    extension_directory = _directory(extension_directory)
    con = _connect(database, extension_directory)
    try:
        row = _extension_row(con)
        if not row["installed"]:
            raise SpatialError(
                "missing", f"Spatial is not installed for DuckDB {duckdb.__version__}",
                "Run `moses spatial install` explicitly (add --extension-directory "
                "if using a custom cache)",
            )
        _check_version(row, expected_version)
        _load(con)
        _check_version(_extension_row(con), expected_version)
        yield con
    finally:
        con.close()
