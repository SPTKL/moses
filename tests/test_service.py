import http.client
import json
from pathlib import Path
import sqlite3
import threading

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from moses.catalog import Catalog
from moses.service import _safe_value, create_server


TOKEN = "test-token-at-least-sixteen-characters"


def request(server, method, path, *, token=TOKEN, host=None, origin=None, body=None, headers=None):
    address, port = server.server_address
    connection = http.client.HTTPConnection(address, port, timeout=5)
    given = {"Host": host or f"{address}:{port}"}
    if token is not None:
        given["Authorization"] = "Bearer " + token
    if origin is not None:
        given["Origin"] = origin
    if body is not None:
        given["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    if headers:
        given.update(headers)
    connection.request(method, path, body=body, headers=given)
    response = connection.getresponse()
    payload = response.read()
    content_type = response.getheader("Content-Type")
    result = json.loads(payload) if payload and content_type and content_type.startswith("application/json") else payload
    status = response.status
    connection.close()
    return status, result


@pytest.fixture
def warehouse(tmp_path):
    root = tmp_path / "warehouse"
    source = tmp_path / "source.csv"
    source.write_text("id,value\na,old\n", encoding="utf-8")
    catalog = Catalog(root)
    first = catalog.ingest(source, name="places", key="id", provenance={"private_path": str(source)})
    source.write_text("id,value\na,new\nb,added\n", encoding="utf-8")
    second = catalog.ingest(source, name="places", key="id")
    return root, first, second


@pytest.fixture
def server(warehouse):
    root, _, _ = warehouse
    instance = create_server(root, TOKEN)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


def test_auth_origin_host_and_loopback(server):
    assert request(server, "GET", "/v1/datasets", token=None)[0] == 401
    assert request(server, "GET", "/v1/datasets", token="wrong")[1]["error"]["code"] == "unauthorized"
    assert request(server, "GET", "/v1/datasets", token=TOKEN + "é")[1]["error"]["code"] == "unauthorized"
    assert request(server, "GET", "/v1/datasets", host="evil.example")[1]["error"]["code"] == "invalid_host"
    assert request(server, "GET", "/v1/datasets", origin="https://evil.example")[1]["error"]["code"] == "invalid_origin"
    address, port = server.server_address
    assert request(server, "GET", "/v1/datasets", origin=f"http://{address}:{port}")[0] == 200
    with pytest.raises(ValueError, match="loopback"):
        create_server(server.root, TOKEN, host="0.0.0.0")
    with pytest.raises(ValueError, match="token"):
        create_server(server.root, "short")


def test_opaque_persistent_exact_versions_preview_compare_and_download(server, warehouse):
    root, first, second = warehouse
    status, listing = request(server, "GET", "/v1/datasets")
    assert status == 200
    dataset = listing["datasets"][0]
    dataset_id = dataset["dataset_id"]
    assert dataset_id.startswith("ds_")
    assert dataset["current_version_id"].startswith("ver_")
    status, history = request(server, "GET", f"/v1/datasets/{dataset_id}/versions")
    assert status == 200
    older, newer = history["versions"]
    assert older["version_id"] != newer["version_id"]
    assert older["row_count"] == 1 and newer["row_count"] == 2
    assert str(root) not in json.dumps(history)
    assert str(root.parent / "source.csv") not in json.dumps(history)
    for key in ("parquet_path", "raw_files", "source_files", "provenance"):
        assert key not in older
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{older['version_id']}")[1] == older

    route = f"/v1/datasets/{dataset_id}/versions/{older['version_id']}"
    preview = request(server, "GET", route + "/preview?limit=1")[1]
    assert preview["rows"] == [{"id": "a", "value": "old"}], preview
    assert preview["version_id"] == older["version_id"]
    status, data = request(server, "GET", route + "/download")
    assert status == 200 and data == Path(first["parquet_path"]).read_bytes()

    diff = request(server, "GET", f"/v1/datasets/{dataset_id}/compare?from={older['version_id']}&to={newer['version_id']}")[1]
    assert (diff["added"], diff["removed"], diff["changed"]) == (1, 0, 1)
    assert second["version"] not in json.dumps(diff)
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/compare?broken")[1]["error"]["code"] == "invalid_request"
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{newer['version_id']}/preview?limit=2")[1]["rows"][0]["value"] == "new"

    with create_server(root, TOKEN) as reopened:
        thread = threading.Thread(target=reopened.serve_forever, daemon=True)
        thread.start()
        try:
            assert request(reopened, "GET", "/v1/datasets")[1] == listing
        finally:
            reopened.shutdown()
            thread.join(timeout=5)


def test_rejects_path_inputs_unknown_ids_and_structured_errors(server, warehouse):
    root, _, _ = warehouse
    dataset_id = request(server, "GET", "/v1/datasets")[1]["datasets"][0]["dataset_id"]
    assert request(server, "GET", "/v1/datasets/../catalog.sqlite3")[0] in {400, 404}
    assert request(server, "GET", "/v1/datasets/%2e%2e")[1]["error"]["code"] == "invalid_request"
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/versions/ver_{'0'*32}")[1]["error"]["code"] == "not_found"
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/versions")[0] == 200
    assert request(server, "GET", "/v1/queries")[1]["error"]["code"] == "not_found"
    assert request(server, "POST", "/v1/queries", body={"sql": "select 1"})[1]["error"]["code"] == "not_found"
    assert request(server, "OPTIONS", "/v1/datasets", token=None)[0] == 401
    assert request(server, "OPTIONS", "/v1/datasets")[1]["error"]["code"] == "method_not_allowed"
    assert request(server, "PATCH", "/v1/datasets")[1]["error"]["code"] == "method_not_allowed"
    assert request(server, "HEAD", "/v1/datasets")[0] == 405
    status, payload = request(server, "POST", "/v1/uploads", body={"filename": "/etc/passwd", "content_length": 12}, headers={"Idempotency-Key": "abc"})
    assert status == 400 and payload["error"]["code"] == "invalid_request"
    assert str(root) not in json.dumps(payload)


def test_write_contract_is_explicit_and_mutation_free(server):
    before = list((server.root / ".staging").iterdir())
    headers = {"Idempotency-Key": "retry-1"}
    status, body = request(server, "POST", "/v1/uploads", body={"filename": "places.csv", "content_length": 123}, headers=headers)
    assert (status, body["error"]["code"]) == (501, "write_unavailable")
    upload = "upl_" + "1" * 32
    inspection = "ins_" + "2" * 32
    status, body = request(server, "POST", f"/v1/uploads/{upload}/inspections", body={"format": "csv", "preview_rows": 10}, headers=headers)
    assert (status, body["error"]["code"]) == (501, "write_unavailable")
    status, body = request(server, "POST", "/v1/ingestions", body={
        "upload_id": upload, "inspection_id": inspection, "expected_source_sha256": "a" * 64,
        "dataset_name": "places", "key": "id", "options": {}}, headers=headers)
    assert (status, body["error"]["code"]) == (501, "write_unavailable")
    assert request(server, "GET", "/v1/jobs/job_" + "3" * 32)[1]["error"]["code"] == "write_unavailable"
    assert request(server, "POST", "/v1/uploads", body={"filename": "places.csv", "content_length": 123, "url": "http://evil"}, headers=headers)[0] == 400
    assert request(server, "POST", f"/v1/uploads/{upload}/inspections", body={"format": []}, headers=headers)[1]["error"]["code"] == "invalid_request"
    assert request(server, "POST", "/v1/ingestions", body={
        "upload_id": upload, "inspection_id": inspection, "expected_source_sha256": "a" * 64,
        "dataset_name": "places", "options": {"types": {"id": []}}}, headers=headers)[1]["error"]["code"] == "invalid_request"
    assert list((server.root / ".staging").iterdir()) == before


def test_snapshot_escape_is_blocked(server, monkeypatch):
    listing = request(server, "GET", "/v1/datasets")[1]
    dataset_id = listing["datasets"][0]["dataset_id"]
    versions = request(server, "GET", f"/v1/datasets/{dataset_id}/versions")[1]["versions"]
    version_id = versions[0]["version_id"]
    newer_id = versions[1]["version_id"]
    called = []
    monkeypatch.setattr(server.catalog, "diff", lambda *args, **kwargs: called.append(True))
    with sqlite3.connect(server.root / "catalog.sqlite3") as conn:
        raw = conn.execute("SELECT manifest_json FROM versions ORDER BY version LIMIT 1").fetchone()[0]
        manifest = json.loads(raw)
        manifest["parquet_path"] = "../../source.csv"
        conn.execute("UPDATE versions SET manifest_json=? WHERE version=?", (json.dumps(manifest), manifest["version"]))
    status, payload = request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{version_id}/download")
    assert status == 500 and payload["error"]["code"] == "storage_error"
    status, payload = request(server, "GET", f"/v1/datasets/{dataset_id}/compare?from={version_id}&to={newer_id}")
    assert status == 500 and payload["error"]["code"] == "storage_error"
    assert not called

    symlink = server.root / "snapshots" / "escape.parquet"
    symlink.symlink_to(server.root.parent / "source.csv")
    with sqlite3.connect(server.root / "catalog.sqlite3") as conn:
        manifest["parquet_path"] = str(symlink)
        conn.execute("UPDATE versions SET manifest_json=? WHERE version=?", (json.dumps(manifest), manifest["version"]))
    status, payload = request(server, "GET", f"/v1/datasets/{dataset_id}/compare?from={version_id}&to={newer_id}")
    assert status == 500 and payload["error"]["code"] == "storage_error"
    assert not called


def test_large_cells_and_preview_byte_budget(server, tmp_path):
    source = tmp_path / "large.csv"
    source.write_text("id,value\n" + "".join(f"{i},{'x' * 5000}\n" for i in range(30)), encoding="utf-8")
    Catalog(server.root).ingest(source, name="large_cells", key="id")
    listing = request(server, "GET", "/v1/datasets")[1]["datasets"]
    dataset_id = next(item["dataset_id"] for item in listing if item["name"] == "large_cells")
    version_id = request(server, "GET", f"/v1/datasets/{dataset_id}/versions")[1]["versions"][0]["version_id"]
    status, preview = request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{version_id}/preview?limit=30")
    assert status == 200
    assert preview["returned_rows"] == 30
    assert all(row["value"] == {"truncated": True, "byte_length": 5000} for row in preview["rows"])
    assert len(json.dumps(preview).encode()) < 64 * 1024
    assert request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{version_id}/preview?limit=101")[1]["error"]["code"] == "invalid_request"

    source.write_text("id,value\n" + "".join(f"{i},{'y' * 3000}\n" for i in range(100)), encoding="utf-8")
    Catalog(server.root).ingest(source, name="budget_rows", key="id")
    listing = request(server, "GET", "/v1/datasets")[1]["datasets"]
    budget_id = next(item["dataset_id"] for item in listing if item["name"] == "budget_rows")
    budget_version = request(server, "GET", f"/v1/datasets/{budget_id}/versions")[1]["versions"][0]["version_id"]
    preview = request(server, "GET", f"/v1/datasets/{budget_id}/versions/{budget_version}/preview?limit=100")[1]
    assert preview["truncated"] is True and 0 < preview["returned_rows"] < 100
    assert len(json.dumps(preview).encode()) < 66 * 1024


def test_schema_is_exact_or_fails_with_structured_size_error(server, tmp_path):
    source = tmp_path / "schema.parquet"
    long_name = "field_" + "n" * 300
    pq.write_table(pa.table({long_name: [1]}), source)
    Catalog(server.root).ingest(source, name="long_schema")
    listing = request(server, "GET", "/v1/datasets")[1]["datasets"]
    dataset_id = next(item["dataset_id"] for item in listing if item["name"] == "long_schema")
    version = request(server, "GET", f"/v1/datasets/{dataset_id}/versions")[1]["versions"][0]
    assert version["schema"][0]["name"] == long_name

    pq.write_table(pa.table({"n" * 70_000: [1]}), source)
    Catalog(server.root).ingest(source, name="oversized_schema")
    listing = request(server, "GET", "/v1/datasets")[1]["datasets"]
    oversized_id = next(item["dataset_id"] for item in listing if item["name"] == "oversized_schema")
    status, payload = request(server, "GET", f"/v1/datasets/{oversized_id}/versions")
    assert status == 413 and payload["error"]["code"] == "response_too_large"


def test_nested_preview_truncation_is_labeled(server, tmp_path):
    assert _safe_value(list(range(120))) == {"items": list(range(100)), "truncated": True, "omitted_count": 20}
    nested_map = _safe_value({str(i): i for i in range(120)})
    assert nested_map["truncated"] is True and nested_map["omitted_count"] == 20
    source = tmp_path / "nested.parquet"
    pq.write_table(pa.table({"items": pa.array([list(range(120))])}), source)
    Catalog(server.root).ingest(source, name="nested")
    listing = request(server, "GET", "/v1/datasets")[1]["datasets"]
    dataset_id = next(item["dataset_id"] for item in listing if item["name"] == "nested")
    version_id = request(server, "GET", f"/v1/datasets/{dataset_id}/versions")[1]["versions"][0]["version_id"]
    preview = request(server, "GET", f"/v1/datasets/{dataset_id}/versions/{version_id}/preview")[1]
    assert preview["rows"][0]["items"]["omitted_count"] == 20


def test_gui_assets_are_public_but_data_and_files_stay_private(server):
    for route, content_type in (("/", "text/html"), ("/assets/app.js", "text/javascript"),
                                ("/assets/app.css", "text/css")):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        connection.request("GET", route)
        response = connection.getresponse()
        body = response.read()
        assert response.status == 200
        assert response.getheader("Content-Type").startswith(content_type)
        assert response.getheader("Cache-Control") == "no-store"
        assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert TOKEN.encode() not in body and str(server.root).encode() not in body
        assert body
        connection.close()
        assert request(server, "HEAD", route, token=None) == (200, b"")
        assert request(server, "GET", route, token=None, host="evil.example")[0] == 403
        assert request(server, "GET", route, token=None, origin="https://evil.example")[0] == 403

    for route in ("/catalog.sqlite3", "/assets/../service.py", "/assets/%2e%2e/service.py",
                  "/assets/service.py", "/?token=secret", "/v1/datasets"):
        assert request(server, "GET", route, token=None)[0] == 401
    assert request(server, "GET", "/assets/../service.py")[0] == 404
    assert request(server, "GET", "/assets/%2e%2e/service.py")[0] == 400
    assert request(server, "POST", "/", token=None)[0] == 401
    assert request(server, "GET", "/v1/datasets")[0] == 200


def test_compare_exposes_crs_change_for_selected_versions(server, tmp_path):
    source = tmp_path / "coordinates.csv"
    source.write_text("id,x,y\na,1,2\n", encoding="utf-8")
    catalog = Catalog(server.root)
    catalog.ingest(source, name="coordinates", key="id", x="x", y="y", crs="EPSG:4326")
    catalog.ingest(source, name="coordinates", key="id", x="x", y="y", crs="EPSG:3857")
    dataset = next(item for item in request(server, "GET", "/v1/datasets")[1]["datasets"]
                   if item["name"] == "coordinates")
    route = f"/v1/datasets/{dataset['dataset_id']}"
    versions = request(server, "GET", route + "/versions")[1]["versions"]
    old, new = versions
    comparison = request(server, "GET", route + f"/compare?from={old['version_id']}&to={new['version_id']}")[1]
    assert comparison["crs_changed"] is True
    assert comparison["old_crs"] == old["crs"]
    assert comparison["new_crs"] == new["crs"]
    unchanged = request(server, "GET", route + f"/compare?from={new['version_id']}&to={new['version_id']}")[1]
    assert unchanged["crs_changed"] is False


def test_map_route_exact_versions_auth_limits_and_nonspatial(server, tmp_path):
    plain = request(server, 'GET', '/v1/datasets')[1]['datasets'][0]
    base = f"/v1/datasets/{plain['dataset_id']}/versions/{plain['current_version_id']}/map"
    assert request(server, 'GET', base, token=None)[0] == 401
    assert request(server, 'GET', base)[0] == 422
    for query in ('limit=0', 'limit=1001', 'limit=1&limit=2', 'extra=1', 'limit=abc'):
        assert request(server, 'GET', base + '?' + query)[0] == 400
    source = tmp_path / 'points.geojson'
    def write_point(x):
        source.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'properties': {'id': 'a'}, 'geometry': {'type': 'Point', 'coordinates': [x, 40.7]}}
        ]}))
    write_point(-74)
    first = server.catalog.ingest(source, name='map_points', key='id')
    write_point(-73.9)
    server.catalog.ingest(source, name='map_points', key='id')
    dataset = next(d for d in request(server, 'GET', '/v1/datasets')[1]['datasets'] if d['name'] == 'map_points')
    versions = request(server, 'GET', f"/v1/datasets/{dataset['dataset_id']}/versions")[1]['versions']
    old, new = versions
    for version, longitude in [(old, -74), (new, -73.9)]:
        route = f"/v1/datasets/{dataset['dataset_id']}/versions/{version['version_id']}/map?limit=1"
        status, body = request(server, 'GET', route)
        assert status == 200
        assert body['dataset_id'] == dataset['dataset_id'] and body['version_id'] == version['version_id']
        assert body['features'][0]['geometry']['coordinates'] == [longitude, 40.7]
        assert body['features'][0]['properties']['id'] == 'a'
        assert body['returned_features'] == 1 and body['unscanned_rows'] == 0
        assert str(server.root) not in json.dumps(body)
        assert request(server, 'GET', route, origin='https://evil.example')[0] == 403
    cross = f"/v1/datasets/{plain['dataset_id']}/versions/{old['version_id']}/map"
    assert request(server, 'GET', cross)[0] == 404
    assert Path(first['parquet_path']).exists()


def test_map_assets_use_fixed_public_allowlist(server):
    for path in ('/assets/map.js', '/assets/vendor/leaflet.js', '/assets/vendor/leaflet.css',
                 '/assets/fonts/inter-latin-400-normal.woff2', '/assets/icons/search.svg',
                 '/assets/vendor/images/marker-icon.png'):
        status, payload = request(server, 'GET', path, token=None)
        assert status == 200 and payload
    for path in ('/assets/vendor/README.md', '/assets/vendor/../../service.py', '/assets/fonts/not-a-font.woff2'):
        assert request(server, 'GET', path, token=None)[0] == 401
