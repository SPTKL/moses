"""Synthetic contract checks; no production or PostgreSQL parity claim."""
from pathlib import Path
from importlib.util import find_spec

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from moses.catalog import Catalog
from pluto_example.transforms import ParityMismatch, StageValidationError, run_stage


def _ingest(catalog, tmp_path, name, rows, evidence="synthetic"):
    path = tmp_path / f"{name}.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=pa.schema([(field, pa.string()) for field in rows[0]])), path)
    return catalog.ingest(path, name=name, provenance={"evidence": evidence})["version"]


def _row(index, **changes):
    return {"bbl": f"100000{index:04}", "bldgclass": "V0", "landuse": "old", "areasource": None,
            "numbldgs": "0", "bldgarea": "0", "untouched": "preserved", **changes}


@pytest.fixture
def inputs(tmp_path):
    catalog = Catalog(tmp_path / "catalog")
    rows = [
        _row(1), _row(2, bldgclass="UNKNOWN", landuse="77"),
        _row(3, areasource="0", bldgarea=None), _row(4, areasource="1"),
        _row(5, areasource=""), _row(6, numbldgs=None),
        _row(7, numbldgs="1"), _row(8, bldgarea="1e-1000"),
        _row(9, bldgclass="A0", landuse="11"),
        _row(10, bldgclass="NULL", landuse="11"),
        _row(11, numbldgs=" -0.0000 ", bldgarea="0e100"),
        _row(12, bldgclass=None, landuse="11"),
    ]
    versions = {"pluto": _ingest(catalog, tmp_path, "pluto", rows),
                "pluto_input_landuse_bldgclass": _ingest(catalog, tmp_path, "pluto_input_landuse_bldgclass", [
                    {"bldgclass": "V0", "landuse": "11"},
                    {"bldgclass": "A0", "landuse": "01"},
                    {"bldgclass": "NULL", "landuse": None},
                ])}
    return catalog, versions, rows


@pytest.mark.skipif(find_spec("dbt") is None, reason="requires optional pluto extra")
def test_dbt_landuse_conditions_lock_replay_and_lineage(inputs, tmp_path):
    catalog, versions, rows = inputs
    result = run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    output = catalog.read("mapped").to_pylist()
    keyed = {row["bbl"]: row for row in output}
    assert [keyed[row["bbl"]]["areasource"] for row in rows] == ["4", None, "4", "1", "", None, None, None, None, None, "4", "4"]
    assert keyed[rows[1]["bbl"]]["landuse"] == "77"
    assert keyed[rows[8]["bbl"]]["landuse"] == "01"
    assert keyed[rows[9]["bbl"]]["landuse"] is None
    assert all(row["untouched"] == "preserved" for row in output)
    assert set(output[0]) == set(rows[0])
    lineage = result["lineage"]
    assert lineage["engines"]["dbt-duckdb"]
    assert len(lineage["sql_sha256"]) == len(lineage["upstream_sql_sha256"]) == 64
    assert lineage["reference_evidence"] == "not_supplied"
    artifacts = catalog.root / lineage["dbt_artifact_directory"]
    assert (artifacts / "manifest.json").is_file()
    assert (artifacts / "run_results.json").is_file()
    assert list((artifacts / "compiled").rglob("landuse.sql"))
    assert result["output"]["provenance"]["pluto_transform"] == lineage
    # New latest must never alter a replay using the old lock.
    _ingest(catalog, tmp_path, "pluto", [_row(1, numbldgs="9")])
    replay = run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    assert replay["output"]["version"] == result["output"]["version"]
    assert replay["output"]["unchanged"]


@pytest.mark.skipif(find_spec("dbt") is None, reason="requires optional pluto extra")
def test_reference_checked_before_publication(inputs):
    catalog, versions, _ = inputs
    first = run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    reference = catalog.read("mapped")
    reference_path = Path(catalog.root) / "reference.parquet"
    pq.write_table(reference, reference_path)
    success = run_stage(catalog, stage="landuse", inputs=versions, output_name="checked", reference=reference_path)
    assert success["parity"]["equal"]
    wrong = reference.set_column(reference.schema.get_field_index("landuse"), "landuse", pa.array(["wrong"] * reference.num_rows))
    with pytest.raises(ParityMismatch) as error:
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped", reference=wrong)
    assert not error.value.report["equal"]
    assert catalog.get_version("mapped")["version"] == first["output"]["version"]
    assert len(catalog.history("mapped")) == 1


@pytest.mark.parametrize("changes, message", [
    ({"bbl": ""}, "canonical"), ({"bbl": "1000000001.0"}, "canonical"),
    ({"bbl": None}, "canonical"), ({"numbldgs": ""}, "numeric"),
    ({"bldgarea": " "}, "numeric"), ({"numbldgs": "zero"}, "numeric"),
])
def test_invalid_source_preserves_previous_output(inputs, tmp_path, changes, message):
    catalog, versions, rows = inputs
    _ingest(catalog, tmp_path, "mapped", [_row(99)])
    old = catalog.get_version("mapped")["version"]
    versions["pluto"] = _ingest(catalog, tmp_path, "pluto", [{**rows[0], **changes}])
    with pytest.raises(StageValidationError, match=message):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    assert catalog.get_version("mapped")["version"] == old


