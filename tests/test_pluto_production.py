import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from moses.pluto.production import acquire_release_sources, download_url, head_sources, release_inputs


def _manifest():
    return {"version": "26v2", "commit": "abc", "recipe": {"version": "26v2", "inputs": {"datasets": [
        {"id": f"source_{i}", "version": f"v{i}", "file_type": "pg_dump" if i == 1 else "parquet",
         "source": "edm.recipes.datasets", "import_as": "previous_pluto" if i == 0 else None}
        for i in range(38)
    ]}}}


class _Response(BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.status = 200
        self.headers = {"Content-Length": str(len(data) if length is None else length), "ETag": '"etag"'}


def test_exact_release_paths_and_invariants():
    rows = release_inputs(_manifest())
    assert len(rows) == 38
    assert rows[0]["alias"] == "previous_pluto"
    assert rows[0]["url"].endswith("/datasets/source_0/v0/source_0.parquet")
    assert rows[1]["url"].endswith("/datasets/source_1/v1/source_1.sql")
    bad = _manifest()
    bad["recipe"]["inputs"]["datasets"][2]["version"] = "latest"
    with pytest.raises(ValueError, match="Unresolved"):
        release_inputs(bad)
    bad = _manifest()
    bad["recipe"]["inputs"]["datasets"][2]["id"] = "../escape"
    with pytest.raises(ValueError, match="Unresolved"):
        release_inputs(bad)


def test_streamed_download_validates_cache_every_rerun(tmp_path, monkeypatch):
    data = b"production bytes"
    calls = []

    def fetch(request, timeout):
        calls.append(request.full_url)
        return _Response(data)

    monkeypatch.setattr("moses.pluto.production.urlopen", fetch)
    path = tmp_path / "capture.parquet"
    first = download_url("https://example.test/versioned", path, expected_sha256=hashlib.sha256(data).hexdigest())
    assert first["cached"] is False and path.read_bytes() == data
    assert download_url("https://example.test/versioned", path)["cached"] is True
    assert len(calls) == 1
    path.write_bytes(b"corrupt")
    repaired = download_url("https://example.test/versioned", path)
    assert repaired["cached"] is False and path.read_bytes() == data
    assert len(calls) == 2
    assert json.loads(path.with_name(path.name + ".capture.json").read_text())["sha256"] == hashlib.sha256(data).hexdigest()


def test_incomplete_download_keeps_prior_complete_capture(tmp_path, monkeypatch):
    path = tmp_path / "capture.parquet"
    monkeypatch.setattr("moses.pluto.production.urlopen", lambda *_args, **_kwargs: _Response(b"good"))
    download_url("https://example.test/first", path)
    monkeypatch.setattr("moses.pluto.production.urlopen", lambda *_args, **_kwargs: _Response(b"bad", length=20))
    with pytest.raises(ValueError, match="Incomplete transfer"):
        download_url("https://example.test/second", path)
    assert path.read_bytes() == b"good"
    assert not path.with_name(path.name + ".partial").exists()


def test_head_and_acquire_report_exact_statuses(tmp_path, monkeypatch):
    def fetch(request, timeout):
        if "/source_1/" in request.full_url:
            raise HTTPError(request.full_url, 403, "private", {}, None)
        return _Response(b"id\n001\n")

    monkeypatch.setattr("moses.pluto.production.urlopen", fetch)
    head = head_sources(_manifest(), max_workers=2)
    assert [row["status"] for row in head["inputs"][:2]] == [200, 403]
    calls = []

    def adapter(row, path, capture):
        calls.append(row["name"])
        assert Path(path).read_bytes() == b"id\n001\n"
        assert capture["sha256"] == hashlib.sha256(b"id\n001\n").hexdigest()
        return {"catalog_version": "locked"}

    report = acquire_release_sources(_manifest(), tmp_path, ingest_adapter=adapter, max_workers=2)
    assert report["inputs"][0]["status"] == "acquired"
    assert report["inputs"][1]["status"] == "access_blocked"
    assert len(calls) == 37
    assert json.loads((tmp_path / "acquisition-report.json").read_text())["inputs"][1]["http_status"] == 403
