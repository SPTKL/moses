"""Compare every prepared table with the legacy source-cleaning SELECTs.

Maintenance verification only: this is not part of Moses preparation or dbt.
Both databases are read-only. EXCEPT ALL retains duplicate and NULL semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


def verify(prepared_directory, legacy_directory, extension_directory):
    prepared_directory, legacy_directory = Path(prepared_directory), Path(legacy_directory)
    manifest = json.loads((prepared_directory / 'manifest.json').read_text())
    if manifest['status'] != 'ready':
        raise ValueError('Prepared collection is not ready')
    macro_path = ROOT / 'src/pluto_example/dbt_full/macros/pluto_inputs.sql'
    environment = Environment()
    environment.globals['source'] = lambda package, name: 'legacy.sources.' + identifier(name)
    macros = environment.from_string(macro_path.read_text()).make_module()
    with duckdb.connect(config={'extension_directory': str(Path(extension_directory).resolve()),
                                'autoinstall_known_extensions': False,
                                'autoload_known_extensions': False,
                                'memory_limit': '4GB', 'threads': 1,
                                'preserve_insertion_order': False}) as con:
        con.execute('LOAD spatial')
        con.execute('ATTACH ' + literal(legacy_directory / 'pluto.duckdb') + ' AS legacy (READ_ONLY)')
        con.execute('ATTACH ' + literal(prepared_directory / 'prepared.duckdb') + ' AS prepared (READ_ONLY)')
        identity = con.execute('SELECT input_id,descriptor_sha256 FROM prepared.preparation.identity').fetchall()
        if identity != [(manifest['input_id'], manifest['descriptor_sha256'])]:
            raise ValueError('Prepared database identity differs from its ready manifest')
        tables = []
        for source in manifest['sources']:
            name = source['name']
            # Only the 33 input-copy branches implement physical cleanup.
            # The remaining nine source relations were already consumed directly.
            marker = "alias == '" + name + "'"
            old = macros.pluto_input(name).strip() if marker in macro_path.read_text() else 'SELECT * FROM legacy.sources.' + identifier(name)
            new = 'SELECT * FROM prepared.sources.' + identifier(name)
            con.execute('CREATE OR REPLACE TEMP VIEW before_source AS ' + old)
            con.execute('CREATE OR REPLACE TEMP VIEW after_source AS ' + new)
            before_schema = [(row[0], row[1]) for row in con.execute('DESCRIBE before_source').fetchall()]
            after_schema = [(row[0], row[1]) for row in con.execute('DESCRIBE after_source').fetchall()]
            if before_schema != after_schema:
                raise ValueError('Schema mismatch for ' + name)
            added = con.execute('SELECT count(*) FROM (SELECT * FROM after_source EXCEPT ALL SELECT * FROM before_source)').fetchone()[0]
            removed = con.execute('SELECT count(*) FROM (SELECT * FROM before_source EXCEPT ALL SELECT * FROM after_source)').fetchone()[0]
            tables.append({'name': name, 'rows': source['rows'], 'schema_equal': True,
                           'added_rows': added, 'removed_rows': removed})
            print(name + ': added=' + str(added) + ', removed=' + str(removed), flush=True)
    return {'input_id': manifest['input_id'], 'tables': tables,
            'equal': all(not row['added_rows'] and not row['removed_rows'] for row in tables),
            'legacy_macro_sha256': hashlib.sha256(macro_path.read_bytes()).hexdigest(),
            'policy': 'All columns and exact row multisets; NULLs and duplicate rows retained; schema names/order/types must match.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', required=True)
    parser.add_argument('--legacy', required=True)
    parser.add_argument('--extension-directory', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.prepared, args.legacy, args.extension_directory)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    raise SystemExit(0 if result['equal'] else 1)
