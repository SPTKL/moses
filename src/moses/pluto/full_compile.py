"""Compile the pinned PLUTO imperative SQL into an immutable dbt SELECT DAG.

Compilation binds SELECT schemas against empty temporary relations. The business
queries are executed only by dbt; the reference checkout is never modified.
"""
from __future__ import annotations

from functools import lru_cache
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess

import sqlglot
from sqlglot import exp
from sqlglot.dialects.duckdb import DuckDB

PINNED_COMMIT = '32bc98f632f15e7182933a17fb61ecf74e853518'
ROOT = 'products/pluto/'


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def format_replacements(sql):
    """Expand star replacements by editing only whitespace between SQL tokens.

    Token offsets preserve identifiers, literals and array indices. Comments
    are not whitespace and remain unchanged; reverse edits retain the offsets.
    """
    tokens = DuckDB.Tokenizer().tokenize(sql)
    edits = {}

    def break_before(index, indent):
        if index <= 0:
            return
        start, end = tokens[index - 1].end + 1, tokens[index].start
        if not sql[start:end].strip():
            edits[(start, end)] = '\n' + ' ' * indent

    for index, token in enumerate(tokens):
        if token.token_type.name != 'REPLACE' or index < 1 or tokens[index - 1].token_type.name != 'STAR':
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].token_type.name != 'L_PAREN':
            continue
        line = sql[sql.rfind('\n', 0, token.start) + 1:token.start]
        base = len(line) - len(line.lstrip())
        depth, cases = 0, []
        first = index + 2
        break_before(first, base + 2)
        for cursor in range(first, len(tokens)):
            current = tokens[cursor].token_type.name
            gap = sql[tokens[cursor - 1].end + 1:tokens[cursor].start]
            if '\n' in gap:
                paren_depth = depth - 1 if current == 'R_PAREN' else depth
                break_before(cursor, base + 2 + 2 * paren_depth + 2 * len(cases))
            if current == 'L_PAREN':
                depth += 1
            elif current == 'R_PAREN':
                if depth == 0:
                    break_before(cursor, base)
                    break
                depth -= 1
            elif current == 'COMMA' and depth == 0 and not cases:
                break_before(cursor + 1, base + 2)
            elif current == 'CASE':
                case_indent = base + 2 + 2 * depth + 2 * len(cases)
                if cursor != first and tokens[cursor - 1].token_type.name != 'COMMA':
                    break_before(cursor, case_indent)
                cases.append(case_indent)
            elif current in ('WHEN', 'THEN', 'ELSE') and cases:
                break_before(cursor, cases[-1] + 2)
            elif current == 'END' and cases:
                break_before(cursor, cases.pop())
    for (start, end), whitespace in sorted(edits.items(), reverse=True):
        sql = sql[:start] + whitespace + sql[end:]
    return sql



def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@lru_cache(maxsize=512)
def read_pinned(repository, path):
    return subprocess.run(['git', '-C', str(repository), 'show', f'{PINNED_COMMIT}:{ROOT}{path}'],
                          check=True, capture_output=True).stdout.decode()


def seed_column_types(repository):
    """Infer pinned seed types with dbt's loader, honoring text overrides.

    dbt passes every configured column_types key as forced Agate text before
    adapter SQL typing. The pinned project declares only text overrides. Validate
    the simple numeric spelling used here against Agate, rather than guessing
    how an arbitrary future currency/locale value should be interpreted.
    """
    import agate
    import yaml
    from dbt_common.clients.agate_helper import build_type_tester

    result = {}
    config = yaml.safe_load(read_pinned(repository, 'seeds/_seeds.yml'))
    for seed in config['seeds']:
        overrides = seed.get('config', {}).get('column_types', {})
        if any(dtype.lower() != 'text' for dtype in overrides.values()):
            raise ValueError('Unsupported pinned seed column type override')
        csv = read_pinned(repository, 'seeds/' + seed['name'] + '.csv').lstrip('\ufeff')
        table = agate.Table.from_csv(io.StringIO(csv), column_types=build_type_tester(overrides))
        raw = agate.Table.from_csv(io.StringIO(csv), column_types=agate.TypeTester(force={name: agate.Text(cast_nulls=False) for name in table.column_names}))
        types = {}
        for name, dtype in zip(table.column_names, table.column_types):
            kind = type(dtype).__name__
            if kind not in ('Number', 'Text'):
                raise ValueError(f'Unsupported pinned seed type {seed["name"]}.{name}: {kind}')
            if kind == 'Number':
                for spelling, value in zip(raw.columns[name], table.columns[name]):
                    simple = None if spelling is None or spelling.strip().lower() in ('', 'null') else Decimal(spelling.strip().replace(',', ''))
                    if simple != value:
                        raise ValueError(f'Unsupported seed numeric spelling in {seed["name"]}.{name}: {spelling!r}')
            types[name] = kind
        result[seed['name']] = types
    return result


def seed_input_expression(column, kind):
    """SQL counterpart of the pinned Agate Text/Number values, failing strictly."""
    value = quote(column)
    nullable = f"CASE WHEN LOWER(TRIM({value})) IN ('', 'null') THEN NULL ELSE {value} END"
    if kind == 'Number':
        return f"CAST(REPLACE(TRIM({nullable}), ',', '') AS DECIMAL(38,12))"
    return nullable


def ordered_steps(repository):
    """Return file invocations, retaining correction-template invocations/order."""
    steps = []
    for script in ('02_build.sh', '03_corrections.sh'):
        for line in read_pinned(repository, 'pluto_build/' + script).splitlines():
            m = re.match(r'run_sql_file sql/(\w+\.sql)(.*)', line)
            if m:
                field = re.search(r'FIELD=(\w+)', m[2])
                steps.append((m[1], field[1] if field else None))
            if 'dbt run --select tag:pluto_enrichment' in line:
                steps.append(('__enrichments__', None))
    # These relations feed the exports requested by 06_export.sh. Upstream
    # 04_archive.sh prepares them; retain their SELECTs without remote publishing.
    steps += [('export.sql', None), ('export_mappluto_shp.sql', 'mappluto|clipped_2263'),
              ('export_mappluto_shp.sql', 'mappluto_unclipped|geom_2263'),
              ('export_mappluto_gdb.sql', 'mappluto_gdb|clipped_2263'),
              ('export_mappluto_gdb.sql', 'mappluto_unclipped_gdb|geom_2263')]
    return steps


def _jinja_sql(sql):
    sql = re.sub(r'\{\{.*?\}\}', lambda m: m[0].replace(chr(34), chr(39)), sql, flags=re.S)
    # Balanced config block may span lines; no other statement macros upstream.
    sql = re.sub(r'\{\{\s*config\([\s\S]*?\)\s*\}\}', '', sql)
    sql = re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}", r'\1', sql)
    sql = re.sub(r"\{\{\s*source\('[^']+',\s*'([^']+)'\)\s*\}\}", r'\1', sql)
    sql = re.sub(r'\{\{\s*target.schema\s*\}\}\.', '', sql)
    return sql


def _spatial(sql):
    """PostGIS to DuckDB spatial compatibility, with explicit XY axis order."""
    # DuckDB geometries have no SRID metadata. All recipe geometries are WGS84;
    # the only intermediate projected geometries are explicitly named *_2263.
    sql = re.sub(r'\bJSON_BUILD_OBJECT\s*\(', 'json_object(', sql, flags=re.I)
    sql = re.sub(r'\b_ST_', 'ST_', sql, flags=re.I)
    sql = re.sub(r'\bST_MAKEPOINT\s*\(', 'ST_Point(', sql, flags=re.I)
    sql = re.sub(r'\bST_GEOMETRYTYPE\s*\(', 'moses_geometrytype(', sql, flags=re.I)
    sql = re.sub(r'\bST_MAKEVALID\s*\(', 'moses_makevalid(', sql, flags=re.I)
    # Postgres set-returning dump yields one geometry per atomic component.
    sql = re.sub(r'\(ST_DUMP\(([^()]*)\)\)\.geom', r'(UNNEST(ST_Dump(\1))).geom', sql, flags=re.I)
    return sql


