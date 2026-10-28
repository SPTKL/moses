"""FileGDB import contracts using small, locally generated geodatabases."""

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import shutil
import stat
import zipfile
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import pytest
import shapely

from moses.catalog import Catalog
from moses.cli import main
from moses.ingest import read_vector
from moses.source_recipes import prepare_recipe
from moses.destinations.s3 import S3Publisher


@pytest.fixture
def geodatabase(tmp_path):
    if pyogrio.list_drivers().get("OpenFileGDB") not in {"rw", "raw"}:
        pytest.skip("This GDAL build cannot write OpenFileGDB fixtures")
    path = tmp_path / "places.gdb"
    table = pa.table({
        "id": pa.array(["001", "002"], type=pa.string()),
        "amount": pa.array([7, None], type=pa.int64()),
        "day": pa.array([date(2024, 1, 2), None], type=pa.date32()),
        "wkb_geometry": pa.array([
            shapely.to_wkb(shapely.Point(1000, 2000)),
            shapely.to_wkb(shapely.Point(3000, 4000)),
        ], type=pa.binary()),
    })
    pyogrio.write_arrow(
        table, path, layer="places", driver="OpenFileGDB",
        geometry_name="wkb_geometry", geometry_type="Point", crs="EPSG:2263",
        layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"},
    )
    return path


def _add_other_layer(path):
    table = pa.table({
        "id": ["other"],
        "wkb_geometry": pa.array([shapely.to_wkb(shapely.Point(5, 6))], type=pa.binary()),
    })
    pyogrio.write_arrow(
        table, path, layer="other", driver="OpenFileGDB", append=True,
        geometry_name="wkb_geometry", geometry_type="Point", crs="EPSG:2263",
    )


