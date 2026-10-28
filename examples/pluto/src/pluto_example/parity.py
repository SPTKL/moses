"""Strict, bounded-report attribute comparisons for reference stage outputs.

Rows are matched by their original key values, never coerced. Numeric tolerances,
blank/null equivalence and topological geometry equivalence are not inferred.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
import math
import json

import pyarrow as pa


def _json_value(value):
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    return value


def _index(table, key, label):
    if key not in table.column_names:
        raise ValueError(f"{label}: missing key {key!r}")
    rows = table.to_pylist()
    keys = [row[key] for row in rows]
    if any(v is None or isinstance(v, str) and not v.strip() for v in keys):
        raise ValueError(f"{label}: key {key!r} contains null/blank values")
    if any(isinstance(v, float) and not math.isfinite(v) for v in keys):
        raise ValueError(f"{label}: key {key!r} contains nonfinite values")
    try:
        counts = Counter(keys)
    except TypeError as exc:
        raise ValueError(f"{label}: key must have scalar hashable values") from exc
    if any(count > 1 for count in counts.values()):
        raise ValueError(f"{label}: key {key!r} contains duplicate values")
    return dict(zip(keys, rows))


def compare_tables(candidate: pa.Table, reference: pa.Table, key="bbl", columns=None,
                   *, max_examples=20) -> dict:
    """Compare exact keyed values/types with bounded examples and total counts.

    Full comparison also checks column order and schema metadata. Explicit
    columns compare that subset only; this never establishes full-output parity.
    WKB is compared byte-for-byte, not spatially.
    """
    if not isinstance(max_examples, int) or not 0 <= max_examples <= 1000:
        raise ValueError("max_examples must be between 0 and 1000")
    for label, table in (("candidate", candidate), ("reference", reference)):
        if len(set(table.column_names)) != len(table.column_names):
            raise ValueError(f"{label}: duplicate column names")
    before = _index(reference, key, "reference")
    after = _index(candidate, key, "candidate")
    selected = list(dict.fromkeys([key] + list(columns))) if columns is not None else list(reference.column_names)
    if columns is not None and (not columns or isinstance(columns, str)):
        raise ValueError("columns must be a nonempty list of field names")
    schema_differences = []
    if columns is None and candidate.column_names != reference.column_names:
        schema_differences.append({"kind": "column_order_or_names",
                                   "candidate": candidate.column_names,
                                   "reference": reference.column_names})
    comparable = []
    for name in selected:
        if name not in candidate.column_names or name not in reference.column_names:
            schema_differences.append({"kind": "missing_column", "column": name})
        elif not candidate.schema.field(name).equals(reference.schema.field(name), check_metadata=True):
            schema_differences.append({"kind": "field", "column": name,
                                       "candidate": str(candidate.schema.field(name)),
                                       "reference": str(reference.schema.field(name))})
            comparable.append(name)
        else:
            comparable.append(name)
    if columns is None and candidate.schema.metadata != reference.schema.metadata:
        schema_differences.append({"kind": "schema_metadata"})
    added = after.keys() - before.keys()
    removed = before.keys() - after.keys()
    differences = []
    changed_rows = 0
    changed_cells = 0
    for identifier in sorted(before.keys() & after.keys(), key=repr):
        row_changed = False
        for field in comparable:
            left, right = after[identifier][field], before[identifier][field]
            # IEEE NaN does not prove equality, even when both inputs have NaN.
            if left != right:
                row_changed = True
                changed_cells += 1
                if len(differences) < max_examples:
                    differences.append({"key": _json_value(identifier), "column": field,
                                        "candidate": _json_value(left), "reference": _json_value(right)})
        changed_rows += row_changed
    return {"equal": not (schema_differences or added or removed or changed_cells),
            "scope": "attribute_subset" if columns is not None else "strict_table",
            "geometry_comparison": "byte_equality_only",
            "key": key, "columns": selected, "candidate_rows": candidate.num_rows,
            "reference_rows": reference.num_rows, "added_rows": len(added),
            "removed_rows": len(removed), "changed_rows": changed_rows,
            "changed_cells": changed_cells, "schema_differences": schema_differences,
            "added_examples": [_json_value(v) for v in sorted(added, key=repr)[:max_examples]],
            "removed_examples": [_json_value(v) for v in sorted(removed, key=repr)[:max_examples]],
            "differences": differences, "max_examples": max_examples}


def compare_row_multisets(candidate: pa.Table, reference: pa.Table, *, max_examples=20) -> dict:
    """Strict schema and row-multiplicity comparison for tax/easement grain.

    No synthetic unique BBL is invented for a source that can repeat parcels.
    """
    if not isinstance(max_examples, int) or not 0 <= max_examples <= 1000:
        raise ValueError("max_examples must be between 0 and 1000")
    for table in (candidate, reference):
        if len(set(table.column_names)) != len(table.column_names):
            raise ValueError("Duplicate column names cannot be compared")
    same_schema = candidate.schema.equals(reference.schema, check_metadata=True)

    def tokens(table):
        return Counter(json.dumps(_json_value(row), sort_keys=True, separators=(",", ":"),
                                  allow_nan=False) for row in table.to_pylist())

    actual, expected = tokens(candidate), tokens(reference)
    added, removed = actual - expected, expected - actual
    def examples(counts):
        return [{"row": json.loads(row), "count": count}
                for row, count in sorted(counts.items())[:max_examples]]
    return {"equal": same_schema and not added and not removed,
            "scope": "strict_row_multiset", "key": None,
            "geometry_comparison": "byte_equality_only",
            "candidate_rows": candidate.num_rows, "reference_rows": reference.num_rows,
            "schema_equal": same_schema,
            "candidate_schema": str(candidate.schema) if not same_schema else None,
            "reference_schema": str(reference.schema) if not same_schema else None,
            "added_rows": sum(added.values()), "removed_rows": sum(removed.values()),
            "added_examples": examples(added), "removed_examples": examples(removed),
            "max_examples": max_examples}