def compatibility_sql():
    """Macros shared by schema binding and dbt connections."""
    return [
        'CREATE OR REPLACE MACRO ST_SetSRID(g, srid) AS g',
        r"CREATE OR REPLACE MACRO moses_text(g) AS CASE WHEN typeof(g) IN ('DOUBLE','FLOAT','REAL') OR starts_with(typeof(g),'DECIMAL') THEN regexp_replace(regexp_replace(CAST(g AS VARCHAR), '(\.[0-9]*?)0+$', '\1'), '\.$', '') ELSE CAST(g AS VARCHAR) END",
        'CREATE OR REPLACE MACRO moses_subdivide(g, maxvertices) AS ST_Collect(list_transform(ST_Dump(g), part -> ST_Subdivide(part.geom, maxvertices)))',
        "CREATE OR REPLACE MACRO moses_transform_crs(g, source_srid, target_srid) AS ST_Transform(g, 'EPSG:' || CAST(source_srid AS VARCHAR), 'EPSG:' || CAST(target_srid AS VARCHAR), always_xy := true)",
        "CREATE OR REPLACE MACRO moses_geometrytype(g) AS CASE CAST(ST_GeometryType(g) AS VARCHAR) WHEN 'POLYGON' THEN 'ST_Polygon' WHEN 'MULTIPOLYGON' THEN 'ST_MultiPolygon' WHEN 'POINT' THEN 'ST_Point' WHEN 'MULTIPOINT' THEN 'ST_MultiPoint' WHEN 'LINESTRING' THEN 'ST_LineString' WHEN 'MULTILINESTRING' THEN 'ST_MultiLineString' WHEN 'GEOMETRYCOLLECTION' THEN 'ST_GeometryCollection' END",
        # PostGIS lwgeom_make_valid_params preserves collection input as MULTI
        # when GEOS repairs it to a singleton; bare DuckDB returns the singleton.
        "CREATE OR REPLACE MACRO moses_makevalid(g) AS CASE WHEN CAST(ST_GeometryType(g) AS VARCHAR) IN ('MULTIPOINT','MULTILINESTRING','MULTIPOLYGON','GEOMETRYCOLLECTION') THEN ST_Multi(ST_MakeValid(g)) ELSE ST_MakeValid(g) END",
        # The preceding pinned census steps create either two decimal places or
        # an integer. PostgreSQL NUMERIC::text retains that input scale.
        "CREATE OR REPLACE MACRO moses_census_tract_numeric_text(g) AS CASE WHEN contains(g, '.') THEN CAST(CAST(g AS DECIMAL(38,2)) AS VARCHAR) ELSE CAST(CAST(g AS DECIMAL(38,0)) AS VARCHAR) END",
        "CREATE OR REPLACE MACRO moses_union_agg(g) AS CASE WHEN COUNT(g)=0 THEN NULL::GEOMETRY ELSE ST_Union_Agg(g) END",
    ]


