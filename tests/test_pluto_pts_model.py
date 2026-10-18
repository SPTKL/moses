"""Synthetic SELECT-stage checks; no claim of full PLUTO or PostgreSQL parity."""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from moses.catalog import Catalog
from moses.pluto.transforms import ParityMismatch, StageValidationError, run_stage


INVENTORY = json.loads((Path(__file__).parents[1] / "examples/pluto/inventory.json").read_text())
PTS = next(item for item in INVENTORY["datasets"] if item["name"] == "pluto_pts")
FIELDS = PTS["processing_steps"][0]["args"]["columns"]
DOUBLE_SOURCE = {
    "land_area", "gross_sqft", "residential_area_gross", "office_area_gross", "retail_area_gross",
    "garage_area", "storage_area_gross", "factory_area_gross", "other_area_gross", "num_bldgs",
    "bld_story", "coop_apts", "units", "curactland", "curacttot", "curactextot",
}
DIMENSION_SOURCE = {"lot_frt", "lot_dep", "bld_frt", "bld_dep"}
OUTPUT = [
    "boro", "tb", "tl", "bbl", "street_name", "housenum_lo", "housenum_hi", "aptno",
    "zip", "bldgcl", "ease", "owner", "land_area", "gross_sqft", "residarea", "officearea",
    "retailarea", "garagearea", "storagearea", "factoryarea", "otherarea", "bldgs", "story",
    "coop_apts", "units", "ext", "irreg", "curavl_act", "curavt_act", "curext_act",
    "yrbuilt", "yralt1", "yralt2", "condo_number", "ap_boro", "ap_block", "ap_lot",
    "ap_ease", "ap_date", "lfft", "ldft", "bfft", "bdft",
]


def _row(**changes):
    row = {field: "1" if field in DOUBLE_SOURCE | DIMENSION_SOURCE else "text" for field in FIELDS}
    row.update({"boro": "1", "block": "00001", "lot": "0001", "parid": "1000010001", "ease": "",
                "zip_code": "00123", "av_owner": "ACME", "street_name": "MAIN STREET",
                "appt_date": "2026-01-31"})
    row.update(changes)
    return row


def _input(tmp_path, rows):
    catalog = Catalog(tmp_path / "catalog")
    path = tmp_path / "pluto_pts.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    version = catalog.ingest(path, name="pluto_pts", provenance={"evidence": "synthetic"})["version"]
    return catalog, {"pluto_pts": version}


def test_model_maps_every_source_field_and_numeric_rules(tmp_path):
    pytest.importorskip("dbt.cli.main")
    assert len(FIELDS) == len(OUTPUT) == 43
    catalog, inputs = _input(tmp_path, [
        _row(land_area="+12.5", gross_sqft="1e+2", residential_area_gross="-3.25",
             lot_frt="+10.235", lot_dep="-2.235", bld_frt="0.004", bld_dep="+0.005"),
        _row(parid="1000010002", land_area=None, gross_sqft=None, lot_frt=None, lot_dep=None,
             bld_frt=None, bld_dep=None),
        _row(parid="1000010003", lot_frt="9" * 36 + ".994"),
    ])
    result = run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    table = catalog.read("dof_pts_propmaster")
    assert table.column_names == OUTPUT
    first, second, boundary = table.to_pylist()
    assert first["tb"] == "00001" and first["tl"] == "0001" and first["zip"] == "00123"
    assert first["bbl"] == "1000010001" and first["owner"] == "ACME"
    assert first["land_area"] == 12.5 and first["gross_sqft"] == 100.0
    assert first["residarea"] == -3.25 and first["bldgs"] == 1.0
    assert str(first["lfft"]) == "10.24"
    assert str(first["ldft"]) == "-2.24"
    assert str(first["bfft"]) == "0.00"
    assert str(first["bdft"]) == "0.01"
    assert all(second[name] is None for name in ("land_area", "gross_sqft", "lfft", "ldft", "bfft", "bdft"))
    assert str(boundary["lfft"]) == "9" * 36 + ".99"
    lineage = result["lineage"]
    assert lineage["upstream_sql_sha256"] == "d7370df9faae26319b0fb10dd934f198a0da137159b8e3520a1863e4c47d5bf5"
    assert "models/create_pts.sql" in lineage["dbt_project_sha256"]
    assert result["scope"] == "single_stage"


