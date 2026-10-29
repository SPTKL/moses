"""Allowlisted, versioned acquisition and preparation recipes.

Recipes contain data choices and optional named, trusted Python extensions;
they never evaluate inline SQL, Python expressions or shell commands.
Preparation finishes before Catalog.ingest atomically publishes its output.
The ordinary catalog readers retain their existing bounded/in-memory limits.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib
from importlib import metadata as package_metadata
import inspect
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import threading
from urllib.parse import parse_qsl, urlparse
from urllib.request import urlopen
import zipfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from .dependencies import require_spatial

from .catalog import Catalog
from .ingest import _shapefile_sources, _with_canonical_geometry, read_vector
from .column_names import column_name_map, snake_case
from .config import resolve_column_names
from .recipes import apply_types, canonical_types
from .filegdb import bundle_digest, copy_directory, directory_files, reject_symlink_path


class SourceRecipeError(ValueError):
    """A recipe or its acquired data cannot be prepared as declared."""


_SHA = re.compile(r'[0-9a-f]{64}\Z')
_ENV_LOCK = threading.Lock()
_GEOCODE_COLUMNS = ('geosupport_raw', 'geosupport_grc', 'geosupport_ok', 'geosupport_error',
                    'geosupport_longitude', 'geosupport_latitude', 'geometry')


def _mapping(value, allowed, required=(), *, where):
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise SourceRecipeError(f'{where} must be a mapping with string keys')
    if unknown := set(value) - set(allowed):
        raise SourceRecipeError(f'Unknown {where} keys: {sorted(unknown)}')
    if missing := set(required) - set(value):
        raise SourceRecipeError(f'Missing {where} keys: {sorted(missing)}')
    return value


def _text(value, where):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise SourceRecipeError(f'{where} must be a nonempty string')
    return value


def _choice(value, choices, where):
    if value not in choices or not isinstance(value, str):
        raise SourceRecipeError(f'{where} must be one of {sorted(choices)}')


def _checksum(value, where):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise SourceRecipeError(f'{where} must be a lowercase SHA256 digest')


def _no_plaintext_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub('[^a-z]', '', key.lower())
            if any(word in normalized for word in ('password', 'secret', 'authorization', 'apikey', 'token')):
                raise SourceRecipeError('Credentials must use source/step secrets environment references, not plaintext parameters')
            _no_plaintext_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _no_plaintext_secrets(item)


def _validate_secrets(config):
    secrets = config.get('secrets', {})
    if not isinstance(secrets, dict):
        raise SourceRecipeError('secrets must map configuration paths to environment references')
    for path, reference in secrets.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_0-9][A-Za-z0-9_]*)*', path):
            raise SourceRecipeError('Invalid secret configuration path')
        _mapping(reference, ('env',), ('env',), where='secret reference')
        if not isinstance(reference['env'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', reference['env']):
            raise SourceRecipeError('Secret env must name an environment variable')


def _validate_python(config):
    if not isinstance(config.get('callable'), str) or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', config['callable']):
        raise SourceRecipeError('Trusted Python callable must be module:function, never inline code')
    if not isinstance(config.setdefault('parameters', {}), dict):
        raise SourceRecipeError('Python parameters must be a mapping')
    _no_plaintext_secrets(config['parameters'])
    _validate_secrets(config)
    if 'code_sha256' in config:
        _checksum(config['code_sha256'], 'code_sha256')


def _validate_rest(source):
    config = _mapping(source.get('config'), ('client', 'resource_defaults', 'resources'), ('client', 'resources'), where='REST config')
    client = _mapping(config['client'], ('base_url', 'headers', 'auth', 'paginator'), ('base_url',), where='REST client')
    parsed = urlparse(_text(client['base_url'], 'REST base_url'))
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.query:
        raise SourceRecipeError('REST base_url must be HTTP(S) without credentials or query parameters')
    if 'auth' in client:
        auth = _mapping(client['auth'], ('type', 'name', 'location'), ('type',), where='REST auth')
        _choice(auth['type'], ('bearer', 'api_key', 'http_basic'), 'REST auth.type')
        if auth['type'] != 'api_key' and set(auth) - {'type'}:
            raise SourceRecipeError('Auth name/location are only supported for api_key authentication')
        if 'name' in auth:
            _text(auth['name'], 'REST auth.name')
        if 'location' in auth:
            _choice(auth['location'], ('header', 'query', 'cookie'), 'REST auth.location')
    _no_plaintext_secrets(config)
    _validate_secrets(source)
    defaults = _mapping(config.get('resource_defaults', {}), ('endpoint', 'primary_key'), where='REST resource_defaults')
    resources = config['resources']
    if not isinstance(resources, list) or not resources:
        raise SourceRecipeError('REST resources must be a nonempty list of named endpoint mappings')
    names = []
    for resource in resources:
        _mapping(resource, ('name', 'endpoint', 'primary_key', 'selected'), ('name', 'endpoint'), where='REST resource')
        names.append(_text(resource['name'], 'REST resource.name'))
        endpoint = _mapping(resource['endpoint'], ('path', 'method', 'params', 'headers', 'paginator', 'data_selector'), ('path',), where='REST endpoint')
        _text(endpoint['path'], 'REST endpoint.path')
        if '?' in endpoint['path'] or urlparse(endpoint['path']).username:
            raise SourceRecipeError('REST endpoint paths cannot embed query parameters or credentials')
        if endpoint.get('method', 'GET') != 'GET':
            raise SourceRecipeError('Initial REST recipes support GET extraction only')
        inherited = _mapping(defaults.get('endpoint', {}), ('params', 'headers', 'paginator', 'data_selector'), where='REST default endpoint')
        effective = {**inherited, **endpoint}
        _text(effective.get('data_selector'), 'REST endpoint.data_selector')
        paginator = effective.get('paginator', client.get('paginator'))
        if not isinstance(paginator, dict):
            raise SourceRecipeError('REST recipes require an explicit paginator mapping')
        kind = paginator.get('type')
        fields = {'single_page': (), 'json_link': ('next_url_path',), 'header_link': ('links_next_key',),
                  'cursor': ('cursor_path', 'cursor_param'),
                  'offset': ('limit', 'offset', 'offset_param', 'limit_param', 'total_path', 'maximum_offset', 'stop_after_empty_page'),
                  'page_number': ('base_page', 'page_param', 'total_path', 'maximum_page', 'stop_after_empty_page')}
        if kind not in fields:
            raise SourceRecipeError('Unsupported explicit REST paginator type')
        _mapping(paginator, ('type', *fields[kind]), ('type',), where='REST paginator')
        # Incremental objects, callable steps and session instances cannot enter
        # this deliberately small configuration surface.
        for parameters in (endpoint.get('params', {}), inherited.get('params', {}), client.get('headers', {}), endpoint.get('headers', {}), inherited.get('headers', {})):
            if not isinstance(parameters, dict) or any(isinstance(item, (dict, list)) for item in parameters.values()):
                raise SourceRecipeError('REST parameters/headers must be scalar mappings; incremental extraction is unsupported')
    if len(set(names)) != len(names) or source['resource'] not in names:
        raise SourceRecipeError('REST resource names must be unique and selected resource must exist')


def validate_recipe(recipe):
    """Validate schema version 1 and return an independent JSON-safe mapping."""
    def json_values(item, depth=0):
        if depth > 40:
            raise SourceRecipeError('Recipe nesting exceeds the schema limit')
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise SourceRecipeError('Recipe mapping keys must be strings')
            for child in item.values():
                json_values(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                json_values(child, depth + 1)
    json_values(recipe)
    try:
        value = json.loads(json.dumps(recipe, allow_nan=False))
    except (ValueError, TypeError, RecursionError) as exc:
        raise SourceRecipeError('Recipe must contain finite JSON-compatible values without cycles') from exc
    _mapping(value, ('schema_version', 'name', 'source', 'import', 'geometry', 'geosupport', 'key', 'processing'),
             ('schema_version', 'name', 'source'), where='recipe')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise SourceRecipeError('Unsupported recipe schema_version; expected integer 1')
    Catalog._validate_name(value['name'])
    if 'key' in value:
        _text(value['key'], 'key')
    source = _mapping(value['source'], ('kind', 'path', 'url', 'name', 'version', 'sha256', 'archive_member',
                                      'config', 'resource', 'secrets', 'callable', 'parameters', 'code_sha256'), ('kind',), where='source')
    _choice(source['kind'], ('local', 'url', 'catalog', 'dlt_rest_api', 'python'), 'source.kind')
    locations = {'local': ('path',), 'url': ('url',), 'catalog': ('name', 'version'),
                 'dlt_rest_api': ('resource',), 'python': ('callable',)}[source['kind']]
    for field in locations:
        _text(source.get(field), 'source.' + field)
    if set(source) & ({'path', 'url', 'name', 'version', 'resource', 'callable'} - set(locations)):
        raise SourceRecipeError('Source location fields must match its kind')
    additions = {'dlt_rest_api': {'config', 'secrets'}, 'python': {'parameters', 'secrets', 'code_sha256'}}.get(source['kind'], set())
    if set(source) & ({'config', 'parameters', 'secrets', 'code_sha256'} - additions):
        raise SourceRecipeError('Source extension fields must match its kind')
    if source['kind'] in ('dlt_rest_api', 'python') and 'archive_member' in source:
        raise SourceRecipeError('Extracted records cannot select archive members')
    if source['kind'] == 'dlt_rest_api':
        _validate_rest(source)
    elif source['kind'] == 'python':
        _validate_python(source)
    if source['kind'] == 'url':
        parsed = urlparse(source['url'])
        if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or parsed.password:
            raise SourceRecipeError('source.url must be HTTP(S) without embedded credentials')
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = re.sub('[^a-z]', '', key.lower())
            if normalized.startswith('xamz') or normalized in ('sig', 'signature', 'credential', 'credentials') or any(word in normalized for word in ('password', 'secret', 'authorization', 'apikey', 'token')):
                raise SourceRecipeError('Credential-bearing URL queries cannot be saved; use a REST recipe with environment secret references')
    if source['kind'] == 'catalog':
        Catalog._validate_name(source['name'])
        if source['version'].lower() in ('latest', 'current', '*'):
            raise SourceRecipeError('Catalog sources require an exact immutable version')
        if 'archive_member' in source:
            raise SourceRecipeError('Catalog snapshots cannot select archive members')
    if 'sha256' in source:
        _checksum(source['sha256'], 'source.sha256')
    if 'archive_member' in source:
        _safe_member(source['archive_member'])
    options = _mapping(value.get('import', {}), ('format', 'layer', 'types', 'rename', 'null_policy', 'column_names'), where='import')
    if 'column_names' in options:
        _choice(options['column_names'], ('preserve', 'snake_case'), 'import.column_names')
    if 'format' in options:
        _choice(options['format'], ('CSV', 'TSV', 'Parquet', 'GeoJSON', 'GeoPackage', 'Shapefile', 'FileGDB'), 'import.format')
    if 'layer' in options:
        _text(options['layer'], 'import.layer')
    options['types'] = canonical_types(options.get('types'))
    rename = options.setdefault('rename', {})
    if not isinstance(rename, dict):
        raise SourceRecipeError('import.rename must map existing field names to new names')
    for old, new in rename.items():
        _text(old, 'rename source'); _text(new, 'rename target')
    if len(set(rename.values())) != len(rename):
        raise SourceRecipeError('Rename targets must be unique')
    nulls = _mapping(options.setdefault('null_policy', {}), ('tokens', 'trim'), where='import.null_policy')
    tokens = nulls.setdefault('tokens', [])
    if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
        raise SourceRecipeError('null_policy.tokens must be a list of exact string tokens')
    if type(nulls.setdefault('trim', False)) is not bool:
        raise SourceRecipeError('null_policy.trim must be boolean')
    value['import'] = options
    processing = value.setdefault('processing', [])
    if not isinstance(processing, list):
        raise SourceRecipeError('processing must be an ordered list of named Python steps')
    for step in processing:
        _mapping(step, ('callable', 'parameters', 'secrets', 'code_sha256'), ('callable',), where='processing step')
        _validate_python(step)
    if 'geometry' in value and 'geosupport' in value:
        raise SourceRecipeError('Choose geometry construction or geosupport, not both')
    if 'geometry' in value:
        CRS = require_spatial('pyproj', 'Source recipe geometry validation').CRS
        geometry = _mapping(value['geometry'], ('x', 'y', 'column', 'crs', 'on_null', 'on_invalid'), ('crs', 'on_null', 'on_invalid'), where='geometry')
        if ('column' in geometry) == ('x' in geometry or 'y' in geometry):
            raise SourceRecipeError('Geometry needs either column (WKB) or both x and y')
        for field in (('column',) if 'column' in geometry else ('x', 'y')):
            _text(geometry.get(field), 'geometry.' + field)
        CRS.from_user_input(_text(geometry['crs'], 'geometry.crs'))
        for field in ('on_null', 'on_invalid'):
            _choice(geometry[field], ('error', 'null'), 'geometry.' + field)
    if 'geosupport' in value:
        geo = _mapping(value['geosupport'], ('adapter', 'fields', 'runtime', 'function', 'mode', 'on_failure'),
                       ('adapter', 'fields', 'runtime', 'function', 'mode', 'on_failure'), where='geosupport')
        _choice(geo['adapter'], ('address_points',), 'geosupport.adapter')
        fields = _mapping(geo['fields'], ('borough', 'house_number', 'street'), ('borough', 'house_number', 'street'), where='geosupport.fields')
        for field in fields.values():
            _text(field, 'geosupport input field')
        _choice(geo['function'], ('1A', '1E', '1B'), 'geosupport.function')
        _choice(geo['mode'], ('regular', 'extended'), 'geosupport.mode')
        _choice(geo['on_failure'], ('error', 'record'), 'geosupport.on_failure')
        runtime = _mapping(geo['runtime'], ('extension', 'extension_sha256', 'home', 'bundle_id', 'release', 'mode', 'worker_image'),
                           ('extension', 'extension_sha256', 'home', 'bundle_id', 'release', 'mode'), where='geosupport.runtime')
        for field in ('extension', 'home', 'release'):
            _text(runtime[field], 'runtime.' + field)
        for field in ('extension_sha256', 'bundle_id'):
            _checksum(runtime[field], 'runtime.' + field)
        _choice(runtime['mode'], ('local', 'docker'), 'runtime.mode')
        if runtime['mode'] == 'docker':
            _text(runtime.get('worker_image'), 'runtime.worker_image')
        elif 'worker_image' in runtime:
            raise SourceRecipeError('worker_image is only applicable to docker runtime')
    return value


def load_recipe(path):
    """Load safe YAML; reject duplicate mapping keys and executable tags."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        pairs = loader.construct_pairs(node, deep=deep)
        result = {}
        for key, item in pairs:
            if not isinstance(key, str) or key in result:
                raise SourceRecipeError('YAML mapping keys must be unique strings')
            result[key] = item
        return result

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 1024 * 1024:
        raise SourceRecipeError('Recipe exceeds the 1 MiB schema limit')
    try:
        return validate_recipe(yaml.load(path.read_text(encoding='utf-8'), Loader=Loader))
    except yaml.YAMLError as exc:
        raise SourceRecipeError('Invalid or unsupported YAML recipe') from exc


