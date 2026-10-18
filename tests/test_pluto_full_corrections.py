"""Business correction models versus the pinned statement-by-statement rules."""
from collections import Counter
from pathlib import Path
import re

import duckdb
from jinja2 import Environment, StrictUndefined
import pytest
import sqlglot

from moses.pluto.full_compile import SelectCompiler, compatibility_sql, ordered_steps, read_pinned
from moses.pluto.full_corrections import build_correction_models


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / '.extensions'
REPOSITORY = ROOT.parent / 'data-engineering'
pytestmark = pytest.mark.skipif(not list(EXTENSIONS.glob('*/**/spatial.duckdb_extension')),
                                reason='requires installed local Spatial extension')

FIELDS = ('id', 'bbl', 'lot', 'lotarea', 'bldgarea', 'lotfront', 'lotdepth',
          'builtfar', 'yearbuilt', 'ownername', 'cd', 'numfloors', 'numbldgs',
          'unitsres', 'unitstotal', 'bct2020', 'address', 'version', 'sentinel', 'geom')


def _lot(identifier, **changes):
    result = dict(id=identifier, bbl=str(1000000000 + identifier), lot='1',
                  lotarea='100', bldgarea='10', lotfront='1', lotdepth='2',
                  builtfar='0.1', yearbuilt='1900', ownername='OWNER', cd='101',
                  numfloors='1', numbldgs='1', unitsres='1', unitstotal='1',
                  bct2020='1000100', address='ADDRESS ' + str(identifier),
                  version='26v2m3', sentinel='preserved', geom=None)
    result.update(changes)
    return result


def _research(lot, field, old, new, *, reason='fixture', version='26v1', type_=2):
    return (None if lot is None else str(1000000000 + lot), field, old, new, type_, reason, version)


def _connection(lots, research):
    con = duckdb.connect()
    con.execute("SET extension_directory='" + str(EXTENSIONS) + "'")
    con.execute('LOAD spatial')
    for statement in compatibility_sql():
        con.execute(statement)
    declarations = [f'"{field}" ' + ('BIGINT' if field == 'id' else 'GEOMETRY' if field == 'geom' else 'VARCHAR') for field in FIELDS]
    con.execute('CREATE TABLE map_flags(' + ','.join(declarations) + ')')
    for lot in lots:
        con.execute('INSERT INTO map_flags VALUES (' + ','.join('ST_GeomFromText(?)' if f == 'geom' else '?' for f in FIELDS) + ')', [lot[f] for f in FIELDS])
    con.execute('CREATE TABLE research(bbl VARCHAR,field VARCHAR,old_value VARCHAR,new_value VARCHAR,"Type" DECIMAL(38,12),reason VARCHAR,version VARCHAR)')
    if research:
        con.executemany('INSERT INTO research VALUES (?,?,?,?,?,?,?)', research)
    return con


def _new(con):
    definitions = build_correction_models(research_sql='research')
    env = Environment(undefined=StrictUndefined)
    env.globals['ref'] = lambda name: name
    macros = '\n'.join(definitions['macros'].values())
    for name, body in definitions['models'].items():
        rendered = env.from_string(macros + '\n' + body).render()
        con.execute('CREATE TABLE "' + name + '" AS ' + rendered)
    return {name: name for name in definitions['models']}


def _old(con, tmp_path):
    if not (REPOSITORY / '.git').exists():
        pytest.skip('pinned upstream checkout required for equivalence checks')
    compiler = SelectCompiler(con, tmp_path / 'legacy', {
        'pluto': 'map_flags', 'pluto_input_research': 'research',
        'stg__pluto_input_research': 'research',
    })
    for filename, field in ordered_steps(REPOSITORY):
        if not filename.startswith('corr_') and filename != 'remove_unitlots.sql':
            continue
        text = read_pinned(REPOSITORY, 'pluto_build/sql/' + filename)
        if field:
            text = text.replace(":'FIELD'", repr(field)).replace(':FIELD', field)
        for number, statement in enumerate(sqlglot.parse(text, read='postgres'), 1):
            if statement is not None:
                compiler.statement(statement, 'pluto_build/sql/' + filename + f' statement {number}')
    for model in compiler.models:
        sql = (compiler.destination / 'models' / (model['name'] + '.sql')).read_text()
        sql = re.sub(r'\{\{\s*config\([^\n]*\)\s*\}\}', '', sql)
        sql = re.sub(r"\{\{\s*ref\('([^']+)'\)\s*\}\}", r'\1', sql)
        con.execute('DROP TABLE "' + model['name'] + '"')
        con.execute('CREATE TABLE "' + model['name'] + '" AS ' + sql)
    return {name: compiler.current[name] for name in ('pluto', 'pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records')}


