"""Publish immutable, physical source collections for independent transformations.

Preparation owns acquisition adapters and physical input normalization. It never
runs dbt, imports a business compiler, or materializes product output models.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

import duckdb
import yaml


class PreparedError(ValueError):
    """A collection cannot be published with its declared input identity."""


PLUTO_COMMIT='32bc98f632f15e7182933a17fb61ecf74e853518'
NATIVE_PREPARATION={
    'pluto_input_geocodes':{'adapter':'nyc_geosupport_parcel_cohort','runtime':'explicit_pinned_bundle','axis_policy':'historical_recipe_compatibility; generic address recipes use longitude as X'},
    'pluto_input_numbldgs':{'adapter':'nyc_geosupport_building_counts','runtime':'explicit_pinned_bundle','axis_policy':'historical_recipe_compatibility; generic address recipes use longitude as X'},
}


def _hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _literal(value):
    return "'"+str(value).replace("'","''")+"'"


def _identifier(value):
    return '"'+str(value).replace('"','""')+'"'


def _load(value):
    if isinstance(value,dict):return value
    path=Path(value)
    def unique(pairs):
        result={}
        for key,item in pairs:
            if key in result:raise PreparedError('Duplicate recipe/lock key: '+str(key))
            result[key]=item
        return result
    class UniqueLoader(yaml.SafeLoader):pass
    def mapping(loader,node):
        loader.flatten_mapping(node)
        return unique(loader.construct_pairs(node))
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
    result=json.loads(path.read_text(),object_pairs_hook=unique) if path.suffix.lower()=='.json' else yaml.load(path.read_text(),Loader=UniqueLoader)
    if not isinstance(result,dict):raise PreparedError('Recipe/lock must be a mapping')
    return result


def _versions(lock):
    versions=lock.get('versions',lock.get('input_lock',{}).get('versions'))
    if not isinstance(versions,dict) or not versions or any(not isinstance(value,str) or not value for value in versions.values()):
        raise PreparedError('An explicit nonempty versions input lock is required')
    return versions


def _validate_recipe(recipe,versions):
    metadata={'description','note','preparation','upstream','provisional'}
    unknown=set(recipe)-({'schema_version','kind','name','provider','release','source_commit','previous_release','inputs'}|metadata)
    if unknown:raise PreparedError('Unknown collection fields: '+', '.join(sorted(unknown)))
    if type(recipe.get('schema_version')) is not int or recipe['schema_version']!=1 or recipe.get('kind')!='source_collection':
        raise PreparedError('Expected schema_version 1 source_collection recipe')
    if recipe.get('provider')!='nyc_pluto_26v2':
        raise PreparedError('Unsupported collection provider: '+str(recipe.get('provider')))
    for field,value in (('release','26v2'),('previous_release','26v1'),('source_commit',PLUTO_COMMIT)):
        if recipe.get(field)!=value:raise PreparedError('nyc_pluto_26v2 requires '+field+'='+value)
    if not isinstance(recipe.get('name'),str) or not recipe['name']:
        raise PreparedError('Collection name must be nonempty')
    inputs=recipe.get('inputs')
    if not isinstance(inputs,list) or not inputs:raise PreparedError('Collection inputs must be a nonempty list')
    names=set();datasets=set()
    for item in inputs:
        if not isinstance(item,dict):raise PreparedError('Collection inputs must be mappings')
        unknown=set(item)-({'name','source','role','columns'}|metadata)
        if unknown:raise PreparedError('Unknown input fields: '+', '.join(sorted(unknown)))
        name=item.get('name');source=item.get('source',{})
        if not isinstance(source,dict) or set(source)-({'kind','dataset','version'}|metadata):
            raise PreparedError(str(name)+': unsupported source fields')
        if 'provisional' in item and not isinstance(item['provisional'],bool):
            raise PreparedError(str(name)+': provisional must be boolean')
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',name) or name in names:
            raise PreparedError('Collection source names must be unique SQL identifiers')
        names.add(name)
        if source.get('kind')!='catalog' or source.get('version')!='input_lock' or not source.get('dataset'):
            raise PreparedError(name+': expected exact catalog input_lock source')
        dataset=source['dataset']
        if not isinstance(dataset,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',dataset):
            raise PreparedError(name+': catalog dataset must be a valid identifier')
        declared=item.get('preparation')
        required=NATIVE_PREPARATION.get(name) if dataset.startswith('raw__') else None
        if required is not None and declared!=required:
            raise PreparedError(name+': preparation must match the pinned native adapter, runtime and axis_policy')
        if required is None and declared is not None:
            raise PreparedError(name+': per-input preparation is unsupported for this provider source')
        if dataset in datasets:raise PreparedError('Duplicate catalog source '+dataset)
        datasets.add(dataset)
        if item.get('role') not in ('prepared_input','retained_source'):
            raise PreparedError(name+': role must be prepared_input or retained_source')
        if not isinstance(item.get('columns',{}),dict):raise PreparedError(name+': columns must be a mapping')
        for field,policy in item.get('columns',{}).items():
            if not isinstance(field,str) or not field:raise PreparedError(name+': column names must be nonempty strings')
            if not isinstance(policy,dict) or set(policy)-{'nulls','type','numeric_grouping'}:
                raise PreparedError(name+'.'+field+': unsupported column policy')
            if policy.get('nulls') not in (None,'empty','trimmed_empty_or_null'):
                raise PreparedError(name+'.'+field+': unsupported null policy')
            if policy.get('type') not in (None,'decimal_38_12'):
                raise PreparedError(name+'.'+field+': unsupported type policy')
            if 'numeric_grouping' in policy and not isinstance(policy['numeric_grouping'],bool):
                raise PreparedError(name+'.'+field+': numeric_grouping must be boolean')
            if policy.get('numeric_grouping') and policy.get('type')!='decimal_38_12':
                raise PreparedError(name+'.'+field+': numeric_grouping requires decimal_38_12')
    if datasets!=set(versions):
        raise PreparedError('Recipe catalog inputs differ from lock: missing='+str(sorted(datasets-set(versions)))+', extra='+str(sorted(set(versions)-datasets)))
    if not any(item['role']=='prepared_input' for item in inputs):raise PreparedError('No prepared inputs were declared')
    return inputs


def _catalog_inputs(catalog,inputs,versions):
    records=[]
    for item in inputs:
        dataset=item['source']['dataset'];version=versions[dataset]
        manifest=catalog.get_version(dataset,version)
        if manifest.get('version')!=version or not manifest.get('content_sha256'):
            raise PreparedError(dataset+': catalog version/hash does not match the exact lock')
        path=Path(manifest['parquet_path']).resolve(strict=True)
        records.append({'name':item['name'],'role':item['role'],'catalog_name':dataset,'catalog_version':version,
                        'source_content_sha256':manifest['content_sha256'],'source_rows':manifest['row_count'],
                        'parquet_path':str(path),'provisional':bool(item.get('provisional',False)),
                        'upstream':item.get('upstream'), 'columns_policy':item.get('columns',{})})
    return records


def _verify_source_report(report,records,versions):
    if report.get('status') not in ('prepared','prepared_provisional'):
        raise PreparedError('Source preparation report is incomplete')
    if _versions(report.get('input_lock',{}))!=versions:
        raise PreparedError('Source preparation lock differs from requested exact versions')
    source_records=report.get('inputs',[])
    by_name={row['catalog_name']:row for row in source_records}
    if len(by_name)!=len(records) or set(by_name)!=set(versions):
        raise PreparedError('Source preparation lineage inventory differs from the lock')
    for row in records:
        source=by_name[row['catalog_name']]
        if source.get('catalog_version')!=row['catalog_version'] or source.get('content_sha256')!=row['source_content_sha256']:
            raise PreparedError(row['catalog_name']+': cached source version/content hash differs from catalog')
        if Path(source.get('parquet_path','')).resolve()!=Path(row['parquet_path']):
            raise PreparedError(row['catalog_name']+': cached catalog path differs')
        row['provisional']=bool(source.get('provisional',row['provisional']))
    identity={'versions':versions,'content':{row['catalog_name']:row['source_content_sha256'] for row in records},
              'runtime':report.get('native_runtime'),'code_sha256':report.get('code_sha256')}
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    if fingerprint!=report.get('fingerprint'):
        raise PreparedError('Source preparation fingerprint does not match its recorded identity')
    if any(row['name'] in NATIVE_PREPARATION and row['catalog_name'].startswith('raw__') for row in records) and not report.get('native_runtime'):
        raise PreparedError('Native recipe inputs require a recorded pinned native runtime')
    return fingerprint


def _legacy_source(build,records,versions,recipe):
    build=Path(build).resolve(strict=True)
    report_path=build/'build-report.json';source_path=build/'source-preparation.json'
    report=_load(report_path);sources=_load(source_path)
    if report.get('status')!='completed' or not report.get('run_id'):
        raise PreparedError('Legacy source migration requires a completed build report with run identity')
    if not isinstance(report.get('output'),dict) or not report['output'].get('version'):
        raise PreparedError('Legacy source migration requires a completed accepted output receipt')
    if report.get('input_lock')!=versions:
        raise PreparedError('Legacy build lock differs from requested exact versions')
    if recipe.get('source_commit') and report.get('upstream_commit')!=recipe['source_commit']:
        raise PreparedError('Legacy build upstream revision differs from the collection recipe')
    fingerprint=_verify_source_report(sources,records,versions)
    recorded=report.get('sources',{})
    for key in ('fingerprint','code_sha256','native_runtime','input_lock'):
        if recorded.get(key)!=sources.get(key):raise PreparedError('Legacy build/source reports disagree on '+key)
    implementation=report.get('implementation',{}).get('full_sources.py',{})
    archive=Path(implementation.get('path','')).resolve(strict=True)
    if not archive.is_relative_to(build) or archive.name!='full_sources.py':
        raise PreparedError('Legacy source implementation must be archived inside the completed build')
    code_hash=_hash(archive)
    if code_hash!=implementation.get('sha256') or code_hash!=sources.get('code_sha256'):
        raise PreparedError('Legacy archived source implementation hash differs from cached identity')
    database=build/'pluto.duckdb'
    if Path(sources.get('database_path','')).resolve()!=database:
        raise PreparedError('Legacy report points to a different source database')
    migration={'mode':'legacy_completed_build','build_path':str(build),'run_id':report['run_id'],
               'build_report_sha256':_hash(report_path),'source_report_sha256':_hash(source_path),
               'archived_implementation':str(archive),'archived_code_sha256':code_hash,
               'source_fingerprint':fingerprint,'native_runtime':sources.get('native_runtime'),
               'production_parity':bool(sources.get('production_parity',False))}
    return database,sources,migration


def _normalization_query(relation,columns,policies):
    """Apply explicit spelling/type policies while retaining column order.

    Grouped decimals require conventional three-digit comma groups before
    commas are removed. This is stricter than blindly replacing commas; plain
    numeric spellings still use DuckDB's strict DECIMAL cast, never TRY_CAST.
    """
    known=dict(columns);expressions=[]
    for name,policy in policies.items():
        if name not in known:raise PreparedError('Normalization references missing column '+name)
        expression=_identifier(name)
        nulls=policy.get('nulls')
        if nulls:
            if known[name].upper()!='VARCHAR':raise PreparedError(name+': null spelling policy requires VARCHAR input')
            if nulls=='empty':expression='NULLIF('+expression+", '')"
            else:expression="CASE WHEN lower(trim("+expression+")) IN ('','null') THEN NULL ELSE "+expression+' END'
        if policy.get('numeric_grouping'):
            text='CAST(('+expression+') AS VARCHAR)'
            pattern=r'^[+-]?[0-9]{1,3}(,[0-9]{3})+(\.[0-9]+)?$'
            expression="CASE WHEN contains("+text+", ',') AND NOT regexp_full_match(trim("+text+'), '+_literal(pattern)+') THEN error('+_literal('Invalid numeric grouping in '+name)+') ELSE replace('+text+", ',', '') END"
        if policy.get('type')=='decimal_38_12':expression='CAST(('+expression+') AS DECIMAL(38,12))'
        if policy:expressions.append(expression+' AS '+_identifier(name))
    replacement=' REPLACE ('+', '.join(expressions)+')' if expressions else ''
    return 'SELECT *'+replacement+' FROM '+relation


def prepare_collection(catalog,recipe_path,*,input_lock,output_dir,extension_directory,
                       geosupport_release=None,geosupport_extension=None,geosupport_home=None,
                       legacy_source_build=None):
    """Publish prepared.duckdb plus a ready manifest in a new directory.

    Explicit legacy migration reads completed source tables only and verifies
    their archived implementation identity. It never reruns business models or
    rewrites the identity to match the currently installed source adapter.
    """
    recipe=_load(recipe_path);lock=_load(input_lock);versions=_versions(lock)
    if legacy_source_build and any(value is not None for value in (geosupport_release,geosupport_extension,geosupport_home)):
        raise PreparedError('Native runtime arguments cannot be combined with legacy source migration; its recorded runtime is preserved')
    inputs=_validate_recipe(recipe,versions);records=_catalog_inputs(catalog,inputs,versions)
    output_dir=Path(output_dir).resolve();output_dir.mkdir(parents=True,exist_ok=False)
    final=output_dir/'prepared.duckdb';temporary=output_dir/('.prepared-'+uuid.uuid4().hex+'.duckdb')
    manifest_path=output_dir/'manifest.json';source_report=None;source_database=None;before=None;con=None
    try:
        if legacy_source_build:
            source_database,source_report,provenance=_legacy_source(legacy_source_build,records,versions,recipe)
            before=_hash(source_database)
            provenance['source_database_sha256_before']=before
        else:
            from .pluto.full_sources import prepare_sources
            source_database=output_dir/'.source-work.duckdb'
            source_report=prepare_sources(catalog,lock,source_database,extension_directory,
                geosupport_release=geosupport_release,geosupport_extension=geosupport_extension,geosupport_home=geosupport_home)
            _verify_source_report(source_report,records,versions)
            provenance={'mode':'source_adapters','source_fingerprint':source_report['fingerprint'],
                        'source_code_sha256':source_report['code_sha256'],'native_runtime':source_report.get('native_runtime')}
        descriptor={'recipe':recipe,'input_lock':versions,'preparation_provenance':json.loads(json.dumps(provenance))}
        descriptor_hash=_json_hash(descriptor);input_id=str(uuid.uuid4())
        con=duckdb.connect(str(temporary),config={'extension_directory':str(Path(extension_directory).resolve()),
            'autoinstall_known_extensions':False,'autoload_known_extensions':False})
        con.execute('LOAD spatial');con.execute("SET memory_limit='4GB'");con.execute('SET threads=1')
        con.execute('SET preserve_insertion_order=false')
        con.execute('ATTACH '+_literal(source_database)+' AS captured (READ_ONLY)')
        identity=con.execute('SELECT fingerprint FROM captured.source_work.identity').fetchall()
        if identity!=[(source_report['fingerprint'],)]:raise PreparedError('Source database identity differs from source preparation report')
        con.execute('CREATE SCHEMA sources');con.execute('CREATE SCHEMA preparation')
        con.execute('CREATE TABLE preparation.identity(input_id VARCHAR,descriptor_sha256 VARCHAR)')
        con.execute('INSERT INTO preparation.identity VALUES (?,?)',[input_id,descriptor_hash])
        sources=[]
        for item,record in zip(inputs,records):
            if item['role']!='prepared_input':continue
            relation=source_report.get('source_relations',{}).get(item['name'])
            if not relation or not re.fullmatch(r'sources\.(?:"[A-Za-z_][A-Za-z_0-9]*"|[A-Za-z_][A-Za-z_0-9]*)',relation):
                raise PreparedError(item['name']+': source adapter did not provide a safe physical source relation')
            captured='captured.'+relation
            columns=[(row[0],row[1]) for row in con.execute('DESCRIBE SELECT * FROM '+captured).fetchall()]
            query=_normalization_query(captured,columns,item.get('columns',{}))
            target='sources.'+_identifier(item['name'])
            con.execute('CREATE TABLE '+target+' AS '+query)
            count=con.execute('SELECT count(*) FROM '+target).fetchone()[0]
            expected=con.execute('SELECT count(*) FROM '+captured).fetchone()[0]
            if count!=expected:raise PreparedError(item['name']+': normalization changed source cardinality')
            fields=[{'name':row[0],'type':row[1]} for row in con.execute('DESCRIBE SELECT * FROM '+target).fetchall()]
            sources.append({'name':item['name'],'relation':target,'rows':count,'columns':fields,
                            'source_content_sha256':record['source_content_sha256'],
                            'normalization_sha256':_json_hash(item.get('columns',{}))})
        views=con.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog=current_database() AND table_schema='sources' AND table_type!='BASE TABLE'").fetchall()
        if views:raise PreparedError('Prepared publication contains external views')
        con.execute('DETACH captured');con.execute('CHECKPOINT');con.close();con=None
        if before:
            after=_hash(source_database)
            if after!=before:raise PreparedError('Read-only legacy extraction changed the source database')
            provenance['source_database_sha256_after']=after
        database_hash=_hash(temporary)
        manifest={'schema_version':1,'kind':'prepared_source_collection','status':'ready',
                  'input_id':input_id,'descriptor_sha256':descriptor_hash,'descriptor':descriptor,
                  'name':recipe['name'],'provider':recipe.get('provider'),'release':recipe.get('release'),
                  'created_at':datetime.now(timezone.utc).isoformat(),'database_path':str(final),
                  'database_sha256':database_hash,'manifest_path':str(manifest_path),
                  'input_count':len(records),'prepared_input_count':len(sources),'retained_source_count':len(records)-len(sources),
                  'input_lock':{'versions':versions},'inputs':records,'sources':sources,'provenance':provenance,
                  'provisional':any(row['provisional'] for row in records),'production_parity':False,
                  'normalization_policy':'Column order/cardinality preserved. Explicit empty or trimmed-empty/literal-null spelling rules; strict DECIMAL(38,12) casts. Comma-grouped numbers require signed conventional three-digit groups with optional decimal fraction before comma removal.',
                  'publisher_sha256':_hash(__file__),'engines':{'duckdb':duckdb.__version__}}
        temporary.replace(final);final.chmod(0o444)
        (output_dir/'source-preparation.json').write_text(json.dumps(source_report,indent=2,sort_keys=True)+'\n')
        staging_manifest=manifest_path.with_suffix('.json.tmp')
        staging_manifest.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');staging_manifest.replace(manifest_path)
        return manifest
    except Exception as exc:
        if con is not None:con.close()
        temporary.unlink(missing_ok=True)
        if final.exists() and not manifest_path.exists():final.unlink()
        (output_dir/'failed.json').write_text(json.dumps({'status':'failed','error':str(exc)},indent=2)+'\n')
        raise