def _hash(path):
    if Path(path).is_dir():
        return bundle_digest(Path(path))
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _path(value, base):
    path = Path(value).expanduser()
    path = path if path.is_absolute() else base / path
    if path.is_dir() or path.name.lower().endswith(('.gdb', '.gdb.zip')):
        reject_symlink_path(path)
    return path.resolve(strict=True)


def _safe_member(name):
    _text(name, 'archive_member')
    member = PurePosixPath(name)
    if member.is_absolute() or '..' in member.parts or '\\' in name:
        raise SourceRecipeError('Archive member must be a safe relative POSIX path')


def _resolved_parameters(value, references):
    resolved = json.loads(json.dumps(value))
    for path, reference in references.items():
        secret = os.environ.get(reference['env'])
        if secret is None:
            raise SourceRecipeError(f'Required secret environment variable is absent: {reference["env"]}')
        parts = path.split('.')
        parent = resolved
        try:
            for part in parts[:-1]:
                parent = parent[int(part)] if isinstance(parent, list) else parent[part]
            if isinstance(parent, list):
                parent[int(parts[-1])] = secret
            else:
                parent[parts[-1]] = secret
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise SourceRecipeError(f'Secret path does not address a declared configuration object: {path}') from exc
    return resolved


def _trusted_callable(config):
    module_name, name = config['callable'].split(':')
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, name)
    except Exception:
        raise SourceRecipeError('Trusted Python module/callable could not be imported; exception details suppressed') from None
    if not callable(function):
        raise SourceRecipeError('Named Python extension is not callable')
    filename = inspect.getsourcefile(function) or getattr(module, '__file__', None)
    if not filename or not Path(filename).is_file():
        raise SourceRecipeError('Trusted Python extension requires an inspectable module file')
    actual = _hash(filename)
    if 'code_sha256' in config and config['code_sha256'] != actual:
        raise SourceRecipeError('Trusted Python module SHA256 does not match the recipe')
    packages = package_metadata.packages_distributions().get(module_name.split('.')[0], [])
    identity = {'callable': config['callable'], 'module_path': str(Path(filename).resolve()),
                'code_sha256': actual, 'packages': {name: package_metadata.version(name) for name in packages},
                'python_version': __import__('platform').python_version(), 'trusted_python_not_sandboxed': True}
    return function, identity


