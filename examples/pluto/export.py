#!/usr/bin/env python3
"""Export completed dbt output relations; no acquisition or transformation runner."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import duckdb


def literal(value):
    return "'"+str(value).replace("'","''")+"'"


def identifier(value):
    return '"'+value.replace('"','""')+'"'


def export(database, output_dir, extension_directory, *, input_database, overwrite=False):
    output_dir=Path(output_dir)
    con=duckdb.connect(str(database),read_only=True,config={
        'extension_directory':str(extension_directory),
        'autoinstall_known_extensions':False,
        'autoload_known_extensions':False,
    })
    artifacts=[]
    try:
        con.execute('LOAD spatial')
        # Export/QA views retain their source lineage. Reattach the same
        # prepared database read-only rather than copying it into the output.
        con.execute('ATTACH '+literal(input_database)+' AS prepared (READ_ONLY)')
        receipt=con.execute('SELECT status,input_id,descriptor_sha256 FROM pluto_execution.receipt').fetchall()
        identity=con.execute('SELECT input_id,descriptor_sha256 FROM prepared.preparation.identity').fetchall()
        if len(receipt)!=1 or receipt[0][0]!='complete':
            raise ValueError('Exports require a successful full PLUTO dbt build; partial or failed runs are not complete')
        if len(identity)!=1 or tuple(receipt[0][1:])!=tuple(identity[0]):
            raise ValueError('Prepared input identity differs from the warehouse used by this PLUTO build')
        output_dir.mkdir(parents=True,exist_ok=True)
        specifications=[('export_pluto','pluto.csv','CSV, HEADER TRUE'),
                        ('export_pluto','pluto.parquet','PARQUET, COMPRESSION ZSTD')]
        diagnostics=('pluto_changes_applied','pluto_changes_not_applied','pluto_removed_records',
                     'qaqc_expected','qaqc_bbl_diffs','qaqc_aggregate','qaqc_mismatch','qaqc_null','qaqc_outlier')
        specifications += [(name,name+'.csv','CSV, HEADER TRUE') for name in diagnostics]
        specifications += [(name,name+'.parquet','PARQUET, COMPRESSION ZSTD') for name in ('mappluto','mappluto_unclipped')]
        for name,filename,options in specifications:
            path=output_dir/filename
            if path.exists() and not overwrite:
                raise FileExistsError(str(path)+' already exists; choose another output directory or --overwrite')
            relation='main.'+identifier(name)
            count=con.execute('SELECT count(*) FROM '+relation).fetchone()[0]
            projection='*'
            geometry=None
            if name.startswith('mappluto'):
                columns=con.execute('DESCRIBE SELECT * FROM '+relation).fetchall()
                geometries=[column for column,dtype,*_ in columns if dtype.startswith('GEOMETRY')]
                if len(geometries)!=1:raise ValueError(name+' must have one geometry column')
                geometry=geometries[0]
                field=identifier(geometry)
                projection='* REPLACE (ST_SetCRS('+field+", 'EPSG:2263') AS "+field+')'
                if count==0:
                    # DuckDB omits automatic GeoParquet metadata for zero rows.
                    # Keep an empty result valid using the same published CRS.
                    crs=json.loads(Path(__file__).with_name('epsg2263.projjson').read_text())
                    geo={'version':'1.1.0','primary_column':geometry,'columns':{geometry:{'encoding':'WKB','geometry_types':[],'crs':crs}}}
                    options+=', KV_METADATA {geo: '+literal(json.dumps(geo))+'}'
            temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
            try:
                con.execute('COPY (SELECT '+projection+' FROM '+relation+') TO '+literal(temporary)+' (FORMAT '+options+')')
                if geometry:
                    metadata=con.execute('SELECT value FROM parquet_kv_metadata('+literal(temporary)+") WHERE CAST(key AS VARCHAR)='geo'").fetchone()
                    geo=json.loads(bytes(metadata[0])) if metadata else {}
                    crs=geo.get('columns',{}).get(geometry,{}).get('crs',{}).get('id')
                    if crs!={'authority':'EPSG','code':2263}:raise ValueError(name+' lost EPSG:2263 GeoParquet metadata')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            artifact={'relation':name,'path':filename,'rows':count}
            if geometry:artifact.update(geometry_column=geometry,crs='EPSG:2263')
            artifacts.append(artifact)
    finally:
        con.close()
    report={'database':str(Path(database).resolve()),'input_id':identity[0][0],
            'descriptor_sha256':identity[0][1],'artifacts':artifacts}
    (output_dir/'exports.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default=os.environ.get('PLUTO_OUTPUT_DATABASE'))
    parser.add_argument('--input-database',default=os.environ.get('PLUTO_INPUT_DATABASE'))
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--extension-directory',default=os.environ.get('PLUTO_SPATIAL_DIRECTORY'))
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    if not args.database or not args.input_database or not args.extension_directory:
        parser.error('set --database, --input-database and --extension-directory, or their PLUTO environment variables')
    export(args.database,args.output_dir,args.extension_directory,input_database=args.input_database,overwrite=args.overwrite)


if __name__=='__main__':
    main()