def _equivalent(tmp_path, lots, research):
    actual = _connection(lots, research)
    expected = _connection(lots, research)
    try:
        new = _new(actual)
        old = _old(expected, tmp_path)
        for output, relation in old.items():
            actual_schema = actual.execute('DESCRIBE SELECT * FROM ' + new[output]).fetchall()
            expected_schema = expected.execute('DESCRIBE SELECT * FROM ' + relation).fetchall()
            assert [(r[0], r[1]) for r in actual_schema] == [(r[0], r[1]) for r in expected_schema], output
            assert Counter(actual.execute('SELECT * FROM ' + new[output]).fetchall()) == Counter(expected.execute('SELECT * FROM ' + relation).fetchall()), output
    finally:
        expected.close()
    return actual


def test_numeric_area_nulls_auto_area_and_recalculated_far_match_pinned_rules(tmp_path):
    square = 'POLYGON((-74 40.7,-73.9999 40.7,-73.9999 40.7001,-74 40.7001,-74 40.7))'
    lots = [_lot(1, lotarea=None), _lot(2), _lot(3, lotarea='100.0', bldgarea='20'),
            _lot(4, lotarea='0', geom=square), _lot(5, lotarea='0', geom=square),
            _lot(6, lotfront='1.00', lotdepth=None)]
    changes = [_research(1, 'lotarea', '0', '20'), _research(2, 'lotarea', None, '20'),
               _research(3, 'lotarea', '100', '200'), _research(3, 'bldgarea', '20.00', '40'),
               _research(5, 'lotarea', '999', '20'), _research(6, 'lotfront', '1', '2'),
               _research(6, 'lotdepth', '0', '3')]
    con = _equivalent(tmp_path, lots, changes)
    try:
        assert con.execute("SELECT builtfar FROM pluto WHERE id=3").fetchone()[0] == '0.2'
        assert con.execute("SELECT count(*) FROM correction_decisions WHERE target_id IN (1,2)").fetchone()[0] == 0
        assert con.execute("SELECT reason FROM pluto_changes_applied WHERE bbl='1000000004'").fetchone()[0] == 'Zero lot area'
        assert con.execute("SELECT dcpedited FROM pluto WHERE id=5").fetchone()[0] is None
    finally:
        con.close()


def test_specific_global_null_writes_and_per_insert_audit_multiplicity(tmp_path):
    lots = [_lot(1, ownername='OLD'), _lot(2, yearbuilt=None), _lot(3),
            _lot(4, ownername='. STANDALONE'), _lot(5, ownername='NOOP')]
    noop_specific = _research(5, 'ownername', 'NOOP', 'NOOP', reason='same')
    noop_global = _research(None, 'ownername', 'NOOP', 'NOOP', reason='same')
    changes = [_research(1, 'ownername', 'OLD', 'MID'), _research(None, 'ownername', 'MID', '. CLEAN'),
               _research(None, 'ownername', '. CLEAN', 'DO NOT CHAIN'), _research(2, 'yearbuilt', None, '1850'),
               _research(2, 'numbldgs', '1', None), _research(3, 'cd', '100', '102'),
               _research(999, 'yearbuilt', '1900', '1800'), _research(None, 'ownername', 'ABSENT', 'UNUSED'),
               noop_specific, noop_specific, noop_global, noop_global,
               _research(5, 'ownername', 'NOOP', 'NOOP', reason='same', version='26v2')]
    con = _equivalent(tmp_path, lots, changes)
    try:
        assert con.execute('SELECT ownername FROM pluto WHERE id=1').fetchone()[0] == 'CLEAN'
        assert con.execute('SELECT yearbuilt,numbldgs FROM pluto WHERE id=2').fetchone() == ('1850', None)
        assert con.execute('SELECT ownername,dcpedited FROM pluto WHERE id=4').fetchone() == ('STANDALONE', 't')
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE bbl='1000000004'").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE bbl='1000000005' AND version='26v1'").fetchone()[0] == 2
        assert con.execute("SELECT found_value FROM pluto_changes_not_applied WHERE bbl='1000000003'").fetchone()[0] == '101'
        assert con.execute("SELECT count(*) FROM correction_decisions WHERE bbl='1000000999'").fetchone()[0] == 0
    finally:
        con.close()


def test_removal_order_concat_keys_and_research_audits_survive_removal(tmp_path):
    point = 'POINT(-74 40.7)'
    lots = [_lot(1, lot='1001', unitstotal='2', address='PAIR'),
            _lot(2, lot='1002', geom=point, address='PAIR'),
            _lot(3, lot='1003', geom=point, address='A1', bldgarea='2'),
            _lot(4, lot='1004', geom=point, address='A1', bldgarea='2'),
            _lot(5, lot='1005', geom=point, address='A', bldgarea='12'),
            _lot(6, lot='7501', unitstotal='2'), _lot(7, lot='1007')]
    changes = [_research(7, 'unitstotal', '1', '2'), _research(3, 'yearbuilt', '1900', '1890')]
    con = _equivalent(tmp_path, lots, changes)
    try:
        assert con.execute('SELECT id FROM pluto ORDER BY id').fetchall() == [(2,), (6,)]
        assert con.execute('SELECT id FROM pluto_removed_records ORDER BY id').fetchall() == [(1,), (3,), (4,), (5,), (7,)]
        assert con.execute("SELECT unitstotal FROM pluto_removed_records WHERE id=7").fetchone()[0] == '2'
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE bbl IN ('1000000003','1000000007')").fetchone()[0] == 2
    finally:
        con.close()