@pytest.mark.parametrize("field,value", [
    ("land_area", ""), ("gross_sqft", " "), ("num_bldgs", "not-a-number"),
    ("lot_frt", ""), ("lot_dep", "NaN"), ("bld_frt", "1e+100"),
    ("lot_frt", "9" * 36 + ".995"),
])
def test_invalid_numeric_rejected_before_publish(tmp_path, field, value):
    catalog, inputs = _input(tmp_path, [_row(**{field: value})])
    with pytest.raises(StageValidationError, match=field):
        run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    assert "dof_pts_propmaster" not in catalog.lock()


def test_missing_source_column_and_unlocked_input_rejected(tmp_path):
    row = _row()
    row.pop("appt_ease")
    catalog, inputs = _input(tmp_path, [row])
    with pytest.raises(StageValidationError, match="appt_ease"):
        run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    with pytest.raises(StageValidationError, match="version"):
        run_stage(catalog, stage="create_pts", inputs={"pluto_pts": "latest"}, output_name="dof_pts_propmaster")


def test_lock_replay_ignores_new_latest(tmp_path):
    pytest.importorskip("dbt.cli.main")
    catalog, inputs = _input(tmp_path, [_row()])
    first = run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    path = tmp_path / "changed.parquet"
    pq.write_table(pa.Table.from_pylist([_row(land_area="999")]), path)
    catalog.ingest(path, name="pluto_pts", provenance={"evidence": "synthetic"})
    replay = run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    assert replay["output"]["version"] == first["output"]["version"]
    assert replay["output"]["unchanged"]


def test_same_bbl_tax_rows_compare_as_multiset_before_publish(tmp_path):
    pytest.importorskip("dbt.cli.main")
    catalog, inputs = _input(tmp_path, [_row(av_owner="OWNER A"), _row(av_owner="OWNER B")])
    accepted = run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    reference = catalog.read("dof_pts_propmaster")
    reordered = reference.take(pa.array([1, 0]))
    checked = run_stage(catalog, stage="create_pts", inputs=inputs,
                        output_name="dof_pts_propmaster", reference=reordered)
    assert checked["parity"]["equal"]
    with pytest.raises(ParityMismatch) as error:
        run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster",
                  reference=reference.slice(0, 1))
    assert not error.value.report["equal"]
    assert catalog.get_version("dof_pts_propmaster")["version"] == accepted["output"]["version"]
    assert len(catalog.history("dof_pts_propmaster")) == 1


def test_easement_parid_is_preserved_with_its_suffix(tmp_path):
    pytest.importorskip("dbt.cli.main")
    catalog, inputs = _input(tmp_path, [
        _row(parid="1000060001E", ease="E"),
        _row(parid="1000870001F", ease="F"),
        _row(parid="1000870001", ease=""),
    ])
    run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    rows = catalog.read("dof_pts_propmaster").select(["bbl", "ease"]).to_pylist()
    assert rows == [
        {"bbl": "1000060001E", "ease": "E"},
        {"bbl": "1000870001F", "ease": "F"},
        {"bbl": "1000870001", "ease": ""},
    ]


@pytest.mark.parametrize("parid,ease", [
    ("1000060001e", "e"),
    ("1000060001EE", "E"),
    ("1000060001E", "F"),
    ("1000060001", "E"),
    ("0000060001E", "E"),
])
def test_invalid_pts_identifier_rejected_before_publish(tmp_path, parid, ease):
    catalog, inputs = _input(tmp_path, [_row(parid=parid, ease=ease)])
    with pytest.raises(StageValidationError, match="pluto_pts.parid"):
        run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    assert "dof_pts_propmaster" not in catalog.lock()


def test_candidate_easement_identifier_is_validated(tmp_path, monkeypatch):
    catalog, inputs = _input(tmp_path, [_row(parid="1000060001E", ease="E")])
    candidate = pa.Table.from_pylist([{"bbl": "1000060001E", "ease": "F"}])
    monkeypatch.setattr("moses.pluto.transforms._run_dbt", lambda *_args: (candidate, {}))
    with pytest.raises(StageValidationError, match="create_pts.bbl"):
        run_stage(catalog, stage="create_pts", inputs=inputs, output_name="dof_pts_propmaster")
    assert "dof_pts_propmaster" not in catalog.lock()
