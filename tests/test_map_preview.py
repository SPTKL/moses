import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pyproj import Transformer
from shapely.geometry import (
    GeometryCollection, LineString, MultiLineString, MultiPoint,
    MultiPolygon, Point, Polygon,
)

from moses.map_preview import MapPreviewError, build_map_preview


def _snapshot(tmp_path, geometries, *, crs="EPSG:4326", values=None):
    path = tmp_path / "accepted.parquet"
    values = values if values is not None else list(range(len(geometries)))
    table = pa.table({"geometry": pa.array([None if g is None else g.wkb if hasattr(g, "wkb") else g
                                             for g in geometries], type=pa.binary()),
                      "value": pa.array(values)})
    pq.write_table(table, path)
    return path, {"geometry_column": "geometry", "crs": crs, "crs_source": "source",
                  "row_count": len(geometries)}


def test_point_xy_and_display_copy(tmp_path):
    east, north = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True).transform(-73.99, 40.73)
    path, manifest = _snapshot(tmp_path, [Point(east, north)], crs="EPSG:2263")
    original = path.read_bytes()
    result = build_map_preview(path, manifest)
    assert result["features"][0]["geometry"]["coordinates"] == pytest.approx((-73.99, 40.73), abs=1e-6)
    assert result["bbox"] == pytest.approx([-73.99, 40.73, -73.99, 40.73], abs=1e-6)
    assert result["display_crs"] == "EPSG:4326"
    assert result["scanned_rows"] == result["returned_features"] == 1
    assert path.read_bytes() == original


def test_supported_types_z_and_properties(tmp_path):
    geometries = [
        Point(-74, 40, 10), MultiPoint([(-74, 40), (-73, 41)]),
        LineString([(-74, 40), (-73, 41)]),
        MultiLineString([[(-74, 40), (-73, 41)]]),
        Polygon([(-74, 40), (-73, 40), (-73, 41), (-74, 40)]),
        MultiPolygon([Polygon([(-74, 40), (-73, 40), (-73, 41), (-74, 40)])]),
    ]
    path, manifest = _snapshot(tmp_path, geometries, values=[2**60] + [0] * 5)
    result = build_map_preview(path, manifest)
    assert [f["geometry"]["type"] for f in result["features"]] == [g.geom_type for g in geometries]
    assert result["features"][0]["geometry"]["coordinates"] == [-74.0, 40.0] or result["features"][0]["geometry"]["coordinates"] == (-74.0, 40.0)
    assert result["features"][0]["properties"]["value"] == str(2**60)
    assert any("Z coordinates" in w for w in result["warnings"])
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("manifest,code", [
    ({"geometry_column": None, "crs": "EPSG:4326"}, "nonspatial"),
    ({"geometry_column": "geometry", "crs": None}, "unknown_crs"),
    ({"geometry_column": "geometry", "crs": "EPSG:bad"}, "invalid_crs"),
])
def test_missing_or_invalid_spatial_metadata(tmp_path, manifest, code):
    path, _ = _snapshot(tmp_path, [Point(0, 0)])
    with pytest.raises(MapPreviewError) as error:
        build_map_preview(path, manifest)
    assert error.value.status == 422
    assert error.value.code == code


def test_omissions_and_stable_row_ids(tmp_path):
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    path, manifest = _snapshot(tmp_path, [None, b"bad", Point(), bowtie,
                                          GeometryCollection([Point(0, 0)]), Point(1, 2)])
    result = build_map_preview(path, manifest)
    assert [feature["id"] for feature in result["features"]] == [5]
    assert result["omissions"] == {"null": 1, "invalid": 2, "empty": 1, "unsupported": 1}
    assert result["omitted_features"] == 5
    assert result["unscanned_rows"] == 0


