"""Remote source helpers with explicit pagination and provenance."""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
_DATASET = re.compile(r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
_PAGE_SIZE = 50_000
_TIMEOUT_SECONDS = 30


def download_socrata(
    domain: str,
    dataset_id: str,
    destination: str | Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Download a Socrata dataset as a GeoJSON snapshot.

    Results are paged in stable ``:id`` order and held one page at a time.
    Socrata does not provide a transaction spanning all pages, so the source
    may change during retrieval even though the local file is installed
    atomically after every requested page succeeds.
    """
    if not isinstance(domain, str) or not _DOMAIN.fullmatch(domain):
        raise ValueError("domain must be a hostname such as data.city.gov")
    if not isinstance(dataset_id, str) or not _DATASET.fullmatch(dataset_id):
        raise ValueError("dataset_id must have the form abcd-1234")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise ValueError("limit must be a positive integer")
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    endpoint = f"https://{domain.lower()}/resource/{dataset_id}.geojson"
    urls: list[str] = []
    offset = 0
    record_count = 0
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=dest.parent,
            prefix=f".{dest.name}.", suffix=".part", delete=False,
        ) as stream:
            temp_name = stream.name
            stream.write('{"type":"FeatureCollection","features":[')
            first = True
            while limit is None or record_count < limit:
                page_limit = _PAGE_SIZE if limit is None else min(_PAGE_SIZE, limit - record_count)
                query = urllib.parse.urlencode({"$limit": page_limit, "$offset": offset, "$order": ":id"})
                url = f"{endpoint}?{query}"
                urls.append(url)
                request = urllib.request.Request(url, headers={"Accept": "application/geo+json, application/json", "User-Agent": "Moses/1.0"})
                try:
                    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                except Exception as exc:
                    raise ValueError(f"Socrata request failed at offset {offset}: {exc}") from exc
                if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                    raise ValueError("Socrata response was not a GeoJSON FeatureCollection")
                page = payload["features"]
                if any(not isinstance(feature, dict) or feature.get("type") != "Feature" for feature in page):
                    raise ValueError("Socrata response contains an invalid GeoJSON feature")
                if len(page) > page_limit:
                    raise ValueError("Socrata returned more records than requested")
                for feature in page:
                    if not first:
                        stream.write(",")
                    json.dump(feature, stream, ensure_ascii=False, separators=(",", ":"))
                    first = False
                record_count += len(page)
                offset += len(page)
                if len(page) < page_limit:
                    break
            stream.write("]}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, dest)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return {
        "source": "Socrata",
        "domain": domain.lower(),
        "dataset_id": dataset_id,
        "url": endpoint,
        "query": {"$order": ":id", "$limit": limit, "paging": "offset"},
        "request_urls": urls,
        "record_count": record_count,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "destination": str(dest.resolve()),
        "snapshot_atomic": False,
        "file_write_atomic": True,
    }