class SelectCompiler:
    def __init__(self, connection, destination, source_relations):
        self.con = connection
        self.destination = Path(destination)
        (self.destination / 'models').mkdir(parents=True, exist_ok=True)
        # Remove only compiler-owned models from a previous partial compilation.
        for pattern in ('__m_*.sql', 'input__*.sql', 'patch__*.sql', 'check__*.sql'):
            for old_model in (self.destination / 'models').glob(pattern):
                old_model.unlink()
        self.current = dict(source_relations)
        self.models = []
        self.model_counter = 0
        self.model_names = set()
        self.schemas = {}
        self.defaults = {}
        self.serials = {}
        self.temp_names = []
        self.active_comments = []
        for statement in compatibility_sql():
            self.con.execute(statement)

    def schema(self, table):
        return self.schemas.setdefault(table, [(r[0], r[1]) for r in self.con.execute(
            'DESCRIBE SELECT * FROM ' + self.current[table]).fetchall()])

    def render(self, expression):
        def spatial(node):
            if isinstance(node, exp.Anonymous) and node.name.lower()=='st_union' and len(node.expressions)==1:
                return exp.Anonymous(this='moses_union_agg',expressions=[node.expressions[0].copy()])
            if isinstance(node, exp.Mul) and all(isinstance(value.unnest(),exp.Cast) and value.unnest().args['to'].this==exp.DataType.Type.DECIMAL for value in (node.this,node.expression)):
                # Reset scale after each NUMERIC product. Otherwise three
                # scale-12 operands accumulate scale 36 and overflow even for
                # ordinary building dimensions such as 40 * 21 * 4.
                return exp.Cast(this=node.copy(),to=exp.DataType.build('DECIMAL(38,12)'))
            if isinstance(node, exp.Dot) and isinstance(node.this.unnest(),exp.Anonymous) and node.this.unnest().name.lower()=='st_dump':
                inner=node.this.unnest().sql(dialect='duckdb')
                return sqlglot.parse_one('(UNNEST('+inner+')).geom',read='duckdb')
            if isinstance(node, exp.Round) and node.this.find(exp.Div) and any(isinstance(c,exp.Cast) and c.args['to'].this==exp.DataType.Type.DECIMAL for c in node.this.walk()):
                # DuckDB decimal division produces DOUBLE; re-establish decimal
                # rounding before business rules such as built FAR round(2).
                node=node.copy()
                node.set('this',exp.Cast(this=node.this.copy(),to=exp.DataType.build('DECIMAL(38,12)')))
                return node
            if isinstance(node, exp.Cast) and node.args['to'].this in (exp.DataType.Type.TEXT,exp.DataType.Type.VARCHAR):
                converted = exp.Anonymous(this='moses_text', expressions=[node.this.copy()])
                params = node.args['to'].expressions
                if params:
                    converted = exp.Anonymous(this='substring', expressions=[converted, exp.Literal.number(1), params[0].this.copy()])
                return converted
            if isinstance(node, exp.Anonymous) and node.name.lower() == 'jsonb_agg':
                return exp.Anonymous(this='to_json', expressions=[exp.Anonymous(this='list', expressions=[x.copy() for x in node.expressions])])
            if isinstance(node, exp.Anonymous) and node.name.lower() == 'json_build_object':
                return exp.Anonymous(this='json_object', expressions=[x.copy() for x in node.expressions])
            if isinstance(node, exp.Any) and isinstance(node.this.unnest(), exp.Literal) and node.this.unnest().is_string and node.this.unnest().this.startswith('{'):
                import csv
                values = next(csv.reader([node.this.unnest().this[1:-1]], skipinitialspace=True))
                return exp.Any(this=exp.Paren(this=exp.Array(expressions=[exp.Literal.string(v) for v in values])))
            if isinstance(node, exp.Anonymous) and node.name.lower() == 'st_area' and any(isinstance(c, exp.Cast) and c.args['to'].this == exp.DataType.Type.GEOGRAPHY for c in node.walk()):
                geom = node.expressions[0].copy().transform(lambda c: c.this.copy() if isinstance(c, exp.Cast) and c.args['to'].this == exp.DataType.Type.GEOGRAPHY else c)
                return exp.Anonymous(this='ST_Area_Spheroid', expressions=[exp.Anonymous(this='ST_FlipCoordinates', expressions=[geom])])
            if isinstance(node, exp.Anonymous) and node.name.lower() == 'st_transform':
                geom, target = node.expressions
                source = exp.Literal.number(4326)
                if isinstance(geom, exp.Anonymous) and geom.name.lower() == 'st_setsrid':
                    geom, source = geom.expressions
                elif isinstance(geom, exp.Column) and geom.name.endswith('_2263'):
                    source = exp.Literal.number(2263)
                return exp.Anonymous(this='moses_transform_crs', expressions=[geom.copy(), source.copy(), target.copy()])
            if isinstance(node, exp.Anonymous) and node.name.lower() == 'st_subdivide':
                args = [x.copy() for x in node.expressions]
                if len(args) == 1: args.append(exp.Literal.number(256))
                inner = exp.Anonymous(this='moses_subdivide', expressions=args).sql(dialect='duckdb')
                return sqlglot.parse_one('(UNNEST(ST_Dump(' + inner + '))).geom', read='duckdb')
            return node
        # PostgreSQL retains a cast column's name; keep it before casts become
        # compatibility function calls.
        expression = expression.copy()
        for select in expression.find_all(exp.Select):
            projections=[]
            for item in select.expressions:
                base=item
                while isinstance(base,exp.Cast): base=base.this
                if isinstance(item,exp.Cast) and isinstance(base,exp.Column): item=exp.alias_(item,base.name,quoted=True)
                projections.append(item)
            select.set('expressions',projections)
        def rewrite(node):
            node = node.copy()
            for key, value in tuple(node.args.items()):
                if isinstance(value, exp.Expression): node.set(key, rewrite(value))
                elif isinstance(value, list): node.set(key, [rewrite(v) if isinstance(v, exp.Expression) else v for v in value])
            return spatial(node)
        expression = rewrite(expression)
        expression = expression.transform(lambda node: exp.DataType.build('DECIMAL(38,12)') if isinstance(node,exp.DataType) and node.this==exp.DataType.Type.DECIMAL and not node.expressions else node)
        for select in expression.find_all(exp.Select):
            projections=[]
            for item in select.expressions:
                base=item
                while isinstance(base,exp.Cast): base=base.this
                if isinstance(item,exp.Cast) and isinstance(base,exp.Column):
                    item=exp.alias_(item,base.name,quoted=True)
                projections.append(item)
            select.set('expressions',projections)
        sql = expression.sql(dialect='duckdb', comments=True, pretty=True)
        sql = re.sub(r'GEOMETRY\([^)]*\)', 'GEOMETRY', sql, flags=re.I)
        return format_replacements(_spatial(sql))

    def resolve(self, expression):
        expression = expression.copy()
        ctes = {c.alias for c in expression.find_all(exp.CTE)}
        deps = set()
        for table in expression.find_all(exp.Table):
            name = table.name
            if name in ctes:
                continue
            if name in self.current:
                relation = self.current[name]
                if relation in self.model_names:
                    deps.add(relation)
                alias = table.args.get('alias') or exp.TableAlias(this=exp.to_identifier(name))
                replacement = sqlglot.parse_one('SELECT * FROM ' + relation, read='duckdb').args['from_'].this
                replacement.set('alias', alias.copy())
                table.replace(replacement)
            else:
                raise ValueError(f'Unresolved input relation {name}')
        return expression, deps

    def emit(self, table, query, origin, *, materialized='view', model_name=None, explicit_null_order=False):
        resolved, deps = self.resolve(sqlglot.parse_one(query, read='postgres'))
        sql = self.render(resolved)
        if explicit_null_order:
            # SQLGlot omits DuckDB's default NULLS LAST. Retain it explicitly
            # for canonical policies so connection defaults cannot change them.
            tokens=sqlglot.Dialect.get_or_raise('duckdb').tokenize(sql)
            for index in range(len(tokens)-1,-1,-1):
                token=tokens[index]
                if token.token_type==sqlglot.tokens.TokenType.ASC and (index+1==len(tokens) or not tokens[index+1].text.upper().startswith('NULLS')):
                    sql=sql[:token.end+1]+' NULLS LAST'+sql[token.end+1:]
            # Keep the complete payload tie-break inspectable, one key per
            # line. Split only top-level order commas, using token offsets.
            lines=[]
            for line in sql.splitlines():
                if len(line)>120 and line.lstrip().startswith('ORDER BY '):
                    depth=0;commas=[]
                    for token in sqlglot.Dialect.get_or_raise('duckdb').tokenize(line):
                        depth+=(token.text=='(')-(token.text==')')
                        if token.text==',' and depth==0:commas.append(token.end+1)
                    indent=' '*(len(line)-len(line.lstrip())+2)
                    for offset in reversed(commas):line=line[:offset]+'\n'+indent+line[offset:].lstrip()
                lines.append(line)
            sql='\n'.join(lines)
        stage = Path(origin.split(' statement ')[0].split(' FIELD=')[0].split(' ')[0]).stem
        field = re.search(r'FIELD=(\w+)', origin)
        if field: stage += '_' + field[1]
        suffix = stage if stage == table else stage + '__' + table
        suffix = re.sub(r'[^a-zA-Z0-9_]', '_', suffix)
        if model_name is None:
            model = f'__m_{self.model_counter:04d}_{suffix}'
            self.model_counter += 1
        else:
            model = model_name
        try:
            description = self.con.execute('DESCRIBE ' + sql).fetchall()
        except Exception as exc:
            raise ValueError(f'{origin}: cannot bind {table}: {exc}\n{sql}') from exc
        schema = [(r[0], r[1]) for r in description]
        self.con.execute('CREATE TEMP TABLE ' + quote(model) + ' (' + ', '.join(
            quote(n) + ' ' + t for n,t in schema) + ')')
        self.temp_names.append(model)
        dbt_sql = sql
        for dep in sorted(deps, key=len, reverse=True):
            dbt_sql = re.sub(r'\b' + re.escape(dep) + r'\b', "{{ ref('" + dep + "') }}", dbt_sql)
        explanation = ''.join('-- ' + line.strip() + '\n' for comment in self.active_comments for line in comment.splitlines())
        content = "{{ config(materialized=" + repr(materialized) + ") }}\n-- Source: " + origin + '\n' + explanation + dbt_sql + '\n'
        (self.destination/'models'/f'{model}.sql').write_text(content)
        self.current[table] = model
        self.model_names.add(model)
        self.schemas[table] = schema
        self.models.append({'name': model, 'relation': table, 'origin': origin,
                            'depends_on': sorted(deps), 'materialized': materialized,
                            'sha256': hashlib.sha256(content.encode()).hexdigest()})
        return model

    def _with(self, statement):
        w = statement.args.get('with_')
        return w.sql(dialect='postgres') + ' ' if w else ''

    @staticmethod
    def canonical_match_order(alias, schema, identity):
        """Canonical source identity/payload order for explicitly scoped rules.

        This is an operational replay policy, not an inferred business priority.
        Equal identity and payload rows produce the same assignments regardless
        of which duplicate physical row is retained.
        """
        types=dict(schema)
        columns=[name for name in identity if name in types]
        columns+=sorted(set(types)-set(columns))
        expressions=[]
        for name in columns:
            value=quote(alias)+'.'+quote(name)
            if types[name].upper().startswith('GEOMETRY'):
                value='hex(ST_AsWKB('+value+'))'
            else:
                value='CAST('+value+' AS VARCHAR)'
            expressions.append(value+' ASC NULLS LAST')
        return ' ORDER BY '+', '.join(expressions),columns

    def joined_update(self, statement, origin, schema):
        """Use one source-key deduplication instead of a correlated lookup.

        This applies when the predicate separates into equality join keys and
        source-only/target-only filters. Other predicates retain the generic
        LATERAL path, including its matched-NULL behavior.
        """
        source = statement.args['from_'].this
        if not isinstance(source, (exp.Table, exp.Subquery)) or source.args.get('joins'):
            return False
        target_alias = statement.this.alias_or_name
        source_alias = source.alias_or_name
        if not source_alias or source_alias == target_alias:
            return False
        prefix = self._with(statement)
        from_sql = statement.args['from_'].sql(dialect='postgres')
        try:
            probe, _ = self.resolve(sqlglot.parse_one(prefix + 'SELECT * ' + from_sql, read='postgres'))
            source_schema = [(r[0],r[1]) for r in self.con.execute('DESCRIBE ' + self.render(probe)).fetchall()]
            source_columns = {name for name,_ in source_schema}
        except (ValueError, sqlglot.errors.SqlglotError):
            return False
        target_columns = {n for n, _ in schema}

        def sides(expression):
            result = set()
            for column in expression.find_all(exp.Column):
                if column.table == target_alias: result.add('target')
                elif column.table == source_alias: result.add('source')
                elif column.table: return {'unknown'}
                elif column.name in source_columns and column.name not in target_columns: result.add('source')
                elif column.name in target_columns and column.name not in source_columns: result.add('target')
                else: return {'unknown'}
            return result

        def terms(expression):
            expression = expression.unnest()
            if isinstance(expression, exp.And):
                return terms(expression.this) + terms(expression.expression)
            return [expression]

        where = statement.args.get('where')
        if where is None:
            return False
        keys, source_filters, join_filters = [], [], []
        for condition in terms(where.this):
            used = sides(condition)
            if used == {'source'}:
                source_filters.append(condition.sql(dialect='postgres'))
            elif used <= {'target'}:
                # A target-only LEFT JOIN conjunct makes DuckDB choose a
                # blockwise nested loop. Equality to the source TRUE marker is
                # a hashable eligibility key, including false/unknown guards
                # and NULL-safe business join keys.
                join_filters.append('(' + condition.sql(dialect='postgres') + ') = ' + quote(source_alias) + '.__matched')
            elif isinstance(condition, (exp.EQ, exp.NullSafeEQ)):
                left, right = sides(condition.this), sides(condition.expression)
                if left == {'target'} and right == {'source'}:
                    keys.append(condition.expression.sql(dialect='postgres'))
                elif left == {'source'} and right == {'target'}:
                    keys.append(condition.this.sql(dialect='postgres'))
                else:
                    return False
                join_filters.append(condition.sql(dialect='postgres'))
            else:
                return False
        if not keys:
            return False
        values = {assignment.this.name: assignment.expression.sql(dialect='postgres')
                  for assignment in statement.expressions}
        fields = [f'CASE WHEN {quote(source_alias)}.__matched THEN CAST({values[n]} AS {dtype}) ELSE {quote(target_alias)}.{quote(n)} END AS {quote(n)}'
                  for n, dtype in schema if n in values]
        source_filter = ' WHERE ' + ' AND '.join('(' + value + ')' for value in source_filters) if source_filters else ''
        ordering,ordered_columns='',[]
        if origin.startswith('pluto_build/sql/cama_'):
            ordering,ordered_columns=self.canonical_match_order(source_alias,source_schema,('bbl','bldgnum','primebbl','billingbbl'))
        deduplicated = ('SELECT ' + quote(source_alias) + '.*, TRUE AS __matched ' + from_sql + source_filter +
                        ' QUALIFY ROW_NUMBER() OVER (PARTITION BY ' + ', '.join(keys) + ordering + ') = 1')
        query = (prefix + 'SELECT ' + quote(target_alias) + '.* REPLACE (' + ', '.join(fields) + ')' +
                 ' FROM ' + statement.this.name + ' AS ' + quote(target_alias) +
                 ' LEFT JOIN (' + deduplicated + ') AS ' + quote(source_alias) +
                 ' ON ' + ' AND '.join('(' + value + ')' for value in join_filters))
        self.emit(statement.this.name, query, origin,explicit_null_order=bool(ordering))
        self.models[-1]['match_selection']={'method':'equality_key','canonical':bool(ordering),'source_columns':ordered_columns,'null_order':'LAST' if ordering else None}
        return True

    def statement(self, statement, origin):
        self.active_comments = statement.comments if statement is not None else []
        if statement is None or isinstance(statement, (exp.Drop, exp.Analyze, exp.Semicolon)):
            return
        if isinstance(statement, exp.Create) and statement.args.get('kind') == 'INDEX':
            return
        if isinstance(statement, exp.Create):
            target = statement.this
            name = target.this.name if isinstance(target, exp.Schema) else target.name
            if statement.expression is not None:
                q = statement.expression
                if isinstance(q, exp.Subquery): q = q.this
                self.emit(name, q.sql(dialect='postgres'), origin, materialized='table')
            elif isinstance(target, exp.Schema):
                columns=[]; defaults={}; serials=[]
                for col in target.expressions:
                    if isinstance(col, exp.LikeProperty):
                        self.emit(name, f'SELECT * FROM {col.this.name} WHERE FALSE', origin)
                        return
                    if not isinstance(col, exp.ColumnDef): continue
                    dtype=col.args['kind']; serial=dtype.this in (exp.DataType.Type.SERIAL, exp.DataType.Type.BIGSERIAL)
                    dt='BIGINT' if serial else self.render(dtype)
                    if serial:serials.append(col.name)
                    default=next((c.args['kind'].this.sql(dialect='postgres') for c in col.args.get('constraints',[]) if isinstance(c.args['kind'],exp.DefaultColumnConstraint)), 'NULL')
                    defaults[col.name]=default
                    columns.append(f'CAST({default} AS {dt}) AS {quote(col.name)}')
                self.defaults[name]=defaults;self.serials[name]=serials
                self.emit(name, 'SELECT '+', '.join(columns)+' WHERE FALSE', origin)
            else: raise ValueError(f'Unsupported CREATE: {statement}')
        elif isinstance(statement, exp.Select) and statement.args.get('into'):
            name=statement.args['into'].this.name; q=statement.copy();q.set('into',None)
            self.emit(name,q.sql(dialect='postgres'),origin,materialized='table')
        elif isinstance(statement, exp.Select) and any(f.name.lower()=='addgeometrycolumn' for f in statement.find_all(exp.Anonymous)):
            self.emit('pluto','SELECT *, CAST(NULL AS GEOMETRY) AS geom FROM pluto',origin)
        elif isinstance(statement, exp.Update):
            name=statement.this.name;alias=statement.this.alias_or_name
            schema=self.schema(name);assign={e.this.name:e.expression.sql(dialect='postgres') for e in statement.expressions}
            if origin == 'pluto_build/sql/numericfields_geomfields.sql statement 3' and 'ct2010' in assign:
                assign['ct2010']=f'moses_census_tract_numeric_text({quote(alias)}.ct2010)'
            where=statement.args.get('where');condition=where.this.sql(dialect='postgres') if where else 'TRUE'
            prefix=self._with(statement)
            if not statement.args.get('from_'):
                fields=[(f'CAST({assign[n]} AS {t}) AS {quote(n)}' if condition == 'TRUE' else f'CASE WHEN {condition} THEN CAST({assign[n]} AS {t}) ELSE {quote(alias)}.{quote(n)} END AS {quote(n)}') for n,t in schema if n in assign]
                self.emit(name,prefix+f'SELECT {quote(alias)}.* REPLACE ('+', '.join(fields)+f') FROM {name} AS {quote(alias)}',origin)
            else:
                if self.joined_update(statement, origin, schema):
                    return
                # PostgreSQL UPDATE FROM chooses one matching row per target;
                # LIMIT 1 preserves this cardinality, including nullable writes.
                patch=', '.join(f'{v} AS {quote(k)}' for k,v in assign.items())
                source=statement.args['from_'].sql(dialect='postgres')
                ordering,ordered_columns='',[]
                if origin.startswith('pluto_build/sql/spatialjoins.sql ') and set(assign)=={'zipcode'}:
                    probe,_=self.resolve(sqlglot.parse_one(prefix+'SELECT * '+source,read='postgres'))
                    source_schema=[(row[0],row[1]) for row in self.con.execute('DESCRIBE '+self.render(probe)).fetchall()]
                    ordering,ordered_columns=self.canonical_match_order(statement.args['from_'].this.alias_or_name,source_schema,('zipcode','ogc_fid'))
                fields=[f'CASE WHEN __patch.__matched THEN CAST(__patch.{quote(n)} AS {t}) ELSE {quote(alias)}.{quote(n)} END AS {quote(n)}' for n,t in schema if n in assign]
                if name == 'pluto' and origin.startswith('pluto_build/sql/spatialjoins.sql ') and 'id' in self.serials.get(name, []):
                    # The pinned PLUTO serial id is unique and unchanged here.
                    # Materialize only matched keys/values, avoiding a chain of
                    # thirteen lateral hashes retaining full parcel geometry.
                    gate='__spatial_id_integrity'
                    if gate not in self.current:
                        query=f"SELECT CASE WHEN COUNT(*)=COUNT(id) AND COUNT(*)=COUNT(DISTINCT id) THEN TRUE ELSE error('PLUTO spatial update requires unique non-null serial ids') END AS valid FROM {name}"
                        self.emit(gate,query,origin,materialized='table',model_name='check__pluto_spatial_ids')
                    helper=f'__spatial_patch_{self.model_counter:04d}'
                    values=[f'CAST(__patch.{quote(n)} AS {t}) AS {quote(n)}' for n,t in schema if n in assign]
                    query=prefix+f'SELECT {quote(alias)}.id, TRUE AS __matched, '+', '.join(values)+f' FROM {name} AS {quote(alias)} CROSS JOIN {gate} AS __guard INNER JOIN LATERAL (SELECT {patch} {source} WHERE {condition}{ordering} LIMIT 1) AS __patch ON TRUE WHERE __guard.valid'
                    self.emit(helper,query,origin,materialized='table',model_name=f'patch__{self.model_counter:04d}_spatialjoins',explicit_null_order=bool(ordering))
                    self.models[-1]['match_selection']={'method':'lateral','canonical':bool(ordering),'source_columns':ordered_columns,'null_order':'LAST' if ordering else None}
                    fields=[f'CASE WHEN __patch.__matched THEN __patch.{quote(n)} ELSE {quote(alias)}.{quote(n)} END AS {quote(n)}' for n,t in schema if n in assign]
                    self.emit(name,f'SELECT {quote(alias)}.* REPLACE ('+', '.join(fields)+f') FROM {name} AS {quote(alias)} LEFT JOIN {helper} AS __patch ON {quote(alias)}.id=__patch.id',origin)
                    return
                self.emit(name,prefix+f'SELECT {quote(alias)}.* REPLACE ('+', '.join(fields)+f') FROM {name} AS {quote(alias)} LEFT JOIN LATERAL (SELECT TRUE AS __matched, {patch} {source} WHERE {condition}{ordering} LIMIT 1) AS __patch ON TRUE',origin,explicit_null_order=bool(ordering))
                self.models[-1]['match_selection']={'method':'lateral','canonical':bool(ordering),'source_columns':ordered_columns,'null_order':'LAST' if ordering else None}
        elif isinstance(statement, exp.Insert):
            target=statement.this;name=target.this.name if isinstance(target,exp.Schema) else target.name
            schema=self.schema(name);cols=[c.name for c in target.expressions] if isinstance(target,exp.Schema) else [n for n,t in schema]
            q=statement.expression.copy()
            if statement.args.get('with_'):q.set('with_',statement.args['with_'].copy())
            values=[]
            for n,t in schema:
                if n in cols: value=f'__new.{quote(n)}'
                elif n in self.serials.get(name,[]):value=f'(SELECT COALESCE(MAX({quote(n)}),0) FROM {name}) + ROW_NUMBER() OVER ()'
                else:value=self.defaults.get(name,{}).get(n,'NULL')
                values.append(f'CAST({value} AS {t}) AS {quote(n)}')
            query=f'SELECT * FROM {name} UNION ALL SELECT '+', '.join(values)+f' FROM ({q.sql(dialect="postgres")}) AS __new('+','.join(map(quote,cols))+')'
            self.emit(name,query,origin)
        elif isinstance(statement,exp.Delete):
            name=statement.this.name;alias=statement.this.alias_or_name
            where=statement.args.get('where');condition=where.this.sql(dialect='postgres') if where else 'TRUE'
            self.emit(name,self._with(statement)+f'SELECT * FROM {name} AS {quote(alias)} WHERE NOT COALESCE(({condition}), FALSE)',origin)
        elif isinstance(statement,exp.Alter):
            self.alter(statement,origin)
        else:raise ValueError(f'{origin}: unsupported {type(statement).__name__}: {statement}')

    def alter(self, statement, origin):
        name = statement.this.name
        for action in statement.args['actions']:
            schema = dict(self.schema(name))
            projection = None
            if isinstance(action, exp.ColumnDef):
                if action.name in schema and action.args.get('exists'):
                    continue
                dtype = action.args['kind']
                serial = dtype.this == exp.DataType.Type.SERIAL
                value = 'ROW_NUMBER() OVER ()' if serial else 'CAST(NULL AS ' + self.render(dtype) + ')'
                projection = '*, ' + value + ' AS ' + quote(action.name)
                if serial:
                    self.serials.setdefault(name, []).append(action.name)
            elif isinstance(action, (exp.RenameColumn, exp.AlterRename)):
                new = action.args['to'].name if isinstance(action, exp.RenameColumn) else statement.args['options'][0].this.name
                projection = '* RENAME (' + quote(action.this.name) + ' AS ' + quote(new) + ')'
            elif isinstance(action, exp.Drop):
                dropped = [c.name for c in action.args.get('tables', [action.this]) if c is not None and c.name in schema]
                if dropped:
                    projection = '* EXCLUDE (' + ', '.join(map(quote, dropped)) + ')'
            elif isinstance(action, exp.AlterColumn):
                dtype = action.args.get('dtype')
                if dtype:
                    column = quote(action.this.name)
                    projection = '* REPLACE (CAST(' + column + ' AS ' + self.render(dtype) + ') AS ' + column + ')'
                # NOT NULL and index constraints do not transform values.
            elif isinstance(action, exp.AlterSet):
                continue  # PostgreSQL parallel-worker performance settings.
            else:
                raise ValueError(f'{origin}: unsupported ALTER {action}')
            if projection:
                self.emit(name, 'SELECT ' + projection + ' FROM ' + name, origin)

    def close(self):
        for table in reversed(self.temp_names):self.con.execute('DROP TABLE IF EXISTS '+quote(table))


