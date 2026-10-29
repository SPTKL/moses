"""Immutable S3 version bundles, with their publication manifest written last."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


class S3Publisher:
    def __init__(self, bucket, prefix="moses", *, client=None, endpoint_url=None):
        if not bucket or "/" in bucket:
            raise ValueError("bucket must be a bucket name, not an S3 URL")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise ImportError('S3 publishing requires the s3 extra: use uv run --extra s3 in the Moses checkout, or uv add "moses-geo[s3]" in a consumer project') from exc
            client = boto3.client("s3", endpoint_url=endpoint_url, config=Config(s3={"addressing_style": "path"}))
        self.client = client

    def _put_immutable(self, key, body, content_type):
        digest = hashlib.sha256(body).hexdigest()
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type, Metadata={"sha256": digest}, IfNoneMatch="*")
        except Exception as exc:
            response = getattr(exc, "response", {})
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            code = response.get("Error", {}).get("Code")
            if status != 412 and code not in {"PreconditionFailed", "412"}:
                raise
            existing = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = existing["Body"]
            try:
                existing_digest = hashlib.sha256(stream.read()).hexdigest()
            finally:
                stream.close()
            if existing_digest != digest:
                raise ValueError(f"Immutable S3 object already exists with different contents: {key}") from exc
        return {"uri": f"s3://{self.bucket}/{key}", "sha256": digest, "size": len(body)}

    def publish(self, catalog, name, version=None):
        manifest = catalog.get_version(name, version)
        base = "/".join(filter(None, [self.prefix, name, manifest["version"]]))
        parquet = Path(manifest["parquet_path"])
        objects = {"table": self._put_immutable(f"{base}/table.parquet", parquet.read_bytes(), "application/vnd.apache.parquet"), "raw": []}
        for raw in manifest.get("raw_files", []):
            path = Path(raw)
            relative = path.relative_to(catalog.root / "raw" / manifest["source_sha256"]).as_posix()
            objects["raw"].append(self._put_immutable(f"{base}/raw/{relative}", path.read_bytes(), "application/octet-stream"))
        portable = {k: v for k, v in manifest.items() if k not in {"parquet_path", "raw_files"}}
        # Retain provenance, but local path fields never define remote locations.
        portable["objects"] = objects
        body = json.dumps(portable, sort_keys=True, separators=(",", ":")).encode()
        published = self._put_immutable(f"{base}/manifest.json", body, "application/json")
        return {"dataset": name, "version": manifest["version"], "manifest_uri": published["uri"], "parquet_uri": objects["table"]["uri"]}
