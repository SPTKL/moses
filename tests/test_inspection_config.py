import json
from datetime import date
from decimal import Decimal

import pyarrow as pa
import pytest

from moses.config import load_config, resolve_default_crs, set_default_crs
from moses.inspection import inspect_source


def test_inspection_reports_entire_csv_but_bounds_preview_and_does_not_write(tmp_path):
    source = tmp_path / "points.csv"
    source.write_text("id,longitude,latitude\n" + "".join(f"{i:03d},-73.9,40.7\n" for i in range(125)), encoding="utf-8")
    result = inspect_source(source, preview_rows=3)
    assert result["format"] == "CSV"
    assert result["detection"]["method"] == "filename_suffix"
    assert result["detection"]["suffix"] == ".csv"
    assert ".tsv" in result["detection"]["supported_suffixes"]
    assert result["scan"] == "full_file"
    assert result["row_count"] == 125
    assert len(result["preview"]) == 3
    assert result["preview"][0]["id"] == "000"
    assert result["geometry_column"] is None
    assert result["coordinate_candidates"] == [{"x": "longitude", "y": "latitude"}]
    assert any("suggestions only" in warning for warning in result["warnings"])
    assert not (tmp_path / "config.json").exists()
    assert len(list(tmp_path.iterdir())) == 1


def test_inspection_json_safes_dates_decimals_binary_and_nonfinite(monkeypatch, tmp_path):
    table = pa.table({
        "when": pa.array([date(2024, 2, 3)], type=pa.date32()),
        "amount": pa.array([Decimal("12.340")], type=pa.decimal128(8, 3)),
        "blob": pa.array([b"\x00\xff"], type=pa.binary()),
        "measure": pa.array([float("inf")], type=pa.float64()),
    })
    monkeypatch.setattr(
        "moses.inspection.read_vector",
        lambda *args, **kwargs: (table, {"format": "CSV", "crs": None, "crs_source": None, "geometry_column": None, "warnings": [], "layer": None}),
    )
    result = inspect_source(tmp_path / "fake.csv")
    assert result["preview"] == [{
        "when": "2024-02-03", "amount": "12.340", "blob": "0x00ff", "measure": "Infinity",
    }]
    assert json.loads(json.dumps(result)) == result
    assert result["schema"] == [
        {"name": "when", "type": "date32[day]", "nullable": True},
        {"name": "amount", "type": "decimal128(8, 3)", "nullable": True},
        {"name": "blob", "type": "binary", "nullable": True},
        {"name": "measure", "type": "double", "nullable": True},
    ]


@pytest.mark.parametrize("value", [-1, 101, True, 1.2])
def test_inspection_validates_preview_bound(value, tmp_path):
    with pytest.raises(ValueError, match="preview_rows"):
        inspect_source(tmp_path / "anything.csv", preview_rows=value)


def test_config_load_set_and_preserve_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"future_option": {"enabled": true}, "default_crs": "EPSG:3857"}\n', encoding="utf-8")
    loaded = load_config(tmp_path)
    assert loaded["default_crs"] == "EPSG:3857"
    updated = set_default_crs(tmp_path, "urn:ogc:def:crs:EPSG::4326")
    assert updated == {"future_option": {"enabled": True}, "default_crs": "EPSG:4326"}
    assert json.loads(path.read_text(encoding="utf-8")) == updated
    assert resolve_default_crs(tmp_path) == "EPSG:4326"
    assert not list(tmp_path.glob("*.tmp"))


def test_config_environment_precedence_and_empty_value(tmp_path, monkeypatch):
    set_default_crs(tmp_path, "EPSG:3857")
    monkeypatch.setenv("MOSES_DEFAULT_CRS", "  EPSG:2263 ")
    assert resolve_default_crs(tmp_path) == "EPSG:2263"
    monkeypatch.setenv("MOSES_DEFAULT_CRS", "   ")
    assert resolve_default_crs(tmp_path) == "EPSG:3857"


def test_config_invalid_crs_and_invalid_config_fail_without_overwrite(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    with pytest.raises(ValueError, match="invalid default CRS"):
        set_default_crs(tmp_path, "not-a-crs")
    assert not path.exists()
    monkeypatch.setenv("MOSES_DEFAULT_CRS", "not-a-crs")
    with pytest.raises(ValueError, match="MOSES_DEFAULT_CRS"):
        resolve_default_crs(tmp_path)
    monkeypatch.delenv("MOSES_DEFAULT_CRS")

    path.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="could not read Moses config"):
        load_config(tmp_path)
    path.write_text('{"default_crs": "bogus"}', encoding="utf-8")
    with pytest.raises(ValueError, match="stored default CRS"):
        load_config(tmp_path)
