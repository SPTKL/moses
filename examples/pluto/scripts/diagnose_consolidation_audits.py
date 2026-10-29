"""Compare correction audit CSVs exactly, with explicitly separate diagnostics.

Example::

    uv run --locked python scripts/diagnose_consolidation_audits.py \
      --baseline .moses/pluto-build/26v2m2 \
      --candidate .moses/pluto-build/26v2m4 --output /tmp/audit-diagnosis.json

No database is opened. Quoted empty strings remain distinct from NULL. Raw
schema/multiset failures are retained even when a narrowly named diagnostic
normalization explains them. Numeric equivalence is never used as exact equality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb


FILES = ('pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records')


def _quote(value):
    return '"' + value.replace('"', '""') + '"'


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _records(con, sql):
    result = con.execute(sql)
    return [dict(zip([column[0] for column in result.description], row)) for row in result.fetchall()]


def _difference(con, left, right, columns):
    fields = ', '.join(_quote(column) for column in columns)
    query = f'SELECT {fields} FROM {left} EXCEPT ALL SELECT {fields} FROM {right}'
    return {'rows': con.execute('SELECT count(*) FROM (' + query + ')').fetchone()[0],
            'examples': _records(con, 'SELECT * FROM (' + query + ') LIMIT 3')}


def diagnose(baseline: Path, candidate: Path) -> dict:
    baseline, candidate = baseline.resolve(strict=True), candidate.resolve(strict=True)
    builds = [json.loads((path / 'build-report.json').read_text()) for path in (baseline, candidate)]
    if any(build.get('status') != 'completed' for build in builds):
        raise ValueError('Both build reports must say completed before comparing immutable exports')
    if builds[0]['input_lock'] != builds[1]['input_lock'] or builds[0]['upstream_commit'] != builds[1]['upstream_commit']:
        raise ValueError('Audit diagnosis requires identical input locks and upstream commits')
    report = {'baseline': str(baseline), 'candidate': str(candidate),
              'run_ids': [build['run_id'] for build in builds],
              'candidate_versions': [build['candidate_version'] for build in builds],
              'upstream_commit': builds[0]['upstream_commit'],
              'input_locks_equal': True, 'numeric_equivalence_used': False,
              'csv_policy': {'delimiter': ',', 'quote': '"', 'escape': '"',
                             'unquoted_empty': 'NULL', 'quoted_empty': 'empty string',
                             'all_varchar': True, 'strict_mode': True},
              'script_sha256': _digest(Path(__file__)), 'audits': {}}
    con = duckdb.connect()
    try:
        con.execute("SET memory_limit='1GB'")
        con.execute('SET threads=1')
        for filename in FILES:
            entry, schemas = {}, []
            for side, directory in (('baseline', baseline), ('candidate', candidate)):
                source = directory / (filename + '.csv')
                table = side + '_' + filename
                con.execute(f'CREATE TEMP TABLE {table} AS SELECT * FROM read_csv({_literal(source)}, '
                            "header=true, all_varchar=true, delim=',', quote='\"', escape='\"', "
                            "nullstr=[''], allow_quoted_nulls=false, strict_mode=true, "
                            'null_padding=false, ignore_errors=false)')
                schema = [(row[0], row[1]) for row in con.execute('DESCRIBE ' + table).fetchall()]
                schemas.append(schema)
                entry[side] = {'path': str(source), 'sha256': _digest(source),
                               'rows': con.execute('SELECT count(*) FROM ' + table).fetchone()[0],
                               'schema': schema}
            entry['raw_exact'] = {'schema_equal': schemas[0] == schemas[1]}
            report['audits'][filename] = entry
            if schemas[0] != schemas[1]:
                entry['diagnostic_normalization'] = {'performed': False, 'reason': 'Schemas differ; no silent column alignment'}
                continue
            columns = [name for name, _ in schemas[0]]
            left, right = 'baseline_' + filename, 'candidate_' + filename
            entry['raw_exact']['baseline_only'] = _difference(con, left, right, columns)
            entry['raw_exact']['candidate_only'] = _difference(con, right, left, columns)
            entry['raw_exact']['matches'] = not (entry['raw_exact']['baseline_only']['rows'] or entry['raw_exact']['candidate_only']['rows'])
            if filename == 'pluto_changes_not_applied':
                entry['diagnostic_normalization'] = {'performed': False, 'reason': 'Research rejection rows have no generated release labels'}
                continue
            omitted = ['id'] if filename == 'pluto_removed_records' and 'id' in columns else []
            rule = ("Map only automatic lotarea rows with reason 'Zero lot area', old_value '0' and version equal to the build's current label"
                    if filename == 'pluto_changes_applied' else
                    "Exclude only internal serial id; map only removed-row version equal to the build's current label")
            for side, build in zip(('baseline', 'candidate'), builds):
                expressions = []
                for column in columns:
                    if column in omitted:
                        continue
                    if column == 'version':
                        predicate = 'version = ' + _literal(build['candidate_version'])
                        if filename == 'pluto_changes_applied':
                            predicate += " AND field='lotarea' AND reason='Zero lot area' AND old_value='0'"
                        expressions.append('CASE WHEN ' + predicate + " THEN '__current_candidate_release__' ELSE version END AS version")
                    else:
                        expressions.append(_quote(column))
                con.execute(f'CREATE TEMP TABLE {side}_diagnostic AS SELECT ' + ', '.join(expressions) + ' FROM ' + side + '_' + filename)
            compared = [column for column in columns if column not in omitted]
            entry['diagnostic_normalization'] = {
                'performed': True, 'rule': rule, 'excluded_columns': omitted,
                'historical_research_versions_preserved': True,
                'all_other_strings_nulls_and_multiplicity_exact': True,
                'baseline_only': _difference(con, 'baseline_diagnostic', 'candidate_diagnostic', compared),
                'candidate_only': _difference(con, 'candidate_diagnostic', 'baseline_diagnostic', compared)}
            con.execute('DROP TABLE baseline_diagnostic')
            con.execute('DROP TABLE candidate_diagnostic')
            if filename == 'pluto_removed_records':
                integrity = {}
                for side in ('baseline', 'candidate'):
                    integrity[side] = con.execute(f'SELECT count(*)=count(bbl) AND count(*)=count(DISTINCT bbl) FROM {side}_{filename}').fetchone()[0]
                entry['keyed_removed_comparison'] = {'key': 'bbl', 'unique_nonnull_keys': integrity}
                if all(integrity.values()):
                    differences = {}
                    for column in columns:
                        count = con.execute(f'SELECT count(*) FROM {left} AS a JOIN {right} AS b ON a.bbl=b.bbl '
                                            f'WHERE a.{_quote(column)} IS DISTINCT FROM b.{_quote(column)}').fetchone()[0]
                        if count:
                            differences[column] = count
                    entry['keyed_removed_comparison']['column_difference_counts'] = differences
                    entry['keyed_removed_comparison']['baseline_only_bbls'] = con.execute(f'SELECT count(*) FROM (SELECT bbl FROM {left} EXCEPT SELECT bbl FROM {right})').fetchone()[0]
                    entry['keyed_removed_comparison']['candidate_only_bbls'] = con.execute(f'SELECT count(*) FROM (SELECT bbl FROM {right} EXCEPT SELECT bbl FROM {left})').fetchone()[0]
    finally:
        con.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = diagnose(args.baseline, args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: {'raw_exact': entry['raw_exact'].get('matches', False),
                            'diagnostic': entry['diagnostic_normalization']}
                      for name, entry in result['audits'].items()}, indent=2))


if __name__ == '__main__':
    main()
