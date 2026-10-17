import json
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import pytest
import shapely

from moses.ingest import read_vector


def _table():
    return pa.table(
        {
            "id": pa.array(["001", "002"], type=pa.string()),
            "wkb_geometry": pa.array(
                [shapely.to_wkb(shapely.Point(-73.9, 40.7)), shapely.to_wkb(shapely.Point(-73.8, 40.8))],
                type=pa.binary(),
            ),
        }
    )


def _write(path, *, layer="places", driver=None):
    kwargs = {"layer": layer, "geometry_name": "wkb_geometry", "geometry_type": "Point", "crs": "EPSG:4326"}
    if driver:
        kwargs["driver"] = driver
    pyogrio.write_arrow(_table(), path, **kwargs)


def test_csv_coordinate_ingest_keeps_ids_and_builds_wkb(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text("id,x,y\n001,-73.9,40.7\n002,,\n", encoding="utf-8")
    table, info = read_vector(path, x="x", y="y")
    assert table.schema.field("id").type == pa.string()
    assert table["id"].to_pylist() == ["001", "002"]
    assert table["geometry"].to_pylist()[1] is None
    assert info["crs"] == "EPSG:4326"
    geo = json.loads(table.schema.metadata[b"geo"])
    assert geo["version"] == "1.1.0"
    assert geo["columns"]["geometry"]["encoding"] == "WKB"
    assert geo["columns"]["geometry"]["crs"]["id"]["code"] == 4326


def test_csv_rejects_partial_or_malformed_coordinates(tmp_path):
    path = tmp_path / "points.csv"
    path.write_text("x,y\n1,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="partial missing"):
        read_vector(path, x="x", y="y")
    path.write_text("x,y\nnope,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        read_vector(path, x="x", y="y")


def test_plain_csv_has_no_geometry_and_requires_coordinate_pair(tmp_path):
    path = tmp_path / "attributes.csv"
    path.write_text("id,name\n001,One\n", encoding="utf-8")
    table, info = read_vector(path)
    assert table.column_names == ["id", "name"]
    assert info["geometry_column"] is None
    with pytest.raises(ValueError, match="together"):
        read_vector(path, x="id")
    with pytest.raises(ValueError, match="not applicable"):
        read_vector(path, layer="layer")


def test_unapproved_vector_drivers_and_vrt_are_rejected(tmp_path):
    vrt = tmp_path / "remote.vrt"
    vrt.write_text('<OGRVRTDataSource><OGRVRTLayer name="remote"><SrcDataSource>/vsicurl/https://example.invalid/data.geojson</SrcDataSource></OGRVRTLayer></OGRVRTDataSource>', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported vector source extension"):
        read_vector(vrt)

    disguised_json = tmp_path / "redirect.json"
    disguised_json.write_text('<OGRVRTDataSource><OGRVRTLayer name="remote"><SrcDataSource>/vsicurl/https://example.invalid/data.geojson</SrcDataSource></OGRVRTLayer></OGRVRTDataSource>', encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        read_vector(disguised_json)

    disguised_gpkg = tmp_path / "redirect.gpkg"
    disguised_gpkg.write_text('<OGRVRTDataSource><SrcDataSource>/vsicurl/https://example.invalid/data.geojson</SrcDataSource></OGRVRTDataSource>', encoding="utf-8")
    with pytest.raises(ValueError, match="SQLite header"):
        read_vector(disguised_gpkg)

    disguised_shp = tmp_path / "redirect.shp"
    disguised_shp.write_text('<OGRVRTDataSource><SrcDataSource>/vsicurl/https://example.invalid/data.geojson</SrcDataSource></OGRVRTDataSource>', encoding="utf-8")
    with pytest.raises(ValueError, match="Shapefile header"):
        read_vector(disguised_shp)


def test_zip_must_be_a_shapefile_bundle_without_vrt_or_other_drivers(tmp_path):
    bad = tmp_path / "mislabeled.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("data.gpkg", b"not a shapefile")
    with pytest.raises(ValueError, match="non-Shapefile"):
        read_vector(bad)

    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("places.shp", b"shape")
        archive.writestr("places.shx", b"index")
        archive.writestr("places.dbf", b"attributes")
        archive.writestr("remote.vrt", '<OGRVRTDataSource><SrcDataSource>/vsicurl/https://example.invalid/data.geojson</SrcDataSource></OGRVRTDataSource>')
    with pytest.raises(ValueError, match="VRT content"):
        read_vector(bad)

    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("places.shp", b"shape")
    with pytest.raises(ValueError, match="matching .shx and .dbf"):
        read_vector(bad)

    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("places.shp", b"<OGRVRTDataSource></OGRVRTDataSource>".ljust(100, b" "))
        archive.writestr("places.shx", b"index")
        archive.writestr("places.dbf", b"attributes")
    with pytest.raises(ValueError, match="Shapefile header"):
        read_vector(bad)


def test_geopackage_roundtrip_and_reject_ambiguous_layers(tmp_path):
    path = tmp_path / "places.gpkg"
    _write(path)
    table, info = read_vector(path)
    assert table.column_names == ["id", "geometry"]
    assert info["layer"] == "places"
    assert info["crs"] == "EPSG:4326"
    assert shapely.from_wkb(table["geometry"][0].as_py()).x == pytest.approx(-73.9)
    pyogrio.write_arrow(_table(), path, layer="other", geometry_name="wkb_geometry", geometry_type="Point", crs="EPSG:4326", append=True)
    with pytest.raises(ValueError, match="specify layer"):
        read_vector(path)
    assert read_vector(path, layer="other")[1]["layer"] == "other"


def test_geojson_roundtrip_and_geometry_name_fallback(tmp_path):
    path = tmp_path / "places.geojson"
    pyogrio.write_arrow(_table(), path, layer="places", geometry_name="wkb_geometry", geometry_type="Point", crs="EPSG:4326", driver="GeoJSON")
    table, info = read_vector(path)
    assert table.column_names == ["id", "geometry"]
    assert info["format"] == "GeoJSON"
    assert info["crs"] == "EPSG:4326"


def test_shapefile_includes_existing_companions_and_zip_reads(tmp_path):
    shp = tmp_path / "places.shp"
    _write(shp, driver="ESRI Shapefile")
    _, info = read_vector(shp)
    assert {p.rsplit("/", 1)[-1] for p in info["source_files"]} >= {"places.shp", "places.shx", "places.dbf", "places.prj"}
    archive = tmp_path / "places.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for child in tmp_path.glob("places.*"):
            if child != archive:
                zf.write(child, child.name)
    table, zipped = read_vector(archive)
    assert len(table) == 2
    assert zipped["source_files"] == [str(archive.resolve())]


def test_geoparquet_and_crs_conflict(tmp_path):
    gpkg = tmp_path / "places.gpkg"
    _write(gpkg)
    table, _ = read_vector(gpkg)
    parquet = tmp_path / "places.parquet"
    pq.write_table(table, parquet)
    loaded, info = read_vector(parquet)
    assert loaded.column_names == ["id", "geometry"]
    assert info["format"] == "GeoParquet"
    with pytest.raises(ValueError, match="conflicts"):
        read_vector(parquet, crs="EPSG:3857")


def test_geoparquet_crs_semantics_and_encoding_validation(tmp_path):
    geom = pa.array([shapely.to_wkb(shapely.Point(1, 2))], type=pa.binary())
    schema = pa.schema([("geometry", pa.binary())], metadata={
        b"geo": json.dumps({"version":"1.1.0", "primary_column":"geometry", "columns":{"geometry":{"encoding":"WKB", "geometry_types":["Point"]}}}).encode()
    })
    path = tmp_path / "default-crs.parquet"
    pq.write_table(pa.Table.from_arrays([geom], schema=schema), path)
    _, info = read_vector(path)
    assert info["crs"] == "OGC:CRS84"
    bad_schema = pa.schema([("geometry", pa.binary())], metadata={
        b"geo": json.dumps({"version":"1.1.0", "primary_column":"geometry", "columns":{"geometry":{"encoding":"point", "geometry_types":["Point"], "crs":None}}}).encode()
    })
    pq.write_table(pa.Table.from_arrays([geom], schema=bad_schema), path)
    with pytest.raises(ValueError, match="WKB"):
        read_vector(path)


@pytest.mark.parametrize(
    "column_metadata, message",
    [
        ({"encoding": "WKB", "geometry_types": ["Point"], "crs": None, "edges": "spherical"}, "planar"),
        ({"encoding": "WKB", "geometry_types": ["Point"], "crs": None, "epoch": 2020.5}, "epochs"),
    ],
)
def test_geoparquet_rejects_unpreserved_edge_and_epoch_semantics(tmp_path, column_metadata, message):
    geometry = pa.array([shapely.to_wkb(shapely.Point(1, 2))], type=pa.binary())
    schema = pa.schema([("geometry", pa.binary())], metadata={
        b"geo": json.dumps({"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": column_metadata}}).encode()
    })
    path = tmp_path / "special-semantics.parquet"
    pq.write_table(pa.Table.from_arrays([geometry], schema=schema), path)
    with pytest.raises(ValueError, match=message):
        read_vector(path)


def test_geoparquet_geometry_types_are_sorted_and_all_null_declaration_survives(tmp_path):
    metadata = {"version": "1.1.0", "primary_column": "geometry", "columns": {
        "geometry": {"encoding": "WKB", "geometry_types": ["Polygon Z", "Point"], "crs": None}
    }}
    wkb = [shapely.to_wkb(shapely.Point(1, 2)), shapely.to_wkb(shapely.LineString([(0, 0), (1, 1)]))]
    outputs = []
    for index, values in enumerate((wkb, list(reversed(wkb)))):
        path = tmp_path / f"order-{index}.parquet"
        schema = pa.schema([("geometry", pa.binary())], metadata={b"geo": json.dumps(metadata).encode()})
        pq.write_table(pa.Table.from_arrays([pa.array(values, type=pa.binary())], schema=schema), path)
        table, _ = read_vector(path)
        outputs.append(json.loads(table.schema.metadata[b"geo"])["columns"]["geometry"]["geometry_types"])
    assert outputs == [["LineString", "Point"], ["LineString", "Point"]]

    path = tmp_path / "all-null.parquet"
    schema = pa.schema([("geometry", pa.binary())], metadata={b"geo": json.dumps(metadata).encode()})
    pq.write_table(pa.Table.from_arrays([pa.array([None, None], type=pa.binary())], schema=schema), path)
    table, _ = read_vector(path)
    assert json.loads(table.schema.metadata[b"geo"])["columns"]["geometry"]["geometry_types"] == ["Point", "Polygon Z"]


def test_wkb_output_uses_iso_z_encoding_and_rejects_m(tmp_path):
    schema = pa.schema([("geometry", pa.binary())], metadata={
        b"geo": json.dumps({"version": "1.1.0", "primary_column": "geometry", "columns": {
            "geometry": {"encoding": "WKB", "geometry_types": ["Point Z"], "crs": None}
        }}).encode()
    })
    z_path = tmp_path / "z.parquet"
    ewkb_z = shapely.to_wkb(shapely.Point(1, 2, 3))
    pq.write_table(pa.Table.from_arrays([pa.array([ewkb_z], type=pa.binary())], schema=schema), z_path)
    table, _ = read_vector(z_path)
    output_wkb = table["geometry"][0].as_py()
    assert int.from_bytes(output_wkb[1:5], "little") == 1001

    m_path = tmp_path / "m.parquet"
    measured = shapely.to_wkb(shapely.from_wkt("POINT M (1 2 3)"), flavor="iso")
    pq.write_table(pa.Table.from_arrays([pa.array([measured], type=pa.binary())], schema=schema), m_path)
    with pytest.raises(ValueError, match=r"measured \(M\)"):
        read_vector(m_path)


def test_geoparquet_rejects_invalid_declared_types_and_nonbinary_storage(tmp_path):
    path = tmp_path / "invalid-types.parquet"
    metadata = {"version": "1.1.0", "primary_column": "geometry", "columns": {
        "geometry": {"encoding": "WKB", "geometry_types": ["Point M"], "crs": None}
    }}
    schema = pa.schema([("geometry", pa.binary())], metadata={b"geo": json.dumps(metadata).encode()})
    pq.write_table(pa.Table.from_arrays([pa.array([None], type=pa.binary())], schema=schema), path)
    with pytest.raises(ValueError, match="geometry_types"):
        read_vector(path)

    metadata["columns"]["geometry"]["geometry_types"] = ["Point"]
    schema = pa.schema([("geometry", pa.string())], metadata={b"geo": json.dumps(metadata).encode()})
    pq.write_table(pa.Table.from_arrays([pa.array([None], type=pa.string())], schema=schema), path)
    with pytest.raises(ValueError, match="binary storage"):
        read_vector(path)


def test_invalid_geometry_is_rejected(tmp_path):
    table = pa.table({"geometry": pa.array([b"not-wkb"], type=pa.binary())})
    # GeoParquet metadata enables the reader to reach WKB validation.
    schema = table.schema.with_metadata({b"geo": json.dumps({"version":"1.1.0", "primary_column":"geometry", "columns":{"geometry":{"encoding":"WKB", "geometry_types":[], "crs":None}}}).encode()})
    pq.write_table(pa.Table.from_arrays([table["geometry"]], schema=schema), tmp_path / "bad-geoparquet.parquet")
    with pytest.raises(ValueError, match="malformed WKB"):
        read_vector(tmp_path / "bad-geoparquet.parquet")

