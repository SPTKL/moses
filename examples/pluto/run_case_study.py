"""Bounded integration of real PLUTO-related sources; never runs a PLUTO build.

Run from the Moses checkout with .venv/bin/python examples/pluto/run_case_study.py.
Network captures and warehouses stay under ignored .moses/, not in the report.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request

import pyarrow.parquet as pq

from moses import Catalog
from moses.cli import main as moses_cli
from moses.inspection import inspect_source
from moses.sources import download_socrata


ROOT = Path(__file__).resolve().parents[2]
SEED = "products/pluto/seeds/pluto_input_landuse_bldgclass.csv"
SOURCES = [
    {"name": "pluto_public_sample", "dataset_id": "64uk-42ks", "format": "csv", "key": "bbl",
     "recipe_evidence": "ingest_templates/dcp_pluto.yml",
     "scope": "Alternate live public PLUTO distribution; not the versioned DCP ZIP required by the production previous_pluto input."},
    {"name": "lpc_landmarks", "dataset_id": "ncre-qhxs", "format": "geojson", "key": None,
     "recipe_evidence": "ingest_templates/lpc_landmarks.yml",
     "scope": "Exact public endpoint from recipe template; bounded capture without production rename/date-coercion steps. BBL is not a unique landmark key."},
    {"name": "dpr_greenthumb", "dataset_id": "p78i-pat6", "format": "csv", "key": None,
     "recipe_evidence": "ingest_templates/dpr_greenthumb.yml",
     "scope": "Same public dataset as recipe; CSV attribute representation only, not the recipe GeoJSON/geometry transformation."},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_revision(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def fetch_csv(dataset_id, path, limit):
    query = {"$limit": limit, "$order": ":id"}
    url = f"https://data.cityofnewyork.us/resource/{dataset_id}.csv?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Moses-PLUTO-case-study/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        # A server ignoring the requested limit must not cause an unbounded download.
        body = response.read(10_000_001)
        if len(body) > 10_000_000:
            raise ValueError("CSV response exceeded the 10 MB case-study bound")
        content_type = response.headers.get("Content-Type")
    path.write_bytes(body)
    return {"source": "Socrata CSV (case-study adapter)", "dataset_id": dataset_id,
            "url": url, "query": query, "retrieved_at": now(),
            "content_type": content_type, "snapshot_atomic": False}


def cli_json(args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = moses_cli(args)
    if code:
        raise RuntimeError(stderr.getvalue() or stdout.getvalue())
    return json.loads(stdout.getvalue())


def exercise_source(catalog, path, spec, provenance, exports, limit=None):
    inspection = inspect_source(path, preview_rows=0)
    if limit is not None and inspection["row_count"] > limit:
        raise ValueError("Publisher returned more rows than the requested bound")
    first = catalog.ingest(path, name=spec["name"], key=spec["key"], provenance=provenance)
    repeat = catalog.ingest(path, name=spec["name"], key=spec["key"], provenance=provenance)
    if not repeat["unchanged"] or first["version"] != repeat["version"]:
        raise AssertionError("Identical capture unexpectedly created a new accepted version")
    count = catalog.query(f'SELECT count(*) AS n FROM "{spec["name"]}"').to_pylist()[0]["n"]
    if count != inspection["row_count"]:
        raise AssertionError("Query count differs from inspection")
    destination = exports / f'{spec["name"]}.parquet'
    export = cli_json(["--warehouse", str(catalog.root), "export", spec["name"], str(destination), "--version", first["version"]])
    if not pq.read_table(destination).equals(catalog.read(spec["name"], first["version"])):
        raise AssertionError("Export does not match accepted snapshot")
    return {"status": "passed", "inspection": inspection, "version": first["version"],
            "capture_sha256": sha256(path), "source_sha256": first["source_sha256"],
            "content_sha256": first["content_sha256"], "runtime_versions": first["runtime_versions"],
            "repeat_unchanged": repeat["unchanged"], "observations": len(catalog.observations(spec["name"])),
            "query_row_count": count, "export_verified": True,
            "export_sha256": sha256(destination), "export_version": export["version"]}


def run(args):
    repo = args.data_engineering.resolve()
    work_parent = ROOT / ".moses" / "pluto-case-study"
    work_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=work_parent))
    captures, exports = work / "captures", work / "exports"
    captures.mkdir()
    exports.mkdir()
    catalog = Catalog(work / "warehouse")
    report = {"started_at": now(), "case_study": "bounded-real-pluto-inputs", "full_build": False,
              "mode": "seed_only" if args.seed_only else ("offline_captures" if args.offline_from else "live_capture"),
              "limit_per_remote_source": args.limit, "data_engineering_commit": git_revision(repo),
              "moses_commit": git_revision(ROOT), "work_directory": str(work),
              "moses_source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in sorted((ROOT / "src/moses").rglob("*.py"))},
              "scope": "Source normalization and local version lifecycle only. No recipe transformation, PostGIS, dbt, Geosupport, Axway, or full-city scale validation.",
              "datasets": [], "failures": []}
    specs = ([] if args.seed_only else SOURCES) + [{"name": "pluto_input_landuse_bldgclass", "format": "csv", "key": "bldgclass",
                        "recipe_evidence": "products/pluto/seeds/_seeds.yml", "scope": "Complete real repository lookup seed; not sampled."}]
    for spec in specs:
        result = dict(spec)
        path = captures / f'{spec["name"]}.{spec["format"]}'
        sidecar = path.with_suffix(path.suffix + ".provenance.json")
        try:
            if args.offline_from:
                original = args.offline_from / path.name
                shutil.copyfile(original, path)
                provenance = json.loads(original.with_suffix(original.suffix + ".provenance.json").read_text())
                if sha256(path) != provenance["capture_sha256"]:
                    raise ValueError("Offline capture hash does not match recorded provenance")
            elif spec.get("dataset_id"):
                if spec["format"] == "geojson":
                    provenance = download_socrata("data.cityofnewyork.us", spec["dataset_id"], path, limit=args.limit)
                else:
                    provenance = fetch_csv(spec["dataset_id"], path, args.limit)
            else:
                shutil.copyfile(repo / SEED, path)
                provenance = {"source": "NYCPlanning/data-engineering repository seed", "repository_path": SEED,
                              "repository_commit": report["data_engineering_commit"], "captured_at": now()}
            provenance.update({"capture_sha256": sha256(path), "recipe_evidence": spec["recipe_evidence"], "scope": spec["scope"]})
            sidecar.write_text(json.dumps(provenance, indent=2) + "\n")
            result["provenance"] = provenance
            result.update(exercise_source(catalog, path, spec, provenance, exports,
                                         args.limit if spec.get("dataset_id") else None))
        except Exception as exc:
            result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            report["failures"].append({"dataset": spec["name"], "error": result["error"]})
        report["datasets"].append(result)
    try:
        lock_path = work / "inputs.lock.json"
        cli_json(["--warehouse", str(catalog.root), "lock", str(lock_path)])
        lock = json.loads(lock_path.read_text())
        sql = """SELECT p.bldgclass, s.landuse AS seed_landuse, count(*) AS sampled_parcels
                 FROM pluto_public_sample p LEFT JOIN pluto_input_landuse_bldgclass s
                 ON p.bldgclass = s.bldgclass GROUP BY p.bldgclass, s.landuse
                 ORDER BY p.bldgclass, s.landuse"""
        if args.seed_only:
            sql = "SELECT landuse, count(*) AS building_classes FROM pluto_input_landuse_bldgclass GROUP BY landuse ORDER BY landuse"
        current = catalog.query(sql).to_pylist()
        replay = cli_json(["--warehouse", str(catalog.root), "query", sql, "--lock", str(lock_path)])
        if current != replay:
            raise AssertionError("Locked replay differs from current query")
        report["lock_replay"] = {"status": "passed", "versions": lock, "sql": sql,
                                 "result": replay, "same_result": True,
                                 "limitation": "Replays retained snapshots in the same warehouse; upstream changes and a cross-engine/full-build replay were not tested."}
        seed = catalog.read("pluto_input_landuse_bldgclass")
        report["seed_identifier_check"] = {"landuse_arrow_type": str(seed.schema.field("landuse").type),
                                           "leading_zero_codes_preserved": "01" in seed["landuse"].to_pylist()}
        if not args.seed_only:
            queries = {
                "pluto_publisher_versions": "SELECT version, count(*) AS rows FROM pluto_public_sample GROUP BY version ORDER BY version",
                "unmatched_building_classes": "SELECT count(*) AS rows FROM pluto_public_sample p LEFT JOIN pluto_input_landuse_bldgclass s ON p.bldgclass = s.bldgclass WHERE s.bldgclass IS NULL",
                "landmark_key_cardinality": "SELECT count(*) AS rows, count(DISTINCT bbl) AS distinct_bbl FROM lpc_landmarks",
                "blank_pluto_bbl": "SELECT count(*) AS rows FROM pluto_public_sample WHERE bbl = '' OR bbl IS NULL",
            }
            report["evidence_queries"] = {name: {"sql": query, "result": catalog.query(query, versions=lock).to_pylist()}
                                          for name, query in queries.items()}
    except Exception as exc:
        report["failures"].append({"stage": "lock_replay", "error": f"{type(exc).__name__}: {exc}"})
    report["finished_at"] = now()
    report["status"] = "passed" if not report["failures"] else "failed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": str(args.output.resolve()), "work_directory": str(work),
                      "datasets": [{"name": x["name"], "status": x["status"], "rows": x.get("query_row_count"), "error": x.get("error")} for x in report["datasets"]]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-engineering", type=Path, default=ROOT.parent / "data-engineering")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=ROOT / "examples/pluto/results.json")
    parser.add_argument("--offline-from", type=Path, help="Reuse a previous run's captures directory with provenance sidecars")
    parser.add_argument("--seed-only", action="store_true", help="Exercise only the real repository seed, with no network access")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    raise SystemExit(run(args))