def test_antimeridian_range_and_mercator_limit(tmp_path):
    path, manifest = _snapshot(tmp_path, [LineString([(179, 0), (-179, 0)]), Point(181, 0), Point(0, 95)])
    result = build_map_preview(path, manifest)
    assert result["omissions"] == {"antimeridian": 1, "out_of_range": 2}
    assert result["bbox"] is None
    mercator_y = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform(0, 86)[1]
    path, manifest = _snapshot(tmp_path, [Point(0, mercator_y)], crs="EPSG:3857")
    assert build_map_preview(path, manifest)["omissions"] == {"mercator_latitude": 1}
    path, manifest = _snapshot(tmp_path, [Point(0, 86)], crs="EPSG:4326")
    assert build_map_preview(path, manifest)["omissions"] == {"mercator_latitude": 1}


def test_geometry_and_coordinate_budgets(tmp_path):
    huge = b"0" * (1024 * 1024 + 1)
    many = LineString([(i / 1000, 0) for i in range(20_001)])
    path, manifest = _snapshot(tmp_path, [huge, many, Point(0, 0)])
    result = build_map_preview(path, manifest)
    assert result["omissions"] == {"oversized_geometry": 1, "oversized_coordinates": 1}
    assert [f["id"] for f in result["features"]] == [2]
    assert len(json.dumps(result, allow_nan=False).encode()) < result["limits"]["max_bytes"]


def test_row_scan_limit_and_assumed_crs(tmp_path):
    path, manifest = _snapshot(tmp_path, [None] * 1100 + [Point(0, 0)])
    manifest["crs_source"] = "default"
    result = build_map_preview(path, manifest, limit=2)
    assert result["scanned_rows"] == 1000
    assert result["returned_features"] == 0
    assert result["omitted_features"] == 1000
    assert result["unscanned_rows"] == 101
    assert result["truncated"]
    assert any("assumed" in warning for warning in result["warnings"])
    manifest["crs_source"] = "legacy_csv_default"
    assert any("assumed" in warning for warning in build_map_preview(path, manifest)["warnings"])


def test_metadata_alone_cannot_exceed_response_limit(tmp_path):
    path, manifest = _snapshot(tmp_path, [Point(0, 0)])
    manifest["crs_source"] = "x" * (2 * 1024 * 1024)
    with pytest.raises(MapPreviewError) as error:
        build_map_preview(path, manifest)
    assert error.value.status == 422
    assert error.value.code == "preview_metadata_too_large"


def test_feature_limit_does_not_claim_unscanned_rows(tmp_path):
    path, manifest = _snapshot(tmp_path, [Point(0, 0)] * 6)
    result = build_map_preview(path, manifest, limit=2)
    assert [f["id"] for f in result["features"]] == [0, 1]
    assert (result["scanned_rows"], result["returned_features"], result["unscanned_rows"]) == (2, 2, 4)
    assert result["truncated"]


def test_property_summaries_are_counted(tmp_path):
    path = tmp_path / "accepted.parquet"
    pq.write_table(pa.table({
        "geometry": pa.array([Point(0, 0).wkb]),
        "long": pa.array(["x" * 5000]),
        "nested": pa.array([list(range(120))]),
        "binary": pa.array([b"abc"]),
    }), path)
    manifest = {"geometry_column": "geometry", "crs": "EPSG:4326", "crs_source": "source"}
    result = build_map_preview(path, manifest)
    assert result["property_omissions"] == {
        "large_cell": 1, "nested_truncated": 1, "binary_summarized": 1,
    }
    assert result["features"][0]["properties"]["long"] == {"truncated": True, "byte_length": 5000}
    assert result["features"][0]["properties"]["nested"]["omitted_count"] == 20
    json.dumps(result, allow_nan=False)


def test_coordinate_work_budget_stops_with_counted_row(tmp_path):
    line = LineString([(i % 2 * 0.001, 0) for i in range(20_000)])
    path, manifest = _snapshot(tmp_path, [line] * 6)
    result = build_map_preview(path, manifest)
    assert result["omissions"]["coordinate_budget"] == 1
    assert result["scanned_rows"] == 6
    assert result["unscanned_rows"] == 0
    assert result["returned_features"] == 5
