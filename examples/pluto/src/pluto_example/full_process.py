"""Business process DAG for the pinned PLUTO operation graph.

The imperative compiler remains the schema/operation oracle. This module removes
unreachable work, folds safe adjacent projections, and emits meaningful process
models with local rule CTEs and shared input macros.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
import hashlib
import json
from pathlib import Path
import re

import sqlglot
from sqlglot import exp

REF = re.compile(r"\{\{\s*ref\('([^']+)'\)\s*\}\}")
REF_NAMES = re.compile(r"\bref\(['\"]([^'\"]+)['\"]\)")
CONFIG = re.compile(r'^\{\{ config\([^\n]*\) \}\}\n')


def _body(text):
    text=CONFIG.sub('', text, count=1).strip()
    cleaned=[];alternative=False
    for line in text.splitlines():
        if re.match(r'^-- Source: ',line):continue
        if re.match(r'^\s*--\s*(DROP TABLE|CREATE TABLE)\b',line,re.I):alternative=True
        if alternative and re.match(r'^\s*--',line):continue
        alternative=False
        cleaned.append(line)
    result='\n'.join(cleaned)
    dialect=sqlglot.Dialect.get_or_raise('duckdb')
    tokens=lambda value:[(token.token_type,token.text) for token in dialect.tokenize(value)]
    if tokens(text)!=tokens(result):raise ValueError('Rule comment cleanup changed SQL tokens')
    return result


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _plain(text):
    return REF.sub(lambda match: match[1], text)


def _tree(text):
    try:
        return sqlglot.parse_one(_plain(text), read='duckdb')
    except sqlglot.errors.ParseError:
        return None


def projection_update(text):
    """Return a pure row-preserving replacement, including all expression reads."""
    tree = _tree(text)
    if not isinstance(tree, exp.Select):
        return None
    if any(tree.args.get(key) for key in ('joins', 'where', 'group', 'having', 'qualify', 'limit', 'offset', 'distinct', 'with_', 'order', 'sample')):
        return None
    if any(isinstance(node, (exp.Window, exp.Subquery, exp.AggFunc)) for node in tree.walk()):
        return None
    if any(isinstance(node, exp.Anonymous) and node.name.lower() in ('random', 'uuid', 'nextval', 'now', 'setseed', 'moses_union_agg') or isinstance(node, (exp.Rand, exp.CurrentTimestamp)) for node in tree.walk()):
        return None
    if len(tree.expressions) != 1:
        return None
    star = tree.expressions[0]
    if isinstance(star, exp.Column) and isinstance(star.this, exp.Star):
        star = star.this
    if not isinstance(star, exp.Star) or not star.args.get('replace') or star.args.get('except_') or star.args.get('rename'):
        return None
    source = tree.args.get('from_')
    if not source or not isinstance(source.this, exp.Table):
        return None
    replacements = star.args['replace']
    if any(not isinstance(value, exp.Alias) for value in replacements):
        return None
    writes = {value.alias.lower() for value in replacements}
    reads = {column.name.lower() for value in replacements for column in value.find_all(exp.Column) if not isinstance(column.this, exp.Star)}
    return tree, star, writes, reads


def fuse_projection_pair(first, second):
    """Fuse disjoint updates when every later RHS/CASE read is independent.

    Callers additionally require one consumer and adjacent nodes. Each original
    cast/CASE is copied intact; joins and serial/window expressions are excluded.
    """
    left, right = projection_update(first), projection_update(second)
    if not left or not right:
        return None
    left_tree, left_star, writes, _ = left
    right_tree, right_star, later_writes, later_reads = right
    if writes & (later_writes | later_reads):
        return None
    right_alias = right_tree.args['from_'].this.alias_or_name
    left_alias = left_tree.args['from_'].this.alias_or_name
    appended = []
    for value in right_star.args['replace']:
        value = value.copy()
        for column in value.find_all(exp.Column):
            if column.table == right_alias:
                column.set('table', exp.to_identifier(left_alias, quoted=True))
        appended.append(value)
    fused = left_tree.copy()
    fused.add_comments(right_tree.comments or [])
    result_star = next(fused.find_all(exp.Star))
    result_star.set('replace', [value.copy() for value in left_star.args['replace']] + appended)
    result = fused.sql(dialect='duckdb', pretty=True, comments=True)
    for dependency in sorted(set(REF.findall(first)) | set(REF.findall(second)), key=len, reverse=True):
        result = re.sub(r'\b' + re.escape(dependency) + r'\b', "{{ ref('" + dependency + "') }}", result)
    return result


def _root(rows, relation, filename=None, statement=None):
    matches = [row for row in rows if row['relation'] == relation and
               (filename is None or row['origin'].startswith('pluto_build/sql/' + filename + '.sql ')) and
               (statement is None or row['origin'].endswith(' statement ' + str(statement)))]
    if not matches:
        raise ValueError(f'Missing process boundary: {relation}, {filename}, {statement}')
    return matches[-1]['name']


def process_boundaries(rows, alias_roots):
    """Explicit capacity and business boundaries, rather than a model quota."""
    specs = [
        ('geocode_attributes', 'stg__pluto_input_geocodes', 'create_rpad_geo', None),
        ('pts_property_records', 'dof_pts_propmaster', 'primebbl', None),
        ('tax_lot_attributes', 'pluto_rpad_geo', 'apdate', None),
        ('allocated_lots', 'pluto_allocated', 'yearbuiltalt', None),
        ('parcel_base', 'pluto', 'landuse', None),
        ('parcel_cama', 'pluto', 'cama_easements', None),
        ('property_attributes', 'pluto', 'address', None),
        ('tax_lot_geometry', 'pluto_dtm', 'dtmmergepolygons', None),
        ('parcel_geometry', 'pluto', 'dtmgeoms', None),
        ('zoning', 'pluto', 'zoning_splitzone', None),
        ('mih', 'int_pluto__miharea', None, None),
        ('transit', 'int_pluto__transitzone', None, None),
        ('parcel_enriched', 'pluto', 'apply_dbt_enrichments', None),
        ('parcel_classification', 'pluto', 'update_empty_coord', None),
        ('flood', 'pluto', 'flood_flag', None),
        ('political_geography', 'pluto', 'spatialjoins', 7),
        ('service_geography', 'pluto', 'spatialjoins', 16),
        ('normalized_parcels', 'pluto', 'sanitboro', None),
        ('shoreline_coverage', 'dof_shoreline_subdivide', 'plutomapid', None),
        ('map_flags', 'pluto', 'plutomapid_2', None),
    ]
    first_cama = next(index for index,row in enumerate(rows) if row['origin'].startswith('pluto_build/sql/create_cama_primebbl.sql '))
    result = OrderedDict((name, _root(rows[:first_cama] if name == 'parcel_base' else rows, relation, filename, statement)) for name, relation, filename, statement in specs)
    for name in ('pluto_geom', 'export_pluto', 'archive_pluto', 'mappluto', 'mappluto_unclipped', 'mappluto_gdb', 'mappluto_unclipped_gdb', 'qaqc_expected', 'qaqc_bbl_diffs', 'qaqc_aggregate', 'qaqc_mismatch', 'qaqc_null', 'qaqc_outlier'):
        result[name] = alias_roots[name]
    return result


def spatial_process_queries(process, root, rows, sql):
    """Match disjoint spatial fields against one stable parcel snapshot.

    This is specific to the pinned service assignments. Reject any future rule
    reading a field changed by an earlier patch, rather than changing its order.
    """
    if process not in ('political_geography', 'service_geography'):
        return {}
    end = int(root[4:8])
    low, high = (196, 200) if process == 'political_geography' else (201, 208)
    base = '__m_0195_spatialjoins__pluto' if process == 'political_geography' else '__m_0200_spatialjoins__pluto'
    if end != (200 if process == 'political_geography' else 209):
        raise ValueError('Pinned spatial boundary changed')
    patches = [row for row in rows.values() if row['name'].startswith('patch__') and low <= int(row['name'][7:11]) <= high]
    overrides, writes, replacements, joins = {}, set(), [], []
    for index,row in enumerate(patches):
        name = row['name']
        tree = _tree(sql[name])
        if not isinstance(tree,exp.Select):
            raise ValueError('Spatial patch is not a SELECT')
        alias = tree.args['from_'].this.alias_or_name
        reads = {column.name.lower() for column in tree.find_all(exp.Column) if column.table == alias or not column.table}
        fields = [item.alias_or_name for item in tree.expressions if item.alias_or_name not in ('id','__matched')]
        if reads & writes or writes & set(fields):
            raise ValueError('Spatial assignment depends on an earlier changed field')
        writes.update(fields)
        target = REF.findall(sql[name])[0]
        overrides[name] = sql[name].replace("{{ ref('"+target+"') }}", "{{ ref('"+base+"') }}")
        patch_alias = 'matched_' + '_'.join(fields)
        joins.append("LEFT JOIN {{ ref('"+name+"') }} AS "+patch_alias+' ON p.id='+patch_alias+'.id')
        for field in fields:
            replacements.append(f'CASE WHEN {patch_alias}.__matched THEN {patch_alias}."{field}" ELSE p."{field}" END AS "{field}"')
    if len(patches) != high-low+1:
        raise ValueError('Incomplete pinned spatial assignment set')
    exclude = ' EXCLUDE ("centroid")' if process == 'service_geography' else ''
    overrides[root] = 'SELECT p.*'+exclude+' REPLACE ('+', '.join(replacements)+") FROM {{ ref('"+base+"') }} AS p\n"+'\n'.join(joins)+"\nCROSS JOIN {{ ref('check__pluto_spatial_ids') }} AS required_ids WHERE required_ids.valid"
    overrides['check__pluto_spatial_ids'] = "SELECT CASE WHEN COUNT(*)=COUNT(id) AND COUNT(*)=COUNT(DISTINCT id) THEN TRUE ELSE error('PLUTO spatial update requires unique non-null serial ids') END AS valid FROM {{ ref('"+base+"') }}"
    return overrides


def _rule_name(row, text):
    origin = row['origin']
    stage = Path(origin.split(' statement ')[0].split(' FIELD=')[0].split(' ')[0]).stem
    parsed = projection_update(text)
    if parsed:
        fields = sorted(parsed[2])
        label = 'assign_' + '_'.join(fields[:3])
    elif row['name'].startswith('patch__'):
        tree = _tree(text)
        fields = [item.alias_or_name for item in tree.expressions if item.alias_or_name not in ('id', '__matched')] if tree else []
        label = 'match_' + '_'.join(fields[:3])
    elif row['name'].startswith('check__'):
        label = 'require_unique_parcel_ids'
    else:
        label = row['relation'].removeprefix('pluto_').removeprefix('int_')
    result = re.sub(r'[^a-z0-9_]', '_', (stage + '_' + label).lower()).strip('_')
    if result and result[0].isdigit():result='rule_'+result
    return result[:85] or 'business_rule'


def mismatch_diagnostic(rows, queries, external, macro_keys, family='qaqc_mismatch'):
    """One explicit field-expression list shared by the four QA variants."""
    variants={row['relation'].removeprefix(family+'_'):row['name'] for row in rows.values() if row['relation'].startswith(family+'_')}
    plain=_plain(queries[variants['false_false']])
    tokens=sqlglot.Dialect.get_or_raise('duckdb').tokenize(plain)
    if tokens[0].text=='(':
        plain=plain[tokens[0].end+1:tokens[-1].start]
        tokens=sqlglot.Dialect.get_or_raise('duckdb').tokenize(plain)
    depth=0;commas=[];start=None;end=None
    for token in tokens:
        depth+=(token.text=='(')-(token.text==')')
        if depth==0 and token.token_type==sqlglot.tokens.TokenType.SELECT and start is None:start=token.end+1
        elif depth==0 and token.token_type==sqlglot.tokens.TokenType.FROM:end=token.start;break
        elif depth==0 and token.text==',':commas.append(token.start)
    if start is None or end is None:
        raise ValueError('Pinned diagnostic projection shape changed')
    offsets=[start]+[position+1 for position in commas]
    endings=commas+[end]
    projections=[plain[left:right].strip() for left,right in zip(offsets,endings)]
    fields=[]
    for projection in projections[4:]:
        alias=re.search(r'\s+AS\s+([a-zA-Z_][a-zA-Z_0-9]*)\s*$',projection,re.I)
        if alias is None:raise ValueError('Pinned QA field alias changed')
        fields.append((alias[1],projection[:alias.start()]))
    flags=projections[:4]
    for index,projection in enumerate(flags):
        for flag in ('mapped','condo'):
            if re.search(r'\bAS\s+'+flag+r'$',projection,re.I):
                flags[index]="{{ 'TRUE' if "+flag+" else 'FALSE' }} AS "+flag
    loop="{% for field, expression in fields %}\n{{ expression }} AS {{ field }}{% if not loop.last %},{% endif %}\n{% endfor %}"
    text=plain[:start]+'\n'+',\n'.join(flags)+',\n'+loop+'\n'+plain[end:]
    for dependency in sorted(set(REF.findall(queries[variants['false_false']])),key=len,reverse=True):
        target="{{ ref('"+external[dependency]+"') }}" if dependency in external else "({{ pluto_input('"+macro_keys[dependency]+"') }})"
        # Replace relation identifiers only, never coincidentally equal text in
        # labels or JSON keys. Work backwards so tokenizer offsets remain valid.
        matching=[token for token in sqlglot.Dialect.get_or_raise('duckdb').tokenize(text) if token.text==dependency and token.token_type in (sqlglot.tokens.TokenType.VAR,sqlglot.tokens.TokenType.IDENTIFIER)]
        for token in reversed(matching):
            text=text[:token.start]+target+text[token.end+1:]
    predicates=[]
    for key in ('true_false','false_true'):
        original=queries[variants[key]]
        tokens=sqlglot.Dialect.get_or_raise('duckdb').tokenize(_plain(original))
        depth=0;clauses=[]
        for token in tokens:
            depth+=(token.text=='(')-(token.text==')')
            if token.token_type==sqlglot.tokens.TokenType.WHERE:clauses.append((depth,token))
        token=min(clauses,key=lambda value:value[0])[1]
        plain=_plain(original)
        end=tokens[-1].start if tokens[0].text=='(' else len(plain)
        predicates.append(plain[token.end+1:end].strip())
    text+="\n{% if mapped or condo %}\nWHERE\n{% if mapped %}"+predicates[0]+"{% endif %}\n{% if mapped and condo %}AND{% endif %}\n{% if condo %}"+predicates[1]+"{% endif %}\n{% endif %}"
    macro="{% macro pluto_"+family+"(mapped, condo) %}\n{% set fields = "+json.dumps(fields,indent=2)+" %}\n"+text+"\n{% endmacro %}\n"
    model='\nUNION ALL\n'.join("{{ pluto_"+family+"("+str(mapped).lower()+', '+str(condo).lower()+") }}" for mapped,condo in ((True,True),(True,False),(False,True),(False,False)))
    return model,macro


def outlier_diagnostic(rows, queries, external, macro_keys):
    """Share the outlier rule body; retain its exact SQL and JSON expressions."""
    variants={row['relation'].removeprefix('qaqc_outlier_'):queries[row['name']] for row in rows.values() if row['relation'].startswith('qaqc_outlier_')}
    pattern=re.compile(r'(WITH\s+pluto_filtered\s+AS\s*\()(.*?)(\)\s*,\s*building_area_increase)',re.I|re.S)
    baseline=variants['false_false']
    filtered=pattern.search(baseline)
    if filtered is None or re.search(r'\bWHERE\b',filtered[2],re.I):
        raise ValueError('Pinned outlier filter shape changed')
    predicates=[]
    for key in ('true_false','false_true'):
        selected=pattern.search(variants[key])
        predicates.append(re.split(r'\bWHERE\b',selected[2],flags=re.I,maxsplit=1)[1].strip())
    dynamic="\n{% if mapped or condo %}\nWHERE\n{% if mapped %}"+predicates[0]+"{% endif %}\n{% if mapped and condo %}AND{% endif %}\n{% if condo %}"+predicates[1]+"{% endif %}\n{% endif %}\n"
    text=baseline[:filtered.end(2)].rstrip()+'\n'+dynamic+baseline[filtered.end(2):]
    for flag in ('condo','mapped'):
        text=re.sub(r'\bFALSE(\s+AS\s+'+flag+r'\b)',lambda match:"{{ 'TRUE' if "+flag+" else 'FALSE' }}"+match[1],text,flags=re.I)
    for dependency in sorted(set(REF.findall(baseline)),key=len,reverse=True):
        target="{{ ref('"+external[dependency]+"') }}" if dependency in external else "({{ pluto_input('"+macro_keys[dependency]+"') }})"
        text=text.replace("{{ ref('"+dependency+"') }}",target)
    macro='{% macro pluto_qaqc_outlier(mapped, condo) %}\n'+text+'\n{% endmacro %}\n'
    model='\nUNION ALL\n'.join('{{ pluto_qaqc_outlier('+str(mapped).lower()+', '+str(condo).lower()+') }}' for mapped,condo in ((True,True),(True,False),(False,True),(False,False)))
    return model,macro


def verify_diagnostic_variants(family, rows, queries, macro, external, macro_keys):
    """Check every factored variant against the original DuckDB token stream."""
    from jinja2 import Environment, StrictUndefined
    environment=Environment(undefined=StrictUndefined)
    environment.globals.update(ref=lambda name:name,pluto_input=lambda alias:'SELECT * FROM normalized_'+alias)
    def tokens(text):
        values=[(token.token_type,token.text) for token in sqlglot.Dialect.get_or_raise('duckdb').tokenize(text)]
        if values and values[0][1]=='(' and values[-1][1]==')':
            depth=0
            for index,(_,value) in enumerate(values):
                depth+=(value=='(')-(value==')')
                if depth==0:
                    if index==len(values)-1:values=values[1:-1]
                    break
        return values
    verified=[]
    for row in rows.values():
        if not row['relation'].startswith(family+'_'):
            continue
        mapped,condo=(value=='true' for value in row['relation'].removeprefix(family+'_').split('_'))
        expected=queries[row['name']]
        for dependency in set(REF.findall(expected)):
            replacement=external[dependency] if dependency in external else '(SELECT * FROM normalized_'+macro_keys[dependency]+')'
            expected=expected.replace("{{ ref('"+dependency+"') }}",replacement)
        actual=environment.from_string(macro+'\n{{ pluto_'+family+'(mapped,condo) }}').render(mapped=mapped,condo=condo)
        # The SELECT generator may remove a whole-query parenthesis wrapper.
        # It otherwise preserves tokens, including casts, flags and conditions.
        if tokens(actual)!=tokens(expected):
            left,right=tokens(actual),tokens(expected)
            difference=next((index for index,pair in enumerate(zip(left,right)) if pair[0]!=pair[1]),min(len(left),len(right)))
            raise ValueError('Factored QA token mismatch: '+row['relation']+' at '+str(difference)+': '+repr(left[max(0,difference-2):difference+3])+' != '+repr(right[max(0,difference-2):difference+3]))
        verified.append(row['relation'])
    if len(verified)!=4:
        raise ValueError('Expected four pinned QA variants: '+family)
    return verified


def validate_process_graph(models):
    by_name = {row['name']: row for row in models}
    if len(by_name) != len(models):
        raise ValueError('Duplicate business process name')
    visiting, complete = set(), set()
    def visit(name):
        if name in visiting:
            raise ValueError('Cycle in business process DAG: ' + name)
        if name in complete:
            return
        if name not in by_name:
            raise ValueError('Dangling business process dependency: ' + name)
        visiting.add(name)
        for dependency in by_name[name]['depends_on']:
            visit(dependency)
        visiting.remove(name)
        complete.add(name)
    for name in by_name:
        visit(name)


def consolidate_project(destination, manifest):
    """Replace operation files with process models, keeping operation provenance."""
    import yaml
    from .full_compile import format_replacements
    from .full_corrections import build_correction_models

    destination = Path(destination)
    directory = destination / 'models'
    rows = manifest['models']
    by_name = {row['name']: row for row in rows}
    sql = {path.stem: _body(path.read_text()) for path in directory.glob('*.sql')}
    alias_roots = {name: REF.search(sql[name])[1] for name in manifest['outputs']}
    boundaries = process_boundaries(rows, alias_roots)
    external = {root: name for name, root in boundaries.items()}
    for name in ('pluto', 'pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records'):
        external[alias_roots[name]] = name

    # Deterministic source normalization/renaming is shared SQL, not forty tables.
    macro_rows = {row['name']: row for row in rows if row['name'].startswith('input__') or row['origin'].startswith('models/stg__')}
    base_pts = _root(rows, 'dof_pts_propmaster', 'create_pts')
    macro_rows[base_pts] = by_name[base_pts]
    macro_keys = {name: ('pts_properties_base' if name == base_pts else row['relation']) for name, row in macro_rows.items()}
    uses = Counter(dependency for row in rows for dependency in REF.findall(sql[row['name']]))
    operations = {row['name']: dict(row, processes=[], status='unused') for row in rows}
    macro_used = set()

    def macro_query(name):
        macro_used.add(name)
        return "{{ pluto_input('" + macro_keys[name] + "') }}"

    process_sql, process_metadata = {}, []
    for process, root in boundaries.items():
        overrides = spatial_process_queries(process,root,by_name,sql)
        def query(name):
            return overrides.get(name,sql[name])
        ordered, seen, active = [], set(), set()
        def visit(name):
            if name in macro_rows:
                macro_used.add(name)
                return
            if name in external and name != root:
                return
            if name in seen:
                return
            if name in active:
                raise ValueError('Cycle in operation CTE graph: '+name)
            if name not in by_name:
                raise ValueError('Unresolved operation: ' + name)
            active.add(name)
            for dependency in REF.findall(query(name)):
                visit(dependency)
            active.remove(name)
            seen.add(name)
            ordered.append(name)
        visit(root)
        names, counts = {}, Counter()
        for name in ordered:
            label = _rule_name(by_name[name], query(name))
            counts[label] += 1
            names[name] = label + (f'_{counts[label]}' if counts[label] > 1 else '')

        # Fuse only adjacent pure projection versions with a single consumer.
        queries, fused, previous = {}, {}, None
        for name in ordered:
            text = query(name)
            if previous and by_name[name]['depends_on'] == [previous] and uses[previous] == 1 and previous not in external and not previous.startswith(('patch__', 'check__')):
                joined = fuse_projection_pair(queries[previous], text)
                if joined is not None:
                    queries[name] = joined
                    fused[previous] = name
                    queries.pop(previous)
                    previous = name
                    continue
            queries[name] = text
            previous = name

        def replacement(match):
            dependency = match[1]
            while dependency in fused:
                dependency = fused[dependency]
            if dependency in external and dependency != root:
                return "{{ ref('" + external[dependency] + "') }}"
            if dependency in macro_rows:
                return '(' + macro_query(dependency) + ')'
            if dependency in names:
                return names[dependency]
            raise ValueError(f'{process}: dangling CTE dependency {dependency}')

        # A shared nondeterministic choice is evaluated once. Pure projections
        # can remain inline, avoiding many retained copies of parcel geometry.
        demands, materializations = Counter({root:1}), {}
        for name in reversed(ordered):
            if name in fused:
                continue
            text = queries[name]
            tree = _tree(text)
            serial = tree is not None and any(isinstance(node,exp.Alias) and node.alias.lower()=='id' and node.find(exp.RowNumber) for node in tree.walk())
            sensitive = bool(re.search(r'ROW_NUMBER\s*\(\s*\)\s+OVER|\bQUALIFY\b|\bLATERAL\b',text,re.I))
            materializations[name] = name.startswith(('patch__','check__')) or serial or sensitive and demands[name]>1
            repeat = 1 if materializations[name] else max(1,demands[name])
            for dependency in REF.findall(text):
                while dependency in fused:
                    dependency=fused[dependency]
                if dependency in names and dependency not in external:
                    demands[dependency]+=repeat
        ctes = []
        for name in ordered:
            operations[name]['processes'].append(process)
            operations[name]['status'] = 'fused' if name in fused else 'cte'
            representative=name
            while representative in fused:
                representative=fused[representative]
            operations[name]['cte'] = names[representative]
            if name in fused:
                operations[name]['fused_into'] = fused[name]
                continue
            text = REF.sub(replacement, queries[name])
            # Never copy serial/arbitrary matching decisions across CTE scans.
            # Full geometry projections stay inline; compact spatial patches are
            # evaluated once, avoiding the former nested lateral-memory blowup.
            materialized = materializations[name]
            mode = 'MATERIALIZED' if materialized else 'NOT MATERIALIZED'
            comment = '-- ' + by_name[name]['origin'] + '\n'
            ctes.append(f'{names[name]} AS {mode} (\n' + '\n'.join('  ' + line for line in (comment + text).splitlines()) + '\n)')
        body = 'WITH\n' + ',\n'.join(ctes) + '\nSELECT * FROM ' + names[root]
        process_sql[process] = format_replacements(body)
        process_metadata.append({'name': process, 'relation': process, 'origin': 'business/' + process, 'depends_on': sorted(set(REF_NAMES.findall(body))), 'materialized': 'view' if process.startswith(('mappluto', 'qaqc_')) or process in ('export_pluto', 'archive_pluto') else 'table', 'operation_count': len(ordered), 'cte_count': len(ctes)})
        if process in ('political_geography','service_geography'):
            low,high=(196,200) if process=='political_geography' else (201,208)
            for name,operation in operations.items():
                if name.startswith('__m_') and low<=int(name[4:8])<=high and name!=root:
                    operation.update(status='fused_spatial_projection',processes=[process],cte=names[root])

    correction = build_correction_models(base_model='map_flags', research_sql="({{ pluto_input('pluto_input_research') }})")
    for name, body in correction['models'].items():
        process_sql[name] = body
        process_metadata.append({'name': name, 'relation': name, 'origin': 'business/corrections/' + name, 'depends_on': sorted(set(REF_NAMES.findall(body))), 'materialized': correction.get('materialized', {}).get(name, 'table'), 'operation_count': 0, 'cte_count': 0})
    for operation in operations.values():
        origin=operation['origin']
        if origin.startswith('pluto_build/sql/corr_') or origin.startswith('pluto_build/sql/remove_unitlots.sql'):
            relation=operation['relation']
            owners=[relation] if relation in ('pluto_changes_applied','pluto_changes_not_applied','pluto_removed_records') else ['pluto']
            if not origin.startswith('pluto_build/sql/remove_unitlots.sql'):
                owners.append('correction_decisions')
            operation.update(status='rewritten',processes=owners,macro=next(iter(correction['macros'])))
    # The correction macro's input is deliberately shared with normal models.
    for name, key in macro_keys.items():
        if key == 'pluto_input_research':
            macro_used.add(name)

    pending = list(macro_used)
    while pending:
        name = pending.pop()
        for dependency in by_name[name]['depends_on']:
            if dependency not in macro_rows:
                raise ValueError('Input macro depends on a business decision: ' + name)
            if dependency not in macro_used:
                macro_used.add(dependency)
                pending.append(dependency)
    definitions = ['{% macro pluto_input(alias) %}']
    for index, name in enumerate(sorted(macro_used, key=lambda key: macro_keys[key])):
        key = macro_keys[name]
        definitions.append("{% " + ('if' if index == 0 else 'elif') + " alias == '" + key + "' %}")
        query = REF.sub(lambda match: '(' + macro_query(match[1]) + ')', sql[name])
        definitions.append('-- ' + by_name[name]['origin'] + '\n' + query)
        operations[name]['status'] = 'input_macro'
        operations[name]['macro'] = key
    definitions += ["{% else %}", "{{ exceptions.raise_compiler_error('Unknown PLUTO input: ' ~ alias) }}", '{% endif %}', '{% endmacro %}']
    macros = {'pluto_inputs.sql': '\n'.join(definitions) + '\n', **correction['macros']}
    qa_verified=[]
    for family in ('qaqc_mismatch','qaqc_null','qaqc_outlier'):
        generator=outlier_diagnostic if family=='qaqc_outlier' else mismatch_diagnostic
        args=() if family=='qaqc_outlier' else (family,)
        process_sql[family],macros['pluto_'+family+'.sql']=generator(by_name,sql,external,macro_keys,*args)
        qa_verified+=verify_diagnostic_variants(family,by_name,sql,macros['pluto_'+family+'.sql'],external,macro_keys)
        next(row for row in process_metadata if row['name']==family)['cte_count']=0
        for operation in operations.values():
            if family in operation['processes']:
                operation.update(status='qa_macro',macro='pluto_'+family+'.sql')
                operation.pop('cte',None)
    compatibility_names, compatibility = [], []
    for statement in manifest['compatibility_macros']:
        name = 'define_' + re.search(r'MACRO (\w+)', statement)[1].lower()
        compatibility_names.append(name)
        compatibility.append('{% macro ' + name + '() %}\n' + statement + '\n{% endmacro %}')
    macros['compatibility.sql'] = '\n\n'.join(compatibility) + '\n'

    # Canonical source() calls keep input dependencies inspectable in dbt.
    source_names = set()
    def source_reference(match):
        alias = match[1] or match[2]
        source_names.add(alias)
        return "{{ source('pluto_inputs', '" + alias + "') }}"
    pattern = r'\bsources\.(?:"([^"]+)"|([A-Za-z_][A-Za-z_0-9]*))'
    macros = {name: re.sub(pattern, source_reference, body) for name, body in macros.items()}
    process_sql = {name: re.sub(pattern, source_reference, body) for name, body in process_sql.items()}
    validate_process_graph(process_metadata)
    for old in directory.glob('*.sql'):
        old.unlink()
    macro_directory = destination / 'macros'
    macro_directory.mkdir(exist_ok=True)
    for old in macro_directory.glob('*.sql'):
        old.unlink()
    for filename, body in macros.items():
        (macro_directory / filename).write_text(body)
    for row in process_metadata:
        body = process_sql[row['name']]
        text = "{{ config(materialized='" + row['materialized'] + "') }}\n-- Business process: " + row['name'] + '\n' + body.strip() + '\n'
        (directory / (row['name'] + '.sql')).write_text(text)
        row['sha256'] = _digest(text)
    project = yaml.safe_load((destination / 'dbt_project.yml').read_text())
    project['macro-paths'] = ['macros']
    project['on-run-start'] = ['{{ ' + name + '() }}' for name in compatibility_names]
    (destination / 'dbt_project.yml').write_text(yaml.safe_dump(project, sort_keys=False))
    (directory / 'sources.yml').write_text(yaml.safe_dump({'version': 2, 'sources': [{'name': 'pluto_inputs', 'schema': 'sources', 'tables': [{'name': name} for name in sorted(source_names)]}]}, sort_keys=False))
    manifest = dict(manifest)
    manifest['operations'] = list(operations.values())
    manifest['models'] = process_metadata
    manifest['model_count'] = len(process_metadata)
    manifest['outputs'] = {name: name for name in manifest['outputs']}
    manifest['macro_hashes'] = {'macros/' + name: _digest(body) for name, body in macros.items()}
    manifest['qa_factoring_verification']={'dialect':'duckdb','method':'Original versus rendered shared-macro token streams, ignoring whitespace/comments and a whole-query wrapper.', 'variants':qa_verified,'passed':len(qa_verified)}
    manifest['consolidation'] = {'original_operations': len(rows), 'business_models': len(process_metadata), 'operation_ctes_before_fusion':sum(row['operation_count'] for row in process_metadata), 'operation_ctes': sum(row['cte_count'] for row in process_metadata), 'fused_operations': sum(row['status'] == 'fused' for row in operations.values()), 'spatial_projections_combined':sum(row['status']=='fused_spatial_projection' for row in operations.values()), 'rewritten_correction_operations':sum(row['status']=='rewritten' for row in operations.values()), 'unused_operations': sum(row['status'] == 'unused' for row in operations.values()), 'source_macros':len(macro_used), 'max_model_lines': max(len(body.splitlines()) for body in process_sql.values()), 'policy': 'Explicit business boundaries, shared source macros, local rule CTEs; fuse only adjacent pure disjoint projection updates with independent read sets.'}
    return manifest


def process_readme(manifest, release):
    """Describe the maintained project in business terms, with inspectable SQL."""
    descriptions = {
        'geocode_attributes':'Clean native geography fields and coordinates.',
        'pts_property_records':'Prepare PTS property records and prime billing BBLs.',
        'tax_lot_attributes':'Join PTS/geocodes; repair vacancy, lot area and apportionment dates.',
        'allocated_lots':'Aggregate billing/condominium lots and construction years.',
        'parcel_base':'Create parcel rows, allocate attributes, attach geography and initial land use.',
        'parcel_cama':'Apply CAMA basement, lot type, proximity, area and easement rules.',
        'property_attributes':'Attach environmental designation, owner type and addresses.',
        'tax_lot_geometry':'Deduplicate condo mappings and union regular/condo tax-lot polygons.',
        'parcel_geometry':'Attach geometry and append DTM-only lots with stable serial ids.',
        'zoning':'Measure district coverage, rank/tie-break assignments, overlays and special districts.',
        'mih':'Assign mandatory inclusionary housing options by lot overlap.',
        'transit':'Rank block/lot transit zones and restrict assignments to coverage.',
        'parcel_enriched':'Join FAR, landmark, numeric, coordinate, MIH and transit attributes.',
        'parcel_classification':'Refine building class/land use and fill missing coordinates.',
        'flood':'Set floodplain flags from parcel/polygon intersections.',
        'political_geography':'Validate ids; independently match district/census fields.',
        'service_geography':'Independently match schools, council, emergency, health, sanitation and ZIP.',
        'normalized_parcels':'Normalize tract suffixes, identifiers, numeric text and sanitation fields.',
        'shoreline_coverage':'Prepare reusable shoreline geometry subdivisions.',
        'map_flags':'Set mapped/unmapped status while preserving SQL NULL versus explicit empty geometry.',
        'pluto_geom':'Clip shoreline geometry and prepare projected mapped geometries.',
        'correction_decisions':'One ordered ledger of automatic, specific-BBL and global research decisions.',
        'pluto':'Apply canonical decisions, punctuation rules and both ordered unit-lot removals.',
        'pluto_changes_applied':'Retain distinct applied events per upstream insertion phase.',
        'pluto_changes_not_applied':'Retain researched mismatches and their found values.',
        'pluto_removed_records':'Capture corrected records before each removal phase.',
        'export_pluto':'Publish the typed 99-column tabular candidate.',
        'archive_pluto':'Retain full attributes/geometry for current-release QA.',
        'mappluto':'Mapped clipped geometry with SHP-compatible text attributes.',
        'mappluto_unclipped':'Mapped unclipped geometry with SHP-compatible text attributes.',
        'mappluto_gdb':'Mapped clipped geometry with GDB-compatible numeric attributes.',
        'mappluto_unclipped_gdb':'Mapped unclipped geometry with GDB-compatible numeric attributes.',
        'qaqc_expected':'Calculate expected derived values.',
        'qaqc_bbl_diffs':'Compare BBL membership with the locked reference.',
        'qaqc_aggregate':'Calculate aggregate values for mapped/condo variants.',
        'qaqc_mismatch':'Compare 99 attributes for mapped/condo variants.',
        'qaqc_null':'Calculate attribute null counts for mapped/condo variants.',
        'qaqc_outlier':'Identify area, floor and unit outliers for mapped/condo variants.',
    }
    lines = ['# PLUTO business process models','',f'Complete SELECT-only transformation at pinned upstream `{manifest["source_commit"]}`. The candidate variable defaults to `{release}`.','',
             'The project has 38 process models. Source normalization is defined once in [pluto_inputs.sql](macros/pluto_inputs.sql); each process calls that shared policy through named local CTEs. There are no separate input or staging models.','',
             '```mermaid','flowchart LR','  inputs[Locked inputs] --> tax[Tax records and allocation]','  tax --> attributes[CAMA and property attributes]','  attributes --> geometry[Parcel geometry]','  geometry --> zoning[Zoning and enrichment]','  zoning --> geography[Political and service geography]','  geography --> mapping[Map flags and shoreline]','  mapping --> decisions[Correction decision ledger]','  decisions --> pluto[Corrected lots and audit outputs]','  pluto --> exports[Tabular and four mapped schemas]','  exports --> qa[Six QA families]','```','',
             '| Process | Business rule |','| --- | --- |']
    for row in manifest['models']:
        lines.append(f'| [{row["name"]}]({row["path"]}) | {descriptions.get(row["name"],row["name"])} |')
    metrics = manifest['consolidation']
    lines += ['', 'Local CTEs retain rule names and pinned statement comments. Safe adjacent projections are fused only when writes are disjoint and later expressions/guards do not read earlier writes. Original casts and NULL behavior remain at their semantic points.', '',
              f'The generated graph uses {metrics["operation_ctes"]} operation CTEs after {metrics["fused_operations"]} pure projection fusions; {metrics["spatial_projections_combined"]} spatial projections share stable bases. The correction ledger replaces {metrics["rewritten_correction_operations"]} imperative correction operations; {metrics["unused_operations"]} unreachable operations are omitted. The manifest records each original operation, source hash, owning process and rewrite/fusion status.', '',
              'Spatial matches are compact MATERIALIZED key/value CTEs, followed by one projection of the parcel rows. Political and service assignments have separate capacity checkpoints. Serial assignment and reused arbitrary matches are evaluated once; a required id gate rejects NULL/duplicate ids.', '',
              '[pluto_corrections.sql](macros/pluto_corrections.sql) applies specific-BBL decisions before global decisions, preserves per-phase audit DISTINCT and NULL matching, and performs both removal phases in order. Removed lots remain in the audit ledger.', '',
              'Mismatch and null diagnostics each define one explicit field/expression list, shared across four mapped/condo invocations. Outlier rules also share one body across those variants. Zoning is the largest process because intersection areas, coverage thresholds, ranking and priority ties are distinct business rules.', '',
              'Compatibility macros preserve PostGIS collection repair, SQL NULL union aggregates, projected CRS handling and geography area. Bare NUMERIC uses bounded DECIMAL(38,12); arbitrary PostgreSQL precision and historical production parity are not claimed.', '',
              'CAMA UPDATE matches and the ZIP spatial fallback use a canonical identity/payload order with explicit NULLS LAST. This is a documented operational replay policy, not inferred business precedence. The manifest lists every scoped operation and all remaining unordered UPDATE choices.', '',
              'Regenerate with `compile_full_project` and `write_review_project`. `full_manifest.json` includes all model and macro hashes; changing a shared macro invalidates cached models. Historical QA accumulator rows are not imported.','']
    return '\n'.join(lines)
