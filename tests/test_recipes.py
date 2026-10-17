import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely

from moses.catalog import Catalog
from moses.cli import main
from moses.ingest import read_vector
from moses.inspection import inspect_source


def test_primitive_types_validate_all_rows_and_keep_default_text(tmp_path):
    source = tmp_path / "records.csv"
    source.write_text("id,count,enabled,amount\n001,1,true,1.25\n002,2,false,2.5\n", encoding="utf-8")
    default, _ = read_vector(source)
    assert default["id"].to_pylist() == ["001", "002"]
    assert default.schema.field("id").type == pa.string()

    table, _ = read_vector(source, infer_types=True, types={"id": "string", "count": "integer", "enabled": "boolean", "amount": "float"})
    assert table["id"].to_pylist() == ["001", "002"]
    assert table.schema.field("count").type == pa.int64()
    assert table["enabled"].to_pylist() == [True, False]
    assert table["amount"].to_pylist() == [1.25, 2.5]

    source.write_text("id,count\n001,1\n002,2\n003,broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="field 'count' at row 4"):
        read_vector(source, types={"count": "int64"})
    with pytest.raises(ValueError, match="field 'count' at row 4"):
        inspect_source(source, preview_rows=1, types={"count": "int64"})
    with pytest.raises(ValueError, match="does not exist"):
        read_vector(source, types={"missing": "int64"})
    with pytest.raises(ValueError, match="unsupported type"):
        read_vector(source, types={"count": "date"})


def test_primitive_override_rejects_overflow_fraction_and_nonfinite(tmp_path):
    source = tmp_path / "values.csv"
    for value, type_name in [("9223372036854775808", "int64"), ("1.5", "int64"), ("NaN", "float64"), ("1e999", "float64")]:
        source.write_text(f"value\n{value}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="field 'value' at row 2"):
            read_vector(source, types={"value": type_name})
    source.write_text("value,other\n,foo\n3,bar\n", encoding="utf-8")
    table, _ = read_vector(source, types={"value": "int64"})
    assert table["value"].to_pylist() == [None, 3]


def test_signatures_reject_mismatch_and_explicit_reader_is_allowlisted(tmp_path):
    source = tmp_path / "misnamed.csv"
    source.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":"001"},"geometry":{"type":"Point","coordinates":[1,2]}}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="content signature"):
        read_vector(source)
    _, metadata = read_vector(source, format="GeoJSON")
    assert metadata["format"] == "GeoJSON"
    inspected = inspect_source(source, format="GeoJSON")
    assert inspected["detection"]["method"] == "explicit_format"
    catalog = Catalog(tmp_path / "warehouse")
    accepted = catalog.ingest(source, name="misnamed", key="id", format="GeoJSON")
    assert accepted["recipe"]["format"] == "GeoJSON"
    assert catalog.ingest(source, name="misnamed", key="id", format="GeoJSON")["unchanged"] is True
    with pytest.raises(ValueError, match="unsupported format"):
        read_vector(source, format="VRT")

    parquet = tmp_path / "disguised.csv"
    parquet.write_bytes(b"PAR1payloadPAR1")
    with pytest.raises(ValueError, match="content signature"):
        read_vector(parquet)


def test_version_recipe_tracks_effective_choices_and_noop(tmp_path):
    source = tmp_path / "points.csv"
    source.write_text("id,x,y,count\n001,-73.9,40.7,1\n", encoding="utf-8")
    catalog = Catalog(tmp_path / "warehouse")
    first = catalog.ingest(source, name="points", key="id", x="x", y="y", types={"count": "integer"})
    recipe = first["recipe"]
    assert recipe == {
        "version": 1,
        "format": "CSV",
        "layer": None,
        "coordinates": {"x": "x", "y": "y"},
        "types": {"count": "int64"},
        "type_blank_policy": "empty_to_null_for_non_string_overrides",
        "infer_types": False,
        "crs": {"value": "EPSG:4326", "source": "legacy_csv_default"},
    }
    assert first["options"]["types"] == {"count": "int64"}
    same = catalog.ingest(source, name="points", key="id", x="x", y="y", types={"count": "int64"}, format="CSV")
    assert same["unchanged"] is True
    assert same["version"] == first["version"]
    assert catalog.get_version("points")["recipe"] == recipe

    source.write_text("id,x,y,count\n001,-73.9,40.7,bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="field 'count' at row 2"):
        catalog.ingest(source, name="points", key="id", x="x", y="y", types={"count": "int64"})
    assert catalog.get_version("points")["version"] == first["version"]


def test_cli_type_options_and_recipe(tmp_path, capsys):
    source = tmp_path / "values.tsv"
    source.write_text("id\tcount\n001\t2\n", encoding="utf-8")
    warehouse = tmp_path / "warehouse"
    assert main(["-w", str(warehouse), "load", str(source), "--name", "values", "--type", "count=int64"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["recipe"]["types"] == {"count": "int64"}
    assert main(["-w", str(warehouse), "inspect", str(source), "--type", "count=int64"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["schema"][1]["type"] == "int64"
    assert main(["-w", str(warehouse), "inspect", str(source), "--type", "count=date"]) == 1
    assert "unsupported type" in capsys.readouterr().err


def test_effective_reader_controls_inference_and_recipe_identity(tmp_path):
    disguised_csv = tmp_path / "values.bin"
    disguised_csv.write_text("id,count\n001,2\n", encoding="utf-8")
    catalog = Catalog(tmp_path / "warehouse")
    inspected = inspect_source(disguised_csv, format="csv", infer_types=True)
    assert inspected["schema"][1]["type"] == "int64"
    accepted = catalog.ingest(disguised_csv, name="values", key="id", format="csv", infer_types=True)
    assert accepted["recipe"]["infer_types"] is True
    assert accepted["options"]["infer_types"] is True
    assert catalog.read("values").schema.field("count").type == pa.int64()
    assert catalog.ingest(disguised_csv, name="values", key="id", format="CSV", infer_types=True)["unchanged"] is True

    disguised_geojson = tmp_path / "point.csv"
    disguised_geojson.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":"001"},"geometry":{"type":"Point","coordinates":[1,2]}}]}', encoding="utf-8")
    first = catalog.ingest(disguised_geojson, name="point", key="id", format="geojson")
    same = catalog.ingest(disguised_geojson, name="point", key="id", format="geojson", infer_types=True)
    assert same["unchanged"] is True
    assert same["version"] == first["version"]
    assert first["recipe"]["infer_types"] is False


def test_nonspatial_geometry_field_can_receive_primitive_override(tmp_path):
    source = tmp_path / "attributes.csv"
    source.write_text("id,geometry\n001,7\n", encoding="utf-8")
    table, metadata = read_vector(source, types={"geometry": "int64"})
    assert metadata["geometry_column"] is None
    assert table["geometry"].to_pylist() == [7]

    parquet = tmp_path / "attributes.parquet"
    pq.write_table(pa.table({"geometry": ["7"]}), parquet)
    table, metadata = read_vector(parquet, types={"geometry": "int64"})
    assert metadata["geometry_column"] is None
    assert table["geometry"].to_pylist() == [7]

    spatial = tmp_path / "points.parquet"
    geo = {"version": "1.1.0", "primary_column": "geometry",
           "columns": {"geometry": {"encoding": "WKB", "geometry_types": ["Point"], "crs": None}}}
    pq.write_table(pa.table({"geometry": pa.array([shapely.to_wkb(shapely.Point(1, 2))], type=pa.binary())})
                   .replace_schema_metadata({b"geo": json.dumps(geo).encode()}), spatial)
    with pytest.raises(ValueError, match="geometry cannot receive"):
        read_vector(spatial, types={"geometry": "int64"})
