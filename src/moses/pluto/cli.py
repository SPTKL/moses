"""Local PLUTO planning, dbt execution and reference comparison commands."""
from __future__ import annotations

import json
from pathlib import Path


def add_parser(sub):
    pluto = sub.add_parser("pluto", help="Rebuild PLUTO stages with pinned inputs and dbt-duckdb")
    commands = pluto.add_subparsers(dest="pluto_command", required=True)
    build = commands.add_parser("build", help="Build and export a complete PLUTO candidate from locked sources")
    build.add_argument("--lock", required=True, help="Production ingestion report or exact Moses input lock")
    build.add_argument("--source-repo", required=True, help="Read-only upstream checkout containing the pinned 26v2 commit")
    build.add_argument("--output-dir", required=True, help="New directory for database, dbt artifacts and exported PLUTO")
    build.add_argument("--resume", action="store_true", help="Resume a failed build with the same lock and native checkpoints")
    build.add_argument("--reuse-build", help="Clone a completed build's verified caches into a new candidate directory")
    build.add_argument("--candidate-version", default="26v2m4")
    build.add_argument("--output", default="pluto_moses", help="Moses dataset name for accepted candidate")
    build.add_argument("--extension-directory", default=".extensions")
    build.add_argument("--geosupport-release", help="Explicit installed native bundle, e.g. 26b; historical runtime remains unattested")
    build.add_argument("--geosupport-extension", help="Path to the local native DuckDB extension")
    build.add_argument("--geosupport-home", help="Existing bundle store; no automatic downloads")
    build.add_argument("--geosupport-runtime", choices=["local", "docker"], help="Native runtime; use docker on macOS")
    build.add_argument("--reference", help="Published PLUTO CSV used only for post-build comparison")
    build.add_argument("--report")
    fetch = commands.add_parser("fetch-production", help="Capture published inputs and ingest full sources with Moses")
    fetch.add_argument("--release", default="26v2")
    fetch.add_argument("--source-repo", help="Read-only data-engineering checkout containing the release commit")
    fetch.add_argument("--cache", required=True)
    fetch.add_argument("--extension-directory", default=".extensions", help="Directory containing installed DuckDB Spatial")
    fetch.add_argument("--offline", action="store_true", help="Verify and ingest previously captured sources without network")
    fetch.add_argument("--capture-only", action="store_true", help="Capture inputs without normalizing or importing")
    fetch.add_argument("--report")
    plan = commands.add_parser("plan", help="Resolve supplied upstream release metadata without downloading")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--config", required=True)
    plan.add_argument("--report", help="Save JSON report; destination must not exist")
    acquire = commands.add_parser("acquire", help="Verify and capture resolved local source artifacts")
    acquire.add_argument("--plan", required=True)
    acquire.add_argument("--report", required=True, help="Save acquired input lock and provenance")
    run = commands.add_parser("run", help="Build one SELECT-only dbt stage from exact catalog versions")
    run.add_argument("--stage", required=True, choices=["landuse", "create_pts"])
    run.add_argument("--lock", required=True, help="Moses name/version lock or PLUTO acquisition report")
    run.add_argument("--output", required=True, help="Accepted output dataset name")
    run.add_argument("--reference", help="Reference stage CSV/Parquet; mismatches block publication")
    run.add_argument("--evidence", required=True, choices=["synthetic", "sample", "exact_stage_input"])
    run.add_argument("--report", help="Save successful or failed parity report")
    compare = commands.add_parser("compare", help="Compare keyed reference and candidate table files")
    compare.add_argument("candidate")
    compare.add_argument("reference")
    compare.add_argument("--key", default="bbl")
    compare.add_argument("--column", action="append", dest="columns")
    compare.add_argument("--report")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(result, destination=None):
    text = json.dumps(result, indent=2, allow_nan=False, default=str) + "\n"
    if destination:
        with Path(destination).open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")