def _write_extracted(items, output, types, *, source_name_hints=(), snake_case_types=False):
    """Capture one flat resource without dlt loading/schema normalization."""
    if isinstance(items, pa.RecordBatch):
        items = pa.Table.from_batches([items])
    if isinstance(items, pa.Table):
        pq.write_table(items, output)
        return items.num_rows
    writer, count, pending = None, 0, []
    try:
        def write(rows):
            nonlocal writer, count
            keys = sorted((set(source_name_hints) if snake_case_types else set(types)) |
                          {key for row in rows for key in row})
            # Keep explicitly typed capture fields lexical until the later
            # declared null/type policy runs. This stabilizes all-null first
            # pages without interpreting NA tokens or rounding numeric values.
            columns = {}
            for key in keys:
                values = [row.get(key) for row in rows]
                if key in types or (snake_case_types and snake_case(key) in types):
                    values = [None if value is None else value if isinstance(value, str) else str(value) for value in values]
                    columns[key] = pa.array(values, type=pa.string())
                else:
                    try:
                        columns[key] = pa.array(values)
                    except (pa.ArrowInvalid, pa.ArrowTypeError):
                        raise SourceRecipeError('Incompatible undeclared capture values; declare import.types or return an explicit Arrow schema') from None
            table = pa.table(columns)
            if writer is None:
                writer = pq.ParquetWriter(output, table.schema)
            elif table.schema != writer.schema:
                # No implicit widening or identifier conversion across pages.
                raise SourceRecipeError('Extracted resource schema changed across batches; supply a trusted Python source with an explicit Arrow schema')
            writer.write_table(table)
            count += table.num_rows
        try:
            iterator = iter(items)
        except Exception:
            raise SourceRecipeError('Source did not return records or an Arrow table') from None
        while True:
            try:
                item = next(iterator)
            except StopIteration:
                break
            except Exception:
                raise SourceRecipeError('Source extraction failed before publication; remote/custom exception details suppressed') from None
            if not isinstance(item, dict):
                raise SourceRecipeError('REST/Python record sources must yield mappings or return an Arrow table')
            if any(not isinstance(key, str) for key in item):
                raise SourceRecipeError('Extracted record keys must be strings')
            if any(isinstance(value, (dict, list, tuple)) for value in item.values()):
                raise SourceRecipeError('Nested record payloads require data_selector or a trusted Python source returning an explicit Arrow schema')
            pending.append(item)
            if len(pending) == 1000:
                write(pending)
                pending = []
        if pending:
            write(pending)
        if writer is None:
            if not types:
                raise SourceRecipeError('Empty extracted resource requires explicit import.types to retain its schema')
            arrow_types = {'string': pa.string(), 'bool': pa.bool_(), 'int64': pa.int64(), 'float64': pa.float64()}
            pq.write_table(pa.table({name: pa.array([], type=arrow_types[dtype]) for name, dtype in types.items()}), output)
    finally:
        if writer is not None:
            writer.close()
    return count


