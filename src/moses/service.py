"""Authenticated, loopback-only HTTP boundary for accepted catalog releases.

Write routes advertise and validate the v1 contract. Durable upload and job
storage is intentionally left to the separate ingestion-job implementation.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
from pathlib import Path
import re
import sqlite3
from threading import Lock
from urllib.parse import parse_qs, urlsplit
import uuid

import pyarrow.parquet as pq

from .catalog import Catalog
from .map_preview import MAX_BYTES as MAX_MAP_BYTES, MapPreviewError, build_map_preview


_ID = re.compile(r"^(?:ds|ver|upl|ins|job)_[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_BODY = 16 * 1024
_MAX_PREVIEW_ROWS = 100
_MAX_PREVIEW_BYTES = 64 * 1024
_MAX_CELL_BYTES = 4096
_MAX_SCHEMA_BYTES = 64 * 1024
_MAX_COMPARE_ROWS = 100_000
_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/app.css": ("app.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/map.js": ("map.js", "text/javascript; charset=utf-8"),
    "/assets/vendor/leaflet.js": ("vendor/leaflet.js", "text/javascript; charset=utf-8"),
    "/assets/vendor/leaflet.css": ("vendor/leaflet.css", "text/css; charset=utf-8"),
}
for _weight in (400, 600, 700):
    _name = f"fonts/inter-latin-{_weight}-normal.woff2"
    _STATIC[f"/assets/{_name}"] = (_name, "font/woff2")
for _icon in ("search", "refresh-cw", "download", "chevron-down", "x", "info", "maximize",
              "plus", "minus", "map", "grid", "arrow-left", "menu", "crosshair"):
    _name = f"icons/{_icon}.svg"
    _STATIC[f"/assets/{_name}"] = (_name, "image/svg+xml")
for _image in ("layers.png", "layers-2x.png", "marker-icon.png", "marker-icon-2x.png", "marker-shadow.png"):
    _name = f"vendor/images/{_image}"
    _STATIC[f"/assets/{_name}"] = (_name, "image/png")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _bad(message: str = "Invalid request") -> APIError:
    return APIError(400, "invalid_request", message)


def _object(value: object, required: set[str], optional: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - optional:
        raise _bad("Request fields do not match the API contract")
    return value


def _string(value: object, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length or "\x00" in value:
        raise _bad("Expected a nonempty string")
    return value


def _resource_id(value: str, prefix: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or not value.startswith(prefix + "_"):
        raise _bad("Invalid resource ID")
    return value


def _safe_value(value: object) -> object:
    """Encode small Arrow values without exposing binary data or huge cells."""
    from datetime import date, datetime, time
    from decimal import Decimal

    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return value if len(raw) <= _MAX_CELL_BYTES else {"truncated": True, "byte_length": len(raw)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {"base64": base64.b64encode(raw).decode("ascii")} if len(raw) <= _MAX_CELL_BYTES else {"truncated": True, "byte_length": len(raw)}
    if isinstance(value, (date, datetime, time, Decimal)):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = [_safe_value(item) for item in value[:100]]
        if len(value) > 100:
            return {"items": items, "truncated": True, "omitted_count": len(value) - 100}
        return items
    if isinstance(value, dict):
        entries = list(value.items())
        if len(entries) > 100:
            return {"entries": [{"key": str(k), "value": _safe_value(v)} for k, v in entries[:100]],
                    "truncated": True, "omitted_count": len(entries) - 100}
        return {str(k): _safe_value(v) for k, v in entries}
    encoded = str(value).encode("utf-8")
    return str(value) if len(encoded) <= _MAX_CELL_BYTES else {"truncated": True, "byte_length": len(encoded)}


class _Resources:
    """Root-local stable IDs; catalog names and versions never act as API keys."""

    def __init__(self, root: Path):
        self.path = root / "service-resources.sqlite3"
        self.lock = Lock()
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY, catalog_name TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
                    catalog_version TEXT NOT NULL,
                    UNIQUE(dataset_id, catalog_version));
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def sync(self, catalog: Catalog) -> None:
        # Serialize discovery so concurrent readers cannot invent competing IDs.
        with self.lock, self._connect() as conn:
            for item in catalog.datasets():
                name = item["dataset"]
                conn.execute("INSERT OR IGNORE INTO datasets VALUES (?, ?)", ("ds_" + uuid.uuid4().hex, name))
                dataset_id = conn.execute("SELECT id FROM datasets WHERE catalog_name=?", (name,)).fetchone()["id"]
                for version in catalog.history(name):
                    conn.execute("INSERT OR IGNORE INTO versions VALUES (?, ?, ?)",
                                 ("ver_" + uuid.uuid4().hex, dataset_id, version["version"]))
            conn.commit()

    def datasets(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT id,catalog_name FROM datasets ORDER BY catalog_name").fetchall()

    def dataset(self, dataset_id: str) -> sqlite3.Row:
        _resource_id(dataset_id, "ds")
        with self._connect() as conn:
            row = conn.execute("SELECT id,catalog_name FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if row is None:
            raise APIError(404, "not_found", "Dataset not found")
        return row

    def versions(self, dataset_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT id,catalog_version FROM versions WHERE dataset_id=? ORDER BY catalog_version", (dataset_id,)).fetchall()

    def version(self, dataset_id: str, version_id: str) -> sqlite3.Row:
        _resource_id(version_id, "ver")
        with self._connect() as conn:
            row = conn.execute("SELECT id,catalog_version FROM versions WHERE dataset_id=? AND id=?", (dataset_id, version_id)).fetchone()
        if row is None:
            raise APIError(404, "not_found", "Version not found")
        return row


def _metadata(root: Path, manifest: dict, dataset_id: str, version_id: str) -> dict:
    # Deliberate allowlist: manifest paths, source_files, and arbitrary provenance
    # are never serialized, even if they contain local filesystem details.
    return {
        "dataset_id": dataset_id, "version_id": version_id,
        "created_at": manifest["created_at"], "row_count": manifest["row_count"],
        "schema": _schema(root, manifest),
        "key": manifest.get("key"), "format": manifest.get("format"),
        "layer": manifest.get("layer"), "geometry_column": manifest.get("geometry_column"),
        "crs": manifest.get("crs"), "crs_source": manifest.get("crs_source"),
        "source_sha256": manifest.get("source_sha256"),
        "content_sha256": manifest.get("content_sha256"),
    }


def _snapshot(root: Path, manifest: dict) -> Path:
    relative = manifest.get("parquet_path")
    if not isinstance(relative, str):
        raise APIError(500, "storage_error", "Accepted snapshot is unavailable")
    base = (root / "snapshots").resolve()
    unresolved = Path(relative) if Path(relative).is_absolute() else root / relative
    candidate = unresolved.resolve()
    if (not candidate.is_relative_to(base) or not candidate.is_file()
            or any(part.is_symlink() for part in (unresolved, *unresolved.parents) if part.is_relative_to(root))):
        raise APIError(500, "storage_error", "Accepted snapshot is unavailable")
    return candidate


def _schema(root: Path, manifest: dict) -> list[dict]:
    # Arrow schema metadata can contain arbitrary user bytes and local paths.
    # Only field names, data types and nullability are useful to API clients.
    arrow = pq.ParquetFile(_snapshot(root, manifest)).schema_arrow
    fields = [{"name": field.name, "type": str(field.type), "nullable": field.nullable}
              for field in arrow]
    if len(json.dumps(fields, ensure_ascii=False).encode("utf-8")) > _MAX_SCHEMA_BYTES:
        raise APIError(413, "response_too_large", "Version schema exceeds the service response limit")
    return fields


def _query_params(query: str) -> dict[str, list[str]]:
    try:
        return parse_qs(query, strict_parsing=True, keep_blank_values=True, max_num_fields=10)
    except ValueError:
        raise _bad("Invalid query parameters") from None


class MosesHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], root: Path, token: str):
        super().__init__(address, _Handler)
        self.root = root
        self.token = token
        self.catalog = Catalog(root)
        self.resources = _Resources(root)


class _Handler(BaseHTTPRequestHandler):
    server: MosesHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        # Access logs may contain credentials in accidental query strings.
        pass

    def _json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, error: APIError) -> None:
        # Rejected bodies may be unread; do not parse their trailing bytes as a
        # second request on the same keep-alive connection.
        self.close_connection = True
        self._json(error.status, {"error": {"code": error.code, "message": error.message}})

    def _guard(self, *, require_auth: bool = True) -> None:
        if len(self.headers.get_all("Host", [])) != 1 or len(self.headers.get_all("Authorization", [])) > 1 or len(self.headers.get_all("Origin", [])) > 1:
            raise APIError(403, "invalid_headers", "Request headers are ambiguous")
        if len(self.headers.get_all("Content-Length", [])) > 1 or self.headers.get("Transfer-Encoding") is not None:
            raise APIError(400, "invalid_request", "Unsupported request framing")
        host = self.headers.get("Host")
        expected = f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        if host != expected:
            raise APIError(403, "invalid_host", "Host is not the local service origin")
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + expected:
            raise APIError(403, "invalid_origin", "Origin is not the local service origin")
        if not require_auth:
            return
        authorization = self.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not supplied.isascii() or not hmac.compare_digest(supplied, self.server.token):
            raise APIError(401, "unauthorized", "Bearer token required")

    def _asset(self) -> None:
        # Only fixed package assets are public. Never resolve request paths
        # against the warehouse or the working directory.
        filename, content_type = _STATIC[self.path]
        body = (Path(__file__).parent / "static" / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self) -> dict:
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise APIError(415, "unsupported_media_type", "Expected application/json")
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > _MAX_BODY:
            raise APIError(413, "request_too_large", "JSON body is missing or too large")
        try:
            value = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeDecodeError):
            raise _bad("Invalid JSON body") from None
        if not isinstance(value, dict):
            raise _bad("Expected a JSON object")
        return value

    def _idempotency(self) -> None:
        key = self.headers.get("Idempotency-Key")
        if not key or len(key) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key):
            raise _bad("A valid Idempotency-Key is required")

    def _unavailable(self) -> None:
        raise APIError(501, "write_unavailable", "Durable uploads and ingestion jobs are not available yet")

    def _dispatch(self, method: str) -> None:
        try:
            public_asset = method in {"GET", "HEAD"} and self.path in _STATIC
            self._guard(require_auth=not public_asset)
            if public_asset:
                self._asset()
                return
            if not self.path.startswith("/") or self.path.startswith("//") or "%" in self.path or "\\" in self.path:
                raise _bad("Invalid URL path")
            url = urlsplit(self.path)
            parts = url.path.strip("/").split("/")
            if not parts or parts[0] != "v1":
                raise APIError(404, "not_found", "Route not found")
            if method == "GET":
                self._get(parts, url.query)
            elif method in {"POST", "PUT"}:
                if url.query:
                    raise _bad("Query parameters are not accepted")
                self._write(method, parts)
            else:
                raise APIError(405, "method_not_allowed", "Method not allowed")
        except APIError as error:
            self._error(error)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            # No catalog exception, filename, SQLite detail, or token leaks.
            self._error(APIError(500, "internal_error", "Service request failed"))

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def do_OPTIONS(self) -> None:
        self._dispatch("OPTIONS")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_TRACE(self) -> None:
        self._dispatch("TRACE")

    def do_CONNECT(self) -> None:
        self._dispatch("CONNECT")

    def _get(self, parts: list[str], query: str) -> None:
        if len(parts) == 3 and parts[1] in {"jobs", "inspections"}:
            _resource_id(parts[2], "job" if parts[1] == "jobs" else "ins")
            if query:
                raise _bad("Query parameters are not accepted")
            self._unavailable()
        if len(parts) < 2 or parts[1] != "datasets":
            raise APIError(404, "not_found", "Route not found")
        self.server.resources.sync(self.server.catalog)
        if len(parts) == 2:
            if query:
                raise _bad("Query parameters are not accepted")
            result = []
            for row in self.server.resources.datasets():
                manifest = self.server.catalog.get_version(row["catalog_name"])
                versions = self.server.resources.versions(row["id"])
                current = next(v["id"] for v in versions if v["catalog_version"] == manifest["version"])
                result.append({"dataset_id": row["id"], "name": row["catalog_name"],
                               "current_version_id": current, "version_count": len(versions)})
            self._json(200, {"datasets": result})
            return
        dataset = self.server.resources.dataset(parts[2])
        if len(parts) == 4 and parts[3] == "versions":
            if query:
                raise _bad("Query parameters are not accepted")
            versions = [
                _metadata(self.server.root, self.server.catalog.get_version(dataset["catalog_name"], v["catalog_version"]), dataset["id"], v["id"])
                for v in self.server.resources.versions(dataset["id"])
            ]
            self._json(200, {"dataset_id": dataset["id"], "versions": versions})
            return
        if len(parts) == 4 and parts[3] == "compare":
            params = _query_params(query)
            if set(params) != {"from", "to"} or any(len(v) != 1 for v in params.values()):
                raise _bad("Comparison requires one from and one to version ID")
            first = self.server.resources.version(dataset["id"], params["from"][0])
            second = self.server.resources.version(dataset["id"], params["to"][0])
            old = self.server.catalog.get_version(dataset["catalog_name"], first["catalog_version"])
            new = self.server.catalog.get_version(dataset["catalog_name"], second["catalog_version"])
            _snapshot(self.server.root, old)
            _snapshot(self.server.root, new)
            if old["row_count"] + new["row_count"] > _MAX_COMPARE_ROWS:
                raise APIError(413, "comparison_too_large", "Comparison exceeds the local service row limit")
            difference = self.server.catalog.diff(dataset["catalog_name"], first["catalog_version"], second["catalog_version"])
            self._json(200, {"dataset_id": dataset["id"], "from_version_id": first["id"],
                             "to_version_id": second["id"], "added": difference["added"],
                             "removed": difference["removed"], "changed": difference["changed"],
                             "key": difference["key"], "schema_changed": difference["schema_changed"],
                             "crs_changed": old.get("crs") != new.get("crs"),
                             "old_crs": old.get("crs"), "new_crs": new.get("crs"),
                             "old_schema": _schema(self.server.root, old) if difference["schema_changed"] else None,
                             "new_schema": _schema(self.server.root, new) if difference["schema_changed"] else None})
            return
        if len(parts) not in (5, 6) or parts[3] != "versions":
            raise APIError(404, "not_found", "Route not found")
        version = self.server.resources.version(dataset["id"], parts[4])
        manifest = self.server.catalog.get_version(dataset["catalog_name"], version["catalog_version"])
        if len(parts) == 5:
            if query:
                raise _bad("Query parameters are not accepted")
            self._json(200, _metadata(self.server.root, manifest, dataset["id"], version["id"]))
            return
        if parts[5] == "map":
            params = _query_params(query) if query else {}
            if set(params) - {"limit"} or len(params.get("limit", ["500"])) != 1:
                raise _bad("Only one limit parameter is accepted")
            limit_text = params.get("limit", ["500"])[0]
            if not limit_text.isdigit() or not 1 <= int(limit_text) <= 1000:
                raise _bad("Map limit must be between 1 and 1000")
            try:
                result = build_map_preview(_snapshot(self.server.root, manifest), manifest, limit=int(limit_text))
            except MapPreviewError as error:
                raise APIError(error.status, error.code, error.message) from None
            result.update(dataset_id=dataset["id"], version_id=version["id"])
            if len(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_MAP_BYTES:
                raise APIError(422, "preview_metadata_too_large", "Preview metadata exceeds the response size limit")
            self._json(200, result)
            return
        if parts[5] == "preview":
            params = _query_params(query) if query else {}
            if set(params) - {"limit"} or len(params.get("limit", ["10"])) != 1:
                raise _bad("Only one limit parameter is accepted")
            limit_text = params.get("limit", ["10"])[0]
            if not limit_text.isdigit() or not 1 <= int(limit_text) <= _MAX_PREVIEW_ROWS:
                raise _bad("Preview limit must be between 1 and 100")
            path = _snapshot(self.server.root, manifest)
            rows, used = [], 0
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=min(int(limit_text), 32)):
                for row in batch.to_pylist():
                    safe = {str(k): _safe_value(v) for k, v in row.items()}
                    size = len(json.dumps(safe, ensure_ascii=False, allow_nan=False).encode("utf-8"))
                    if used + size > _MAX_PREVIEW_BYTES:
                        self._json(200, {"dataset_id": dataset["id"], "version_id": version["id"],
                                         "rows": rows, "returned_rows": len(rows), "total_rows": manifest["row_count"],
                                         "truncated": True, "byte_limit": _MAX_PREVIEW_BYTES})
                        return
                    rows.append(safe)
                    used += size
                    if len(rows) >= int(limit_text):
                        break
                if len(rows) >= int(limit_text):
                    break
            self._json(200, {"dataset_id": dataset["id"], "version_id": version["id"],
                             "rows": rows, "returned_rows": len(rows), "total_rows": manifest["row_count"],
                             "truncated": len(rows) < manifest["row_count"], "byte_limit": _MAX_PREVIEW_BYTES})
            return
        if parts[5] == "download":
            if query:
                raise _bad("Query parameters are not accepted")
            path = _snapshot(self.server.root, manifest)
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apache.parquet")
            self.send_header("Content-Disposition", f'attachment; filename="{version["id"]}.parquet"')
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    self.wfile.write(chunk)
            return
        raise APIError(404, "not_found", "Route not found")

    def _write(self, method: str, parts: list[str]) -> None:
        if method == "POST" and parts == ["v1", "uploads"]:
            self._idempotency()
            body = _object(self._body(), {"filename", "content_length"}, {"sha256"})
            filename = _string(body["filename"])
            if filename in {".", ".."} or "/" in filename or "\\" in filename:
                raise _bad("Filename must be a basename")
            if type(body["content_length"]) is not int or not 0 < body["content_length"] <= 1024 * 1024 * 1024:
                raise _bad("Invalid content_length")
            if "sha256" in body and (not isinstance(body["sha256"], str) or not _SHA.fullmatch(body["sha256"])):
                raise _bad("Invalid sha256")
            self._unavailable()
        if method == "PUT" and len(parts) == 4 and parts[1] == "uploads" and parts[3] == "content":
            _resource_id(parts[2], "upl")
            self._idempotency()
            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit() or int(length) > 1024 * 1024 * 1024:
                raise APIError(413, "request_too_large", "Upload length is missing or too large")
            self._unavailable()
        if method == "POST" and len(parts) == 4 and parts[1] == "uploads" and parts[3] == "inspections":
            _resource_id(parts[2], "upl")
            self._idempotency()
            body = _object(self._body(), set(), {"format", "layer", "preview_rows"})
            if "format" in body and (not isinstance(body["format"], str) or body["format"] not in {"csv", "tsv", "parquet", "geojson", "gpkg"}):
                raise _bad("Unsupported format")
            if "layer" in body:
                _string(body["layer"])
            if "preview_rows" in body and (type(body["preview_rows"]) is not int or not 1 <= body["preview_rows"] <= 100):
                raise _bad("Invalid preview_rows")
            self._unavailable()
        if method == "POST" and parts == ["v1", "ingestions"]:
            self._idempotency()
            body = _object(self._body(), {"upload_id", "inspection_id", "expected_source_sha256", "dataset_name", "options"}, {"key"})
            _resource_id(body["upload_id"], "upl")
            _resource_id(body["inspection_id"], "ins")
            if not isinstance(body["expected_source_sha256"], str) or not _SHA.fullmatch(body["expected_source_sha256"]):
                raise _bad("Invalid source hash")
            if not isinstance(body["dataset_name"], str) or not _NAME.fullmatch(body["dataset_name"]):
                raise _bad("Invalid dataset name")
            if "key" in body and body["key"] is not None:
                _string(body["key"])
            options = _object(body["options"], set(), {"x", "y", "crs", "layer", "types", "infer_types"})
            for field in ("x", "y", "crs", "layer"):
                if field in options:
                    _string(options[field])
            if "infer_types" in options and type(options["infer_types"]) is not bool:
                raise _bad("Invalid infer_types")
            if "types" in options:
                types = options["types"]
                if not isinstance(types, dict) or len(types) > 200 or any(
                    not isinstance(k, str) or not k or len(k) > 128 or not isinstance(v, str) or v not in {"string", "bool", "int64", "float64"}
                    for k, v in types.items()
                ):
                    raise _bad("Invalid type overrides")
            self._unavailable()
        raise APIError(404, "not_found", "Route not found")


def create_server(root: str | Path, token: str, host: str = "127.0.0.1", port: int = 0) -> MosesHTTPServer:
    """Create a local v1 server; the caller owns serve_forever()/shutdown()."""
    if not isinstance(token, str) or len(token) < 16 or not token.isascii() or any(ch.isspace() for ch in token):
        raise ValueError("A bearer token of at least 16 characters is required")
    try:
        address = ipaddress.ip_address(host)
        if address.version != 4 or not address.is_loopback:
            raise ValueError("Service must bind to a loopback IP address")
    except ValueError as error:
        raise ValueError("Service must bind to a loopback IP address") from error
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Invalid TCP port")
    return MosesHTTPServer((host, port), Path(root).expanduser().resolve(), token)


def serve(root: str | Path, token: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    with create_server(root, token, host, port) as server:
        server.serve_forever()
