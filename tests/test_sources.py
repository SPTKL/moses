import json
from urllib.parse import parse_qs, urlsplit

import pytest

from moses.sources import download_socrata


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.payload


def _feature(identifier):
    return {"type": "Feature", "id": identifier, "geometry": None, "properties": {"id": identifier}}


def test_download_pages_in_stable_order_and_records_provenance(tmp_path, monkeypatch):
    requests = []
    monkeypatch.setattr("moses.sources._PAGE_SIZE", 2)

    def fake_urlopen(request, timeout):
        assert timeout <= 60
        query = parse_qs(urlsplit(request.full_url).query)
        requests.append(query)
        offset = int(query["$offset"][0])
        return _Response({"type": "FeatureCollection", "features": [_feature(offset + 1), _feature(offset + 2)] if offset == 0 else [_feature(offset + 1)]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    dest = tmp_path / "download.geojson"
    info = download_socrata("data.example.gov", "abcd-1234", dest)
    result = json.loads(dest.read_text())
    assert [f["id"] for f in result["features"]] == [1, 2, 3]
    assert [q["$offset"][0] for q in requests] == ["0", "2"]
    assert all(q["$order"] == [":id"] for q in requests)
    assert info["record_count"] == 3
    assert info["snapshot_atomic"] is False
    assert len(info["request_urls"]) == 2
    assert info["retrieved_at"].endswith("+00:00")


def test_limit_is_explicit_and_respected(tmp_path, monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        q = parse_qs(urlsplit(request.full_url).query)
        requests.append(q)
        n = int(q["$limit"][0])
        start = int(q["$offset"][0])
        return _Response({"type": "FeatureCollection", "features": [_feature(i) for i in range(start, start + n)]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    info = download_socrata("data.example.gov", "abcd-1234", tmp_path / "limited.json", limit=3)
    assert info["record_count"] == 3
    assert info["query"]["$limit"] == 3
    assert len(requests) == 1


@pytest.mark.parametrize(
    "domain,dataset,limit",
    [
        ("https://data.example.gov", "abcd-1234", None),
        ("data.example.gov/path", "abcd-1234", None),
        ("data.example.gov", "not-an-id", None),
        ("data.example.gov", "abcd-1234", 0),
        ("data.example.gov", "abcd-1234", True),
    ],
)
def test_download_rejects_unsafe_arguments(tmp_path, domain, dataset, limit):
    with pytest.raises(ValueError):
        download_socrata(domain, dataset, tmp_path / "out.json", limit=limit)


def test_invalid_response_is_rejected_without_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Response({"type": "Feature", "features": []}))
    dest = tmp_path / "bad.geojson"
    with pytest.raises(ValueError, match="FeatureCollection"):
        download_socrata("data.example.gov", "abcd-1234", dest)
    assert not dest.exists()


def test_failed_later_page_preserves_existing_destination(tmp_path, monkeypatch):
    monkeypatch.setattr("moses.sources._PAGE_SIZE", 1)
    dest = tmp_path / "existing.geojson"
    dest.write_text('{"old":true}\n', encoding="utf-8")
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Response({"type": "FeatureCollection", "features": [_feature(1)]})
        raise OSError("temporary network failure")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="request failed"):
        download_socrata("data.example.gov", "abcd-1234", dest)
    assert dest.read_text(encoding="utf-8") == '{"old":true}\n'
    assert list(tmp_path.glob("*.part")) == []
