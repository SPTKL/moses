import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from moses import Catalog
from moses.cli import main


def test_inspect_does_not_create_warehouse_and_scans_beyond_preview(tmp_path, capsys):
    source = tmp_path / "source.csv"
    source.write_text("id,value\n001,1\n002,text\n")
    warehouse = tmp_path / "absent"
    assert main(["-w", str(warehouse), "inspect", str(source), "--infer-types", "--preview-rows", "1"]) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["row_count"] == 2
    assert inspection["preview"] == [{"id": "001", "value": "1"}]
    assert inspection["schema"][1]["type"] == "string"
    assert not warehouse.exists()


def test_init_crs_and_tabular_load_roundtrip(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MOSES_DEFAULT_CRS", raising=False)
    root = tmp_path / "warehouse"
    args = ["-w", str(root)]
    assert main(args + ["init", "--default-crs", "EPSG:2263"]) == 0
    assert json.loads(capsys.readouterr().out)["default_crs"] == "EPSG:2263"
    assert json.loads((root / "config.json").read_text())["default_crs"] == "EPSG:2263"
    source = tmp_path / "rows.tsv"
    source.write_text("id\tcount\n001\t2\n002\t3\n")
    assert main(args + ["load", str(source), "--name", "rows", "--key", "id", "--infer-types"]) == 0
    release = json.loads(capsys.readouterr().out)
    assert release["crs"] is None
    assert release["geometry_column"] is None
    catalog = Catalog(root)
    assert catalog.read("rows")["id"].to_pylist() == ["001", "002"]
    assert catalog.read("rows").schema.field("count").type == pa.int64()
    assert catalog.ingest(source, name="rows", key="id", infer_types=True)["unchanged"]
    monkeypatch.setenv("MOSES_DEFAULT_CRS", "EPSG:3857")
    assert catalog.ingest(source, name="rows", key="id", infer_types=True)["unchanged"]
    output = tmp_path / "output.parquet"
    assert main(args + ["export", "rows", str(output)]) == 0
    capsys.readouterr()
    assert pq.read_table(output).schema.field("count").type == pa.int64()


def test_crs_config_environment_explicit_and_embedded_precedence(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MOSES_DEFAULT_CRS", raising=False)
    root = tmp_path / "warehouse"
    args = ["-w", str(root)]
    assert main(args + ["init", "--default-crs", "EPSG:2263"]) == 0
    capsys.readouterr()
    source = tmp_path / "points.csv"
    source.write_text("id,x,y\n001,100,200\n")
    catalog = Catalog(root)
    first = catalog.ingest(source, name="points", x="x", y="y")
    assert first["crs"] == "EPSG:2263"
    assert first["crs_source"] == "default"
    assert first["options"]["default_crs"] == "EPSG:2263"
    monkeypatch.setenv("MOSES_DEFAULT_CRS", "EPSG:3857")
    assert catalog.ingest(source, name="points", x="x", y="y")["crs"] == "EPSG:3857"
    explicit = catalog.ingest(source, name="points", x="x", y="y", crs="EPSG:32618")
    assert explicit["crs"] == "EPSG:32618"
    assert explicit["crs_source"] == "explicit"
    assert main(args + ["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["crs"] == "EPSG:4326"


def test_legacy_ingestion_options_remain_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("MOSES_DEFAULT_CRS", raising=False)
    source = tmp_path / "records.csv"
    source.write_text("id\n001\n")
    release = Catalog(tmp_path / "warehouse").ingest(source, name="records")
    assert release["options"] == {"layer": None, "x": None, "y": None, "crs": None}


@pytest.mark.parametrize("first_infer", [False, True])
def test_parquet_noop_inference_does_not_create_version(tmp_path, monkeypatch, first_infer):
    monkeypatch.delenv("MOSES_DEFAULT_CRS", raising=False)
    source = tmp_path / "records.parquet"
    table = pa.table({"id": ["001"], "count": pa.array([2], type=pa.int32())})
    pq.write_table(table, source)
    catalog = Catalog(tmp_path / "warehouse")

    first = catalog.ingest(source, name="records", key="id", infer_types=first_infer)
    second = catalog.ingest(source, name="records", key="id", infer_types=not first_infer)

    assert second["unchanged"] is True
    assert second["version"] == first["version"]
    assert second["content_sha256"] == first["content_sha256"]
    assert "infer_types" not in first["options"]
    assert catalog.read("records", first["version"]).equals(table)
    assert len(catalog.history("records")) == 1
    assert len(catalog.observations("records")) == 2


@pytest.mark.parametrize("suffix,delimiter", [(".csv", ","), (".tsv", "\t")])
def test_tabular_inference_still_versions_changed_types(tmp_path, monkeypatch, suffix, delimiter):
    monkeypatch.delenv("MOSES_DEFAULT_CRS", raising=False)
    source = tmp_path / f"records{suffix}"
    source.write_text(f"id{delimiter}count\n001{delimiter}2\n")
    catalog = Catalog(tmp_path / "warehouse")
    first = catalog.ingest(source, name="records", key="id")
    locked = catalog.lock()

    inferred = catalog.ingest(source, name="records", key="id", infer_types=True)

    assert inferred["version"] != first["version"]
    assert inferred["options"]["infer_types"] is True
    assert catalog.read("records").schema.field("count").type == pa.int64()
    assert catalog.read("records", first["version"])["count"].to_pylist() == ["2"]
    assert catalog.query("SELECT count FROM records", versions=locked)["count"].to_pylist() == ["2"]
    assert catalog.read("records")["id"].to_pylist() == ["001"]
    assert catalog.ingest(source, name="records", key="id", infer_types=True)["unchanged"] is True
