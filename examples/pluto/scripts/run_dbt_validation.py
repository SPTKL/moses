#!/usr/bin/env python3
"""Offline synthetic dbt-stage validation, optionally against original PG SQL.

This validates two bounded stages, not a production PLUTO release or its inputs.
The optional PostgreSQL container must already exist; this script never starts
containers or opens ports. Legacy UPDATE statements run only as the reference.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import uuid

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from moses.catalog import Catalog
from pluto_example.transforms import run_stage


ROOT = Path(__file__).resolve().parents[1]
DOUBLE_FIELDS = set("land_area gross_sqft residential_area_gross office_area_gross retail_area_gross garage_area storage_area_gross factory_area_gross other_area_gross num_bldgs bld_story coop_apts units curactland curacttot curactextot".split())
DIMENSIONS = {"lot_frt", "lot_dep", "bld_frt", "bld_dep"}


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _landuse():
    rows = []
    cases = [{}, {"bldgclass": "UNKNOWN", "landuse": "77"},
             {"areasource": "0", "bldgarea": None}, {"areasource": "1"},
             {"areasource": ""}, {"numbldgs": None}, {"numbldgs": "1"},
             {"bldgarea": "1e-1000"}, {"bldgclass": "A0", "landuse": "11"},
             {"bldgclass": "NULL", "landuse": "11"},
             {"numbldgs": " -0.0000 ", "bldgarea": "0e100"},
             {"bldgclass": None, "landuse": "11"}]
    for index, changes in enumerate(cases, 1):
        rows.append({"bbl": f"100000{index:04}", "bldgclass": "V0", "landuse": "old",
                     "areasource": None, "numbldgs": "0", "bldgarea": "0", **changes})
    return {"pluto": rows, "pluto_input_landuse_bldgclass": [
        {"bldgclass": "V0", "landuse": "11"}, {"bldgclass": "A0", "landuse": "01"},
        {"bldgclass": "NULL", "landuse": None}]}


def _pts():
    inventory = json.loads((ROOT / "scripts/inventory.json").read_text())
    fields = next(item for item in inventory["datasets"] if item["name"] == "pluto_pts")["processing_steps"][0]["args"]["columns"]
    rows = []
    for index in range(1, 4):
        row = {field: "1" if field in DOUBLE_FIELDS | DIMENSIONS else "text" for field in fields}
        row.update({"boro": "1", "block": "00001", "lot": f"{index:04}", "parid": f"100001{index:04}",
                    "ease": "", "zip_code": "00123", "av_owner": "ACME", "street_name": "MAIN STREET"})
        rows.append(row)
    rows[0].update(land_area="+12.5", gross_sqft="1e+2", residential_area_gross="-3.25",
                   lot_frt="+10.235", lot_dep="-2.235", bld_frt="0.004", bld_dep="+0.005")
    rows[1].update({name: None for name in DOUBLE_FIELDS | DIMENSIONS})
    rows[2].update(lot_frt="999999999999999999999999999999999999.994", lot_dep="1e-1000")
    return {"pluto_pts": rows}


def _table(rows):
    # Preserve normalized text inputs and SQL NULL, including all-null fields.
    return pa.Table.from_pylist(rows, schema=pa.schema([(field, pa.string()) for field in rows[0]]))


def _csv(table):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n", quoting=csv.QUOTE_ALL)
    writer.writerow(table.column_names)
    for row in table.to_pylist():
        # PostgreSQL CSV distinguishes quoted empty strings from unquoted NULL.
        parts = []
        for name in table.column_names:
            value = row[name]
            parts.append("" if value is None else '"' + str(value).replace('"', '""') + '"')
        output.write(",".join(parts) + "\n")
    return output.getvalue()


def _pg_reference(container, stage, tables, upstream_sql, schema, directory):
    namespace = "moses_validation_" + uuid.uuid4().hex
    commands = [f"CREATE SCHEMA {namespace}; SET search_path TO {namespace};"]
    for alias, table in tables.items():
        columns = ", ".join(f'"{name}" text' for name in table.column_names)
        commands.append(f'CREATE TABLE "{alias}" ({columns});')
        commands.append(f'COPY "{alias}" FROM STDIN WITH (FORMAT CSV, HEADER TRUE);\n' + _csv(table) + "\\.\n")
    commands.append(upstream_sql)
    output_table = "pluto" if stage == "landuse" else "dof_pts_propmaster"
    commands.append(f"COPY (SELECT * FROM {output_table} ORDER BY bbl) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);")
    commands.append(f"DROP SCHEMA {namespace} CASCADE;")
    command = ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At"]
    result = subprocess.run(command, input="\n".join(commands), capture_output=True, text=True, timeout=60)
    (directory / "postgres-reference.log").write_text(result.stderr)
    if result.returncode:
        subprocess.run(command, input=f"DROP SCHEMA IF EXISTS {namespace} CASCADE;", capture_output=True, text=True, timeout=30)
        raise RuntimeError(f"PostgreSQL reference failed: {result.stderr}")
    path = directory / "postgres-reference.csv"
    path.write_text(result.stdout)
    reference = pacsv.read_csv(path, convert_options=pacsv.ConvertOptions(
        column_types={field.name: field.type for field in schema}, strings_can_be_null=True,
        null_values=[""], quoted_strings_can_be_null=False))
    reference = reference.cast(schema)
    pq.write_table(reference, directory / "postgres-reference.parquet")
    return reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-engineering", type=Path, default=ROOT.parents[2] / "data-engineering")
    parser.add_argument("--postgres-container")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".moses/pluto-dbt-validation")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    run = args.output_root / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True)
    report = {"evidence": "synthetic", "production_parity": False, "release_reproduced": None,
              "run_directory": str(run.resolve()), "reference_engine": None, "stages": {}}
    if args.postgres_container:
        probe = subprocess.run(["docker", "exec", args.postgres_container, "psql", "-U", "postgres", "-Atc", "SELECT version()"], capture_output=True, text=True, check=True, timeout=30)
        report["reference_engine"] = probe.stdout.strip()
    for stage, fixtures in (("landuse", _landuse()), ("create_pts", _pts())):
        directory = run / stage
        directory.mkdir()
        catalog = Catalog(directory / "catalog")
        tables = {alias: _table(rows) for alias, rows in fixtures.items()}
        versions = {}
        for alias, table in tables.items():
            path = directory / f"{alias}.parquet"
            pq.write_table(table, path)
            versions[alias] = catalog.ingest(path, name=alias, provenance={"evidence": "synthetic"})["version"]
        (directory / "lock.json").write_text(json.dumps(versions, indent=2))
        initial = run_stage(catalog, stage=stage, inputs=versions, output_name="candidate")
        candidate = catalog.read("candidate")
        upstream_path = args.data_engineering / f"products/pluto/pluto_build/sql/{stage}.sql"
        upstream = upstream_path.read_text()
        (directory / "upstream.sql").write_text(upstream)
        if _digest(upstream_path) != initial["lineage"]["upstream_sql_sha256"]:
            raise RuntimeError(f"Upstream SQL hash differs from approved {stage} baseline")
        checked = None
        if args.postgres_container:
            reference = _pg_reference(args.postgres_container, stage, tables, upstream, candidate.schema, directory)
            checked = run_stage(catalog, stage=stage, inputs=versions, output_name="reference_checked", reference=reference)
        # Update latest input to a distinct valid row; the replay retains old lock.
        alias = "pluto" if stage == "landuse" else "pluto_pts"
        changed = tables[alias].slice(0, 1)
        path = directory / "changed-latest.parquet"
        pq.write_table(changed, path)
        newer = catalog.ingest(path, name=alias, provenance={"evidence": "synthetic"})
        assert newer["version"] != versions[alias]
        replay = run_stage(catalog, stage=stage, inputs=versions, output_name="candidate")
        assert replay["output"]["version"] == initial["output"]["version"]
        report["stages"][stage] = {
            "rows": candidate.num_rows, "input_lock": versions, "lock_replay_equal": True,
            "parity": checked["parity"] if checked else None,
            "reference_schema_adaptation": "PostgreSQL unconstrained numeric dimensions represented as decimal(38,2) within validated range" if stage == "create_pts" and checked else None,
            "upstream_sql_sha256": _digest(upstream_path), "upstream_path": str(upstream_path.resolve()),
            "lineage": initial["lineage"], "checked_output": checked["output"]["version"] if checked else None,
            "limitations": ["synthetic stage fixtures only", "not full PLUTO build parity", "create_pts duplicate BBL grain covered by unit tests separately"]}
        (run / "report.json").write_text(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps({"report": str(run / "report.json"), "production_parity": False,
                      "stages": {name: {"rows": result["rows"], "lock_replay_equal": result["lock_replay_equal"], "reference_equal": result["parity"]["equal"] if result["parity"] else None} for name, result in report["stages"].items()}}, indent=2))


if __name__ == "__main__":
    main()