def _extract_records(source, stage, types, *, source_name_hints=(), snake_case_types=False):
    if source['kind'] == 'dlt_rest_api':
        try:
            import dlt
            from dlt.sources.rest_api import rest_api_resources
        except ImportError as exc:
            raise SourceRecipeError('REST recipes require the optional moses-geo[dlt] dependency') from exc
        config = _resolved_parameters(source['config'], source.get('secrets', {}))
        # Iteration uses dlt extraction only. No dlt pipeline.load, destination,
        # merge state or transactional incremental cursor is implied.
        try:
            resources = rest_api_resources(config)
            items = next(resource for resource in resources if resource.name == source['resource'])
        except Exception:
            raise SourceRecipeError('dlt REST resource configuration failed; resolved credentials are suppressed') from None
        identity = {'backend': 'dlt.sources.rest_api.rest_api_resources', 'dlt_version': dlt.__version__,
                    'resource': source['resource'], 'incremental': False, 'config': source['config'],
                    'secrets': source.get('secrets', {})}
    else:
        function, identity = _trusted_callable(source)
        try:
            items = function(**_resolved_parameters(source.get('parameters', {}), source.get('secrets', {})))
        except Exception:
            raise SourceRecipeError('Trusted Python source failed; resolved parameters are suppressed') from None
        identity = {'backend': 'trusted_python', **identity, 'parameters': source.get('parameters', {}), 'secrets': source.get('secrets', {})}
    output = stage / 'extracted.parquet'
    try:
        rows = _write_extracted(items, output, types, source_name_hints=source_name_hints,
                                snake_case_types=snake_case_types)
    except SourceRecipeError:
        raise
    except Exception:
        # HTTP/client/custom exception strings may contain authorization headers,
        # request URLs or values. Preserve the cause class, never its message.
        raise SourceRecipeError('Source extraction failed before publication; remote/custom exception details suppressed') from None
    return output, identity | {'rows': rows, 'capture_format': 'Parquet'}


