"""Offline production fetch must reject a cache from another release."""
import json

from moses.cli import main


def test_offline_fetch_rejects_cached_release_mismatch_before_catalog(tmp_path, capsys):
    cache = tmp_path / "cache"
    metadata = cache / "release/build_metadata.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"version": "26v1", "commit": "a" * 40}))
    warehouse = tmp_path / "warehouse"
    result = main(["-w", str(warehouse), "pluto", "fetch-production", "--offline",
                   "--release", "26v2", "--cache", str(cache)])
    assert result == 1
    assert not warehouse.exists()
    assert "Cached release does not match --release" in capsys.readouterr().err