def _compile_qaqc(compiler, repository, release):
    previous = compiler.current.get('previous_pluto')
    compiler.active_comments=[]
    prior_release = 'previous_locked'
    if previous:
        rows = compiler.con.execute('SELECT version FROM ' + previous + ' WHERE version IS NOT NULL LIMIT 1').fetchall()
        if rows: prior_release = rows[0][0]
    for name in ('qaqc_expected','qaqc_bbl_diffs','qaqc_aggregate','qaqc_mismatch','qaqc_null','qaqc_outlier'):
        variants=[]
        conditions=[(None,None)] if name in ('qaqc_expected','qaqc_bbl_diffs') else [(True,True),(True,False),(False,True),(False,False)]
        for mapped,condo in conditions:
            text=read_pinned(repository,'pluto_build/sql/'+name+'.sql')
            text=text.replace(":'VERSION_PREV'",literal(prior_release)).replace(":'VERSION'",literal(release))
            condition=[]
            if mapped:condition.append('a.geom IS NOT NULL')
            if condo:condition.append("right(a.bbl::bigint::text,4) LIKE '75%%'")
            text=text.replace(':CONDO',str(bool(condo)).upper()).replace(':MAPPED',str(bool(mapped)).upper()).replace(':CONDITION',('WHERE '+' AND '.join(condition)) if condition else '')
            queries=[]
            for statement in sqlglot.parse(text,read='postgres'):
                if not isinstance(statement,exp.Insert):continue
                query=statement.expression.copy()
                if isinstance(query,exp.Subquery):query=query.this
                if statement.args.get('with_'):query.set('with_',statement.args['with_'].copy())
                queries.append(query.sql(dialect='postgres'))
            variant=name+('_'+str(mapped).lower()+'_'+str(condo).lower() if mapped is not None else '_current')
            compiler.emit(variant,' UNION ALL '.join('('+q+')' for q in queries),'pluto_build/sql/'+name+'.sql current-release SELECTs',materialized='table')
            variants.append(variant)
        compiler.emit(name,' UNION ALL '.join('SELECT * FROM '+v for v in variants),'05_qaqc.sh current-release variants',materialized='table')
    return {'history_policy':'Current release QA computed; historical accumulator rows are not copied.', 'previous_release':prior_release}


