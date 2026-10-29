"""Explicit delivery writers for accepted immutable catalog versions."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
from .dependencies import require_spatial


def _geometry_structure(value):
    if value is None:
        return None
    shapely = require_spatial("shapely", "FileGDB geometry verification")
    geom = shapely.from_wkb(value)
    dimensions = (geom.geom_type, geom.has_z, geom.has_m, geom.is_empty)
    if geom.geom_type == 'Polygon':
        shape = (len(geom.exterior.coords), tuple(len(ring.coords) for ring in geom.interiors))
    elif hasattr(geom, 'geoms'):
        shape = tuple(_geometry_structure(shapely.to_wkb(part)) for part in geom.geoms)
    else:
        shape = len(geom.coords)
    return dimensions, shape


def _verify_filegdb(table, staged, layer, geometry, crs):
    from .ingest import read_vector

    pyogrio = require_spatial("pyogrio", "FileGDB export verification")
    layers = pyogrio.list_layers(staged)
    if [str(item[0]) for item in layers] != [layer]:
        raise ValueError('FileGDB driver changed the requested layer name')
    result, metadata = read_vector(staged, layer=layer)
    if result.num_rows != table.num_rows or result.column_names != table.column_names:
        raise ValueError('FileGDB export changed row count or field names/order')
    for field in table.schema:
        if field.name == geometry:
            continue
        actual = result.schema.field(field.name)
        if actual.type != field.type:
            raise ValueError(f'FileGDB export changed field {field.name!r} type from {field.type} to {actual.type}')
        if not table[field.name].equals(result[field.name]):
            raise ValueError(f'FileGDB export changed values or nulls in field {field.name!r}')
    if geometry:
        CRS = require_spatial("pyproj", "FileGDB CRS verification").CRS
        if metadata.get('crs') is None or not CRS.from_user_input(crs).equals(CRS.from_user_input(metadata['crs'])):
            raise ValueError('FileGDB export changed the CRS')
        if any(_geometry_structure(before) != _geometry_structure(after)
               for before, after in zip(table[geometry].to_pylist(), result[geometry].to_pylist())):
            raise ValueError('FileGDB export changed geometry types, dimensions, nulls, or structure')


def export_filegdb(catalog, name, destination, *, version, layer):
    """Write one exact accepted version as a new OpenFileGDB feature class/table.

    Native FileGDB precision may quantize coordinates. This delivery does not
    reconstruct ArcGIS domains, relationships, attachments, or other behavior.
    """
    if not isinstance(version, str) or not version or version.lower() in {'latest', 'current', '*'}:
        raise ValueError('FileGDB export requires an exact accepted version')
    if not isinstance(layer, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,159}', layer):
        raise ValueError('FileGDB export requires a layer name of letters, digits, and underscores, starting with a letter or underscore')
    destination = Path(destination).expanduser().absolute()
    if destination.suffix.lower() != '.gdb':
        raise ValueError('FileGDB export destination must end in .gdb')
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Destination already exists: {destination}')
    pyogrio = require_spatial("pyogrio", "FileGDB export")
    manifest = catalog.get_version(name, version)
    table = pq.read_table(manifest['parquet_path'])
    geometry = manifest.get('geometry_column')
    geometry_type = None
    crs = None
    if geometry:
        CRS = require_spatial("pyproj", "FileGDB spatial export").CRS
        geo = json.loads(table.schema.metadata[b'geo'])['columns'][geometry]
        kinds = geo.get('geometry_types', [])
        supported = {'Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon'}
        if len(kinds) != 1 or kinds[0].removesuffix(' Z') not in supported:
            raise ValueError('FileGDB export requires one declared supported geometry type')
        geometry_type = kinds[0]
        if geo.get('crs') is None:
            raise ValueError('FileGDB spatial export requires a known CRS')
        crs = CRS.from_user_input(geo['crs']).to_wkt()
    for field in table.schema:
        if field.name == geometry:
            continue
        # Fail before writing when GDAL would coerce a known lossy type.
        if not (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
                or pa.types.is_boolean(field.type) or pa.types.is_signed_integer(field.type)
                or pa.types.is_float32(field.type) or pa.types.is_float64(field.type)
                or pa.types.is_date32(field.type) or pa.types.is_binary(field.type)
                or pa.types.is_timestamp(field.type)):
            raise ValueError(f'Unsupported FileGDB attribute type for {field.name!r}: {field.type}')
        if pa.types.is_timestamp(field.type) and (field.type.tz is not None or field.type.unit not in {'s', 'ms'}):
            raise ValueError(f'FileGDB export requires naive timestamps at second or millisecond precision: {field.name!r}')
        if pa.types.is_int64(field.type) and any(abs(value) > 2**53 for value in table[field.name].to_pylist() if value is not None):
            raise ValueError(f'FileGDB integer outside exact supported range in {field.name!r}')
        if field.name.casefold() in {'objectid', 'shape', 'shape_length', 'shape_area'}:
            raise ValueError(f'FileGDB reserved attribute name: {field.name!r}')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', field.name):
            raise ValueError(f'Unsupported FileGDB field name: {field.name!r}')
    attributes = [field.name.casefold() for field in table.schema if field.name != geometry]
    if len(attributes) != len(set(attributes)):
        raise ValueError('FileGDB field names must be unique ignoring case')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.moses-export-', dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        try:
            pyogrio.write_arrow(table, staged, layer=layer, driver='OpenFileGDB',
                                geometry_name=geometry, geometry_type=geometry_type, crs=crs,
                                layer_options={'TARGET_ARCGIS_VERSION': 'ARCGIS_PRO_3_2_OR_LATER'})
        except Exception as exc:
            raise ValueError(f'Could not write FileGDB export: {exc}') from exc
        _verify_filegdb(table, staged, layer, geometry, crs)
        if sys.platform == 'win32':
            # Windows rename refuses an existing destination, including an
            # empty directory, so it already provides exclusive publication.
            staged.rename(destination)
        else:
            # POSIX rename can replace an empty directory. Reserve the name
            # exclusively, then replace only our own empty reservation.
            destination.mkdir()
            try:
                staged.rename(destination)
            except BaseException:
                destination.rmdir()
                raise
    return {'path': str(destination.resolve()), 'version': manifest['version'],
            'format': 'FileGDB', 'layer': layer, 'driver': 'OpenFileGDB',
            'target_arcgis_version': 'ARCGIS_PRO_3_2_OR_LATER',
            'warnings': ['FileGDB coordinate precision may quantize coordinates.',
                         'Selected-layer delivery does not reproduce domains, relationships, attachments, or other geodatabase behavior.']}