@pytest.fixture
def nonspatial_geodatabase(tmp_path):
    if pyogrio.list_drivers().get("OpenFileGDB") not in {"rw", "raw"}:
        pytest.skip("This GDAL build cannot write OpenFileGDB fixtures")
    path = tmp_path / "tables.gdb"
    table = pa.table({
        "id": pa.array(["001", "002"], type=pa.string()),
        "amount": pa.array([7, None], type=pa.int64()),
        "day": pa.array([date(2024, 1, 2), None], type=pa.date32()),
    })
    pyogrio.write_arrow(table, path, layer="records", driver="OpenFileGDB",
                        layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    return path


def _zip_gdb(path, archive, *, prefix=None):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        for member in sorted(path.rglob("*")):
            if member.is_file():
                output.write(member, Path(prefix or path.name) / member.relative_to(path))
    return archive


def test_directory_reader_preserves_layer_types_crs_and_geometry(geodatabase):
    table, info = read_vector(geodatabase, format="filegdb")
    assert info["format"] == "FileGDB"
    assert info["layer"] == "places"
    assert info["crs"] == "EPSG:2263"
    assert table["id"].to_pylist() == ["001", "002"]
    assert table.schema.field("id").type == pa.string()
    assert table["amount"].to_pylist() == [7, None]
    assert table.schema.field("amount").type == pa.int64()
    assert table["day"].to_pylist() == [date(2024, 1, 2), None]
    assert table.schema.field("day").type == pa.date32()
    assert table.column_names[-1] == "geometry"
    point = shapely.from_wkb(table["geometry"][0].as_py())
    assert point.x == pytest.approx(1000, abs=0.01)
    assert point.y == pytest.approx(2000, abs=0.01)
    geo = json.loads(table.schema.metadata[b"geo"])
    assert geo["columns"]["geometry"]["crs"]["id"]["code"] == 2263


def test_nonspatial_filegdb_table_reads_and_exports_without_geometry(nonspatial_geodatabase, tmp_path, capsys):
    table, info = read_vector(nonspatial_geodatabase)
    assert info["format"] == "FileGDB"
    assert info["layer"] == "records"
    assert info["geometry_column"] is None
    assert info["crs"] is None
    assert table.column_names == ["id", "amount", "day"]
    assert table["id"].to_pylist() == ["001", "002"]
    assert table["amount"].to_pylist() == [7, None]
    assert table["day"].to_pylist() == [date(2024, 1, 2), None]

    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(nonspatial_geodatabase, name="records", key="id")
    assert manifest["geometry_column"] is None
    destination = tmp_path / "records.gdb"
    assert main(["-w", str(catalog.root), "export", "records", str(destination),
                 "--version", manifest["version"], "--format", "FileGDB", "--layer", "exported_records"]) == 0
    capsys.readouterr()
    assert pyogrio.list_layers(destination).tolist() == [["exported_records", None]]
    exported_info, exported = pyogrio.read_arrow(destination, layer="exported_records")
    assert exported_info["geometry_type"] is None
    assert exported.column_names == ["id", "amount", "day"]
    assert exported["id"].to_pylist() == ["001", "002"]
    assert exported["amount"].to_pylist() == [7, None]
    assert exported["day"].to_pylist() == [date(2024, 1, 2), None]


def test_two_spatial_layers_require_explicit_selection(geodatabase):
    _add_other_layer(geodatabase)
    with pytest.raises(ValueError, match="(?i)layer"):
        read_vector(geodatabase)
    table, info = read_vector(geodatabase, layer="other")
    assert info["layer"] == "other"
    assert table["id"].to_pylist() == ["other"]


def test_directory_capture_is_complete_and_repeat_does_not_publish_new_version(geodatabase, tmp_path):
    (geodatabase / "empty-support-directory").mkdir()
    source_table = pyogrio.read_arrow(geodatabase, layer="places")[1]
    original = {member.relative_to(geodatabase): member.read_bytes()
                for member in geodatabase.rglob("*") if member.is_file()}
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(geodatabase, name="places", key="id")
    assert manifest["format"] == "FileGDB"
    assert len(manifest["raw_files"]) == len(original)
    captured = {Path(path).relative_to(catalog.root / "raw" / manifest["source_sha256"] / geodatabase.name): Path(path).read_bytes()
                for path in manifest["raw_files"]}
    assert captured == original
    assert (catalog.root / "raw" / manifest["source_sha256"] / geodatabase.name / "empty-support-directory").is_dir()
    shutil.rmtree(geodatabase)
    accepted = catalog.read("places")
    for field in ("id", "amount", "day"):
        assert accepted[field].to_pylist() == source_table[field].to_pylist()
        assert accepted.schema.field(field).type == source_table.schema.field(field).type
    assert [shapely.from_wkb(value.as_py()).wkt for value in accepted["geometry"]] == [
        shapely.from_wkb(value.as_py()).wkt for value in source_table["SHAPE"]
    ]
    assert all(Path(path).is_file() for path in manifest["raw_files"])

    restored = tmp_path / "places.gdb"
    for relative, data in original.items():
        target = restored / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    again = catalog.ingest(restored, name="places", key="id")
    assert again["unchanged"] is True
    assert again["version"] == manifest["version"]
    assert len(catalog.history("places")) == 1
    assert len(catalog.observations("places")) == 2


def test_zipped_filegdb_imports_and_keeps_original_archive(geodatabase, tmp_path):
    archive = _zip_gdb(geodatabase, tmp_path / "places.gdb.zip")
    table, info = read_vector(archive)
    assert table["id"].to_pylist() == ["001", "002"]
    assert info["format"] == "FileGDB"
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(archive, name="places", key="id")
    assert any(Path(path).read_bytes() == archive.read_bytes() for path in manifest["raw_files"])
    archive.unlink()
    assert catalog.read("places")["id"].to_pylist() == ["001", "002"]


def test_unsafe_directory_symlink_and_invalid_zip_do_not_publish(geodatabase, tmp_path):
    catalog = Catalog(tmp_path / "warehouse")
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    link = geodatabase / "outside.gdbtable"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        catalog.ingest(geodatabase, name="places")
    link.unlink()
    assert catalog.datasets() == []

    valid = _zip_gdb(geodatabase, tmp_path / "bad.gdb.zip")
    with zipfile.ZipFile(valid, "a") as output:
        output.writestr("../escape.txt", "unsafe")
    with pytest.raises(ValueError):
        catalog.ingest(valid, name="places")
    assert catalog.datasets() == []

    ambiguous = tmp_path / "ambiguous.gdb.zip"
    with zipfile.ZipFile(ambiguous, "w") as output:
        output.writestr("first.gdb/a00000001.gdbtable", b"a")
        output.writestr("second.gdb/a00000001.gdbtable", b"b")
    with pytest.raises(ValueError):
        catalog.ingest(ambiguous, name="places")
    assert catalog.datasets() == []


def test_zipped_filegdb_rejects_symlink_member(geodatabase, tmp_path):
    archive = _zip_gdb(geodatabase, tmp_path / "links.gdb.zip")
    symlink = zipfile.ZipInfo("places.gdb/linked.gdbtable")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(symlink, "../../outside")
    with pytest.raises(ValueError):
        read_vector(archive)


def test_zipped_filegdb_rejects_extreme_compression_before_loading(geodatabase, tmp_path):
    archive = _zip_gdb(geodatabase, tmp_path / "compressed.gdb.zip")
    with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("places.gdb/huge.gdbtable", b"\0" * (4 * 1024 * 1024))
    with pytest.raises(ValueError, match="(?i)compression|limit"):
        read_vector(archive)


def test_s3_publication_keeps_complete_filegdb_member_paths(geodatabase, tmp_path, monkeypatch):
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(geodatabase, name="places", key="id")
    objects = {}

    def record_object(self, key, body, content_type):
        objects[key] = body
        return {"uri": f"s3://example/{key}", "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}

    monkeypatch.setattr(S3Publisher, "_put_immutable", record_object)
    S3Publisher("example", client=object()).publish(catalog, "places")
    assert list(objects)[-1].endswith("manifest.json")
    remote = json.loads(objects[list(objects)[-1]])
    remote_raw = remote["objects"]["raw"]
    assert len(remote_raw) == len(manifest["raw_files"])
    assert all("/raw/places.gdb/" in item["uri"] for item in remote_raw)
    for item, local_path in zip(remote_raw, manifest["raw_files"]):
        assert objects[item["uri"].removeprefix("s3://example/")] == Path(local_path).read_bytes()


def test_local_yaml_recipe_prepares_filegdb_directory(geodatabase, tmp_path):
    recipe = tmp_path / "places.yml"
    recipe.write_text("""schema_version: 1
name: recipe_places
source:
  kind: local
  path: places.gdb
import:
  format: FileGDB
  layer: places
key: id
""")
    catalog = Catalog(tmp_path / "warehouse")
    report = prepare_recipe(recipe, catalog)
    assert report["manifest"]["dataset"] == "recipe_places"
    assert catalog.read("recipe_places")["id"].to_pylist() == ["001", "002"]
    assert catalog.read("recipe_places").schema.field("amount").type == pa.int64()
    assert report["source"]["capture_path"]


def test_cli_inspect_and_load_filegdb(geodatabase, tmp_path, capsys):
    args = ["-w", str(tmp_path / "warehouse")]
    assert main(args + ["inspect", str(geodatabase), "--format", "filegdb"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["format"] == "FileGDB"
    assert inspected["row_count"] == 2
    assert inspected["crs"] == "EPSG:2263"
    assert not (tmp_path / "warehouse").exists()
    assert main(args + ["load", str(geodatabase), "--name", "places", "--key", "id", "--format", "FileGDB"]) == 0
    loaded = json.loads(capsys.readouterr().out)
    assert loaded["format"] == "FileGDB"
    assert Catalog(tmp_path / "warehouse").read("places")["id"].to_pylist() == ["001", "002"]


def test_cli_exports_exact_filegdb_version_with_layer_and_types(geodatabase, tmp_path, capsys):
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(geodatabase, name="places", key="id")
    output = tmp_path / "export.gdb"
    args = ["-w", str(catalog.root), "export", "places", str(output),
            "--version", manifest["version"], "--format", "FileGDB", "--layer", "exported_places"]
    assert main(args) == 0
    capsys.readouterr()
    assert output.is_dir()
    assert pyogrio.list_layers(output).tolist() == [["exported_places", "Point"]]
    exported_info, exported = pyogrio.read_arrow(output, layer="exported_places")
    assert exported_info["crs"] == "EPSG:2263"
    assert exported["id"].to_pylist() == ["001", "002"]
    assert exported["amount"].to_pylist() == [7, None]
    assert exported.schema.field("amount").type == pa.int64()
    assert exported["day"].to_pylist() == [date(2024, 1, 2), None]
    assert exported.schema.field("day").type == pa.date32()
    assert main(args) == 1
    assert "already exists" in capsys.readouterr().err


def test_filegdb_export_requires_an_exact_version(geodatabase, tmp_path, capsys):
    catalog = Catalog(tmp_path / "warehouse")
    catalog.ingest(geodatabase, name="places", key="id")
    destination = tmp_path / "missing-version.gdb"
    assert main(["-w", str(catalog.root), "export", "places", str(destination),
                 "--format", "FileGDB", "--layer", "places"]) == 1
    assert "exact" in capsys.readouterr().err.lower()
    assert not destination.exists()


def test_filegdb_export_rejects_gdal_int8_to_int16_coercion(tmp_path, capsys):
    source = tmp_path / "small.parquet"
    table = pa.table({"id": pa.array(["001"], type=pa.string()),
                      "small": pa.array([12], type=pa.int8())})
    pq.write_table(table, source)
    direct = tmp_path / "raw-writer.gdb"
    pyogrio.write_arrow(table, direct, layer="small", driver="OpenFileGDB",
                        layer_options={"TARGET_ARCGIS_VERSION": "ARCGIS_PRO_3_2_OR_LATER"})
    assert pyogrio.read_arrow(direct, layer="small")[1].schema.field("small").type == pa.int16()
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(source, name="small", key="id")
    assert catalog.read("small").schema.field("small").type == pa.int8()
    destination = tmp_path / "small.gdb"
    assert main(["-w", str(catalog.root), "export", "small", str(destination),
                 "--version", manifest["version"], "--format", "FileGDB", "--layer", "small"]) == 1
    error = capsys.readouterr().err.lower()
    assert "type" in error or "coerc" in error
    assert not destination.exists()


def test_export_rejects_mixed_geometries_without_partial_destination(tmp_path, capsys):
    source = tmp_path / "mixed.geojson"
    source.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "001"},
         "geometry": {"type": "Point", "coordinates": [1, 2]}},
        {"type": "Feature", "properties": {"id": "002"},
         "geometry": {"type": "LineString", "coordinates": [[1, 2], [3, 4]]}},
    ]}))
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(source, name="mixed", key="id")
    destination = tmp_path / "mixed.gdb"
    assert main(["-w", str(catalog.root), "export", "mixed", str(destination),
                 "--version", manifest["version"], "--format", "FileGDB", "--layer", "mixed"]) == 1
    assert "geometry type" in capsys.readouterr().err
    assert not destination.exists()


def test_export_rejects_unsupported_attribute_without_partial_destination(geodatabase, tmp_path, capsys):
    table, _ = read_vector(geodatabase)
    table = table.append_column("price", pa.array([Decimal("1.25"), None], type=pa.decimal128(8, 2)))
    source = tmp_path / "decimal.parquet"
    pq.write_table(table, source)
    catalog = Catalog(tmp_path / "warehouse")
    manifest = catalog.ingest(source, name="decimal_places", key="id")
    destination = tmp_path / "decimal.gdb"
    assert main(["-w", str(catalog.root), "export", "decimal_places", str(destination),
                 "--version", manifest["version"], "--format", "FileGDB", "--layer", "decimal_places"]) == 1
    assert "attribute type" in capsys.readouterr().err
    assert not destination.exists()