def test_audit_distinct_uses_original_columns_not_target_id_or_applied_found_value(tmp_path):
    lots = [_lot(1, lotarea='100'), _lot(2, bbl='1000000001', lotarea='100.0')]
    changes = [_research(1, 'lotarea', '100.00', '200'),
               _research(1, 'lotdepth', '999', '3'),
               _research(1, 'ownername', 'OWNER', 'OWNER', reason='same'),
               _research(None, 'ownername', 'OWNER', 'OWNER', reason='same')]
    # Rejected area records distinguish lexical found values; applied records do
    # not. Duplicate lot BBLs are intentionally retained to exercise INSERT grain.
    lots[0]['lotdepth'] = '2'
    lots[1]['lotdepth'] = '2.0'
    con = _equivalent(tmp_path, lots, changes)
    try:
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE field='lotarea'").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE field='ownername'").fetchone()[0] == 2
        assert con.execute("SELECT found_value FROM pluto_changes_not_applied ORDER BY found_value").fetchall() == [('2',), ('2.0',)]
        assert con.execute('SELECT lotarea FROM pluto ORDER BY id').fetchall() == [('200',), ('200',)]
    finally:
        con.close()


def test_final_removal_deletes_by_bbl_but_captures_only_rows_matching_each_removal(tmp_path):
    lots = [_lot(1, lot='1001', unitstotal='2'),
            _lot(2, bbl='1000000001', lot='1002', geom='POINT(-74 40.7)', address='SHARED'),
            _lot(3), _lot(4, bbl=None), _lot(5, bbl=None, lot='1005', unitstotal='2'),
            _lot(6, lot='1006', geom='POINT(-74 40.7)', address='SHARED')]
    con = _equivalent(tmp_path, lots, [])
    try:
        assert con.execute('SELECT id FROM pluto ORDER BY id').fetchall() == [(3,), (4,)]
        assert con.execute('SELECT id FROM pluto_removed_records ORDER BY id').fetchall() == [(1,), (2,), (5,), (6,)]
    finally:
        con.close()


def test_automatic_area_writes_and_far_eligibility_follow_audit_bbl_not_target_id(tmp_path):
    square = 'POLYGON((-74 40.7,-73.9999 40.7,-73.9999 40.7001,-74 40.7001,-74 40.7))'
    lots = [_lot(1, lotarea='0', geom=square),
            _lot(2, bbl='1000000001', lotarea='0', geom=None),
            _lot(3, lotarea='100', bldgarea='20', builtfar='999'),
            _lot(4, bbl='1000000003', lotarea='200', bldgarea='20', builtfar='999')]
    con = _equivalent(tmp_path, lots, [_research(3, 'lotarea', '100', '400')])
    try:
        automatic = con.execute('SELECT lotarea,dcpedited FROM pluto WHERE id IN (1,2) ORDER BY id').fetchall()
        assert automatic[0] == automatic[1]
        assert automatic[0][0] != '0'
        assert automatic[0][1] == 't'
        assert con.execute("SELECT count(*) FROM pluto_changes_applied WHERE bbl='1000000001'").fetchone()[0] == 1
        assert con.execute('SELECT lotarea,builtfar,dcpedited FROM pluto WHERE id=4').fetchone() == ('200', '0.1', None)
    finally:
        con.close()


@pytest.mark.parametrize('values', [('1800', '1850'), (None, '1850')])
def test_conflicting_eligible_proposals_fail_with_evidence_instead_of_silent_choice(values):
    con = _connection([_lot(1)], [_research(1, 'yearbuilt', '1900', v) for v in values])
    try:
        with pytest.raises(duckdb.Error, match='Conflicting research corrections for BBL 1000000001, field yearbuilt, pass specific'):
            _new(con)
    finally:
        con.close()


def test_model_contract_is_five_named_select_models_and_shared_semantic_macros():
    result = build_correction_models()
    assert set(result['models']) == {'correction_decisions', 'pluto', 'pluto_changes_applied', 'pluto_changes_not_applied', 'pluto_removed_records'}
    assert len(result['macros']) == 1
    assert all(value == 'table' for value in result['materialized'].values())
    assert 'corrected_lot_rows' in next(iter(result['macros'].values()))