def _acquire(source, catalog, base, stage, types, format=None, *, source_name_hints=(), snake_case_types=False):
    identity = dict(source)
    if source['kind'] in ('dlt_rest_api', 'python'):
        path, extraction = _extract_records(source, stage, types, source_name_hints=source_name_hints,
                                            snake_case_types=snake_case_types)
        identity['extraction'] = extraction
    elif source['kind'] == 'catalog':
        manifest = catalog.get_version(source['name'], source['version'])
        path = Path(manifest['parquet_path']).resolve(strict=True)
        identity['catalog_content_sha256'] = manifest['content_sha256']
    elif source['kind'] == 'local':
        local_path = Path(source['path']).expanduser()
        if format == 'FileGDB':
            reject_symlink_path(local_path if local_path.is_absolute() else base / local_path)
        path = _path(source['path'], base)
    else:
        basename = PurePosixPath(urlparse(source['url']).path).name or 'download'
        path = stage / basename
        with urlopen(source['url'], timeout=60) as response, path.open('wb') as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
    if not path.is_file() and not (source['kind'] == 'local' and path.is_dir() and path.suffix.lower() == '.gdb'):
        raise SourceRecipeError('Acquired source must be a regular file or local .gdb directory')
    if source['kind'] == 'local':
        # Parse a stable capture, including loose Shapefile sidecars, rather
        # than re-reading a mutable user file after its digest was computed.
        frozen = stage / 'input'
        frozen.mkdir()
        if path.is_dir():
            copy_directory(path, frozen / path.name)
        else:
            files = _shapefile_sources(path) if path.suffix.lower() == '.shp' else [str(path)]
            for filename in files:
                candidate = Path(filename)
                shutil.copyfile(candidate, frozen / candidate.name)
        path = frozen / path.name
    actual = _hash(path)
    if 'sha256' in source and actual != source['sha256']:
        raise SourceRecipeError('Source SHA256 does not match the recipe')
    identity.update({'sha256': actual, 'bytes': sum(item.stat().st_size for item in directory_files(path)) if path.is_dir() else path.stat().st_size})
    if path.is_dir():
        identity['checksum_method'] = 'sha256_relative_posix_paths_and_member_sha256'
        if 'archive_member' in source:
            raise SourceRecipeError('Directory sources cannot select archive members')
    original = path
    if 'archive_member' in source:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise SourceRecipeError('Archive has duplicate member names')
            for name in names:
                _safe_member(name)
            wanted = source['archive_member']
            if wanted not in names:
                raise SourceRecipeError('Declared archive member is absent')
            # Extract only the explicitly named member. Shapefile sidecars need
            # the existing whole-ZIP reader instead of this single-file option.
            path = stage / 'member' / PurePosixPath(wanted).name
            path.parent.mkdir()
            with archive.open(wanted) as stream, path.open('wb') as output:
                shutil.copyfileobj(stream, output)
            identity['member_sha256'] = _hash(path)
    return path, original, identity


