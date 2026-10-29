"""Spatial extension lifecycle and command behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pytest

from moses.cli import main
from moses.spatial import SpatialError, install_spatial, spatial_connection, spatial_status


def _cached_extension():
    cache = Path(os.environ.get("MOSES_EXTENSION_DIRECTORY", Path(__file__).resolve().parents[1] / ".extensions"))
    con = duckdb.connect()
    try:
        platform = con.execute("PRAGMA platform").fetchone()[0]
    finally:
        con.close()
    return cache, cache / f"v{duckdb.__version__}" / platform / "spatial.duckdb_extension"


def test_missing_extension_is_actionable_and_never_installed(tmp_path):
    cache = tmp_path / "extensions"
    status = spatial_status(cache)
    assert status["state"] == "missing"
    assert status["duckdb_version"] == duckdb.__version__
    assert "moses spatial install" in status["remedy"]
    with pytest.raises(SpatialError) as caught:
        with spatial_connection(extension_directory=cache):
            pass
    assert caught.value.code == "missing"
    assert "moses spatial install" in caught.value.remedy
    assert not list(cache.rglob("*.duckdb_extension"))


def test_environment_cache_and_explicit_override(monkeypatch, tmp_path):
    env_cache = tmp_path / "environment"
    explicit_cache = tmp_path / "explicit"
    monkeypatch.setenv("MOSES_EXTENSION_DIRECTORY", str(env_cache))
    assert spatial_status()["extension_directory"] == str(env_cache)
    assert spatial_status(explicit_cache)["extension_directory"] == str(explicit_cache)


def test_cli_status_does_not_create_warehouse(tmp_path, capsys):
    cache = tmp_path / "extensions"
    warehouse = tmp_path / "warehouse"
    assert main(["--warehouse", str(warehouse), "spatial", "status", "--extension-directory", str(cache)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "missing"
    assert result["extension_directory"] == str(cache)
    assert not warehouse.exists()


def test_cli_spatial_bypasses_warehouse_configuration(monkeypatch, tmp_path, capsys):
    def unexpected_resolution(*args, **kwargs):
        raise AssertionError("warehouse configuration should not be read")

    monkeypatch.setattr("moses.config.resolve_warehouse", unexpected_resolution)
    cache = tmp_path / "extensions"
    assert main(["spatial", "status", "--extension-directory", str(cache)]) == 1
    assert json.loads(capsys.readouterr().out)["state"] == "missing"


def test_install_failure_is_structured(monkeypatch):
    class FailingConnection:
        closed = False

        def execute(self, sql):
            assert sql == "INSTALL spatial"
            raise duckdb.IOException("network unavailable")

        def close(self):
            self.closed = True

    con = FailingConnection()
    monkeypatch.setattr("moses.spatial._connect", lambda database, extension_directory: con)
    with pytest.raises(SpatialError) as caught:
        install_spatial()
    assert caught.value.code == "install_failed"
    assert "network unavailable" in caught.value.detail
    assert "retry" in caught.value.remedy
    assert con.closed


def test_incompatible_cached_extension_has_clear_status(monkeypatch, tmp_path):
    cache = tmp_path / "extensions"
    monkeypatch.setattr("moses.spatial._extension_row", lambda con: {
        "installed": True, "loaded": False, "install_path": str(cache / "spatial.duckdb_extension"),
        "extension_version": "old", "install_mode": "REPOSITORY", "installed_from": "core",
    })

    def incompatible(con):
        raise SpatialError("load_failed", "Binary is incompatible", "Install a compatible copy")

    monkeypatch.setattr("moses.spatial._load", incompatible)
    status = spatial_status(cache)
    assert status["state"] == "incompatible"
    assert status["error"]["code"] == "load_failed"
    assert status["error"]["remedy"] == "Install a compatible copy"


def test_version_mismatch_never_loads_extension(monkeypatch, tmp_path):
    monkeypatch.setattr("moses.spatial._extension_row", lambda con: {
        "installed": True, "loaded": False, "install_path": str(tmp_path / "spatial.duckdb_extension"),
        "extension_version": "other", "install_mode": "REPOSITORY", "installed_from": "core",
    })

    def unexpected_load(con):
        raise AssertionError("a mismatched extension must not load")

    monkeypatch.setattr("moses.spatial._load", unexpected_load)
    status = spatial_status(tmp_path, expected_version="pinned")
    assert status["error"]["code"] == "version_mismatch"
    with pytest.raises(SpatialError) as caught:
        with spatial_connection(extension_directory=tmp_path, expected_version="pinned"):
            pass
    assert caught.value.code == "version_mismatch"


@pytest.mark.integration
def test_pinned_version_rejects_mismatch_before_yield():
    cache, extension = _cached_extension()
    if not extension.exists():
        pytest.skip("No compatible Spatial extension in the local test cache")
    actual = spatial_status(cache)["extension_version"]
    assert spatial_status(cache, expected_version=actual)["state"] == "ready"
    mismatch = spatial_status(cache, expected_version="wrong-version")
    assert mismatch["state"] == "incompatible"
    assert mismatch["error"]["code"] == "version_mismatch"
    yielded = False
    with pytest.raises(SpatialError, match="version_mismatch"):
        with spatial_connection(extension_directory=cache, expected_version="wrong-version"):
            yielded = True
    assert not yielded


def test_cli_install_is_an_explicit_action(monkeypatch, tmp_path, capsys):
    calls = []

    def install(extension_directory, *, expected_version, force):
        calls.append((extension_directory, expected_version, force))
        return {"state": "ready", "extension_name": "spatial"}

    monkeypatch.setattr("moses.spatial.install_spatial", install)
    cache = str(tmp_path / "cache")
    assert main(["spatial", "install", "--extension-directory", cache,
                 "--expected-version", "pinned", "--force"]) == 0
    assert calls == [(cache, "pinned", True)]
    assert json.loads(capsys.readouterr().out)["state"] == "ready"


def test_force_install_uses_explicit_replacement(monkeypatch):
    class Connection:
        def __init__(self):
            self.commands = []

        def execute(self, sql):
            self.commands.append(sql)

        def close(self):
            pass

    con = Connection()
    monkeypatch.setattr("moses.spatial._connect", lambda database, extension_directory: con)
    monkeypatch.setattr("moses.spatial._extension_row", lambda connection: {
        "installed": True, "loaded": True, "install_path": "cache/spatial.duckdb_extension",
        "extension_version": "pinned", "install_mode": "REPOSITORY", "installed_from": "core",
    })
    assert install_spatial(expected_version="pinned", force=True)["state"] == "ready"
    assert con.commands == ["FORCE INSTALL spatial", "LOAD spatial"]


@pytest.mark.integration
def test_cached_spatial_loads_without_download():
    cache, extension = _cached_extension()
    if not extension.exists():
        pytest.skip("No compatible Spatial extension in the local test cache")
    with spatial_connection(extension_directory=cache) as con:
        assert con.execute("SELECT ST_AsText(ST_Point(1, 2))").fetchone()[0] == "POINT (1 2)"
        assert con.execute("SELECT current_setting('autoinstall_known_extensions')").fetchone()[0] is False
        assert con.execute("SELECT current_setting('autoload_known_extensions')").fetchone()[0] is False
    status = spatial_status(cache)
    assert status["state"] == "ready"
    assert status["extension_version"]
    assert status["install_path"] == str(extension)
