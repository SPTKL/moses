import json
from pathlib import Path
import zipfile

import pyarrow.parquet as pq
import pytest

from moses.pluto.raw_normalize import RawNormalizationError, normalize_raw


EXTENSIONS = Path(__file__).parents[1] / ".extensions"
pytestmark = pytest.mark.skipif(not list(EXTENSIONS.glob("*/**/spatial.duckdb_extension")), reason="requires installed local DuckDB spatial extension")


def test_csv_projection_explicit_names_keeps_raw_duplicates(tmp_path):
    source = tmp_path / "source.tsv"
    source.write_text("discard\t1\t00001\t0010\nother\t1\t00001\t0010\n")
    config = {"id": "fixture", "file_format": {"type": "csv", "delimiter": "\t", "names": ["boro", "block", "lot"], "usecols": [1, 2, 3], "dtype": "str"},
              "processing_steps": [{"name": "deduplicate"}, {"name": "geocode_bbl"}, {"name": "convert_to_geometry"}]}
    output = tmp_path / "output.parquet"
    report = normalize_raw(source, config, output, extension_directory=EXTENSIONS)
    assert report["rows"] == 2
    assert pq.read_table(output).to_pylist() == [{"boro": "1", "block": "00001", "lot": "0010"}] * 2
    assert report["normalization_pending"]
    assert len(report["recipe_steps_pending"]) == 4


def test_csv_dates_nulls_and_geometry_use_duckdb(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text('ID,date,x,y,empty\n001,11/30/1999 0:00:00.000,-74,40,""\n002,bad,,,\n')
    config = {"id": "fixture", "file_format": {"type": "csv", "dtype": "str", "geometry": {"crs": "EPSG:4326", "geom_column": {"x": "x", "y": "y"}}},
              "processing_steps": [{"name": "clean_column_names", "args": {"lower": True}}, {"name": "coerce_column_types", "args": {"column_types": {"date": "date"}, "errors": "coerce"}}]}
    output = tmp_path / "output.parquet"
    report = normalize_raw(source, config, output, extension_directory=EXTENSIONS)
    table = pq.read_table(output)
    assert table["id"].to_pylist() == ["001", "002"]
    assert [str(value) for value in table["date"].to_pylist()] == ["1999-11-30", "None"]
    assert table["empty"].to_pylist() == ["", None]
    assert table["wkb_geometry"].null_count == 1
    assert json.loads(table.schema.metadata[b"geo"])["primary_column"] == "wkb_geometry"
    assert report["geometry_status"] == "valid_spatial"
    assert report["transform_engine"] == "DuckDB SELECT and COPY only"
    assert report["normalization_pending"]
    assert report["csv_null_policy"]["upstream_pandas_compatibility"] == "not_proven"


def test_string_dtype_does_not_imply_pandas_null_policy_parity(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text('id,value\n001,NA\n002,""\n003,\n')
    output = tmp_path / "output.parquet"
    report = normalize_raw(source, {"id": "fixture", "file_format": {"type": "csv", "dtype": "str"}}, output, extension_directory=EXTENSIONS)
    assert pq.read_table(output)["value"].to_pylist() == ["NA", "", None]
    assert report["normalization_pending"]
    assert [step["name"] for step in report["recipe_steps_pending"]] == ["csv_null_policy_compatibility"]


def test_invalid_geojson_geometry_is_raw_blob_without_spatial_metadata(tmp_path):
    source = tmp_path / "source.geojson"
    source.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": "001"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]}}]}))
    output = tmp_path / "output.parquet"
    report = normalize_raw(source, {"id": "fixture", "file_format": {"type": "geojson"}}, output, extension_directory=EXTENSIONS)
    table = pq.read_table(output)
    assert report["rows"] == report["invalid_geometries"] == 1
    assert report["geometry_status"] == "raw_invalid_topology"
    assert b"geo" not in (table.schema.metadata or {})
    assert json.loads(table.schema.metadata[b"moses_raw_geometry"])["status"] == "raw_invalid_topology"
    assert table["wkb_geometry"][0].as_py()


def test_zip_traversal_and_unsupported_format_preserve_output(tmp_path):
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../escape.csv", "id\n001\n")
    output = tmp_path / "output.parquet"
    output.write_bytes(b"previous")
    with pytest.raises(RawNormalizationError, match="Unsafe ZIP"):
        normalize_raw(source, {"id": "fixture", "file_format": {"type": "csv"}}, output, extension_directory=EXTENSIONS)
    assert output.read_bytes() == b"previous"
    with pytest.raises(RawNormalizationError, match="Unsupported"):
        normalize_raw(source, {"id": "fixture", "file_format": {"type": "spreadsheet"}}, output, extension_directory=EXTENSIONS)