def _retain_capture(path, catalog, stage, expected=None):
    actual = _hash(path)
    if expected is not None and actual != expected:
        raise SourceRecipeError('Source changed during preparation')
    capture = catalog.root / 'raw' / 'source-recipes' / actual / path.name
    capture.parent.mkdir(parents=True, exist_ok=True)
    if capture.exists():
        if _hash(capture) != actual:
            raise SourceRecipeError('Existing immutable source capture is corrupt')
    else:
        copied = stage / 'capture'
        if path.is_dir():
            copied = stage / ('capture-' + path.name)
            copy_directory(path, copied)
        else:
            shutil.copyfile(path, copied)
        if _hash(copied) != actual:
            raise SourceRecipeError('Source changed during preparation')
        copied.replace(capture)
    return {'name': path.name, 'sha256': actual, 'capture_path': str(capture.relative_to(catalog.root))}


def _normalize(table, options):
    source_names = table.column_names[:]
    rename = options['rename']
    if missing := set(rename) - set(table.column_names):
        raise SourceRecipeError(f'Rename fields are absent: {sorted(missing)}')
    names = [rename.get(name, name) for name in table.column_names]
    if len(set(name.lower() for name in names)) != len(names):
        raise SourceRecipeError('Renaming creates colliding field names')
    metadata = dict(table.schema.metadata or {})
    if b'geo' in metadata and rename:
        geo = json.loads(metadata[b'geo'])
        primary = geo['primary_column']
        if rename.get(primary, primary) != primary:
            raise SourceRecipeError('The canonical geometry column cannot be renamed')
    table = table.rename_columns(names).replace_schema_metadata(metadata)
    if options.get('column_names') == 'snake_case':
        mapped = column_name_map(table.column_names, 'snake_case')
        if b'geo' in metadata and mapped[json.loads(metadata[b'geo'])['primary_column']] != 'geometry':
            raise SourceRecipeError('The canonical geometry column cannot be renamed')
        table = table.rename_columns([mapped[name] for name in table.column_names]).replace_schema_metadata(metadata)
        source_map = {source: mapped[target] for source, target in zip(source_names, names)}
    nulls = options['null_policy']
    for index, field in enumerate(table.schema):
        if pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            values = []
            for item in table[field.name].to_pylist():
                item = item.strip() if item is not None and nulls['trim'] else item
                values.append(None if item in nulls['tokens'] else item)
            table = table.set_column(index, field.name, pa.array(values, type=pa.string()))
    for name, choice in options['types'].items():
        if name in table.column_names and choice != 'string' and '' in table[name].to_pylist():
            raise SourceRecipeError(f'Empty values in typed field {name!r}; explicitly include an empty null token')
    table = apply_types(table, options['types'], first_row=1)
    return table, source_map if options.get('column_names') == 'snake_case' else None


def _geometry(table, config):
    CRS = require_spatial('pyproj', 'Source recipe geometry construction').CRS
    shapely = require_spatial('shapely', 'Source recipe geometry construction')
    columns = [config['column']] if 'column' in config else [config['x'], config['y']]
    if missing := set(columns) - set(table.column_names):
        raise SourceRecipeError(f'Geometry input fields are absent: {sorted(missing)}')
    if 'geometry' in table.column_names and config.get('column') != 'geometry':
        raise SourceRecipeError('Geometry construction would overwrite an existing geometry field')
    crs = CRS.from_user_input(config['crs'])
    if config.get('column') == 'geometry' and b'geo' in (table.schema.metadata or {}):
        embedded = json.loads(table.schema.metadata[b'geo'])['columns']['geometry'].get('crs')
        if embedded and not crs.equals(CRS.from_user_input(embedded), ignore_axis_order=True):
            raise SourceRecipeError('Declared geometry CRS conflicts with the embedded CRS')
    values, nulls, invalid = [], 0, 0
    for index, row in enumerate(zip(*(table[name].to_pylist() for name in columns)), 1):
        if any(value is None for value in row):
            nulls += 1
            if config['on_null'] == 'error':
                raise SourceRecipeError(f'NULL geometry input at row {index}')
            values.append(None)
            continue
        try:
            if 'column' in config:
                geom = shapely.from_wkb(row[0])
                if geom is None or not shapely.is_valid(geom) or geom.is_empty:
                    raise ValueError('Invalid or empty WKB geometry')
            else:
                x, y = map(float, row)
                if not math.isfinite(x) or not math.isfinite(y):
                    raise ValueError('Coordinates must be finite')
                if crs.is_geographic and not (-180 <= x <= 180 and -90 <= y <= 90):
                    raise ValueError('Geographic x/y outside longitude/latitude bounds')
                geom = shapely.Point(x, y)
            values.append(shapely.to_wkb(geom))
        except (ValueError, TypeError, shapely.errors.GEOSException) as exc:
            invalid += 1
            if config['on_invalid'] == 'error':
                raise SourceRecipeError(f'Invalid geometry input at row {index}: {exc}') from exc
            values.append(None)
    if 'geometry' in table.column_names:
        table = table.set_column(table.column_names.index('geometry'), 'geometry', pa.array(values, type=pa.binary()))
    else:
        table = table.append_column('geometry', pa.array(values, type=pa.binary()))
    if config.get('column') not in (None, 'geometry'):
        table = table.drop([config['column']])
    return _with_canonical_geometry(table, 'geometry', config['crs'], ['Point'] if 'x' in config else None), {'null_input_rows': nulls, 'invalid_input_rows': invalid, 'axis_policy': 'x then y, no implicit swap', **config}


