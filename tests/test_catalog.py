import json
from pathlib import Path
import shutil
import sqlite3

import pyarrow as pa
import pyogrio
import pytest
import shapely

from moses.catalog import Catalog


def _csv(path: Path, rows: str) -> None:
    path.write_text("id,name,x,y\n" + rows, encoding="utf-8")


def test_versions_diff_query_and_geoparquet_metadata(tmp_path):
    source = tmp_path / "places.csv"
    root = tmp_path / "catalog"
    _csv(source, "001,One,-73.9,40.7\n002,Two,-73.8,40.8\n")
    catalog = Catalog(root)
    first = catalog.ingest(source, name="places", key="id", x="x", y="y", provenance={"agency": "test"})
    assert first["row_count"] == 2
    assert first["provenance"] == {"agency": "test"}
    assert first["crs"] == "EPSG:4326"
    assert Path(first["parquet_path"]).exists()
    assert all(Path(path).exists() for path in first["raw_files"])
    table = catalog.read("places")
    assert table["id"].to_pylist() == ["001", "002"]
    assert json.loads(table.schema.metadata[b"geo"])["columns"]["geometry"]["encoding"] == "WKB"

    _csv(source, "001,One revised,-73.9,40.7\n003,Three,-73.7,40.9\n")
    second = catalog.ingest(source, name="places", key="id", x="x", y="y")
    assert second["version"] != first["version"]
    assert [row["version"] for row in catalog.history("places")] == [first["version"], second["version"]]
    assert catalog.diff("places", first["version"], second["version"]) == {
        "added": 1, "removed": 1, "changed": 1,
        "old_version": first["version"], "new_version": second["version"],
        "key": "id", "schema_changed": False, "old_schema": None, "new_schema": None,
    }
    assert catalog.read("places", first["version"])["id"].to_pylist() == ["001", "002"]
    assert catalog.query("SELECT id FROM places ORDER BY id")["id"].to_pylist() == ["001", "003"]
    assert catalog.datasets()[0]["version"] == second["version"]


