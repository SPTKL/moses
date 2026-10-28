"""Optional, deterministic ASCII snake_case field names."""

from __future__ import annotations

import re


def snake_case(name: str) -> str:
    # Split acronyms at their last capital and ordinary lower-to-upper joins.
    words = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", words)
    result = re.sub(r"[^A-Za-z0-9]+", "_", words).strip("_").lower()
    if not result:
        raise ValueError(f"Column {name!r} has no usable ASCII letters or digits")
    return f"column_{result}" if result[0].isdigit() else result


def column_name_map(names: list[str], mode: str) -> dict[str, str]:
    if mode not in {"preserve", "snake_case"}:
        raise ValueError("column_names must be 'preserve' or 'snake_case'")
    if mode == "preserve":
        return {name: name for name in names}
    mapped = {name: snake_case(name) for name in names}
    if len(mapped) != len(names):
        raise ValueError("Source has duplicate column names")
    reverse: dict[str, str] = {}
    for source, final in mapped.items():
        if final in reverse:
            raise ValueError(f"Column names {reverse[final]!r} and {source!r} collide as {final!r}")
        reverse[final] = source
    return mapped
