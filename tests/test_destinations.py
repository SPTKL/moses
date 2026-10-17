import io
import json
import os

import pytest

from moses import Catalog
from moses.destinations.s3 import S3Publisher
from moses.destinations.ducklake import DuckLakePublisher


class PreconditionFailed(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 412}}


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.fail_on = None

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        assert kwargs["IfNoneMatch"] == "*"
        if self.fail_on and self.fail_on in key:
            raise OSError("simulated interrupted upload")
        if key in self.objects:
            raise PreconditionFailed()
        self.objects[key] = kwargs["Body"]
        self.calls.append(key)

    def get_object(self, **kwargs):
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}


@pytest.fixture
def dataset(tmp_path):
    source = tmp_path / "points.csv"
    source.write_text("id,x,y\n001,-74,40\n002,-73,41\n")
    cat = Catalog(tmp_path / "warehouse")
    first = cat.ingest(source, name="points", key="id", x="x", y="y")
    return cat, first, source


def test_s3_publish_manifest_last_idempotent_and_complete(dataset):
    cat, manifest, _ = dataset
    client = MemoryS3()
    publisher = S3Publisher("example", client=client)
    first = publisher.publish(cat, "points")
    assert client.calls[-1].endswith("manifest.json")
    remote = json.loads(client.objects[client.calls[-1]])
    assert remote["version"] == manifest["version"]
    assert remote["crs"] == "EPSG:4326"
    assert remote["objects"]["raw"]
    assert "parquet_path" not in remote
    assert publisher.publish(cat, "points") == first


def test_s3_failure_does_not_publish_manifest(dataset):
    cat, _, _ = dataset
    client = MemoryS3()
    client.fail_on = "/raw/"
    with pytest.raises(OSError):
        S3Publisher("example", client=client).publish(cat, "points")
    assert not any(key.endswith("manifest.json") for key in client.objects)


def test_s3_existing_different_object_rejected(dataset):
    cat, _, _ = dataset
    client = MemoryS3()
    publisher = S3Publisher("example", client=client)
    publisher.publish(cat, "points")
    client.objects[client.calls[0]] = b"tampered"
    with pytest.raises(ValueError, match="different contents"):
        publisher.publish(cat, "points")


def test_ducklake_missing_extension_does_not_install_and_restores_setting(dataset, tmp_path):
    import duckdb
    cat, _, _ = dataset
    directory = tmp_path / "empty-extensions"
    con = duckdb.connect(config={"extension_directory": str(directory)})
    try:
        with pytest.raises(duckdb.Error):
            DuckLakePublisher(str(tmp_path / "catalog.ducklake"), connection=con).publish(cat, "points")
        assert con.execute("SELECT current_setting('autoinstall_known_extensions')").fetchone()[0] is True
        assert not list(directory.rglob("*.duckdb_extension"))
    finally:
        con.close()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("MOSES_TEST_DUCKLAKE"), reason="Set MOSES_TEST_DUCKLAKE=1 with cached ducklake extension")
def test_ducklake_publication_and_native_time_travel(dataset, tmp_path):
    import duckdb
    cat, manifest, source = dataset
    con = duckdb.connect(config={"extension_directory": os.environ.get("MOSES_EXTENSION_DIRECTORY", str(tmp_path / "extensions"))})
    try:
        publisher = DuckLakePublisher(str(tmp_path / "catalog.ducklake"), data_path=str(tmp_path / "lake-files"), connection=con)
        first = publisher.publish(cat, "points")
        source.write_text("id,x,y\n001,-74,40\n")
        cat.ingest(source, name="points", key="id", x="x", y="y")
        second = publisher.publish(cat, "points")
        assert first["version"] == manifest["version"]
        assert second["ducklake_snapshot"] > first["ducklake_snapshot"]
        con.execute(f"ATTACH 'ducklake:{tmp_path / 'catalog.ducklake'}' AS verify")
        assert con.execute("SELECT count(*) FROM verify.points").fetchone()[0] == 1
        assert con.execute(f"SELECT count(*) FROM verify.points AT (VERSION => {first['ducklake_snapshot']})").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM verify._moses.versions").fetchone()[0] == 2
        assert con.execute("SELECT typeof(geometry) FROM verify.points").fetchone()[0] == "BLOB"
    finally:
        con.close()