@contextmanager
def native_address_adapter(config, base_directory):
    """Load an exact native extension/bundle and yield a bounded batch caller.

    LOAD alone makes no native requests. gs_load verifies bundle payload before
    the first batch; the explicit bundle is never replaced by a mutable alias.
    """
    runtime = config['runtime']
    extension = _path(runtime['extension'], base_directory)
    home = _path(runtime['home'], base_directory)
    if _hash(extension) != runtime['extension_sha256']:
        raise SourceRecipeError('Native extension SHA256 does not match the recipe')
    manifest = json.loads((home / 'bundles' / runtime['bundle_id'] / 'manifest.json').read_text())
    if manifest['identity']['release'].lower() != runtime['release'].lower():
        raise SourceRecipeError('Native bundle release does not match the recipe')
    environment = {'GEOSUPPORT_HOME': str(home), 'GEOSUPPORT_RUNTIME': runtime['mode'],
                   'GEOSUPPORT_DOCKER_IMAGE': runtime.get('worker_image')}
    with _ENV_LOCK:
        old = {key: os.environ.get(key) for key in environment}
        con = None
        try:
            for key, item in environment.items():
                if item is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = item
            con = duckdb.connect(config={'allow_unsigned_extensions': True})
            con.execute("LOAD '" + str(extension).replace("'", "''") + "'")
            actual = con.execute('SELECT bundle_id FROM gs_load(?)', [runtime['bundle_id']]).fetchone()[0]
            if actual != runtime['bundle_id']:
                raise SourceRecipeError('Native runtime loaded a different bundle')

            def call(inputs):
                con.execute('CREATE OR REPLACE TEMP TABLE recipe_inputs(ordinal BIGINT, payload JSON)')
                con.executemany('INSERT INTO recipe_inputs VALUES (?,?)', [(index, json.dumps(item)) for index, item in enumerate(inputs)])
                con.execute('CREATE OR REPLACE TEMP TABLE recipe_results AS SELECT ordinal, gs_call(?,payload,?,?) AS result FROM recipe_inputs',
                            [config['function'], runtime['bundle_id'], config['mode']])
                rows = con.execute('SELECT result.raw,result.grc FROM recipe_results ORDER BY ordinal').fetchall()
                return [{'raw': json.loads(raw), 'grc': grc} for raw, grc in rows]

            call.provenance = {'bundle_manifest_sha256': _hash(home / 'bundles' / runtime['bundle_id'] / 'manifest.json'),
                               'bundle_identity': manifest['identity'], 'extension_path': str(extension),
                               'loaded_bundle_id': actual, 'duckdb_version': duckdb.__version__}
            yield call
        finally:
            if con is not None:
                con.close()
            for key, item in old.items():
                if item is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = item


def _geosupport(table, config, base, adapters):
    if collision := set(table.column_names) & set(_GEOCODE_COLUMNS):
        raise SourceRecipeError(f'Geosupport output fields already exist: {sorted(collision)}')
    if missing := set(config['fields'].values()) - set(table.column_names):
        raise SourceRecipeError(f'Geosupport input fields are absent: {sorted(missing)}')
    factory = adapters.get(config['adapter'], native_address_adapter)
    raw_values, statuses, longitudes, latitudes, success, errors = [], [], [], [], [], []
    with factory(config, base) as call:
        runtime_details = getattr(call, 'provenance', {})
        for batch in table.to_batches(max_chunksize=1000):
            rows = batch.to_pylist()
            inputs = [{'borough_code': row[config['fields']['borough']],
                       'house_number': row[config['fields']['house_number']],
                       'street_name': row[config['fields']['street']]} for row in rows]
            results = call(inputs)
            if len(results) != len(rows):
                raise SourceRecipeError('Geosupport adapter changed row count')
            for result in results:
                raw = result['raw']
                if not isinstance(raw, dict):
                    raise SourceRecipeError('Geosupport adapter raw output must be an object')
                grc = result.get('grc')
                try:
                    x, y = float(raw.get('Longitude')), float(raw.get('Latitude'))
                    valid = math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90
                except (TypeError, ValueError):
                    x, y, valid = None, None, False
                ok = str(grc).strip() in ('00', '01', '0', '1') and valid
                if not ok and config['on_failure'] == 'error':
                    raise SourceRecipeError(f'Geosupport failed at row {len(statuses)+1}, GRC={grc!r}; no output published')
                raw_values.append(json.dumps(raw, sort_keys=True, allow_nan=False))
                statuses.append(None if grc is None else str(grc))
                success.append(ok)
                errors.append(None if ok else ('invalid_coordinates' if str(grc).strip() in ('00', '01', '0', '1') else 'return_code'))
                longitudes.append(x if ok else None); latitudes.append(y if ok else None)
    for name, values, dtype in (
        ('geosupport_raw', raw_values, pa.string()), ('geosupport_grc', statuses, pa.string()),
        ('geosupport_error', errors, pa.string()),
        ('geosupport_ok', success, pa.bool_()), ('geosupport_longitude', longitudes, pa.float64()),
        ('geosupport_latitude', latitudes, pa.float64())):
        table = table.append_column(name, pa.array(values, type=dtype))
    table, geometry = _geometry(table, {'x': 'geosupport_longitude', 'y': 'geosupport_latitude', 'crs': 'EPSG:4326', 'on_null': 'null', 'on_invalid': 'error'})
    return table, {'adapter': config['adapter'], 'runtime': config['runtime'], 'function': config['function'],
                   'runtime_details': runtime_details,
                   'mode': config['mode'], 'on_failure': config['on_failure'], 'rows': len(success),
                   'successful_rows': sum(success), 'failed_rows': len(success)-sum(success),
                   'all_rows_retained': True, 'historical_runtime_attested': False, 'geometry': geometry}


