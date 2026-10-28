"""Approved, bounded PLUTO stages; this is not the complete PLUTO build.

``landuse`` accepts the table immediately preceding either invocation of the
upstream landuse.sql. A finished PLUTO release is only sample evidence, never
proof that preceding stages were reproduced. Numeric blanks are invalid, as in
PostgreSQL's numeric cast; nulls remain null. Invalid numeric values are rejected
throughout both source fields before running the stage.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
from importlib.metadata import PackageNotFoundError, version as package_version
from importlib.resources import files
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from moses import Catalog


_ALIASES = {"pluto", "pluto_input_landuse_bldgclass"}
_EVIDENCE = {"synthetic", "sample", "exact_stage_input"}
_UPSTREAM = "products/pluto/pluto_build/sql/landuse.sql"
_UPSTREAM_SHA256 = "0208fdcf15a8b2f6a6ea8c7e1e0dd45608a23da408574e83cbda3adf665916fc"
_NUMERIC = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
_CODE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class StageValidationError(ValueError):
    """Stage was rejected before publishing any output."""


class ParityMismatch(StageValidationError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__("Reference parity failed; output was not published")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _required(table: pa.Table, names: set[str], alias: str) -> None:
    if len(set(table.column_names)) != len(table.column_names):
        raise StageValidationError(f"{alias}: duplicate column names")
    missing = names - set(table.column_names)
    if missing:
        raise StageValidationError(f"{alias}: missing source fields {sorted(missing)}")


def _explicit_types(table: pa.Table, alias: str) -> None:
    for field in table.schema:
        if pa.types.is_null(field.type):
            raise StageValidationError(
                f"{alias}.{field.name}: Arrow null type is ambiguous; provide explicit "
                "Arrow/Parquet type (string for known PLUTO fields)"
            )


def _text(table: pa.Table, names: set[str], alias: str) -> None:
    for name in names:
        if any(value is not None and not isinstance(value, str) for value in table[name].to_pylist()):
            raise StageValidationError(f"{alias}.{name}: expected text or null")


def _bbl(table: pa.Table, *, column: str = "bbl", unique: bool = True, alias: str = "pluto") -> None:
    values = table[column].to_pylist()
    for row, value in enumerate(values, 1):
        if not isinstance(value, str) or not re.fullmatch(r"[1-5][0-9]{9}", value):
            raise StageValidationError(f"{alias}.{column} row {row}: expected canonical 10-digit BBL")
    if unique and len(values) != len(set(values)):
        raise StageValidationError(f"{alias}.{column}: duplicate BBLs")


def _pts_parid(table: pa.Table, *, column: str, alias: str) -> None:
    """Validate DOF tax-record identifiers, including easement suffixes.

    The published PTS source uses a 10-digit parcel ID for ordinary rows and
    appends one uppercase easement letter for easement rows. The SQL stage
    retains that identifier verbatim as ``bbl``.
    """
    for row, (value, ease) in enumerate(zip(table[column].to_pylist(), table["ease"].to_pylist()), 1):
        if not isinstance(value, str) or not re.fullmatch(r"[1-5][0-9]{9}(?:[A-Z])?", value):
            raise StageValidationError(f"{alias}.{column} row {row}: expected 10-digit parcel ID with optional uppercase easement suffix")
        if len(value) == 10 and ease not in ("", None):
            raise StageValidationError(f"{alias}.{column} row {row}: ordinary parcel must have empty ease")
        if len(value) == 11 and ease != value[-1]:
            raise StageValidationError(f"{alias}.{column} row {row}: easement suffix must match ease")


def _zero(table: pa.Table, name: str) -> pa.Array:
    result = []
    for row, value in enumerate(table[name].to_pylist(), 1):
        if value is None:
            result.append(None)
            continue
        text = str(value).strip(" \t\r\n\v\f")
        if not _NUMERIC.fullmatch(text) and text.lower() not in {"nan", "infinity", "+infinity", "-infinity", "inf", "+inf", "-inf"}:
            raise StageValidationError(f"pluto.{name} row {row}: invalid PostgreSQL numeric value {value!r}")
        try:
            result.append(Decimal(text).is_zero())
        except InvalidOperation as exc:
            raise StageValidationError(f"pluto.{name} row {row}: invalid numeric value") from exc
    return pa.array(result, type=pa.bool_())


def _run_dbt(tables: dict[str, pa.Table], stage: str, catalog: Catalog) -> tuple[pa.Table, dict]:
    try:
        versions = {name: package_version(name) for name in ("dbt-core", "dbt-duckdb")}
    except PackageNotFoundError as exc:
        raise StageValidationError("PLUTO stages require the pluto-example dependencies") from exc
    resource = files("pluto_example").joinpath("dbt")
    project_files = ["dbt_project.yml", "profiles.yml", "models/sources.yml", "models/schema.yml", f"models/{stage}.sql"]
    hashes = {name: _hash(resource.joinpath(name).read_bytes()) for name in project_files}
    with tempfile.TemporaryDirectory(prefix="moses-dbt-") as directory:
        project = Path(directory)
        for name in project_files:
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(resource.joinpath(name).read_bytes())
        database = project / "inputs.duckdb"
        profile = project / "profiles.yml"
        # JSON quoting is valid YAML and preserves arbitrary local path characters.
        profile.write_text(profile.read_text().replace("__DATABASE_PATH__", json.dumps(str(database))))
        con = duckdb.connect(str(database))
        try:
            for name, table in tables.items():
                con.register("_capture", table)
                con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM _capture')
                con.unregister("_capture")
        finally:
            con.close()
        # A separate process isolates dbt's global state; no executable lookup,
        # global environment mutation, arbitrary user SQL, or package downloads.
        command = [sys.executable, "-c", "from dbt.cli.main import dbtRunner; import sys; r=dbtRunner().invoke(sys.argv[1:]); sys.exit(0 if r.success else 1)",
                   "build", "--project-dir", str(project), "--profiles-dir", str(project),
                   "--select", stage, "--no-use-colors", "--no-send-anonymous-usage-stats"]
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=180)
        # Keep dbt's compiled model and execution evidence after the temporary
        # database is removed. UUID directories are never reused or overwritten.
        artifact_dir = catalog.root / "transform_runs" / uuid.uuid4().hex
        artifact_dir.mkdir(parents=True)
        artifacts = {}
        for path in (project / "target").rglob("*"):
            if path.is_file() and (path.suffix == ".sql" or path.name in {"manifest.json", "run_results.json"}):
                relative = path.relative_to(project / "target")
                destination = artifact_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                destination.chmod(0o444)
                artifacts[relative.as_posix()] = _hash(path.read_bytes())
        (artifact_dir / "execution.log").write_text(result.stdout + result.stderr)
        (artifact_dir / "execution.log").chmod(0o444)
        if result.returncode:
            raise StageValidationError(f"dbt {stage} failed before publication; artifacts: {artifact_dir}\n" + (result.stdout + result.stderr)[-4000:])
        con = duckdb.connect(str(database), read_only=True)
        try:
            candidate = con.execute(f'SELECT * FROM moses_stage."{stage}"').to_arrow_table()
        finally:
            con.close()
    return candidate, {"versions": versions, "project_sha256": hashes,
                       "artifact_directory": artifact_dir.relative_to(catalog.root).as_posix(), "artifact_sha256": artifacts}


def _prepare_landuse(tables: dict[str, pa.Table]) -> dict[str, pa.Table]:
    source, lookup = tables["pluto"], tables["pluto_input_landuse_bldgclass"]
    _required(source, {"bbl", "bldgclass", "landuse", "areasource", "numbldgs", "bldgarea"}, "pluto")
    _required(lookup, {"bldgclass", "landuse"}, "pluto_input_landuse_bldgclass")
    _bbl(source)
    _text(source, {"bldgclass", "landuse", "areasource"}, "pluto")
    _text(lookup, {"bldgclass", "landuse"}, "pluto_input_landuse_bldgclass")
    keys = lookup["bldgclass"].to_pylist()
    if any(value is None or not value.strip() for value in keys):
        raise StageValidationError("Lookup bldgclass contains empty identifiers")
    if len(keys) != len(set(keys)):
        raise StageValidationError("Lookup bldgclass contains duplicates")
    for name in ("numbldgs", "bldgarea"):
        helper = f"_moses_{name}_zero"
        if helper in source.column_names:
            raise StageValidationError(f"Reserved source column {helper}")
        source = source.append_column(helper, _zero(source, name))
    return {"pluto": source, "pluto_input_landuse_bldgclass": lookup}


_PTS_DOUBLE = set("land_area gross_sqft residential_area_gross office_area_gross retail_area_gross garage_area storage_area_gross factory_area_gross other_area_gross num_bldgs bld_story coop_apts units curactland curacttot curactextot".split())
_PTS_DIMENSIONS = {"lot_frt", "lot_dep", "bld_frt", "bld_dep"}
_PTS_TEXT = set("boro block lot parid street_name housenum_lo housenum_hi aptno zip_code bldg_class ease av_owner bld_ext lot_irreg yrbuilt yralt1 yralt2 condo_number appt_boro appt_block appt_lot appt_ease appt_date".split())


def _prepare_pts(tables: dict[str, pa.Table]) -> dict[str, pa.Table]:
    source = tables["pluto_pts"]
    fields = _PTS_TEXT | _PTS_DOUBLE | _PTS_DIMENSIONS
    _required(source, fields, "pluto_pts")
    _text(source, fields, "pluto_pts")
    # Tax records can include multiple easement rows for the same parcel.
    _pts_parid(source, column="parid", alias="pluto_pts")
    for name in _PTS_DOUBLE | _PTS_DIMENSIONS:
        for row, value in enumerate(source[name].to_pylist(), 1):
            if value is None:
                continue
            text = value.replace("+", "").strip(" \t\r\n\v\f")
            if not _NUMERIC.fullmatch(text):
                raise StageValidationError(f"pluto_pts.{name} row {row}: invalid numeric value")
            try:
                decimal = Decimal(text)
            except InvalidOperation as exc:
                raise StageValidationError(f"pluto_pts.{name} row {row}: invalid numeric value") from exc
            if name in _PTS_DOUBLE:
                number = float(decimal)
                if not math.isfinite(number) or (number == 0 and not decimal.is_zero()):
                    raise StageValidationError(f"pluto_pts.{name} row {row}: double overflow or underflow")
            else:
                if decimal.adjusted() > 36:
                    raise StageValidationError(f"pluto_pts.{name} row {row}: exceeds decimal(38,2)")
                with localcontext() as context:
                    context.prec = max(40, len(decimal.as_tuple().digits) + 4)
                    rounded = decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if rounded.copy_abs() >= Decimal("1e36"):
                    raise StageValidationError(f"pluto_pts.{name} row {row}: exceeds decimal(38,2)")
    return tables


def run_stage(
    catalog: Catalog, *, stage: str, inputs: dict[str, str], output_name: str,
    reference: str | Path | pa.Table | None = None, evidence: str | None = None,
) -> dict:
    """Run a fixed stage from exact versions, validate, then atomically ingest.

    Landuse uses fixed names ``pluto`` and ``pluto_input_landuse_bldgclass``;
    create_pts uses ``pluto_pts`` (tax-record grain; repeated BBLs allowed).
    Evidence must be explicit here or in each
    input manifest's provenance under ``evidence``. A reference path is a local
    Parquet or CSV table and is compared across all columns before publication.
    """
    if stage not in {"landuse", "create_pts"}:
        raise StageValidationError("Approved stages: landuse, create_pts")
    aliases = _ALIASES if stage == "landuse" else {"pluto_pts"}
    if not isinstance(inputs, dict) or set(inputs) != aliases:
        raise StageValidationError(f"{stage} requires exact input aliases {sorted(aliases)}")
    if any(not isinstance(v, str) or not v or v.lower() == "latest" for v in inputs.values()):
        raise StageValidationError("Every input requires an explicit locked version")
    catalog._validate_name(output_name)
    if output_name.lower() in {name.lower() for name in inputs}:
        raise StageValidationError("Output cannot alias an input dataset")
    manifests = {name: catalog.get_version(name, version) for name, version in inputs.items()}
    categories = {name: evidence or manifest.get("provenance", {}).get("evidence") for name, manifest in manifests.items()}
    if any(value not in _EVIDENCE for value in categories.values()):
        raise StageValidationError(f"Declare evidence as one of {sorted(_EVIDENCE)} for every input")
    tables = {name: catalog.read(name, version) for name, version in inputs.items()}
    for alias, table in tables.items():
        _explicit_types(table, alias)
    prepared = _prepare_landuse(tables) if stage == "landuse" else _prepare_pts(tables)
    candidate, dbt = _run_dbt(prepared, stage, catalog)
    if stage == "landuse":
        original_schema = tables["pluto"].schema
        for field in original_schema:
            if not field.nullable and candidate[field.name].null_count:
                raise StageValidationError(f"pluto.{field.name}: stage introduced nulls into nonnullable field")
        try:
            candidate = candidate.cast(original_schema, safe=True)
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError, pa.ArrowTypeError) as exc:
            raise StageValidationError(f"landuse cannot preserve source schema: {exc}") from exc
        _bbl(candidate)
    else:
        _pts_parid(candidate, column="bbl", alias="create_pts")
    parity = None
    reference_capture = None
    if reference is not None:
        from .parity import compare_row_multisets, compare_tables
        if isinstance(reference, pa.Table):
            expected = reference
        else:
            from moses.ingest import read_vector
            expected, _ = read_vector(Path(reference))
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, expected.schema) as stream:
            stream.write_table(expected)
        reference_capture = {"table_ipc_sha256": _hash(sink.getvalue().to_pybytes()),
                             "row_count": expected.num_rows,
                             "path": str(Path(reference).resolve()) if not isinstance(reference, pa.Table) else None}
        parity = compare_tables(candidate, expected) if stage == "landuse" else compare_row_multisets(candidate, expected)
        if not parity["equal"]:
            raise ParityMismatch(parity)
    lineage = {
        "stage": stage, "scope": "single_stage", "upstream_paths": [f"products/pluto/pluto_build/sql/{stage}.sql", "products/pluto/pluto_build/02_build.sh"],
        "sql_sha256": dbt["project_sha256"][f"models/{stage}.sql"], "code_sha256": _CODE_SHA256,
        "upstream_sql_sha256": _UPSTREAM_SHA256 if stage == "landuse" else "d7370df9faae26319b0fb10dd934f198a0da137159b8e3520a1863e4c47d5bf5", "dbt_project_sha256": dbt["project_sha256"],
        "dbt_artifact_directory": dbt["artifact_directory"], "dbt_artifact_sha256": dbt["artifact_sha256"],
        "engines": {"duckdb": duckdb.__version__, "pyarrow": pa.__version__, **dbt["versions"]},
        "inputs": {name: {"version": m["version"], "content_sha256": m["content_sha256"], "evidence": categories[name]} for name, m in manifests.items()},
        "numeric_policy": "PostgreSQL numeric zero; null preserved; blank/invalid rejected before execution" if stage == "landuse" else "finite double; dimension decimal(38,2), round half away from zero; invalid/overflow/underflow rejected",
        "parity": parity,
        "reference_evidence": "caller_supplied_table; not attested PostgreSQL execution" if reference is not None else "not_supplied",
        "reference_capture": reference_capture,
    }
    with tempfile.TemporaryDirectory(prefix="pluto-stage-") as directory:
        output_path = Path(directory) / f"{stage}.parquet"
        pq.write_table(candidate, output_path)
        output = catalog.ingest(output_path, name=output_name, key="bbl" if stage == "landuse" else None, provenance={"pluto_transform": lineage})
    return {"stage": stage, "scope": "single_stage", "inputs": dict(inputs), "lineage": lineage, "output": output, "parity": parity}