@pytest.mark.parametrize("keys", [["V0", "V0"], [""], [None], [" "]])
def test_invalid_lookup_rejected_before_publication(inputs, tmp_path, keys):
    catalog, versions, _ = inputs
    versions["pluto_input_landuse_bldgclass"] = _ingest(catalog, tmp_path, "pluto_input_landuse_bldgclass", [{"bldgclass": key, "landuse": "11"} for key in keys])
    with pytest.raises(StageValidationError, match="Lookup"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    assert "mapped" not in catalog.lock()


def test_lock_evidence_alias_and_approved_stage_contract(inputs, tmp_path):
    catalog, versions, rows = inputs
    for bad in ({}, {**versions, "pluto": "latest"}, {**versions, "pluto": ""}):
        with pytest.raises(StageValidationError):
            run_stage(catalog, stage="landuse", inputs=bad, output_name="mapped")
    for name in ("pluto", "PLUTO", "pluto_input_landuse_bldgclass"):
        with pytest.raises(StageValidationError, match="alias"):
            run_stage(catalog, stage="landuse", inputs=versions, output_name=name)
    with pytest.raises(StageValidationError, match="Approved"):
        run_stage(catalog, stage="SELECT 1", inputs=versions, output_name="mapped")
    versions["pluto"] = _ingest(catalog, tmp_path, "pluto", rows, evidence=None)
    # Provenance is observation metadata on a logical no-op, so force a new input.
    versions["pluto"] = _ingest(catalog, tmp_path, "pluto", [_row(20)], evidence=None)
    with pytest.raises(StageValidationError, match="evidence"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")


def test_duplicate_bbl_and_missing_fields_rejected(inputs, tmp_path):
    catalog, versions, rows = inputs
    versions["pluto"] = _ingest(catalog, tmp_path, "pluto", [rows[0], rows[0]])
    with pytest.raises(StageValidationError, match="duplicate BBL"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    versions["pluto"] = _ingest(catalog, tmp_path, "pluto", [{"bbl": "1000000001"}])
    with pytest.raises(StageValidationError, match="missing source fields"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")


@pytest.mark.parametrize("alias,field", [("pluto", "bldgclass"), ("pluto_input_landuse_bldgclass", "landuse")])
def test_untyped_null_field_rejected_without_publication(inputs, tmp_path, alias, field):
    catalog, versions, _ = inputs
    table = catalog.read(alias, versions[alias])
    table = table.set_column(table.schema.get_field_index(field), field, pa.nulls(table.num_rows))
    path = tmp_path / "untyped.parquet"
    pq.write_table(table, path)
    versions[alias] = catalog.ingest(path, name=alias, provenance={"evidence": "synthetic"})["version"]
    old = _ingest(catalog, tmp_path, "mapped", [_row(99)])
    with pytest.raises(StageValidationError, match=rf"{alias}\.{field}.*explicit Arrow/Parquet type"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    assert catalog.get_version("mapped")["version"] == old


def test_create_pts_rejects_untyped_field_before_dbt(tmp_path):
    catalog = Catalog(tmp_path / "catalog")
    path = tmp_path / "untyped-pts.parquet"
    pq.write_table(pa.table({"parid": ["1000000001"], "av_owner": pa.nulls(1)}), path)
    version = catalog.ingest(path, name="pluto_pts", provenance={"evidence": "synthetic"})["version"]
    with pytest.raises(StageValidationError, match=r"pluto_pts\.av_owner.*explicit Arrow/Parquet type"):
        run_stage(catalog, stage="create_pts", inputs={"pluto_pts": version}, output_name="mapped")
    assert "mapped" not in catalog.lock()


@pytest.mark.skipif(find_spec("dbt") is None, reason="requires optional pluto extra")
def test_typed_nulls_and_original_field_metadata_preserved(inputs, tmp_path):
    catalog, versions, _ = inputs
    table = pa.Table.from_pylist([_row(1, bldgclass=None, landuse="11")], schema=pa.schema([
        pa.field(name, pa.large_string() if name == "bldgclass" else pa.string(),
                 nullable=name != "bbl", metadata={b"meaning": name.encode()})
        for name in _row(1)
    ], metadata={b"source": b"synthetic"}))
    path = tmp_path / "typed-null.parquet"
    pq.write_table(table, path)
    versions["pluto"] = catalog.ingest(path, name="pluto", provenance={"evidence": "synthetic"})["version"]
    run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    output = catalog.read("mapped")
    assert output.schema.equals(table.schema, check_metadata=True)
    assert output["bldgclass"].null_count == 1
    assert output["areasource"].to_pylist() == ["4"]


@pytest.mark.skipif(find_spec("dbt") is None, reason="requires optional pluto extra")
def test_seed_null_cannot_violate_original_nonnullable_field(inputs, tmp_path):
    catalog, versions, _ = inputs
    row = _row(1, bldgclass="NULL")
    schema = pa.schema([pa.field(name, pa.string(), nullable=name != "landuse") for name in row])
    path = tmp_path / "nonnull.parquet"
    pq.write_table(pa.Table.from_pylist([row], schema=schema), path)
    versions["pluto"] = catalog.ingest(path, name="pluto", provenance={"evidence": "synthetic"})["version"]
    with pytest.raises(StageValidationError, match="landuse.*nonnullable"):
        run_stage(catalog, stage="landuse", inputs=versions, output_name="mapped")
    assert "mapped" not in catalog.lock()
