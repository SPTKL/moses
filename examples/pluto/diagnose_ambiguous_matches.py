"""Explain eligible CAMA and ZIP matches in a completed PLUTO build.

Run with --candidate .moses/pluto-build/26v2m4 --output /tmp/matches.json.
The candidate is opened read-only. Temporary diagnostic tables belong only to
this connection; no candidate relation, macro, or source is changed. No native
Geosupport calls are made. Counts cover all eligible matches; option examples
are bounded, with the three previously observed parcels always included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp

from moses.pluto.full_compile import SelectCompiler


KNOWN_CAMA = ('5024500160', '3002080304')
KNOWN_ZIP = '1012650040'
MAX_OPTIONS = 100


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def records(con, sql):
    result = con.execute(sql)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def json_fields(alias, fields):
    return 'to_json(struct_pack(' + ', '.join(quote(name) + ':=' + quote(alias) + '.' + quote(name) for name in fields) + '))'


def canonical_order(alias, schema, identity):
    # Use exactly the compiler's policy and numeric-to-text adaptation. Avoid
    # its constructor, which installs compatibility macros and writes models.
    order, columns = SelectCompiler.canonical_match_order(alias, schema, identity)
    renderer = object.__new__(SelectCompiler)
    query = renderer.render(sqlglot.parse_one('SELECT 1' + order, read='duckdb'))
    return query[query.upper().index('ORDER BY'):], columns


def with_ctes(ctes, query):
    result = query.copy()
    if ctes:
        existing = result.args.get('with_')
        result.set('with_', exp.With(expressions=[c.copy() for c in ctes] + ([] if existing is None else [c.copy() for c in existing.expressions])))
    return result.sql(dialect='duckdb')


def joined_rules(parsed):
    """Only compiler-created equality-key deduplication, never inner rules."""
    prior = []
    for cte in parsed.args['with_'].expressions:
        query = cte.this
        joins = query.args.get('joins', [])
        if cte.alias_or_name.startswith('cama_') and len(joins) == 1:
            source = joins[0].this
            if isinstance(source, exp.Subquery) and source.this.args.get('qualify'):
                star = next((node for node in query.expressions if node.find(exp.Star)), None)
                replacements = star.find(exp.Star).args.get('replace', []) if star is not None else []
                if replacements:
                    yield cte, prior[:], source, replacements
        prior.append(cte)


def cama_diagnosis(con, compiled, max_groups):
    parsed = sqlglot.parse_one(compiled.read_text(), read='duckdb')
    result = {'compiled_sql': str(compiled), 'compiled_sha256': digest(compiled),
              'scope': 'Each compiled CAMA joined UPDATE, preserving its source filters, prior target state and join predicate. Inner source business windows remain intact.',
              'rules': []}
    conflicting_bbls = set()
    for index, (cte, prior, source, replacements) in enumerate(joined_rules(parsed)):
        source_query = source.this.copy()
        window = source_query.args['qualify'].find(exp.Window)
        keys = window.args.get('partition_by', [])
        if not keys or any(not isinstance(key, exp.Column) for key in keys):
            raise ValueError('Unsupported compiler deduplication key in ' + cte.alias_or_name)
        source_query.set('qualify', None)
        source_sql = with_ctes(prior + ([] if not cte.this.args.get('with_') else cte.this.args['with_'].expressions), source_query)
        schema = [(row[0], row[1]) for row in con.execute('DESCRIBE ' + source_sql).fetchall()]
        fields = [name for name, _ in schema if name != '__matched']
        order, ordered_fields = canonical_order('__s', [(name, dtype) for name, dtype in schema if name != '__matched'], ('bbl', 'bldgnum', 'primebbl', 'billingbbl'))
        partition = ', '.join('__s.' + quote(key.name) for key in keys)
        enumerated = ('SELECT __s.*, count(*) OVER (PARTITION BY ' + partition + ') AS __diagnostic_match_count, '
                      'row_number() OVER (PARTITION BY ' + partition + ' ' + order + ') AS __diagnostic_canonical_rank '
                      'FROM (' + source_query.sql(dialect='duckdb') + ') AS __s QUALIFY __diagnostic_match_count>1')
        query = cte.this.copy()
        join = query.args['joins'][0]
        join.set('side', 'INNER')
        join.set('this', exp.Subquery(this=sqlglot.parse_one(enumerated, read='duckdb'), alias=source.args['alias'].copy()))
        alias = source.alias_or_name
        target = query.args['from_'].this.alias_or_name
        assignments = [replacement.alias_or_name for replacement in replacements]
        assignment_struct = 'to_json(struct_pack(' + ', '.join(quote(item.alias_or_name) + ':=' + item.this.sql(dialect='duckdb') for item in replacements) + '))'
        projection = (quote(target) + '.id AS target_id, ' + quote(target) + '.bbl AS target_bbl, ' +
                      json_fields(alias, fields) + ' AS source_payload, ' + assignment_struct + ' AS assigned_values, ' +
                      quote(alias) + '.__diagnostic_canonical_rank AS canonical_rank')
        query.set('expressions', sqlglot.parse_one('SELECT ' + projection, read='duckdb').expressions)
        table = '__diagnostic_cama_' + str(index)
        con.execute('CREATE TEMP TABLE ' + table + ' AS ' + with_ctes(prior, query))
        groups_sql = ('SELECT target_id,target_bbl,count(*) AS eligible_options,count(DISTINCT assigned_values) AS distinct_assignment_options '
                      'FROM ' + table + ' GROUP BY target_id,target_bbl')
        groups = records(con, 'SELECT count(*) AS multiple_match_targets, count(*) FILTER (WHERE distinct_assignment_options>1) AS conflicting_assignment_targets FROM (' + groups_sql + ')')[0]
        all_conflicts = records(con, 'SELECT * FROM (' + groups_sql + ') WHERE distinct_assignment_options>1 ORDER BY target_bbl,target_id')
        conflicting_bbls.update(row['target_bbl'] for row in all_conflicts)
        selected_groups = all_conflicts[:max_groups]
        for row in records(con, 'SELECT * FROM (' + groups_sql + ') WHERE target_bbl IN (' + ','.join(map(literal, KNOWN_CAMA)) + ') ORDER BY target_bbl,target_id'):
            if row not in selected_groups:
                selected_groups.append(row)
        for group in selected_groups:
            target_id = int(group['target_id'])
            options = records(con, 'SELECT source_payload,assigned_values,canonical_rank FROM ' + table + ' WHERE target_id=' + str(target_id) + ' ORDER BY canonical_rank LIMIT ' + str(MAX_OPTIONS))
            for option in options:
                option['source_payload'] = json.loads(option['source_payload'])
                option['assigned_values'] = json.loads(option['assigned_values'])
            selected_query = sqlglot.parse_one('SELECT ' + json_fields('s', assignments) + ' AS selected_values FROM ' + quote(cte.alias_or_name) + ' AS s WHERE id=' + str(target_id), read='duckdb')
            chosen = records(con, with_ctes(prior + [cte], selected_query))
            group['options'] = options
            group['omitted_option_rows'] = max(0, group['eligible_options'] - MAX_OPTIONS)
            # Re-executing an old unordered UPDATE can choose a different row.
            # Never describe this replay as the value originally materialized.
            group['recomputed_stage_values'] = [json.loads(row['selected_values']) for row in chosen]
            group['actual_final_cama_values'] = records(con, 'SELECT ' + ','.join(quote(name) for name in assignments) + ' FROM parcel_cama WHERE id=' + str(target_id))
        result['rules'].append({'rule': cte.alias_or_name, 'assignment_fields': assignments,
                                'canonical_order_columns': ordered_fields, **groups,
                                'detailed_groups': selected_groups,
                                'omitted_conflicting_groups': max(0, len(all_conflicts) - max_groups)})
        con.execute('DROP TABLE ' + table)
    result['distinct_conflicting_target_bbls'] = len(conflicting_bbls)
    result['conflicting_target_bbls'] = sorted(conflicting_bbls)
    result['known_parcels_final'] = records(con, 'SELECT bbl,bldgarea,comarea,resarea,otherarea,builtfar,areasource FROM pluto WHERE bbl IN (' + ','.join(map(literal, KNOWN_CAMA)) + ') ORDER BY bbl')
    return result


def zip_diagnosis(con, max_groups):
    schema = [(row[0], row[1]) for row in con.execute('DESCRIBE SELECT *,wkb_geometry AS geom FROM sources.doitt_zipcodeboundaries').fetchall()]
    order, columns = canonical_order('b', schema, ('zipcode', 'ogc_fid'))
    payload = []
    for name, dtype in schema:
        value = 'b.' + quote(name)
        if dtype.upper().startswith('GEOMETRY'):
            value = 'hex(ST_AsWKB(' + value + '))'
        payload.append(quote(name) + ':=' + value)
    con.execute('CREATE TEMP TABLE __diagnostic_zip AS SELECT a.id AS target_id,a.bbl AS target_bbl, '
                'ST_AsText(a.centroid) AS target_point, b.zipcode AS option_zipcode, '
                'to_json(struct_pack(' + ','.join(payload) + ')) AS source_payload, '
                'row_number() OVER (PARTITION BY a.id ' + order + ') AS canonical_rank '
                'FROM political_geography AS a JOIN (SELECT *,wkb_geometry AS geom FROM sources.doitt_zipcodeboundaries) AS b '
                'ON ST_Within(a.centroid,b.geom) WHERE a.zipcode IS NULL AND a.xcoord IS NOT NULL')
    groups_sql = ('SELECT target_id,target_bbl,first(target_point) AS target_point,count(*) AS eligible_options, '
                  'count(DISTINCT to_json(struct_pack(zipcode:=option_zipcode))) AS distinct_zipcodes FROM __diagnostic_zip GROUP BY target_id,target_bbl')
    counts = records(con, 'SELECT count(*) AS eligible_targets, count(*) FILTER (WHERE eligible_options>1) AS multiple_match_targets, '
                     'count(*) FILTER (WHERE distinct_zipcodes>1) AS conflicting_zipcode_targets FROM (' + groups_sql + ')')[0]
    conflicts = records(con, 'SELECT * FROM (' + groups_sql + ') WHERE distinct_zipcodes>1 ORDER BY target_bbl,target_id')
    groups = conflicts[:max_groups]
    for row in records(con, 'SELECT * FROM (' + groups_sql + ') WHERE target_bbl=' + literal(KNOWN_ZIP)):
        if row not in groups:
            groups.append(row)
    for group in groups:
        group['options'] = records(con, 'SELECT option_zipcode,canonical_rank,source_payload FROM __diagnostic_zip WHERE target_id=' + str(int(group['target_id'])) + ' ORDER BY canonical_rank LIMIT ' + str(MAX_OPTIONS))
        for option in group['options']:
            option['source_payload'] = json.loads(option['source_payload'])
        group['omitted_option_rows'] = max(0, group['eligible_options'] - MAX_OPTIONS)
        group['actual_selected_service_zipcode'] = con.execute('SELECT zipcode FROM service_geography WHERE id=' + str(int(group['target_id']))).fetchone()[0]
        group['actual_final_pluto_rows'] = records(con, 'SELECT bbl,zipcode FROM pluto WHERE id=' + str(int(group['target_id'])))
    con.execute('DROP TABLE __diagnostic_zip')
    return {'scope': 'political_geography zipcode IS NULL and xcoord IS NOT NULL; exact ST_Within centroid against pinned staged ZIP polygons',
            'target_point_crs': 'EPSG:4326', 'geometry_encoding': 'hexadecimal WKB',
            'canonical_order_columns': columns, **counts, 'detailed_groups': groups,
            'omitted_conflicting_groups': max(0, len(conflicts) - max_groups)}


def diagnose(candidate: Path, max_groups=50, extension_directory: Path | None = None):
    candidate = candidate.resolve(strict=True)
    build = json.loads((candidate / 'build-report.json').read_text())
    if build.get('status') != 'completed':
        raise ValueError('Candidate build must be completed before read-only diagnosis')
    database = candidate / 'pluto.duckdb'
    compiled = candidate / 'dbt/target/compiled/moses_pluto_full/models/parcel_cama.sql'
    config = {} if extension_directory is None else {'extension_directory': str(extension_directory.resolve())}
    con = duckdb.connect(str(database), read_only=True, config=config)
    try:
        con.execute('LOAD spatial')
        result = {'candidate': str(candidate), 'run_id': build['run_id'], 'input_lock': build['input_lock'],
                  'upstream_commit': build['upstream_commit'], 'database_read_only': True,
                  'script_sha256': digest(__file__), 'compiler_sha256': digest(Path(SelectCompiler.render.__code__.co_filename)),
                  'policy': 'Canonical VARCHAR ascending NULLS LAST: identity first, remaining complete payload alphabetical; geometry hex WKB. Operational replay policy, not an inferred source business priority.',
                  'stage_replay_caveat': 'Recomputed stage values rerun compiled SQL; old unordered source selection can differ from the original build. Actual final CAMA and ZIP values are read from persisted tables.',
                  'max_detailed_conflicting_groups_per_rule': max_groups,
                  'max_option_rows_per_detailed_group': MAX_OPTIONS,
                  'cama': cama_diagnosis(con, compiled, max_groups),
                  'zip': zip_diagnosis(con, max_groups)}
    finally:
        con.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--max-groups', type=int, default=50)
    parser.add_argument('--extension-directory', type=Path, default=Path('.extensions'))
    args = parser.parse_args()
    if args.max_groups < 1:
        parser.error('--max-groups must be positive')
    result = diagnose(args.candidate, args.max_groups, args.extension_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, default=str) + '\n')
    print(json.dumps({'cama_conflicting_bbls': result['cama']['distinct_conflicting_target_bbls'],
                      'zip_conflicting_targets': result['zip']['conflicting_zipcode_targets'],
                      'output': str(args.output)}))


if __name__ == '__main__':
    main()
