"""Prepare locked PLUTO inputs, including the native Geosupport recipes.

Relations scan immutable catalog Parquet directly. Native calls are evaluated
once into bounded batch tables before their JSON is projected. This is a
provisional reconstruction: choosing a local native bundle does not establish
which mutable upstream Geosupport image produced the historical release.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

import duckdb

from .raw_normalize import _hash, _identifier as ident, _literal as literal


class FullSourceError(ValueError):
    pass


# pandas read_csv default missing tokens, used by the pinned ingestion recipe.
NA_TOKENS = ('', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN',
             '-nan', '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL',
             'NaN', 'None', 'n/a', 'nan', 'null')


GEO_FIELDS = {
    'billingbbl': ('Condominium Billing BBL',),
    'bbl': ('BOROUGH BLOCK LOT (BBL)', 'BOROUGH BLOCK LOT (BBL)'),
    'cd': ('COMMUNITY DISTRICT', 'COMMUNITY DISTRICT'),
    'ct2010': ('2010 Census Tract',), 'cb2010': ('2010 Census Block',),
    'ct2020': ('2020 Census Tract',), 'cb2020': ('2020 Census Block',),
    'schooldist': ('Community School District',), 'council': ('City Council District',),
    'zipcode': ('ZIP Code',), 'policeprct': ('Police Precinct',),
    'healthcenterdistrict': ('Health Center District',), 'healtharea': ('Health Area',),
    'sanitdistrict': ('Sanitation District',),
    'sanitsub': ('Sanitation Collection Scheduling Section and Subsection',),
    'boepreferredstreetname': ('BOE Preferred Street Name',),
    'taxmap': ('Tax Map Number Section & Volume',),
    'sanbornmapidentifier': ('SBVP (SANBORN MAP IDENTIFIER)', 'SBVP (SANBORN MAP IDENTIFIER)'),
    'latitude': ('Latitude',), 'longitude': ('Longitude',),
    'grc': ('Geosupport Return Code (GRC)',),
    'grc2': ('Geosupport Return Code 2 (GRC 2)',),
    'msg': ('Message',), 'msg2': ('Message 2',),
}


def _json(raw, *keys):
    path = '$' + ''.join('.' + json.dumps(key) for key in keys)
    return f'json_extract_string({raw}, {literal(path)})'


def _success(geo):
    # Pinned python-geosupport accepts numeric GRC 00 and 01, regardless GRC2.
    return f"coalesce(try_cast({geo}.grc AS INTEGER) IN (0, 1), false)"


def _shallow_json_merge(extended, regular):
    """Python dictionary-union semantics, including explicit JSON null values."""
    return ("(SELECT coalesce(json_group_object(key, value), '{}'::JSON) FROM (SELECT key, value FROM ("
            f"SELECT key, value, 0 priority FROM json_each({extended}) UNION ALL "
            f"SELECT key, value, 1 priority FROM json_each({regular})"
            ") entries QUALIFY row_number() OVER (PARTITION BY key ORDER BY priority DESC)=1) selected)")


_NATIVE_MACROS = ('gs_address', 'gs_bbl', 'gs_bin', 'gs_call')


def _native_macros(con):
    placeholders = ','.join('?' for _ in _NATIVE_MACROS)
    return con.execute(
        'SELECT function_name, function_type, parameters, parameter_types, varargs, macro_definition '
        'FROM duckdb_functions() WHERE database_name=current_database() AND schema_name=\'main\' '
        f'AND lower(function_name) IN ({placeholders}) ORDER BY function_name', list(_NATIVE_MACROS)).fetchall()


def _reset_native_macros(con, runtime, fingerprint):
    """Remove only verified extension-generated macros from a prior connection.

    Native C++ registrations are transient, but the extension creates four
    persistent SQL macros. A fresh connection must clear those exact definitions
    before LOAD. Never reuse a connection after a failed native LOAD: it may have
    partially registered C++ functions even though initialization raised.
    """
    rows = con.execute('SELECT fingerprint FROM source_work.identity').fetchall()
    if rows != [(fingerprint,)]:
        raise FullSourceError('Cannot reset native macros: source identity does not match')
    binary = Path(runtime['extension_path']).resolve(strict=True)
    if _hash(binary) != runtime['extension_sha256']:
        raise FullSourceError('Cannot reset native macros: extension checksum does not match')
    if con.execute("SELECT count(*) FROM duckdb_functions() WHERE database_name='system' AND function_name='_gs_call'").fetchone()[0]:
        raise FullSourceError('Native functions already initialized; reopen the connection before resetting macros')
    existing = _native_macros(con)
    if not existing:
        return []
    # Definitions and signatures are obtained from the exact pinned binary using
    # an isolated catalog. Loading registers functions; it makes no native calls.
    expected_con = duckdb.connect(config={'allow_unsigned_extensions': True})
    try:
        expected_con.execute('LOAD ' + literal(binary))
        expected = {row[0]: row for row in _native_macros(expected_con)}
    finally:
        expected_con.close()
    if set(expected) != set(_NATIVE_MACROS):
        raise FullSourceError('Pinned extension does not define the expected native macros')
    if any(expected.get(row[0]) != row for row in existing):
        raise FullSourceError('Refusing to replace a native macro with an unexpected definition or signature')
    database = ident(con.execute('SELECT current_database()').fetchone()[0])
    con.execute('BEGIN')
    try:
        for name in _NATIVE_MACROS:
            if any(row[0] == name for row in existing):
                con.execute(f'DROP MACRO {database}.main.{ident(name)}')
        con.execute('COMMIT')
    except BaseException:
        con.execute('ROLLBACK')
        raise
    return [row[0] for row in existing]


def _schema(con, query):
    return [(r[0], r[1]) for r in con.execute('DESCRIBE ' + query).fetchall()]


def _project_geometry(con, manifest, *, raw):
    query = 'SELECT * FROM read_parquet(' + literal(manifest['parquet_path']) + ')'
    fields = []
    normalization = manifest.get('provenance', {}).get('normalization', {})
    if not isinstance(normalization, dict):
        normalization = {}
    csv = normalization.get('csv_null_policy') is not None
    for name, dtype in _schema(con, query):
        column = ident(name)
        if dtype.startswith('GEOMETRY'):
            # Legacy PostgreSQL sources expose native geometry as wkb_geometry.
            fields.append(f'CAST({column} AS GEOMETRY) AS wkb_geometry')
        elif name in ('wkb_geometry', 'geom') and dtype == 'BLOB':
            fields.append(f'ST_GeomFromWKB({column}) AS {column}')
        elif raw and csv and dtype == 'VARCHAR':
            tokens = ', '.join(literal(t) for t in NA_TOKENS)
            fields.append(f'CASE WHEN {column} IN ({tokens}) THEN NULL ELSE {column} END AS {column}')
        elif manifest['dataset'].removeprefix('raw__') == 'dcp_transit_zone_ranks' and name == 'tz_rank':
            fields.append(f'CAST({column} AS INTEGER) AS {column}')
        else:
            fields.append(column)
    return 'SELECT ' + ', '.join(fields) + ' FROM (' + query + ')'


def _native_config(release, extension_path, home):
    release = release or os.environ.get('MOSES_GEOSUPPORT_RELEASE')
    extension_path = extension_path or os.environ.get('MOSES_GEOSUPPORT_EXTENSION')
    home = home or os.environ.get('GEOSUPPORT_HOME')
    if not release or not extension_path or not home:
        raise FullSourceError('Native reconstruction requires explicit MOSES_GEOSUPPORT_RELEASE, '
                              'MOSES_GEOSUPPORT_EXTENSION and GEOSUPPORT_HOME; historical runtime is unresolved')
    extension_path = Path(extension_path).resolve(strict=True)
    home = Path(home).resolve(strict=True)
    alias = json.loads((home / 'aliases' / (release.lower() + '.json')).read_text())
    bundle = home / 'bundles' / alias['bundle_id']
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest['identity']['release'] != release.lower():
        raise FullSourceError('Geosupport alias release does not match bundle')
    return {'release': release.lower(), 'bundle_id': alias['bundle_id'],
            'engine_version': manifest['identity']['engine_version'],
            'extension_path': str(extension_path), 'extension_sha256': _hash(extension_path),
            'home': str(home), 'historical_runtime_attested': False,
            'runtime': os.environ.get('GEOSUPPORT_RUNTIME', 'local'),
            'worker_image': os.environ.get('GEOSUPPORT_DOCKER_IMAGE', 'duckdb-geosupport-runtime:0.2.0'),
            'selection': 'explicit local reconstruction bundle; not an assertion about upstream mutable image'}


def _materialize_batches(con, stage, keys, expression, projection, *, batch_size, progress):
    """Persist compact results and resume only committed batches of this stage."""
    con.execute('CREATE TABLE IF NOT EXISTS source_work.checkpoints(stage VARCHAR PRIMARY KEY, completed BIGINT)')
    old = con.execute('SELECT completed FROM source_work.checkpoints WHERE stage=?', [stage]).fetchone()
    start = old[0] if old else 0
    total = con.execute('SELECT count(*) FROM ' + keys).fetchone()[0]
    for low in range(start, total, batch_size):
        began = time.monotonic()
        con.execute('BEGIN')
        try:
            con.execute('CREATE OR REPLACE TABLE source_work.native_batch AS SELECT *, ' + expression +
                        f' AS geo FROM {keys} WHERE source_row > {low} AND source_row <= {low + batch_size}')
            query = projection + ' FROM source_work.native_batch'
            if not old and low == 0:
                con.execute(f'CREATE OR REPLACE TABLE source_work.{stage} AS ' + query)
            else:
                con.execute(f'INSERT INTO source_work.{stage} ' + query)
            con.execute('DROP TABLE source_work.native_batch')
            completed = min(low + batch_size, total)
            con.execute('INSERT OR REPLACE INTO source_work.checkpoints VALUES (?, ?)', [stage, completed])
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
        if progress:
            progress(f'Geosupport {stage}: {completed:,}/{total:,} ({time.monotonic()-began:.1f}s batch)')
    # Empty input still needs a typed relation for dbt binding.
    if total == 0 and not old:
        con.execute('CREATE OR REPLACE TABLE source_work.native_batch AS SELECT *, ' + expression + f' AS geo FROM {keys} LIMIT 0')
        con.execute(f'CREATE OR REPLACE TABLE source_work.{stage} AS ' + projection + ' FROM source_work.native_batch')
        con.execute('DROP TABLE source_work.native_batch')


def _geocode(con, runtime, *, batch_size, progress):
    release = literal(runtime['bundle_id'])
    call = lambda function, inputs, mode='regular': f'gs_call({literal(function)}, to_json({inputs}), release := {release}, mode := {literal(mode)})'
    con.execute('CREATE TABLE IF NOT EXISTS source_work.geo_keys AS SELECT row_number() OVER (ORDER BY boro, block, lot) source_row, * FROM (SELECT DISTINCT boro, block, lot FROM source_raw.pluto_input_geocodes)')
    # Keep the small fields needed by parse_output, rather than citywide full JSON.
    needed = list(dict.fromkeys(k[0] for k in GEO_FIELDS.values())) + ['Fire Company Type', 'Fire Company Number']
    fallback = '(SELECT json_group_object(key, value) FROM json_each(geo.raw) WHERE key IN (' + ','.join(literal(k) for k in needed) + '))'
    address_list = "json_extract(geo.raw, '$.\"LIST OF GEOGRAPHIC IDENTIFIERS\"')"
    address = f"(SELECT value FROM json_each({address_list}) WHERE coalesce(json_extract_string(value, '$.\"Low House Number\"'), '') <> '' AND coalesce(json_extract_string(value, '$.\"5-Digit Street Code\"'), '') <> '' ORDER BY cast(key AS INTEGER) LIMIT 1)"
    _materialize_batches(con, 'bl', 'source_work.geo_keys',
        call('BL', "{'bbl': boro || block || lot}"),
        f'SELECT source_row, {_success("geo")} ok, {fallback} raw, CASE WHEN {_success("geo")} THEN {address} END address, {_json("geo.raw", "Number of Existing Structures on Lot")} structures',
        batch_size=batch_size, progress=progress)
    con.execute('CREATE OR REPLACE TABLE source_work.street_keys AS SELECT row_number() OVER (ORDER BY b5sc) source_row, b5sc FROM (SELECT DISTINCT '+
                _json('address', 'Borough Code') + ' || ' + _json('address', '5-Digit Street Code') + ' b5sc FROM source_work.bl WHERE address IS NOT NULL)')
    _materialize_batches(con, 'street', 'source_work.street_keys', call('D', "{'B5SC': b5sc}"),
        f'SELECT source_row, b5sc, CASE WHEN {_success("geo")} THEN coalesce({_json("geo.raw", "First Street Name Normalized")}, \'\') ELSE \'\' END sname',
        batch_size=batch_size, progress=progress)
    con.execute('CREATE OR REPLACE TABLE source_work.address_keys AS SELECT k.*, coalesce(s.sname, \'\') sname, coalesce('+_json('b.address', 'Low House Number')+", '') hnum FROM source_work.geo_keys k JOIN source_work.bl b USING(source_row) LEFT JOIN source_work.street s ON s.b5sc = "+_json('b.address', 'Borough Code')+' || '+_json('b.address', '5-Digit Street Code'))
    address_inputs = "{'street_name': sname, 'house_number': hnum, 'borough': boro}"
    _materialize_batches(con, 'regular', 'source_work.address_keys', call('1A', address_inputs),
        f'SELECT source_row, {_success("geo")} ok, {fallback} raw', batch_size=batch_size, progress=progress)
    # Use a contiguous sequence for the subset that reaches 1E in the try block.
    con.execute('CREATE OR REPLACE TABLE source_work.extended_keys AS SELECT row_number() OVER (ORDER BY a.source_row) source_row, a.source_row geo_row, a.boro, a.sname, a.hnum FROM source_work.address_keys a JOIN source_work.regular r USING(source_row) WHERE r.ok')
    _materialize_batches(con, 'extended', 'source_work.extended_keys', call('1E', address_inputs, 'extended'),
        f'SELECT source_row, geo_row, {_success("geo")} ok, {fallback} raw', batch_size=batch_size, progress=progress)
    # Python merges dictionaries at the top level. Regular keys (including blank
    # values) replace extended keys. JSON objects retain nested BBL/CD fields.
    con.execute("CREATE OR REPLACE TABLE source_work.geo_selected AS SELECT k.*, a.sname input_sname, a.hnum input_hnum, CASE WHEN b.address IS NOT NULL THEN coalesce(b.structures, '') ELSE '' END numberofexistingstructures, CASE WHEN r.ok AND e.ok THEN " + _shallow_json_merge('e.raw', 'r.raw') + " WHEN b.ok THEN b.raw WHEN r.ok THEN e.raw ELSE r.raw END raw FROM source_work.geo_keys k JOIN source_work.address_keys a USING(source_row) JOIN source_work.bl b USING(source_row) JOIN source_work.regular r USING(source_row) LEFT JOIN source_work.extended e ON e.geo_row=k.source_row")
    fields = []
    for field, keys in GEO_FIELDS.items():
        expression = _json('raw', *keys)
        if field in ('latitude', 'longitude'):
            expression = f"nullif({expression}, '')"
        fields.append(expression + ' AS ' + ident(field))
    fire = f"nullif(coalesce({_json('raw', 'Fire Company Type')}, '') || coalesce({_json('raw', 'Fire Company Number')}, ''), '') AS firecomp"
    con.execute('CREATE OR REPLACE TABLE sources.pluto_input_geocodes AS SELECT ' + ', '.join(fields) + ', '+fire+", boro borough, block, lot, '' easement, input_sname, input_hnum, numberofexistingstructures, CASE WHEN try_cast(latitude AS DOUBLE) IS NOT NULL AND try_cast(longitude AS DOUBLE) IS NOT NULL THEN ST_Point(cast(latitude AS DOUBLE), cast(longitude AS DOUBLE)) END geom FROM source_work.geo_selected")
    con.execute('CREATE TABLE IF NOT EXISTS source_work.bin_keys AS SELECT row_number() OVER (ORDER BY bin) source_row, bin, count(*) multiplicity FROM source_raw.pluto_input_numbldgs GROUP BY bin')
    _materialize_batches(con, 'bin_regular', 'source_work.bin_keys', call('BN', "{'bin': bin}"),
        f'SELECT source_row, bin, multiplicity, {_success("geo")} ok, geo.bbl bbl', batch_size=batch_size, progress=progress)
    con.execute('CREATE OR REPLACE TABLE source_work.bin_tpad_keys AS SELECT row_number() OVER (ORDER BY source_row) source_row, source_row bin_row, bin FROM source_work.bin_regular WHERE NOT ok')
    _materialize_batches(con, 'bin_tpad', 'source_work.bin_tpad_keys', call('BN', "{'bin': bin}", 'tpad'),
        'SELECT source_row, bin_row, geo.bbl bbl', batch_size=batch_size, progress=progress)
    con.execute("CREATE OR REPLACE TABLE sources.pluto_input_numbldgs AS SELECT bbl, sum(multiplicity)::BIGINT count FROM (SELECT r.multiplicity, nullif(CASE WHEN r.ok THEN r.bbl ELSE t.bbl END, '') bbl FROM source_work.bin_regular r LEFT JOIN source_work.bin_tpad t ON r.source_row=t.bin_row) WHERE bbl IS NOT NULL GROUP BY bbl")
    return {'geocode_rows': con.execute('SELECT count(*) FROM sources.pluto_input_geocodes').fetchone()[0],
            'building_count_rows': con.execute('SELECT count(*) FROM sources.pluto_input_numbldgs').fetchone()[0],
            'axis_policy': 'captured recipe x=latitude y=longitude retained; downstream upstream coordinate backfill uses longitude/latitude',
            'calls': dict(con.execute('SELECT stage, completed FROM source_work.checkpoints').fetchall())}


def prepare_sources(catalog, lock, database_path, extension_directory, *,
                    geosupport_release=None, geosupport_extension=None,
                    geosupport_home=None, batch_size=10000, progress=None):
    """Create source relations from exact catalog versions, with no Arrow reads.

    The native release/extension/store must be explicit arguments or environment
    settings. Reopening the same database resumes committed native batches only
    when the complete input/runtime fingerprint still agrees.
    """
    if isinstance(lock, (str, Path)):
        lock = json.loads(Path(lock).read_text())
    versions = lock.get('versions', lock.get('input_lock', {}).get('versions'))
    if not isinstance(versions, dict) or not versions:
        raise FullSourceError('A nonempty explicit versions lock is required')
    if not isinstance(batch_size, int) or batch_size < 1:
        raise FullSourceError('batch_size must be a positive integer')
    manifests, aliases = {}, {}
    for name, version in versions.items():
        if not isinstance(version, str) or not version:
            raise FullSourceError('Every locked version must be explicit')
        alias = name.removeprefix('raw__')
        if alias in aliases or alias in ('pluto', 'export_pluto'):
            raise FullSourceError(f'Ambiguous or finished-product source: {alias}')
        manifest = catalog.get_version(name, version)
        if manifest['version'] != version:
            raise FullSourceError('Catalog returned a different version')
        manifests[name] = manifest
        aliases[alias] = name
    native_needed = any(name in aliases and versions[aliases[name]] and aliases[name].startswith('raw__')
                        for name in ('pluto_input_geocodes', 'pluto_input_numbldgs'))
    runtime = _native_config(geosupport_release, geosupport_extension, geosupport_home) if native_needed else None
    identity = {'versions': versions, 'content': {n: m['content_sha256'] for n, m in manifests.items()},
                'runtime': runtime, 'code_sha256': _hash(Path(__file__))}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = database_path.with_suffix('.sources.json')
    con = duckdb.connect(str(database_path), config={'allow_unsigned_extensions': bool(runtime)})
    try:
        con.execute('SET extension_directory=' + literal(Path(extension_directory).resolve()))
        con.execute('SET autoinstall_known_extensions=false')
        con.execute('SET autoload_known_extensions=false')
        con.execute("SET memory_limit='1GB'")
        con.execute('SET threads=1')
        con.execute('LOAD spatial')
        con.execute('CREATE SCHEMA IF NOT EXISTS source_work')
        con.execute('CREATE TABLE IF NOT EXISTS source_work.identity(fingerprint VARCHAR)')
        old = con.execute('SELECT fingerprint FROM source_work.identity').fetchone()
        if old and old[0] != fingerprint:
            raise FullSourceError('Existing source database has different locked inputs, code or native runtime; choose a new database')
        if not old:
            con.execute('INSERT INTO source_work.identity VALUES (?)', [fingerprint])
        con.execute('CREATE SCHEMA IF NOT EXISTS source_raw')
        con.execute('CREATE SCHEMA IF NOT EXISTS sources')
        relations, records = {}, []
        for alias, name in aliases.items():
            manifest = manifests[name]
            raw = name.startswith('raw__')
            query = _project_geometry(con, manifest, raw=raw)
            con.execute(f'CREATE OR REPLACE VIEW source_raw.{ident(alias)} AS ' + query)
            relations[alias] = 'sources.' + ident(alias)
            if alias not in ('pluto_input_geocodes', 'pluto_input_numbldgs') or not raw:
                con.execute(f'CREATE OR REPLACE VIEW sources.{ident(alias)} AS SELECT * FROM source_raw.{ident(alias)}')
            records.append({'catalog_name': name, 'catalog_version': versions[name], 'alias': alias,
                            'rows': manifest['row_count'], 'content_sha256': manifest['content_sha256'],
                            'parquet_path': manifest['parquet_path'], 'provisional': raw,
                            'normalization': manifest.get('provenance', {}).get('normalization'),
                            'source': manifest.get('provenance', {}).get('source')})
        # Names used by historical staging SQL and the current source inventory.
        if 'previous_pluto' not in relations and 'dcp_pluto' in relations:
            relations['previous_pluto'] = relations['dcp_pluto']
        for alias, target in {'dcp_pfirms': 'fema_pfirms2015_100yr',
                              'dcp_pluto': 'previous_pluto', 'dcp_mappluto': 'previous_pluto'}.items():
            if target in relations:
                relations[alias] = relations[target]
        report = {'database_path': str(database_path), 'source_relations': relations,
                  'input_lock': {'versions': versions}, 'inputs': records,
                  'fingerprint': fingerprint, 'code_sha256': identity['code_sha256'],
                  'native_runtime': runtime, 'status': 'preparing',
                  'production_parity': False, 'historical_normalized_lineage_attested': False,
                  'transform_engine': 'DuckDB SELECT/table materialization; no PostgreSQL execution',
                  'resource_limits': {'memory_limit': '1GB', 'threads': 1, 'native_batch_rows': batch_size},
                  'report_path': str(report_path)}
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        if runtime:
            os.environ['GEOSUPPORT_HOME'] = runtime['home']
            report['native_macros_reset'] = _reset_native_macros(con, runtime, fingerprint)
            con.execute('LOAD ' + literal(runtime['extension_path']))
            actual = con.execute('SELECT bundle_id FROM gs_load(?)', [runtime['bundle_id']]).fetchone()[0]
            if actual != runtime['bundle_id']:
                raise FullSourceError('Loaded native bundle identity differs')
            report['native_execution'] = _geocode(con, runtime, batch_size=batch_size, progress=progress)
        report['status'] = 'prepared_provisional' if any(r['provisional'] for r in records) else 'prepared'
        report['source_count'] = len(records)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        return report
    finally:
        con.close()
