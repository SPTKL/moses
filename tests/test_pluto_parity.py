import json

import pyarrow as pa
import pytest

from moses.pluto.parity import compare_tables, compare_row_multisets


def test_keyed_comparison_ignores_row_order_but_not_null_blank():
    a = pa.table({"bbl": ["1000010001", "1000010002"], "value": ["", None]})
    assert compare_tables(a, a.take([1, 0]))["equal"]
    b = pa.table({"bbl": ["1000010001", "1000010002"], "value": [None, ""]})
    result = compare_tables(a, b, max_examples=1)
    assert not result["equal"]
    assert result["changed_cells"] == 2
    assert len(result["differences"]) == 1
    json.dumps(result, allow_nan=False)


def test_reports_added_removed_and_schema_without_coercion():
    a = pa.table({"bbl": ["1000010001"], "value": [1]})
    b = pa.table({"bbl": ["1000010002"], "value": ["1"]})
    result = compare_tables(a, b)
    assert result["added_rows"] == result["removed_rows"] == 1
    assert result["schema_differences"]
    assert not result["equal"]


@pytest.mark.parametrize("keys", [[None], [" "], ["x", "x"]])
def test_bad_keys_rejected(keys):
    table = pa.table({"bbl": keys})
    with pytest.raises(ValueError):
        compare_tables(table, table)


def test_subset_and_binary_do_not_imply_spatial_parity():
    a = pa.table({"bbl": ["1"], "x": [1], "geometry": [b"a"]})
    b = pa.table({"bbl": ["1"], "x": [1], "geometry": [b"b"]})
    assert not compare_tables(a, b)["equal"]
    subset = compare_tables(a, b, columns=["x"])
    assert subset["equal"] and subset["scope"] == "attribute_subset"


def test_schema_metadata_and_column_order_checked():
    a = pa.table({"bbl": ["1"], "value": ["a"]})
    assert not compare_tables(a, a.replace_schema_metadata({b"key": b"value"}))["equal"]
    assert not compare_tables(a, a.select(["value", "bbl"]))["equal"]
    field_schema = a.schema.set(0, a.schema.field(0).with_metadata({b"meaning": b"different"}))
    assert not compare_tables(a, a.cast(field_schema))["equal"]


def test_repeated_parcel_rows_preserve_multiplicity():
    a = pa.table({"bbl": ["1000010001"] * 3, "ease": ["", "A", "A"]})
    assert compare_row_multisets(a, a.take([2, 0, 1]))["equal"]
    result = compare_row_multisets(a, a.take([0, 1]))
    assert not result["equal"] and result["added_rows"] == 1
    assert result["scope"] == "strict_row_multiset"
