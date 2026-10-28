from pathlib import Path
from io import BytesIO
import hashlib
import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from pluto_example.raw import _list_objects, _object_url, acquire_raw_sources, discover_raw_sources


def _discovery():
    return {"target_release": "26v2", "source_commit": "abc", "inputs": [
        {"name": f"source_{i}", "version": "v1", "normalized_head": 403,
         "selected_raw": {"key": f"raw/source_{i}/2026-08-01T12:00:00-04:00/data.zip",
                          "config_key": f"raw/source_{i}/2026-08-01T12:00:00-04:00/config.json",
                          "config_sha256": "a" * 64, "size": 4,
                          "selection_policy": "provisional exact-version candidate"}}
        for i in range(32)
    ]}


def test_raw_capture_reports_normalization_pending(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, path, *, expected_sha256=None):
        calls.append((url, expected_sha256))
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
        return {"path": str(path), "bytes": 4, "sha256": "b" * 64}

    monkeypatch.setattr("pluto_example.raw.download_url", fake_download)
    result = acquire_raw_sources(_discovery(), tmp_path, max_workers=2)
    assert len(result["inputs"]) == 32
    assert all(row["status"] == "raw_downloaded" and row["normalization_status"] == "reconstruction_pending" for row in result["inputs"])
    assert len(calls) == 64
    assert (tmp_path / "raw-acquisition-report.json").exists()


def test_raw_key_and_selection_validation(tmp_path):
    assert "%3A" in _object_url("raw/source_0/2026-08-01T12:00:00-04:00/data.zip", "source_0")
    with pytest.raises(ValueError, match="Unsafe"):
        _object_url("raw/source_0/../../private", "source_0")
    discovery = _discovery()
    discovery["inputs"][0].pop("selected_raw")
    with pytest.raises(ValueError, match="select every inaccessible"):
        acquire_raw_sources(discovery, tmp_path)


def test_acquire_derives_inaccessible_subset_without_fixed_count(tmp_path, monkeypatch):
    discovery = _discovery()
    discovery["inputs"] = discovery["inputs"][:1] + [{"name": "public", "normalized_head": 200}]

    def fake_download(url, path, *, expected_sha256=None):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
        return {"path": str(path), "bytes": 4, "sha256": "b" * 64}

    monkeypatch.setattr("pluto_example.raw.download_url", fake_download)
    result = acquire_raw_sources(discovery, tmp_path)
    assert [row["name"] for row in result["inputs"]] == ["source_0"]


def test_bucket_listing_uses_continuation_tokens(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        query = parse_qs(urlsplit(request.full_url).query)
        requests.append(query)
        if "continuation-token" not in query:
            body = b'''<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>true</IsTruncated><NextContinuationToken>next</NextContinuationToken><Contents><Key>raw/example/a</Key><Size>3</Size></Contents></ListBucketResult>'''
        else:
            body = b'''<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated><Contents><Key>raw/example/b</Key><Size>4</Size></Contents></ListBucketResult>'''
        return BytesIO(body)

    monkeypatch.setattr("pluto_example.raw.urlopen", fake_urlopen)
    result = _list_objects("raw/example/")
    assert [item["key"] for item in result["keys"]] == ["raw/example/a", "raw/example/b"]
    assert requests[1]["continuation-token"] == ["next"]


def test_discovery_selects_latest_matching_raw_before_normalized_archive(tmp_path, monkeypatch):
    entries = [{"id": f"source_{i}", "version": "v1", "file_type": "parquet",
                "source": "edm.recipes.datasets", "archive_date": "2026-08-01"} for i in range(38)]
    metadata = {"version": "26v2", "commit": "abc", "timestamp": "2026-08-08T17:26:18-04:00",
                "recipe": {"version": "26v2", "inputs": {"datasets": entries}}}
    heads = [{"name": f"source_{i}", "status": 403 if i == 0 else 200} for i in range(38)]
    monkeypatch.setattr("pluto_example.raw.head_sources", lambda *_args, **_kwargs: {"inputs": heads})
    old = "raw/source_0/2026-08-01T10:00:00-04:00/"
    selected = "raw/source_0/2026-08-01T11:00:00-04:00/"
    future = "raw/source_0/2026-08-09T10:00:00-04:00/"

    def fake_list(prefix, *, delimiter=None):
        if prefix.startswith("datasets/"):
            name = prefix.split("/")[1]
            return {"keys": [{"key": prefix + name + ".parquet", "size": 10,
                              "last_modified": "2026-08-02T00:00:00Z", "etag": '"a"'}], "prefixes": []}
        if delimiter == "/":
            return {"keys": [], "prefixes": [old, selected, future]}
        return {"keys": [{"key": prefix + "config.json", "size": 20, "etag": '"b"'},
                         {"key": prefix + "data.zip", "size": 4, "etag": '"c"'}], "prefixes": []}

    def fake_download(url, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = "2026-08-01T11:00:00-04:00" if selected in unquote(url) else "2026-08-01T10:00:00-04:00"
        data = json.dumps({"id": "source_0", "version": "v1", "timestamp": stamp, "raw_filename": "data.zip"}).encode()
        path.write_bytes(data)
        return {"sha256": hashlib.sha256(data).hexdigest()}

    monkeypatch.setattr("pluto_example.raw._list_objects", fake_list)
    monkeypatch.setattr("pluto_example.raw.download_url", fake_download)
    monkeypatch.setattr("pluto_example.raw._head_object", lambda *_args: 200)
    report = discover_raw_sources(metadata, tmp_path, max_workers=2)
    first = report["inputs"][0]
    assert first["selected_raw"]["key"] == selected + "data.zip"
    assert first["selected_raw"]["selection_policy"].endswith("provisional until normalized lineage verified")
    assert future not in first["candidate_raw_prefixes"]
    assert report["inputs"][1]["normalized_head"] == 200
    assert (tmp_path / "public-source-discovery.json").exists()


def test_raw_etag_change_blocks_same_size_capture(tmp_path, monkeypatch):
    discovery = _discovery()
    discovery['inputs'] = discovery['inputs'][:1]
    discovery['inputs'][0]['selected_raw']['etag'] = '"before"'
    monkeypatch.setattr('pluto_example.raw.download_url', lambda url, path, **kwargs: {
        'path': str(path), 'bytes': 4, 'sha256': 'b' * 64, 'etag': '"after"'})
    result = acquire_raw_sources(discovery, tmp_path)
    assert result['inputs'][0]['status'] == 'download_error'
    assert 'ETag changed' in result['inputs'][0]['error']
