"""Load optional native dependencies only at the feature that needs them."""

from importlib import import_module
from types import ModuleType


class SpatialDependencyError(ValueError):
    """A spatial operation needs an optional native dependency."""


def require_spatial(package: str, feature: str) -> ModuleType:
    """Import a spatial dependency, with an actionable installation error."""
    try:
        return import_module(package)
    except ImportError as exc:
        raise SpatialDependencyError(
            f"{feature} requires the optional spatial dependencies ({package}). "
            "Install them with uv add 'moses-geo[spatial]' "
            "(or pip install 'moses-geo[spatial]'). In a Moses checkout, use "
            "uv sync --locked --extra spatial and uv run --locked --extra spatial <command>."
        ) from exc