def prepare_recipe(recipe_or_path, catalog: Catalog, *, base_directory=None,
                   extension_directory=None, adapters=None, column_names=None):
    """Prepare and publish one recipe; failures preserve the current version.

    ``adapters`` is a Python test/integration injection only, never YAML code.
    Factories receive (geosupport_config, base_directory), and yield a batch
    caller accepting input dicts and returning equally many {raw, grc} dicts.
    ``extension_directory`` is reserved for CLI compatibility; the native binary
    is always the explicitly hashed runtime.extension from the recipe.
    """
    if isinstance(recipe_or_path, (str, Path)):
        path = Path(recipe_or_path).resolve(strict=True)
        recipe = load_recipe(path)
        base = path.parent if base_directory is None else Path(base_directory).resolve(strict=True)
    else:
        recipe = validate_recipe(recipe_or_path)
        base = Path(base_directory or '.').resolve(strict=True)
    naming = resolve_column_names(explicit=column_names, recipe=recipe['import'].get('column_names'))
    if naming['origin'] != 'built_in' or 'column_names' in recipe['import']:
        recipe['import']['column_names'] = naming['column_names']
    fingerprint = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='recipe-', dir=catalog.root / '.staging') as temporary:
        stage = Path(temporary)
        options = recipe['import']
        inverse_rename = {new: old for old, new in options['rename'].items()}
        if options.get('column_names') == 'snake_case':
            # Capture schemas use source names; recipe type choices use final names.
            capture_types = {inverse_rename.get(target, target): dtype
                             for name, dtype in options['types'].items()
                             for target in [next((new for new in options['rename'].values()
                                                  if snake_case(new) == name), name)]}
        else:
            capture_types = {inverse_rename.get(name, name): dtype for name, dtype in options['types'].items()}
        source_name_hints = {raw for raw in inverse_rename.values() if raw in capture_types}
        path, original, source = _acquire(recipe['source'], catalog, base, stage, capture_types, options.get('format'),
                                          source_name_hints=source_name_hints,
                                          snake_case_types=options.get('column_names') == 'snake_case')
        table, read_metadata = read_vector(path, layer=options.get('layer'), format=options.get('format'))
        table, column_name_mapping = _normalize(table, options)
        normalization = {'import': options, 'reader': read_metadata}
        if column_name_mapping is not None:
            normalization['column_name_map'] = column_name_mapping
        steps = []
        for config in recipe['processing']:
            function, identity = _trusted_callable(config)
            before = table.num_rows
            try:
                result = function(table, **_resolved_parameters(config['parameters'], config.get('secrets', {})))
                processed = stage / 'processed.parquet'
                _write_extracted(result, processed, options['types'])
                table = pq.read_table(processed)
            except Exception:
                raise SourceRecipeError('Trusted Python processing step failed before publication; resolved parameters are suppressed') from None
            steps.append({**identity, 'parameters': config['parameters'], 'secrets': config.get('secrets', {}),
                          'input_rows': before, 'output_rows': table.num_rows})
        normalization['processing'] = steps
        if 'geometry' in recipe:
            table, normalization['geometry'] = _geometry(table, recipe['geometry'])
        if 'geosupport' in recipe:
            table, normalization['geosupport'] = _geosupport(table, recipe['geosupport'], base, adapters or {})
        # Validate keys before creating any retained capture or catalog release.
        Catalog._validate_key(table, recipe.get('key'))
        capture = _retain_capture(original, catalog, stage, source['sha256'])
        source['capture_path'] = capture['capture_path']
        if original.suffix.lower() == '.shp':
            source['sidecar_captures'] = [_retain_capture(Path(item), catalog, stage)
                                          for item in read_metadata['source_files'] if Path(item) != original]
        prepared = stage / 'prepared.parquet'
        pq.write_table(table, prepared)
        dependencies = {}
        for name in ('pyarrow', 'duckdb', 'shapely', 'pyproj', 'pyogrio'):
            try:
                dependencies[name] = package_metadata.version(name)
            except package_metadata.PackageNotFoundError:
                pass
        engine = {'module': __name__, 'code_sha256': _hash(__file__),
                  'dependencies': dependencies}
        provenance = {'source_recipe': {'schema_version': 1, 'recipe_sha256': fingerprint, 'recipe': recipe,
                                        'engine': engine,
                                        'source': source, 'normalization': normalization}}
        manifest = catalog.ingest(prepared, name=recipe['name'], key=recipe.get('key'),
                                  provenance=provenance, column_names='preserve')
    return {'status': 'prepared', 'recipe_sha256': fingerprint, 'engine': engine, 'source': source,
            'normalization': normalization, 'manifest': manifest}
