import json

import pyarrow.parquet as pq
import pytest
from pyproj import CRS
import shapely

from moses.pluto.legacy import LegacyDumpError, normalize_legacy_dump


def _geometry(srid=4326, invalid=False):
    coordinates = [(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)] if invalid else [(0, 0), (1, 0), (1, 1), (0, 0)]
    shape = shapely.set_srid(shapely.MultiPolygon([shapely.Polygon(coordinates)]), srid)
    return shapely.to_wkb(shape, include_srid=True, hex=True)


def _dump(path, *, geometry=None, tail="COMMIT;", altered=""):
    geometry = geometry or _geometry()
    path.write_text('''SET standard_conforming_strings = OFF;
DROP TABLE IF EXISTS "public"."fixture" CASCADE;
BEGIN;
CREATE TABLE "public"."fixture" ( "ogc_fid" SERIAL, CONSTRAINT "fixture_pk" PRIMARY KEY ("ogc_fid") );
SELECT AddGeometryColumn('public','fixture','wkb_geometry',4326,'MULTIPOLYGON',2);
ALTER TABLE "public"."fixture" ADD COLUMN "code" VARCHAR;
ALTER TABLE "public"."fixture" ADD COLUMN "amount" FLOAT8;
''' + altered + '''COPY "public"."fixture" ("wkb_geometry", "code", "amount") FROM STDIN;
''' + geometry + '\t00123\\tA\\nB\\\\N\t-9999.00\n' + geometry + '\t\\N\t\\N\n' + geometry + '\t\t0\n' + '\\.\n' + tail + '\n')


def test_copy_types_nulls_escapes_geometry_and_crs(tmp_path):
    source, output = tmp_path / "fixture.sql", tmp_path / "fixture.parquet"
    _dump(source)
    report = normalize_legacy_dump(source, output, dataset="fixture")
    table = pq.read_table(output)
    assert table.column_names == ["ogc_fid", "wkb_geometry", "code", "amount"]
    assert table["ogc_fid"].to_pylist() == [1, 2, 3]
    assert table["code"].to_pylist() == ["00123\tA\nB\\N", None, ""]
    assert table["amount"].to_pylist() == [-9999.0, None, 0.0]
    geo = json.loads(table.schema.metadata[b"geo"])
    assert CRS.from_json_dict(geo["columns"]["wkb_geometry"]["crs"]).to_epsg() == 4326
    original = shapely.from_wkb(bytes.fromhex(_geometry()))
    normalized = shapely.from_wkb(table["wkb_geometry"][0].as_py())
    assert shapely.equals_exact(original, normalized, tolerance=0)
    assert shapely.get_srid(normalized) == 0  # SRID now lives in GeoParquet metadata.
    assert report["rows"] == 3 and report["invalid_geometries"] == 0
    assert len(report["original_sha256"]) == len(report["normalized_sha256"]) == 64
    assert "no SQL executed" in report["parser"]


def test_invalid_topology_preserved_and_reported(tmp_path):
    source, output = tmp_path / "fixture.sql", tmp_path / "fixture.parquet"
    _dump(source, geometry=_geometry(invalid=True))
    report = normalize_legacy_dump(source, output, dataset="fixture")
    assert report["invalid_geometries"] == 3
    assert not shapely.is_valid(shapely.from_wkb(pq.read_table(output)["wkb_geometry"][0].as_py()))
    assert "Self-intersection" in report["invalid_examples"][0]["reason"]


@pytest.mark.parametrize("failure", ["srid", "statement", "type", "unterminated", "columns"])
def test_unsupported_dump_cannot_replace_accepted_output(tmp_path, failure):
    source, output = tmp_path / "fixture.sql", tmp_path / "fixture.parquet"
    output.write_bytes(b"accepted-output")
    _dump(source, geometry=_geometry(2263) if failure == "srid" else None,
          tail="SELECT arbitrary_function();" if failure == "statement" else "COMMIT;",
          altered='ALTER TABLE "public"."fixture" ADD COLUMN "unsupported" NUMERIC;\n' if failure == "type" else "")
    if failure == "unterminated":
        source.write_text(source.read_text().replace("\\.\n", ""))
    if failure == "columns":
        source.write_text(source.read_text().replace('"code", "amount") FROM', '"code", "missing") FROM'))
    with pytest.raises(LegacyDumpError):
        normalize_legacy_dump(source, output, dataset="fixture")
    assert output.read_bytes() == b"accepted-output"


def test_alternate_serial_declaration_and_copy_escape_bytes(tmp_path):
    source, output = tmp_path / "fixture.sql", tmp_path / "fixture.parquet"
    _dump(source)
    source.write_text(source.read_text().replace(
        'CREATE TABLE "public"."fixture" ( "ogc_fid" SERIAL, CONSTRAINT "fixture_pk" PRIMARY KEY ("ogc_fid") );',
        'CREATE TABLE "public"."fixture"();\nALTER TABLE "public"."fixture" ADD COLUMN "ogc_fid" SERIAL CONSTRAINT "fixture_pk" PRIMARY KEY;'
    ).replace(r"00123\tA\nB\\N", r"\303\251\x41\\N"))
    normalize_legacy_dump(source, output, dataset="fixture")
    assert pq.read_table(output)["code"][0].as_py() == "éA\\N"
