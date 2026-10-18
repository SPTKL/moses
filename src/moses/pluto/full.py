"""Run the complete pinned PLUTO port as a local, auditable dbt candidate build.

A completed candidate is not an attestation of historical production parity.
Reference PLUTO is opened only after dbt has produced its independent output.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
import uuid

import duckdb

from ..catalog import Catalog

UPSTREAM_COMMIT = "32bc98f632f15e7182933a17fb61ecf74e853518"


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _save(path, report):
    temp = Path(path).with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2, default=str, allow_nan=False) + '\n')
    temp.replace(path)


def compare_release(con, candidate, reference, output_dir):
    """SQL-based, null-aware comparison with bounded discrepancy examples.

    CSV numeric values are adapted to the candidate's declared numeric types,
    with no additional tolerance. Text keeps its exact content. Published CSV
    cannot establish spatial equivalence.
    """
    reference = Path(reference).resolve(strict=True)
    output_dir = Path(output_dir)
    con.execute(f"CREATE OR REPLACE TEMP VIEW reference_pluto AS SELECT * FROM read_csv({_literal(reference)}, header=true, all_varchar=true, nullstr='')")
    actual = con.execute(f'DESCRIBE SELECT * FROM {candidate}').fetchall()
    expected = con.execute('DESCRIBE reference_pluto').fetchall()
    acols = {r[0].lower(): (r[0], r[1]) for r in actual}
    ecols = {r[0].lower(): r[0] for r in expected}
    if 'bbl' not in acols or 'bbl' not in ecols:
        raise ValueError('Both candidate and reference require BBL')
    for relation, column in [(candidate, acols['bbl'][0]), ('reference_pluto', ecols['bbl'])]:
        n, unique, invalid = con.execute(f'SELECT count(*), count(DISTINCT try_cast({_identifier(column)} AS DECIMAL(20,0))), count(*) FILTER (WHERE NOT regexp_full_match(cast({_identifier(column)} AS VARCHAR), \'[1-5][0-9]{{9}}([.]0+)?\') OR {_identifier(column)} IS NULL) FROM {relation}').fetchone()
        if n != unique or invalid:
            raise ValueError(f'{relation}: comparison requires unique canonical BBLs')
    # DECIMAL removes CSV decimal formatting without truncating malformed BBLs.
    ck = f'try_cast(c.{_identifier(acols["bbl"][0])} as decimal(20,0))'
    rk = f'try_cast(r.{_identifier(ecols["bbl"])} as decimal(20,0))'
    counts = con.execute(f'SELECT count(*) FILTER (WHERE {rk} IS NULL), count(*) FILTER (WHERE {ck} IS NULL), count(*) FILTER (WHERE {ck} IS NOT NULL AND {rk} IS NOT NULL) FROM {candidate} c FULL JOIN reference_pluto r ON {ck}={rk}').fetchone()
    comparisons = []
    common = [name for name in acols if name in ecols]
    expressions = []
    predicates = {}
    for name in common:
        col, dtype = acols[name]
        c, r = f'c.{_identifier(col)}', f'r.{_identifier(ecols[name])}'
        if re.match(r'^(DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL|BIGINT|INTEGER|SMALLINT|HUGEINT|UBIGINT)', dtype):
            predicate = f'({c} IS DISTINCT FROM try_cast({r} AS {dtype}) OR ({r} IS NOT NULL AND try_cast({r} AS {dtype}) IS NULL))'
        else:
            predicate = f'cast({c} AS VARCHAR) IS DISTINCT FROM {r}'
        predicates[name] = predicate
        expressions.append(f'count(*) FILTER (WHERE {predicate})')
    numbers = con.execute(f'SELECT {", ".join(expressions)} FROM {candidate} c JOIN reference_pluto r ON {ck}={rk}').fetchone()
    for name, n in zip(common, numbers):
        comparisons.append({'column': name, 'mismatched_rows': n})
    worst = sorted(comparisons, key=lambda x: x['mismatched_rows'], reverse=True)
    examples = {}
    for item in worst[:12]:
        if not item['mismatched_rows']:
            continue
        name = item['column']
        rows = con.execute(f'SELECT {ck} AS bbl, cast(c.{_identifier(acols[name][0])} AS VARCHAR), r.{_identifier(ecols[name])} FROM {candidate} c JOIN reference_pluto r ON {ck}={rk} WHERE {predicates[name]} ORDER BY 1 LIMIT 20').fetchall()
        examples[name] = [{'bbl': str(row[0]), 'candidate': row[1], 'reference': row[2]} for row in rows]
    result = {
        'reference': str(reference), 'reference_sha256': _hash(reference),
        'added_bbls': counts[0], 'removed_bbls': counts[1], 'matched_bbls': counts[2],
        'candidate_only_columns': sorted(acols.keys() - ecols.keys()),
        'reference_only_columns': sorted(ecols.keys() - acols.keys()),
        'columns': comparisons, 'examples': examples,
        'policy': 'Exact null-aware values; reference numerics cast to candidate declared types; CSV empty fields are null. Version is compared and expected to differ for a candidate.',
        'spatial_comparison': 'not_available_from_tabular_reference',
        'production_parity': False,
    }
    result['all_compared_values_equal'] = not any(numbers) and not counts[0] and not counts[1] and set(acols) == set(ecols)
    _save(output_dir / 'reference-comparison.json', result)
    return result


def export_spatial(con, outputs, output_dir):
    """Write MapPLUTO geometry with the upstream State Plane CRS explicitly."""
    import pyarrow.parquet as pq
    paths, validation = [], {}
    for name in ('mappluto', 'mappluto_unclipped'):
        if name not in outputs:
            continue
        relation = _identifier(name)
        fields = con.execute(f'DESCRIBE {relation}').fetchall()
        geometries = [r[0] for r in fields if r[1].startswith('GEOMETRY')]
        if len(geometries) != 1:
            raise ValueError(f'{name}: expected one geometry column')
        field = geometries[0]
        geom = _identifier(field)
        total, nulls, invalid = con.execute(f'SELECT count(*), count(*) FILTER (WHERE {geom} IS NULL), count(*) FILTER (WHERE {geom} IS NOT NULL AND NOT ST_IsValid({geom})) FROM {relation}').fetchone()
        validation[name] = {'rows': total, 'null_geometry': nulls, 'invalid_geometry': invalid,
                            'geometry_column': field, 'crs': 'EPSG:2263', 'spatial_reference_parity': False}
        path = Path(output_dir) / f'{name}.parquet'
        temporary = path.with_suffix('.' + uuid.uuid4().hex + '.parquet')
        projection = f"* REPLACE (ST_SetCRS({geom}, 'EPSG:2263') AS {geom})"
        con.execute(f'COPY (SELECT {projection} FROM {relation}) TO {_literal(temporary)} (FORMAT PARQUET, COMPRESSION ZSTD)')
        metadata = json.loads(pq.read_schema(temporary).metadata[b'geo'])
        if metadata['columns'][field]['crs']['id'] != {'authority': 'EPSG', 'code': 2263}:
            raise ValueError(f'{name}: export lost its CRS metadata')
        temporary.replace(path)
        paths.append(path)
    return paths, validation


def _resume_selection(previous, project):
    """Reuse successful unchanged models; rebuild changes and all descendants."""
    old_project = previous.get('project') if previous else None
    if not old_project:
        return [], {}
    old_manifest = old_project['manifest']
    if any(old_manifest.get(key) != project['manifest'].get(key)
           for key in ('compatibility_macros', 'macro_hashes')):
        return [], {}
    ledger = dict(previous.get('execution_ledger', {}))
    results_path = Path(old_project['project_dir']) / 'target' / 'run_results.json'
    old_hashes = {m['name']: m['sha256'] for m in old_manifest['models']}
    if results_path.exists():
        for row in json.loads(results_path.read_text())['results']:
            if row['unique_id'].startswith('model.'):
                name = row['unique_id'].split('.', 2)[2]
                ledger[name] = {'status': row['status'], 'sha256': old_hashes.get(name)}
    changed = []
    for model in project['manifest']['models']:
        old = ledger.get(model['name'], {})
        if old.get('status') != 'success' or old.get('sha256') != model['sha256']:
            changed.append(model['name'] + '+')
    old_outputs = old_project.get('outputs', old_manifest.get('outputs', {}))
    for name, dependency in project.get('outputs', {}).items():
        if ledger.get(name, {}).get('status') != 'success' or old_outputs.get(name) != dependency:
            changed.append(name)
    return changed, ledger


def _validate_resume_engines(previous, engines):
    """Prepared sources and model tables must use the same execution engines."""
    if previous and previous.get('engines') != engines:
        raise ValueError('Resume requires unchanged engine versions; start a new build directory')


def _clone_database(source, destination):
    """Copy a checkpointed database under a read lock; never modify its parent."""
    source, destination = Path(source).resolve(strict=True), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    with duckdb.connect(str(source), read_only=True):
        if Path(str(source) + '.wal').exists():
            raise ValueError('Close and checkpoint the parent database before reusing it')
        if sys.platform == 'darwin':
            # APFS copy-on-write keeps versions independent without duplicating
            # unchanged native caches. A failed clone is never treated as valid.
            subprocess.run(['cp', '-c', str(source), str(destination)], check=True)
            method = 'APFS copy-on-write clone'
        else:
            if shutil.disk_usage(destination.parent).free < source.stat().st_size:
                raise ValueError('Insufficient disk space to copy the parent database')
            shutil.copy2(source, destination)
            method = 'independent file copy'
        if destination.stat().st_size != source.stat().st_size:
            raise ValueError('Parent database copy is incomplete')
    return method


def _prune_obsolete_models(con, previous, project):
    """Remove only superseded, manifest-owned models from a copied build."""
    old_project = previous['project']
    keep = {row['name'] for row in project['manifest']['models']}
    keep.update(project.get('outputs', {}))
    # Output aliases depend on the original operations; remove them first.
    names = list(reversed(old_project.get('outputs', {})))
    names += [row['name'] for row in reversed(old_project['manifest']['models'])]
    relations = dict(con.execute("""
        SELECT table_name, table_type FROM information_schema.tables
        WHERE table_schema = 'main' AND table_catalog = current_database()
    """).fetchall())
    removed, seen = [], set()
    con.execute('BEGIN TRANSACTION')
    try:
        for name in names:
            if name in keep or name in seen or name not in relations:
                continue
            seen.add(name)
            kind = {'BASE TABLE': 'TABLE', 'VIEW': 'VIEW'}[relations[name]]
            con.execute(f'DROP {kind} main.{_identifier(name)}')
            removed.append({'name': name, 'type': kind})
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise
    return removed


def run_full(catalog: Catalog, *, inputs: dict[str, str], source_repo, output_dir,
             candidate_version='26v2m4', output_name='pluto_moses',
             extension_directory='.extensions', reference=None, progress=print,
             geosupport_release=None, geosupport_extension=None, geosupport_home=None,
             resume=False, reuse_build=None):
    """Prepare locked sources, compile and execute dbt, validate, export and ingest."""
    from .full_sources import prepare_sources, _native_config
    from .full_compile import compile_full_project

    catalog._validate_name(output_name)
    if output_name in inputs:
        raise ValueError('Output name must differ from every locked source')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,5}', candidate_version):
        raise ValueError('Candidate version requires at most six characters, matching the PLUTO schema')
    if candidate_version == '26v2':
        raise ValueError('Choose a distinct candidate version, such as 26v2m1')
    if not inputs or any(not isinstance(v, str) or v.lower() == 'latest' for v in inputs.values()):
        raise ValueError('Every input needs an explicit catalog version')
    out = Path(output_dir).expanduser().resolve()
    engines = {p: version(p) for p in ('duckdb', 'dbt-core', 'dbt-duckdb', 'sqlglot')}
    previous = None
    baseline = Path(reuse_build).expanduser().resolve(strict=True) if reuse_build else None
    if resume and baseline:
        raise ValueError('Choose either --resume or --reuse-build')
    if resume:
        previous = json.loads((out / 'build-report.json').read_text())
        _validate_resume_engines(previous, engines)
        if previous['input_lock'] != inputs or previous['candidate_version'] != candidate_version or previous['upstream_commit'] != UPSTREAM_COMMIT:
            raise ValueError('Resume requires the same input lock, candidate version and upstream revision')
        if previous['status'] == 'completed':
            raise ValueError('Build is already completed; choose a new output directory')
        _save(out / f'build-report-attempt-{previous.get("attempt", 1)}.json', previous)
        if not previous.get('project'):
            candidates = sorted(out.glob('dbt*/target/run_results.json'), key=lambda p: p.stat().st_mtime, reverse=True)
            for result in candidates:
                directory = result.parent.parent
                manifest_path = directory / 'full_manifest.json'
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    previous['project'] = {'project_dir': str(directory), 'manifest': manifest, 'outputs': manifest['outputs']}
                    break
    else:
        if baseline:
            previous = json.loads((baseline / 'build-report.json').read_text())
            _validate_resume_engines(previous, engines)
            if previous.get('status') != 'completed' or previous['input_lock'] != inputs or previous['upstream_commit'] != UPSTREAM_COMMIT:
                raise ValueError('Reuse requires a completed parent with the same inputs and upstream revision')
            if previous['candidate_version'] == candidate_version:
                raise ValueError('A new candidate must have a distinct version')
        out.mkdir(parents=True, exist_ok=False)
    attempt = previous.get('attempt', 1) + 1 if resume else 1
    project_dir = out / ('dbt' if attempt == 1 else f'dbt-attempt-{attempt}')
    started = time.monotonic()
    report = {'status': 'preparing', 'candidate_version': candidate_version,
              'upstream_release': '26v2', 'upstream_commit': UPSTREAM_COMMIT,
              'production_parity': False, 'run_id': uuid.uuid4().hex,
              'attempt': attempt,
              'started_at': datetime.now(timezone.utc).isoformat(),
              'input_lock': inputs, 'output_directory': str(out),
              'runner_sha256': _hash(__file__),
              'engines': engines}
    if baseline:
        report['parent_build'] = {'path': str(baseline), 'run_id': previous['run_id'],
                                  'candidate_version': previous['candidate_version'],
                                  'catalog_version': previous.get('output', {}).get('version')}
    elif previous and previous.get('parent_build'):
        report['parent_build'] = previous['parent_build']
    report_file = out / 'build-report.json'
    implementation_dir = out / f'implementation-attempt-{attempt}-{report["run_id"][:8]}'
    implementation_dir.mkdir(exist_ok=False)
    report['implementation'] = {}
    for name in ('full.py', 'full_sources.py', 'full_compile.py',
                 'full_process.py', 'full_corrections.py'):
        snapshot = implementation_dir / name
        shutil.copy2(Path(__file__).with_name(name), snapshot)
        report['implementation'][name] = {'path': str(snapshot), 'sha256': _hash(snapshot)}
    _save(report_file, report)
    try:
        db = out / 'pluto.duckdb'
        progress('Preparing locked production sources')
        if baseline:
            report['parent_build']['copy_method'] = _clone_database(baseline / 'pluto.duckdb', db)
        cached = json.loads((baseline / 'source-preparation.json').read_text()) if baseline else None
        if resume and db.with_suffix('.sources.json').exists():
            cached = json.loads(db.with_suffix('.sources.json').read_text())
        if resume and (not cached or cached.get('status') not in ('prepared', 'prepared_provisional')) and (out / 'source-preparation.json').exists():
            completed = json.loads((out / 'source-preparation.json').read_text())
            if completed.get('status') in ('prepared', 'prepared_provisional'):
                cached = completed
        if cached and cached.get('status') in ('prepared', 'prepared_provisional'):
            from . import full_sources
            expected_runtime = _native_config(geosupport_release, geosupport_extension, geosupport_home) if cached.get('native_runtime') else None
            if cached['input_lock']['versions'] != inputs or cached['code_sha256'] != _hash(full_sources.__file__) or cached.get('native_runtime') != expected_runtime:
                raise ValueError('Prepared source cache does not match the input lock, source code or native runtime')
            with duckdb.connect(str(db), config={'extension_directory': str(Path(extension_directory).resolve())}) as check:
                check.execute('LOAD spatial')
                fingerprint = check.execute('SELECT fingerprint FROM source_work.identity').fetchone()[0]
                if fingerprint != cached['fingerprint']:
                    raise ValueError('Prepared source cache fingerprint does not match its database')
                for relation in set(cached['source_relations'].values()):
                    check.execute(f'SELECT * FROM {relation} LIMIT 0')
            sources = cached
            if baseline:
                sources = dict(cached, report_path=str(db.with_suffix('.sources.json')),
                               reused_from=str(baseline / 'source-preparation.json'))
                if 'database_path' in sources:
                    sources['database_path'] = str(db)
                _save(db.with_suffix('.sources.json'), sources)
            progress('Reusing completed source tables and native geocodes; fingerprints verified')
        else:
            sources = prepare_sources(catalog, {'versions': inputs}, db, Path(extension_directory).resolve(),
                                      geosupport_release=geosupport_release,
                                      geosupport_extension=geosupport_extension,
                                      geosupport_home=geosupport_home, progress=progress)
        report['sources'] = sources
        _save(out / 'source-preparation.json', sources)
        report['status'] = 'compiling'
        _save(report_file, report)
        con = duckdb.connect(str(db))
        try:
            con.execute('SET extension_directory=' + _literal(Path(extension_directory).resolve()))
            con.execute('SET autoinstall_known_extensions=false')
            con.execute('LOAD spatial')
            copy_null_sources = []
            for source in sources['inputs']:
                normalization = source.get('normalization')
                is_dump = isinstance(normalization, dict) and normalization.get('format') == 'ogr2ogr PostgreSQL COPY text'
                is_seed = isinstance(normalization, str) and normalization.startswith('CSV text preservation')
                if not is_dump and (source['provisional'] or is_seed or source['alias'] == 'pluto_pts'):
                    copy_null_sources.append(source['alias'])
            project = compile_full_project(Path(source_repo), project_dir, release=candidate_version,
                                           source_relations=sources['source_relations'], connection=con,
                                           copy_null_sources=copy_null_sources)
            if baseline:
                report['pruned_parent_models'] = _prune_obsolete_models(con, previous, project)
        finally:
            con.close()
        report['project'] = project
        profile = {'moses_pluto_full': {'target': 'local', 'outputs': {'local': {
            'type': 'duckdb', 'path': str(db), 'schema': 'main', 'threads': 1,
            'config_options': {'extension_directory': str(Path(extension_directory).resolve())},
            'extensions': ['spatial'], 'settings': {
                'extension_directory': str(Path(extension_directory).resolve()),
                'autoinstall_known_extensions': False, 'autoinstall_extension_repository': '',
                'memory_limit': '4GB', 'threads': 4, 'preserve_insertion_order': False,
            }}}}}
        (project_dir / 'profiles.yml').write_text(json.dumps(profile, indent=2))
        report['status'] = 'building'
        selection, ledger = _resume_selection(previous, project)
        report['execution_ledger'] = ledger
        report['dbt_selection'] = selection or ['all']
        _save(report_file, report)
        command = [sys.executable, '-c', 'from dbt.cli.main import dbtRunner; import sys; r=dbtRunner().invoke(sys.argv[1:]); sys.exit(0 if r.success else 1)',
                   'build', '--project-dir', str(project_dir), '--profiles-dir', str(project_dir),
                   '--no-use-colors', '--no-send-anonymous-usage-stats']
        if selection:
            command.extend(['--select', *selection])
        log_path = out / ('dbt.log' if attempt == 1 else f'dbt-attempt-{attempt}.log')
        report['dbt_log'] = str(log_path)
        progress(f'Running dbt DAG; log: {log_path}')
        with log_path.open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        run_results = project_dir / 'target' / 'run_results.json'
        if run_results.exists():
            hashes = {m['name']: m['sha256'] for m in project['manifest']['models']}
            for row in json.loads(run_results.read_text())['results']:
                if row['unique_id'].startswith('model.'):
                    name = row['unique_id'].split('.', 2)[2]
                    report['execution_ledger'][name] = {'status': row['status'], 'sha256': hashes.get(name)}
        if result.returncode:
            raise RuntimeError(f'dbt build failed; inspect {log_path}')
        report['status'] = 'validating'
        _save(report_file, report)
        con = duckdb.connect(str(db))
        try:
            con.execute('SET extension_directory=' + _literal(Path(extension_directory).resolve()))
            con.execute('LOAD spatial')
            export = _identifier(project.get('export_model', 'export_pluto'))
            count, unique, missing = con.execute(f'SELECT count(*), count(DISTINCT bbl), count(*) FILTER (WHERE bbl IS NULL) FROM {export}').fetchone()
            if not count or missing or unique != count:
                raise ValueError(f'Final BBL validation failed: rows={count}, unique={unique}, null={missing}')
            report['validation'] = {'rows': count, 'distinct_bbls': unique, 'null_bbls': missing}
            report['schema'] = [{'name': r[0], 'type': r[1]} for r in con.execute(f'DESCRIBE {export}').fetchall()]
            for extension, options in [('parquet', "FORMAT PARQUET, COMPRESSION ZSTD"), ('csv', 'FORMAT CSV, HEADER TRUE')]:
                path = out / f'pluto.{extension}'
                con.execute(f'COPY (SELECT * FROM {export} ORDER BY bbl) TO {_literal(path)} ({options})')
            extra_artifacts = []
            spatial_paths, report['spatial_validation'] = export_spatial(con, project.get('outputs', {}), out)
            extra_artifacts.extend(spatial_paths)
            for name in project.get('outputs', {}):
                if name.startswith('qaqc_') or name in ('pluto_removed_records', 'pluto_changes_applied', 'pluto_changes_not_applied'):
                    path = out / f'{name}.csv'
                    con.execute(f'COPY {_identifier(name)} TO {_literal(path)} (FORMAT CSV, HEADER TRUE)')
                    extra_artifacts.append(path)
            stage_counts = []
            for model in project['manifest']['models']:
                if model['materialized'] == 'table':
                    n = con.execute(f'SELECT count(*) FROM {_identifier(model["name"])}').fetchone()[0]
                    stage_counts.append({'model': model['name'], 'origin': model['origin'], 'rows': n})
            _save(out / 'stage-counts.json', stage_counts)
            report['stage_counts_path'] = str(out / 'stage-counts.json')
            if reference:
                report['comparison'] = compare_release(con, export, reference, out)
            report['artifacts'] = {p.name: {'path': str(p), 'sha256': _hash(p), 'bytes': p.stat().st_size}
                                   for p in [out / 'pluto.csv', out / 'pluto.parquet', *extra_artifacts]}
        finally:
            con.close()
        progress('Accepting validated candidate into Moses')
        report['output'] = catalog.ingest(out / 'pluto.parquet', name=output_name, key='bbl',
                                          provenance={'pluto_full_build': {k: report[k] for k in ('run_id', 'candidate_version', 'upstream_commit', 'input_lock', 'engines', 'production_parity')}, 'build_report': str(report_file)})
        report['status'] = 'completed'
    except Exception as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        factor = 1 if sys.platform == 'darwin' else 1024
        report['resource_usage'] = {
            'parent_process_max_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * factor,
            'largest_child_max_rss_bytes': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * factor,
            'note': 'Process lifetime high-water marks; not simultaneous combined system memory.'}
        _save(report_file, report)
    return report
