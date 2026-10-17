import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely

from moses.ingest import read_vector


def test_tsv_preserves_text_and_delimited_values(tmp_path):
    path = tmp_path / "records.tsv"
    path.write_text('id\tlabel\tblank\n001\t"one, two"\t\n', encoding="utf-8")

    table, meta = read_vector(path)

    assert meta["format"] == "TSV"
    assert table.column_names == ["id", "label", "blank"]
    assert table["id"].to_pylist() == ["001"]
    assert table["label"].to_pylist() == ["one, two"]
    assert table["blank"].to_pylist() == [""]
    assert meta["warnings"] == []


@pytest.mark.parametrize("header, message", [("id,id", "duplicate"), ("id,", "empty")])
def test_tabular_rejects_duplicate_and_empty_column_names(tmp_path, header, message):
    path = tmp_path / "bad.csv"
    path.write_text(f"{header}\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_vector(path)


def test_inference_is_opt_in_conservative_and_full_column(tmp_path):
    path = tmp_path / "values.csv"
    path.write_text(
        "flag,count,amount,identifier,float_identifier,mixed,date,empty\n"
        "true,1,1.25,001,001.25,2,2024-01-01,\n"
        "false,2,2e1,002,002.5,two,2024-01-02,\n",
        encoding="utf-8",
    )
    default, _ = read_vector(path)
    inferred, _ = read_vector(path, infer_types=True)

    assert all(pa.types.is_string(field.type) for field in default.schema)
    assert inferred.schema.field("flag").type == pa.bool_()
    assert inferred.schema.field("count").type == pa.int64()
    assert inferred.schema.field("amount").type == pa.float64()
    for name in ("identifier", "float_identifier", "mixed", "date", "empty"):
        assert inferred.schema.field(name).type == pa.string()
    assert inferred["identifier"].to_pylist() == ["001", "002"]
    assert inferred["float_identifier"].to_pylist() == ["001.25", "002.5"]
    assert inferred["empty"].to_pylist() == ["", ""]


@pytest.mark.parametrize("value", [
    "9223372036854775808", "1,not-an-int", "1e-999", "9007199254740993.0"
])
def test_failed_or_unsafe_inference_keeps_text(tmp_path, value):
    path = tmp_path / "unsafe.csv"
    if "," in value:
        path.write_text("value\n1\nnot-an-int\n", encoding="utf-8")
        expected = ["1", "not-an-int"]
    else:
        path.write_text(f"value\n{value}\n", encoding="utf-8")
        expected = [value]
    table, _ = read_vector(path, infer_types=True)
    assert table.schema.field("value").type == pa.string()
    assert table["value"].to_pylist() == expected


def test_plain_parquet_preserves_native_schema_without_geometry_guess(tmp_path):
    path = tmp_path / "attributes.parquet"
    source = pa.table({
        "geometry": pa.array(["opaque"], type=pa.string()),
        "id": pa.array([7], type=pa.int32()),
    })
    pq.write_table(source, path)

    table, meta = read_vector(path)

    assert table.schema == source.schema
    assert table.to_pylist() == source.to_pylist()
    assert meta["format"] == "Parquet"
    assert meta["geometry_column"] is None
    assert meta["crs"] is None
    assert meta["crs_source"] is None
    assert read_vector(path, default_crs="EPSG:4326")[1]["crs"] is None
    with pytest.raises(ValueError, match="geometry column"):
        read_vector(path, crs="EPSG:4326")


def test_default_crs_is_ignored_for_nonspatial_csv(tmp_path):
    path = tmp_path / "attributes.csv"
    path.write_text("id\n001\n", encoding="utf-8")
    table, meta = read_vector(path, default_crs="EPSG:4326")
    assert table.column_names == ["id"]
    assert meta["crs"] is None
    assert meta["crs_source"] is None
    assert meta["warnings"] == []


def _write_geoparquet(path, crs):
    geo = {
        "version": "1.1.0",
        "primary_column": "geom_wkb",
        "columns": {"geom_wkb": {"encoding": "WKB", "geometry_types": ["Point"], "crs": crs}},
    }
    schema = pa.schema(
        [("geom_wkb", pa.binary()), ("id", pa.string())],
        metadata={b"geo": json.dumps(geo).encode()},
    )
    table = pa.Table.from_arrays(
        [pa.array([shapely.to_wkb(shapely.Point(1, 2))], type=pa.binary()), pa.array(["001"])],
        schema=schema,
    )
    pq.write_table(table, path)


def test_crs_precedence_source_explicit_default_and_csv_fallback(tmp_path):
    geo_path = tmp_path / "source.parquet"
    _write_geoparquet(geo_path, "EPSG:3857")
    _, source_meta = read_vector(geo_path, default_crs="EPSG:4326")
    assert source_meta["crs"] == "EPSG:3857"
    assert source_meta["crs_source"] == "source"
    with pytest.raises(ValueError, match="conflicts"):
        read_vector(geo_path, crs="EPSG:4326")

    unknown_path = tmp_path / "unknown.parquet"
    _write_geoparquet(unknown_path, None)
    _, default_meta = read_vector(unknown_path, default_crs="EPSG:4326")
    assert default_meta["crs"] == "EPSG:4326"
    assert default_meta["crs_source"] == "default"
    _, explicit_meta = read_vector(unknown_path, crs="EPSG:32618", default_crs="EPSG:4326")
    assert explicit_meta["crs"] == "EPSG:32618"
    assert explicit_meta["crs_source"] == "explicit"

    _, unknown_meta = read_vector(unknown_path)
    assert unknown_meta["crs"] is None
    assert unknown_meta["crs_source"] == "unknown"
    assert read_vector(unknown_path, default_crs="EPSG:4326")[1]["warnings"]

    csv_path = tmp_path / "points.csv"
    csv_path.write_text("x,y\n-73.9,40.7\n", encoding="utf-8")
    _, fallback_meta = read_vector(csv_path, x="x", y="y")
    assert fallback_meta["crs"] == "EPSG:4326"
    assert fallback_meta["crs_source"] == "legacy_csv_default"
    assert fallback_meta["warnings"]