def test_reimport_records_observation_without_new_release_and_is_portable(tmp_path):
    source = tmp_path / "places.csv"
    root = tmp_path / "catalog"
    _csv(source, "001,One,-73.9,40.7\n")
    catalog = Catalog(root)
    first = catalog.ingest(source, name="places", key="id", x="x", y="y")
    # Source bytes change while parsed rows, schema and options remain identical.
    source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    same = catalog.ingest(source, name="places", key="id", x="x", y="y", provenance={"checked": True})
    assert same["unchanged"] is True
    assert same["version"] == first["version"]
    assert same["observation_source_sha256"] != first["source_sha256"]
    assert len(catalog.history("places")) == 1
    assert [item["version"] for item in catalog.observations("places")] == [first["version"]] * 2
    assert catalog.observations("places")[1]["provenance"] == {"checked": True}
    with sqlite3.connect(root / "catalog.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2
        stored = json.loads(conn.execute("SELECT manifest_json FROM versions").fetchone()[0])
    assert not Path(stored["parquet_path"]).is_absolute()
    assert all(not Path(path).is_absolute() for path in stored["raw_files"])

    moved = tmp_path / "relocated"
    shutil.move(root, moved)
    reopened = Catalog(moved)
    assert reopened.get_version("places")["parquet_path"].startswith(str(moved))
    assert reopened.read("places")["id"].to_pylist() == ["001"]


def test_failed_import_keeps_latest_and_rejects_key_errors(tmp_path, monkeypatch):
    source = tmp_path / "places.csv"
    _csv(source, "001,One,-73.9,40.7\n")
    catalog = Catalog(tmp_path / "catalog")
    first = catalog.ingest(source, name="places", key="id", x="x", y="y")

    _csv(source, "001,One,-73.9,40.7\n001,Duplicate,-73.8,40.8\n")
    with pytest.raises(ValueError, match="duplicate"):
        catalog.ingest(source, name="places", key="id", x="x", y="y")
    assert catalog.get_version("places")["version"] == first["version"]

    _csv(source, "002,Two,-73.8,40.8\n")
    with pytest.raises(ValueError, match="cannot change"):
        catalog.ingest(source, name="places", key="name", x="x", y="y")

    import moses.catalog as module
    def fail_write(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(module.pq, "write_table", fail_write)
    with pytest.raises(OSError, match="disk full"):
        catalog.ingest(source, name="places", key="id", x="x", y="y")
    assert catalog.get_version("places")["version"] == first["version"]
    assert len(catalog.history("places")) == 1


def test_null_key_schema_change_and_no_key_multiset(tmp_path, monkeypatch):
    source = tmp_path / "data.csv"
    source.write_text("placeholder\n", encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog")
    import moses.ingest as reader

    table = pa.table({"id": pa.array(["a", None]), "value": pa.array([1, 2])})
    def fake_read(path, **kwargs):
        return table, {"format": "CSV", "layer": None, "crs": None,
                       "geometry_column": None, "source_files": [str(path)]}
    monkeypatch.setattr(reader, "read_vector", fake_read)
    with pytest.raises(ValueError, match="null"):
        catalog.ingest(source, name="data", key="id")
    assert catalog.datasets() == []

    table = pa.table({"id": ["a", "b"], "value": [1, 2]})
    first = catalog.ingest(source, name="data", key="id")
    table = pa.table({"id": ["a", "b"], "value": [1, 2], "extra": [None, None]})
    second = catalog.ingest(source, name="data", key="id")
    difference = catalog.diff("data", first["version"], second["version"])
    assert difference["schema_changed"] is True
    assert difference["changed"] == 2

    table = pa.table({"id": ["a", "a", "b"]})
    a = catalog.ingest(source, name="unkeyed")
    table = pa.table({"id": ["a", "b", "b"]})
    b = catalog.ingest(source, name="unkeyed")
    assert catalog.diff("unkeyed", a["version"], b["version"])["added"] == 1
    assert catalog.diff("unkeyed", a["version"], b["version"])["removed"] == 1


def test_shapefile_captures_companions(tmp_path):
    source = tmp_path / "points.shp"
    table = pa.table({
        "id": pa.array(["a"]),
        "wkb_geometry": pa.array([shapely.to_wkb(shapely.Point(-73.9, 40.7))], type=pa.binary()),
    })
    pyogrio.write_arrow(table, source, driver="ESRI Shapefile", layer="points",
                        geometry_name="wkb_geometry", geometry_type="Point", crs="EPSG:4326")
    catalog = Catalog(tmp_path / "catalog")
    manifest = catalog.ingest(source, name="points", key="id")
    assert {Path(path).suffix for path in manifest["raw_files"]} >= {".shp", ".shx", ".dbf", ".prj"}
    assert len({Path(path).parent for path in manifest["raw_files"]}) == 1
    assert catalog.read("points").num_rows == 1


def test_invalid_name_and_query_external_access(tmp_path):
    catalog = Catalog(tmp_path / "catalog")
    source = tmp_path / "values.csv"
    source.write_text("id\na\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Dataset name"):
        catalog.ingest(source, name="bad-name")
    catalog.ingest(source, name="values")
    with pytest.raises(Exception):
        catalog.query(f"SELECT * FROM read_csv('{source}')")
    with pytest.raises(ValueError, match="Only SELECT"):
        catalog.query("DROP TABLE values")


def test_same_source_bytes_with_different_filename_and_casefold_collision(tmp_path):
    first_file = tmp_path / "one.csv"
    second_file = tmp_path / "two.csv"
    first_file.write_text("id\na\n", encoding="utf-8")
    second_file.write_bytes(first_file.read_bytes())
    catalog = Catalog(tmp_path / "catalog")
    first = catalog.ingest(first_file, name="Places", key="id")
    same = catalog.ingest(second_file, name="Places", key="id")
    assert same["unchanged"] is True
    assert same["observation_source_sha256"] != first["source_sha256"]
    observations = catalog.observations("Places")
    assert all(Path(path).exists() for item in observations for path in item["raw_files"])
    assert Path(observations[0]["raw_files"][0]).name == "one.csv"
    assert Path(observations[1]["raw_files"][0]).name == "two.csv"
    with pytest.raises(ValueError, match="conflicts"):
        catalog.ingest(first_file, name="places", key="id")


def test_query_uses_selected_versions_when_catalog_changes(tmp_path, monkeypatch):
    source = tmp_path / "rows.csv"
    source.write_text("id\nold\n", encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog")
    first = catalog.ingest(source, name="rows", key="id")
    saved_lock = catalog.lock()
    assert saved_lock == {"rows": first["version"]}

    original_datasets = catalog.datasets
    def publish_during_selection():
        selected = original_datasets()
        source.write_text("id\nnew\n", encoding="utf-8")
        catalog.ingest(source, name="rows", key="id")
        return selected
    monkeypatch.setattr(catalog, "datasets", publish_during_selection)
    assert catalog.query("SELECT id FROM rows")["id"].to_pylist() == ["old"]
    monkeypatch.setattr(catalog, "datasets", original_datasets)
    assert catalog.query("SELECT id FROM rows")["id"].to_pylist() == ["new"]
    assert catalog.query("SELECT id FROM rows", versions=saved_lock)["id"].to_pylist() == ["old"]


def test_query_lock_validates_versions_and_registers_exact_set(tmp_path):
    catalog = Catalog(tmp_path / "catalog")
    for name in ("alpha", "beta"):
        source = tmp_path / f"{name}.csv"
        source.write_text(f"id\n{name}\n", encoding="utf-8")
        catalog.ingest(source, name=name)
    lock = catalog.lock()
    assert set(lock) == {"alpha", "beta"}
    assert catalog.query("SELECT id FROM alpha", versions={"alpha": lock["alpha"]})["id"].to_pylist() == ["alpha"]
    with pytest.raises(Exception):
        catalog.query("SELECT id FROM beta", versions={"alpha": lock["alpha"]})
    with pytest.raises(KeyError, match="Unknown version"):
        catalog.query("SELECT id FROM alpha", versions={"alpha": "nonexistent"})
    with pytest.raises(KeyError, match="Unknown dataset"):
        catalog.query("SELECT 1", versions={"missing": "version"})
    with pytest.raises(ValueError, match="Dataset name"):
        catalog.query("SELECT 1", versions={"bad-name": "version"})
    with pytest.raises(ValueError, match="nonempty"):
        catalog.query("SELECT 1", versions={"alpha": ""})