def compile_full_project(repository, destination, *, release, source_relations, connection, copy_null_sources=None):
    """Build a complete immutable SELECT-only dbt project from the pinned release.

    ``source_relations`` maps upstream aliases to existing DuckDB relations;
    ``connection`` must have spatial loaded. It is used for schema binding only.
    ``copy_null_sources`` identifies inputs whose CSV/seed import converts empty
    text to NULL. Pass aliases from the source preparation report; exclude
    already-restored PostgreSQL dumps. Independent input__ models keep existing
    transformation IDs stable when this policy changes.
    """
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    compiler=SelectCompiler(connection,destination,source_relations)
    paths=subprocess.run(['git','-C',str(repository),'ls-tree','-r','--name-only',PINNED_COMMIT,ROOT+'models'],check=True,capture_output=True,text=True).stdout.splitlines()
    source_models={Path(p).stem:read_pinned(repository,p.removeprefix(ROOT)) for p in paths if p.endswith('.sql')}
    def model(name):
        if name in compiler.current:return
        compiler.active_comments=[]
        text=_jinja_sql(source_models[name])
        for dep in re.findall(r"\{\{\s*ref\('([^']+)'\)",source_models[name]):model(dep)
        compiler.emit(name,text,'models/'+name+'.sql',materialized='table')
    try:
        seed_types = seed_column_types(repository)
        if copy_null_sources is None:
            seed_paths=subprocess.run(['git','-C',str(repository),'ls-tree','-r','--name-only',PINNED_COMMIT,ROOT+'seeds'],check=True,capture_output=True,text=True).stdout.splitlines()
            copy_null_sources={Path(path).stem for path in seed_paths if path.endswith('.csv')} | {'pluto_pts','pluto_input_geocodes','pluto_input_numbldgs'}
        copy_null_sources=sorted(set(copy_null_sources) & set(source_relations))
        for alias in copy_null_sources:
            fields=[]
            for column,dtype in compiler.schema(alias):
                kind=seed_types.get(alias,{}).get(column)
                if kind:
                    expression=seed_input_expression(column,kind) if dtype=='VARCHAR' else f'CAST({quote(column)} AS DECIMAL(38,12))' if kind=='Number' else quote(column)
                elif dtype=='VARCHAR':
                    expression=f"NULLIF({quote(column)}, '')"
                else:
                    continue
                fields.append(f'{expression} AS {quote(column)}')
            if fields:
                compiler.active_comments=['Seed loading follows dbt Agate inference and configured text overrides: numeric grouping commas are removed; blank and literal null values become NULL. Text codes retain their spelling.' if alias in seed_types else 'The pinned CSV import serializes empty strings as unquoted fields; PostgreSQL COPY reads them as NULL. Preserve whitespace and nonempty text.']
                compiler.emit(alias,'SELECT * REPLACE ('+', '.join(fields)+') FROM '+alias,'input_copy/'+alias+'.sql',model_name='input__'+alias)
        for name in sorted(source_models):
            if name.startswith('stg__'):model(name)
        for filename,field in ordered_steps(repository):
            if filename=='__enrichments__':
                model('pluto_enriched');continue
            text=read_pinned(repository,'pluto_build/sql/'+filename)
            if filename == 'create_pts.sql':
                text = re.sub(r'FROM pluto_pts\b', 'FROM stg__pluto_pts', text)
            text=text.replace(":'VERSION'",literal(release)).replace(":'build_schema'", "'main'")
            if field and '|' in field:
                table, geom = field.split('|')
                text = text.replace(':TABLE', table).replace(':GEOM', geom)
            elif field:text=text.replace(":'FIELD'",literal(field)).replace(':FIELD',field)
            text=re.sub(r'\bGEOMETRY\s*\(\s*GEOMETRY\s*,\s*4326\s*\)', 'GEOMETRY',text,flags=re.I)
            for idx,statement in enumerate(sqlglot.parse(text,read='postgres')):
                compiler.statement(statement,f'pluto_build/sql/{filename}'+(f' FIELD={field}' if field else '')+f' statement {idx+1}')
            # Bound mutation chains at each upstream file, so expensive joins
            # execute once and subsequent files read a checkpoint.
            if compiler.models and compiler.models[-1]['materialized']=='view':
                compiler.models[-1]['materialized']='table'
                file=destination/'models'/(compiler.models[-1]['name']+'.sql')
                file.write_text(file.read_text().replace("materialized='view'","materialized='table'",1))
        qaqc = _compile_qaqc(compiler, repository, release)
        # Native inputs and final geometry checkpoints already hold the data.
        # Projection-only staging and export aliases do not need disk copies.
        for row in compiler.models:
            if row['relation'].startswith(('stg__', 'mappluto')):
                row['materialized']='view'
                file=destination/'models'/(row['name']+'.sql')
                file.write_text(file.read_text().replace("materialized='table'","materialized='view'",1))
        outputs={}
        for name in ('pluto','export_pluto','archive_pluto','pluto_geom','pluto_removed_records','pluto_changes_applied','pluto_changes_not_applied','mappluto_gdb','mappluto_unclipped_gdb','mappluto','mappluto_unclipped','qaqc_expected','qaqc_bbl_diffs','qaqc_aggregate','qaqc_mismatch','qaqc_null','qaqc_outlier'):
            if name not in compiler.current:continue
            dep=compiler.current[name];outputs[name]=name
            (destination/'models'/(name+'.sql')).write_text("{{ config(materialized='view') }}\nSELECT * FROM {{ ref('"+dep+"') }}\n")
        project={'name':'moses_pluto_full','version':'1.0.0','config-version':2,'profile':'moses_pluto_full','model-paths':['models'],'on-run-start':compatibility_sql(),'models':{'moses_pluto_full':{'+materialized':'view'}}}
        import yaml
        (destination/'dbt_project.yml').write_text(yaml.safe_dump(project,sort_keys=False))
        for row in compiler.models:
            row['sha256']=hashlib.sha256((destination/'models'/(row['name']+'.sql')).read_bytes()).hexdigest()
        source_paths=subprocess.run(['git','-C',str(repository),'ls-tree','-r','--name-only',PINNED_COMMIT,ROOT],check=True,capture_output=True,text=True).stdout.splitlines()
        source_files=[{'path':path,'sha256':hashlib.sha256(read_pinned(repository,path.removeprefix(ROOT)).encode()).hexdigest()} for path in source_paths]
        manifest={'source_files':source_files,'source_commit':PINNED_COMMIT,'release':release,'model_count':len(compiler.models),'models':compiler.models,'outputs':outputs,'steps':[{'file':f,'field':v} for f,v in ordered_steps(repository)],'compatibility_macros':compatibility_sql(),'select_only':True,'update_match_policy':'Equality-key updates deduplicate the source once per eligible key, then LEFT JOIN; other predicates use LATERAL LIMIT 1. Both preserve target cardinality and matched NULL writes. Unless scoped by canonical_match_policy, multiple-match source choice is arbitrary, as upstream PostgreSQL UPDATE FROM permits.','qaqc':qaqc,'copy_null_sources':copy_null_sources,'copy_null_policy':'Named input__ models convert empty VARCHAR values to NULL where pinned CSV import/seed loading requires it; nonempty text and whitespace are preserved. Already-restored PostgreSQL dumps may retain meaningful empty strings and should not be included.','numeric_policy':{'bare_numeric':'DECIMAL(38,12)','integer_digits':26,'fractional_digits':12,'rounding':'Values beyond scale12 round on cast; NUMERIC multiplication results reset to scale12 after each operation, and decimal ratios recast before ROUND. Products must still fit DuckDB 38-digit intermediates (14 integer digits for two scale12 factors). PostgreSQL arbitrary precision is not claimed.','numeric_to_text':'Strip fixed-scale trailing zeros for numeric values; existing text stays unchanged.','varchar_casts':'Explicit VARCHAR(n) casts truncate to n characters as PostgreSQL does.'}}
        manifest['seed_types']=seed_types
        manifest['seed_policy']='Pinned dbt load_agate_table inference with configured text overrides. Text blank/literal null markers follow Agate; nonnull text codes retain spelling. Numbers remove validated grouping commas and cast strictly to DECIMAL(38,12). All pinned numeric source spellings are checked against Agate during compilation.'
        manifest['spatial_update_policy']='The pinned spatialjoins.sql uses unchanged PLUTO serial ids. Materialize matched-only id/value patch tables, then join each patch to the original full rows. This bounds geometry retained by lateral matching without copying full parcel tables; numbered transformation model IDs are preserved.'
        manifest['makevalid_policy']='Preserve collection inputs as MULTI when GEOS repairs to a singleton, matching PostGIS lwgeom_make_valid_params. Original atomic inputs and mixed-dimensional collections retain native repair behavior.'
        manifest['makevalid_reference']='https://postgis.net/docs/doxygen/3.7/da/de7/liblwgeom_8h_a35a00d93dcecd177a605b3aab52b5abd.html'
        manifest['numeric_policy']['census_tract_text']='The pinned ct2010 cleanup produces integer or two-digit fractional text. Its numeric-to-text assignment preserves that scale (170.10), while other numeric text continues to trim adaptation-introduced zeros.'
        manifest['union_aggregate_policy']='Single-argument PostgreSQL ST_Union returns SQL NULL for empty/all-NULL groups. Guard DuckDB ST_Union_Agg with COUNT(g)=0; preserve explicit nonnull empty geometries and mixed NULL/valid input. Binary ST_Union remains native.'
        manifest['canonical_match_policy']={
            'scope':'Equality-key CAMA update family and ZIP spatial fallback only.',
            'ordering':'Existing identity columns first (CAMA bbl,bldgnum,primebbl,billingbbl; ZIP zipcode,ogc_fid), then every remaining source column alphabetically. Canonical VARCHAR values ascend with NULLS LAST; geometry uses hexadecimal WKB. Equal full payload rows make identical assignments.',
            'interpretation':'Operational replay policy, not upstream business precedence or a choice derived from reference outputs.',
            'ordered_operations':[{'model':row['name'],'origin':row['origin'],**row['match_selection']} for row in compiler.models if row.get('match_selection',{}).get('canonical')],
            'remaining_unordered_operations':[{'model':row['name'],'origin':row['origin'],'method':row['match_selection']['method']} for row in compiler.models if 'match_selection' in row and not row['match_selection']['canonical']],
            'replay_limitation':'Other multiple-match UPDATE sources and existing upstream window ties retain their pinned unordered choice; complete replay invariance is not claimed.'}
        from .full_process import consolidate_project
        manifest=consolidate_project(destination,manifest)
        (destination/'full_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        return {'project_dir':str(destination),'profiles_dir':str(destination),'final_model':'pluto','export_model':'export_pluto','manifest':manifest,'outputs':outputs}
    finally:compiler.close()


def review_folder(model, origin=''):
    """Group the inspectable snapshot by business purpose; dbt IDs stay stable."""
    groups={
        'tax_records':('geocode_attributes','pts_property_records','tax_lot_attributes'),
        'allocation':('allocated_lots',),
        'cama':('parcel_cama',),
        'geometry':('tax_lot_geometry','parcel_geometry','shoreline_coverage','map_flags','pluto_geom'),
        'zoning':('zoning',),
        'enrichment':('mih','transit','parcel_enriched'),
        'corrections':('correction_decisions','pluto','pluto_changes_applied','pluto_changes_not_applied','pluto_removed_records'),
        'exports':('export_pluto','archive_pluto','mappluto','mappluto_unclipped','mappluto_gdb','mappluto_unclipped_gdb'),
    }
    for folder,names in groups.items():
        if model in names:return folder
    if model.startswith('qaqc_'):return 'qa'
    stage = Path(origin.split(' statement ')[0].split(' FIELD=')[0].split(' ')[0]).stem
    if stage.startswith('stg__') or origin.startswith('input_copy/'): return 'staging'
    if stage.startswith('qaqc_') or model.startswith('qaqc_'): return 'qa'
    if stage.startswith('corr_') or stage == 'remove_unitlots' or model.startswith('pluto_changes_') or model == 'pluto_removed_records': return 'corrections'
    if stage.startswith('export') or model in ('pluto','export_pluto','archive_pluto') or model.startswith('mappluto'): return 'exports'
    if stage.startswith('zoning_'): return 'zoning'
    if stage.startswith('cama_') or stage == 'create_cama_primebbl': return 'cama'
    if stage.startswith('int_') or stage in ('pluto_enriched','apply_dbt_enrichments'): return 'enrichment'
    if stage in ('create_pts','create_rpad_geo','zerovacantlots','lotarea','apdate'): return 'tax_records'
    if stage in ('primebbl','create_allocated','yearbuiltalt','allocated'): return 'allocation'
    if stage in ('dedupecondotable','dtmmergepolygons','plutogeoms','dtmgeoms','shorelineclip','update_empty_coord') or stage.startswith('plutomapid') or model == 'pluto_geom': return 'geometry'
    return 'attributes'


def write_review_project(compiled_project, destination, *, version_default='26v2m4', previous_version_default='26v1'):
    """Save the maintained dbt review snapshot without machine-specific paths.

    Regenerate this snapshot after changing the compiler or pinned upstream
    revision. Runtime builds still bind schemas to their explicit input lock.
    """
    import yaml

    source = Path(compiled_project)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    models_dir = destination / 'models'
    macros_dir = destination / 'macros'
    models_dir.mkdir(exist_ok=True)
    macros_dir.mkdir(exist_ok=True)
    for old in models_dir.rglob('*.sql'):
        old.unlink()
    for old in macros_dir.glob('*.sql'):
        old.unlink()
    manifest = json.loads((source / 'full_manifest.json').read_text())
    release = manifest['release']
    previous = manifest['qaqc']['previous_release']
    sources = set()
    origin_by_model = {row['name']: row['origin'] for row in manifest['models']}
    model_paths = {}
    folder_counts = {}

    def source_reference(match):
        name = match[1] or match[2]
        # Both source inventories have used dcp_pluto for the previous release.
        name = {'dcp_pluto': 'previous_pluto', 'dcp_mappluto': 'previous_pluto'}.get(name, name)
        sources.add(name)
        return "{{ source('pluto_inputs', '" + name + "') }}"

    for path in sorted((source / 'models').glob('*.sql')):
        sql = path.read_text()
        sql = re.sub(r'\bsources\.(?:"([^"]+)"|([A-Za-z_][A-Za-z_0-9]*))', source_reference, sql)
        sql = sql.replace(literal(release), "'{{ var(\"pluto_version\") }}'")
        sql = sql.replace(literal(previous), "'{{ var(\"previous_pluto_version\") }}'")
        folder = review_folder(path.stem, origin_by_model.get(path.stem, ''))
        folder_counts[folder] = folder_counts.get(folder, 0) + 1
        output = models_dir / folder / path.name
        output.parent.mkdir(exist_ok=True)
        output.write_text(sql)
        model_paths[path.stem] = output.relative_to(destination).as_posix()

    macro_names = []
    definitions = []
    for statement in compatibility_sql():
        name = 'define_' + re.search(r'MACRO (\w+)', statement)[1].lower()
        macro_names.append(name)
        definitions.append('{% macro ' + name + '() %}\n' + statement + '\n{% endmacro %}\n')
    (macros_dir / 'compatibility.sql').write_text('\n'.join(definitions))
    for path in sorted((source/'macros').glob('*.sql')):
        text=path.read_text()
        text=re.sub(r'\bsources\.(?:"([^"]+)"|([A-Za-z_][A-Za-z_0-9]*))',source_reference,text)
        text=text.replace(literal(release),"'{{ var(\"pluto_version\") }}'")
        text=text.replace(literal(previous),"'{{ var(\"previous_pluto_version\") }}'")
        sources.update(re.findall(r"source\('pluto_inputs',\s*'([^']+)'\)",text))
        (macros_dir/path.name).write_text(text)
    project = {
        'name': 'moses_pluto_full', 'version': '1.0.0', 'config-version': 2,
        'profile': 'moses_pluto_full', 'model-paths': ['models'], 'macro-paths': ['macros'],
        'vars': {'pluto_version': version_default, 'previous_pluto_version': previous_version_default},
        'on-run-start': ['{{ ' + name + '() }}' for name in macro_names],
        'models': {'moses_pluto_full': {'+materialized': 'view'}},
    }
    (destination / 'dbt_project.yml').write_text(yaml.safe_dump(project, sort_keys=False))
    source_config = {'version': 2, 'sources': [{
        'name': 'pluto_inputs', 'schema': 'sources',
        'description': 'Locked inputs and seeds prepared by Moses; see the build input lock and source preparation report.',
        'tables': [{'name': name} for name in sorted(sources)],
    }]}
    (models_dir / 'sources.yml').write_text(yaml.safe_dump(source_config, sort_keys=False))
    manifest['release'] = '{{ var("pluto_version") }}'
    manifest['qaqc']['previous_release'] = '{{ var("previous_pluto_version") }}'
    manifest['project_kind'] = 'Maintained review snapshot; regenerate with write_review_project after compiler changes.'
    manifest['source_schema'] = 'sources'
    manifest['business_folders'] = folder_counts
    manifest['output_paths'] = {name: model_paths[name] for name in manifest['outputs']}
    for row in manifest['models']:
        row['path'] = model_paths[row['name']]
        row['sha256'] = hashlib.sha256((destination / row['path']).read_bytes()).hexdigest()
    manifest['macro_hashes']={path.relative_to(destination).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in macros_dir.glob('*.sql')}
    (destination / 'full_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'README.md').write_text('''# PLUTO dbt transformation

Readable SELECT models for the complete pinned PLUTO build, corrections, exports,
and current-release QA. Upstream revision: `''' + PINNED_COMMIT + '''`.

The maintained snapshot uses `source('pluto_inputs', ...)` in the `sources`
schema. Moses prepares these relations from an explicit input lock, including
native Geosupport preprocessing when the captured input requires it. It does
not substitute a published finished PLUTO table for the candidate transformation.

| Folder | Purpose |
| --- | --- |
| [staging](models/staging) | Shared `input__*` CSV null adapters, canonical source attributes and geometry names. |
| [tax_records](models/tax_records) | PTS records, geocodes and initial DOF edits. |
| [allocation](models/allocation) | Billing lots, condominium allocation and years. |
| [attributes](models/attributes) | Base PLUTO fields, building class, flood and political attributes. |
| [cama](models/cama) | CAMA building area, basement, proximity and lot attributes. |
| [geometry](models/geometry) | Tax-lot geometry, coordinate backfill, map flags and shoreline clipping. |
| [zoning](models/zoning) | Districts, overlays, special districts and zoning maps. |
| [enrichment](models/enrichment) | FAR, landmarks, MIH and transit-zone assignments. |
| [corrections](models/corrections) | Researched edits, audit records and unit-lot removal. |
| [exports](models/exports) | Typed PLUTO and mapped output variants. |
| [qa](models/qa) | Expected values, aggregates, mismatches, nulls, outliers and BBL changes. |

The overview follows business execution order. Some folders contribute more
than one pass; the model-level `ref()` graph remains acyclic.

```mermaid
flowchart TD
  sources[Locked source relations] --> staging[Staging]
  staging --> tax[Tax records]
  tax --> allocation[Allocation]
  allocation --> base[Base attributes]
  base --> cama[CAMA attributes]
  cama --> lots[Lot geometry]
  staging --> lots
  lots --> zoning[Zoning]
  staging --> zoning
  zoning --> enrichment[Enrichment]
  staging --> enrichment
  enrichment --> final[Final spatial and political attributes]
  final --> shoreline[Map flags and shoreline clipping]
  shoreline --> corrections[Research corrections and unit-lot removal]
  staging --> corrections
  corrections --> exports[Typed exports]
  exports --> qa[Current-release QA]
  previous[Locked previous PLUTO] --> qa
```

Model names contain their source file and target relation. Each model header
identifies the upstream statement and retains business comments. Updates use
`* REPLACE`, and column changes use `* RENAME` or `* EXCLUDE`, so unchanged columns
are not repeated. Equality joins deduplicate eligible source keys once before a
LEFT JOIN, preserving both unmatched rows and matched NULL writes; other update
predicates retain the general LATERAL path. Every transformation is a SELECT; immutable versions retain
the original operation order through `ref()` dependencies.

`full_manifest.json` maps every model to its upstream statement, dependencies,
materialization, business-folder path and SHA-256. It also records hashes of every pinned PLUTO source
file and the compatibility policies. `macros/compatibility.sql` contains the
shared spatial and numeric adapters.

Geometry repair preserves MULTI wrappers for collection inputs, as PostGIS does;
this retains valid repaired zoning polygons in upstream geometry-type filters.
The census tract cleanup preserves the upstream two-digit suffix (`170.10`).

The service-area spatial updates use small materialized `patch__*` tables of
matched PLUTO serial ids and changed values. Each original update model joins
its patch to the parcel rows. This keeps large geometry out of nested matching
hashes and avoids copying full parcel tables at every spatial update.

The `pluto_version` dbt variable defaults to `''' + version_default + '''`;
`previous_pluto_version` defaults to `''' + previous_version_default + '''`.
The upstream export contract limits the current version field to six characters.
Use the runtime-generated project and profile from `moses pluto build` to execute
against the selected database. This directory is an inspectable, maintained
reference of that project's transformations.

After changing the compiler or pinned source, compile against the selected input
schemas, then call `write_review_project(compiled_project, destination)` from
`moses.pluto.full_compile` to regenerate this snapshot. Regeneration preserves
portable source references and dbt version variables.

Numeric compatibility uses DECIMAL(38,12) for bare PostgreSQL NUMERIC, normalizes
numeric text, resets scale after each numeric multiplication and restores decimal
rounding after division. PostgreSQL arbitrary
precision and historical production parity are not claimed. `input__*` models
restore empty-string-to-NULL behavior only for inputs loaded through the pinned
CSV import path. Seeds additionally restore dbt Agate type inference and declared
text overrides: grouping commas in numeric values are removed, blank and literal
null markers follow Agate, and text codes retain their spelling. Already-restored
PostgreSQL dumps retain their captured
empty/null distinction. Multiple source matches use one arbitrary row, as
PostgreSQL UPDATE FROM also permits. QA files
contain current calculations; historical QA accumulator rows are not copied.
''')
    if 'consolidation' in manifest:
        from .full_process import process_readme
        (destination/'README.md').write_text(process_readme(manifest,version_default))
    return {'project_dir': str(destination), 'models': len(manifest['models']) if 'consolidation' in manifest else len(manifest['models']) + len(manifest['outputs']),
            'sources': sorted(sources)}