def _lock(value):
    if isinstance(value, dict) and "input_lock" in value:
        value = value["input_lock"]
    if isinstance(value, dict) and isinstance(value.get("versions"), dict):
        value = value["versions"]
    if isinstance(value, dict) and isinstance(value.get("inputs"), list):
        return {row["alias"]: row["catalog_version"] for row in value["inputs"]}
    if not isinstance(value, dict) or any(not isinstance(v, str) or not v for v in value.values()):
        raise ValueError("Expected a name/version lock or an acquired PLUTO input lock")
    return value


def execute(args):
    # Fail before writes/long-running work if the requested report already exists.
    if args.report and Path(args.report).exists():
        raise ValueError(f"Report destination already exists: {args.report}")
    if args.pluto_command == "build":
        import os
        import sys
        from .full import run_full
        from ..catalog import Catalog
        if args.geosupport_runtime:
            os.environ['GEOSUPPORT_RUNTIME'] = args.geosupport_runtime
        result = run_full(Catalog(args.warehouse), inputs=_lock(_read_json(args.lock)),
                          source_repo=args.source_repo, output_dir=args.output_dir,
                          candidate_version=args.candidate_version, output_name=args.output,
                          extension_directory=args.extension_directory, reference=args.reference,
                          geosupport_release=args.geosupport_release,
                          geosupport_extension=args.geosupport_extension,
                          geosupport_home=args.geosupport_home,
                          resume=args.resume,
                          reuse_build=args.reuse_build,
                          progress=lambda message: print(message, file=sys.stderr, flush=True))
        _emit(result, args.report)
        return 0
    if args.pluto_command == "fetch-production":
        import sys
        from .pipeline import capture_production, ingest_production
        from ..catalog import Catalog
        if args.offline and args.capture_only:
            raise ValueError("--offline and --capture-only cannot be combined")
        if not args.offline:
            if not args.source_repo:
                raise ValueError("--source-repo is required to capture exact release seeds")
            result = capture_production(args.release, args.source_repo, args.cache)
            if args.capture_only:
                _emit(result, args.report)
                captured = {r['name'] for r in result['normalized_artifacts']['inputs'] if r['status'] == 'downloaded'}
                captured.update(r['name'] for r in result['raw_captures']['inputs'] if r['status'] == 'raw_downloaded')
                return 0 if len(captured) == 38 else 2
        metadata = _read_json(Path(args.cache) / "release/build_metadata.json")
        if metadata.get("version") != args.release:
            raise ValueError("Cached release does not match --release")
        result = ingest_production(Catalog(args.warehouse), args.cache,
                                   extension_directory=Path(args.extension_directory).resolve(),
                                   progress=lambda message: print(message, file=sys.stderr, flush=True))
        _emit(result, args.report)
        return 0 if all(r['status'] == 'ingested' for r in result['inputs']) else 2
    if args.pluto_command == "plan":
        from .sources import plan_sources
        result = plan_sources(_read_json(args.inventory), _read_json(args.config))
        _emit(result, args.report)
        return 0 if result["build_ready"] else 2
    if args.pluto_command == "compare":
        from .parity import compare_tables
        from ..ingest import read_vector
        candidate, _ = read_vector(args.candidate)
        reference, _ = read_vector(args.reference)
        result = compare_tables(candidate, reference, key=args.key, columns=args.columns)
        _emit(result, args.report)
        return 0 if result["equal"] else 2
    from ..catalog import Catalog
    catalog = Catalog(args.warehouse)
    if args.pluto_command == "acquire":
        from .sources import acquire_sources
        result = acquire_sources(catalog, _read_json(args.plan))
    else:
        from .transforms import run_stage, ParityMismatch
        locked = _lock(_read_json(args.lock))
        required = {"pluto", "pluto_input_landuse_bldgclass"} if args.stage == "landuse" else {"pluto_pts"}
        missing = required - locked.keys()
        if missing:
            raise ValueError(f"Stage input lock is missing {sorted(missing)}")
        try:
            result = run_stage(catalog, stage=args.stage, inputs={name: locked[name] for name in required},
                               output_name=args.output, reference=args.reference,
                               evidence=args.evidence)
        except ParityMismatch as exc:
            _emit(exc.report, args.report)
            return 2
    _emit(result, args.report)
    return 0
