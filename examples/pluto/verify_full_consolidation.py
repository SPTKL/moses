"""Compare a consolidated candidate with a completed statement-level baseline.

Read exported artifacts only. Report every tabular difference and compare
correction audits as multisets, preserving duplicate rows and NULL values.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from moses.pluto.full import compare_release


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def verify(baseline: Path, candidate: Path, output: Path):
    builds = []
    for directory in (baseline, candidate):
        build = json.loads((directory / 'build-report.json').read_text())
        if build['status'] != 'completed':
            raise ValueError(f'Build is not complete: {directory}')
        builds.append(build)
    for key in ('input_lock', 'upstream_commit'):
        if builds[0][key] != builds[1][key]:
            raise ValueError(f'Builds have different {key}')
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={'memory_limit': '4GB', 'threads': 4}) as con:
        con.execute(f'CREATE VIEW candidate AS SELECT * FROM read_parquet({literal(candidate / "pluto.parquet")})')
        comparison = compare_release(con, 'candidate', baseline / 'pluto.csv', output)
        audits = {}
        for name in ('pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records'):
            for side, directory in [('before', baseline), ('after', candidate)]:
                path = directory / f'{name}.csv'
                con.execute(f"""CREATE OR REPLACE VIEW {side} AS SELECT * FROM read_csv(
                    {literal(path)}, header=true, all_varchar=true, delim=',',
                    quote='"', escape='"', nullstr='', allow_quoted_nulls=false
                )""")
            old_schema = con.execute('DESCRIBE before').fetchall()
            new_schema = con.execute('DESCRIBE after').fetchall()
            if old_schema != new_schema:
                raise ValueError(f'Audit schema changed: {name}')
            added = con.execute('SELECT count(*) FROM (SELECT * FROM after EXCEPT ALL SELECT * FROM before)').fetchone()[0]
            removed = con.execute('SELECT count(*) FROM (SELECT * FROM before EXCEPT ALL SELECT * FROM after)').fetchone()[0]
            audits[name] = {
                'baseline_rows': con.execute('SELECT count(*) FROM before').fetchone()[0],
                'candidate_rows': con.execute('SELECT count(*) FROM after').fetchone()[0],
                'added_rows': added, 'removed_rows': removed,
                'equal_multiset': not added and not removed,
            }
    result = {
        'baseline': str(baseline.resolve()), 'candidate': str(candidate.resolve()),
        'run_ids': [build.get('run_id') for build in builds],
        'input_lock': builds[0]['input_lock'], 'upstream_commit': builds[0]['upstream_commit'],
        'parcel_comparison': comparison, 'correction_audits': audits,
        'policy': 'Parcel comparison uses declared candidate numeric types. Audit CSV rows compare exact text/null multisets; row order is ignored, duplicates retained. No differences are suppressed.',
    }
    (output / 'consolidation-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.baseline, args.candidate, args.output)
    print(json.dumps({
        'parcel_differences': [row for row in result['parcel_comparison']['columns'] if row['mismatched_rows']],
        'correction_audits': result['correction_audits'],
    }, indent=2))
