# Moses

**Local-first, versioned geospatial ELT.** Turn vector files and NYC Open Data into queryable tables, keep their history, and publish accepted versions when you need shared infrastructure.

Moses starts with an ordinary directory. No Docker, database server, cloud account, or DuckDB extension download is needed for local ingestion, history, SQL, or export. Python dependencies include native wheels; installing those dependencies requires internet access or a prepared wheelhouse.

This is an early, working MVP. The distribution is provisionally named `moses-geo`, with Python import and CLI name `moses`. It has **not been published to PyPI**, and name availability has not been reserved.

## Install and try it

Python 3.11 or newer is required. From this repository:

```sh
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install .
moses init
moses demo
moses query 'SELECT id, name FROM places'
moses history places
moses export places places.parquet
```

The bundled demo contains two **synthetic** NYC points. It runs offline after installation. The default warehouse is `.moses/` in the current directory. To choose another directory, put `--warehouse path` before the command.

```sh
moses --warehouse my-city load boroughs.geojson --name boroughs --key borocode
moses --warehouse my-city load buildings.gpkg --layer footprints --name buildings --key bin
moses --warehouse my-city load points.csv --name trees --key tree_id --x longitude --y latitude
moses --warehouse my-city list
```

Use an actual unique, non-null identifier in your source. Omit `--key` when none exists; diffs will then count added and removed rows without inferring updates. CSV attributes remain strings to protect identifiers such as `001`; cast them explicitly in SQL when needed.

## Local catalog GUI

Set `MOSES_TOKEN` to a strong random token, then run
`moses --warehouse my-city serve --port 8765` and open
`http://127.0.0.1:8765/`. Enter that token to browse accepted datasets in a wide
table or bounded map, inspect exact versions and feature properties, compare
releases, and download Parquet snapshots. The token stays in tab memory.

The GUI has a collapsible details panel and a responsive layout. Mapping uses
known source CRS on display copies, labels omissions, and defaults to a blank
offline background. An optional OpenStreetMap basemap discloses external tile
requests. This is a local read-only tool; uploads, SQL and multilayer workspaces
remain planned. See [local service](docs/local-service.md) for limits and routes.

## PLUTO candidate build

The [PLUTO case study](examples/pluto/README.md) exercises bounded real NYCPlanning sources through inspection, versioned ingestion, SQL, lock/replay and export. Its [results](docs/pluto-integration-results.md), [38-input source inventory](docs/pluto-source-inventory.md), and [delivery plan](docs/pluto-delivery-plan.md) distinguish tested samples from the remaining work to reproduce a complete PLUTO build.

The [full PLUTO candidate build](docs/pluto-full-build.md) runs the pinned 26v2
transformation through dbt-duckdb, including allocation, CAMA, geometry, zoning,
corrections, exports and QA. Its [readable SQL project](src/moses/pluto/dbt_full/README.md)
consolidates 405 operation models into 38 business models. Ordered local CTEs
retain process dependencies; shared macros remove repeated source cleanup,
correction rules and QA calculations.
`moses pluto build` prepares locked sources, generates a distinct candidate and
records comparison evidence. Install `.[pluto]` for the dbt runner. Historical
normalized-input and Geosupport runtime parity remain unproven. The earlier
[two-stage guide](docs/pluto-dbt-rebuild.md) retains acquisition and stage evidence.

`moses pluto fetch-production` captures the published release metadata, archived
sources and exact-commit seeds, then normalizes and ingests them with resumable
reports. The 26v2 run locked 38 source datasets and 11 seeds; 32 sources are
explicitly provisional raw reconstructions. The full PTS stage passed on
1,167,836 rows. See the rebuild guide for readiness gaps and replay commands.

## Real NYC Open Data

```sh
moses nyc gthc-hcne --name boroughs --key borocode
moses query 'SELECT boroname FROM boroughs ORDER BY boroname'
```

This command fetches the [Borough Boundaries dataset](https://data.cityofnewyork.us/City-Government/Borough-Boundaries/gthc-hcne) through Socrata's GeoJSON endpoint. Network access is required. `--limit 100` explicitly creates a sample; without a limit, the downloader follows pages. Use the underlying dataset ID, not a derived map ID: some map endpoints return geometry without attributes. Dataset availability and field names are controlled by NYC Open Data. Tabular datasets without a geometry field are better imported as CSV.

Socrata requests use a stable order and record their query and retrieval time. A live dataset can change between pages: the capture is **not a transactionally consistent source snapshot**. Moses preserves the downloaded response, rather than claiming to reconstruct the publisher's entire history.

## Versions and Python API

```python
from moses import Catalog

warehouse = Catalog("my-city")
first = warehouse.ingest("boroughs.geojson", name="boroughs", key="borocode")
# After the source changes:
second = warehouse.ingest("boroughs.geojson", name="boroughs", key="borocode")
print(warehouse.diff("boroughs", first["version"], second["version"]))
historical = warehouse.read("boroughs", first["version"])  # Arrow Table
current = warehouse.query("SELECT boroname FROM boroughs")
inputs = warehouse.lock()
# After future imports, this query still uses the locked versions:
reproduced = warehouse.query("SELECT boroname FROM boroughs", versions=inputs)
```

Each accepted version records raw captures, schema, CRS, parsing options, hashes, runtime versions, and source provenance. A failed import keeps the previous accepted version. Reimporting unchanged content records another observation without creating another release. Dataset keys cannot silently change.

Use `moses lock inputs.json` and `moses query 'SELECT * FROM boroughs' --lock inputs.json` to save and reuse exact input versions. A lockfile refers to versions in this warehouse; retain their snapshots and catalog with it. `warehouse.observations("boroughs")` exposes repeated captures, including unchanged checks.

```text
my-city/
  catalog.sqlite3       version and observation index
  raw/                  captured original files, including Shapefile sidecars
  snapshots/            immutable Parquet / GeoParquet versions
  .staging/             temporary imports
```

Move or back up the **entire directory** while no writes are running. Raw captures, snapshots, and the catalog belong together. There is no automatic expiration or garbage collection yet. Failures can leave unreferenced files but cannot publish an incomplete snapshot through the catalog. Power-loss durability and distributed filesystems are not certified.

## Geometry contract

- GeoJSON, GeoPackage, Shapefile (including ZIP), WKB GeoParquet, and CSV coordinates are supported.
- One geometry column becomes binary WKB named `geometry`, with GeoParquet 1.1 metadata. Attribute types from vector readers are preserved.
- Source CRS is preserved. `--crs` assigns a missing CRS; it does not reproject or silently override an existing CRS. CSV coordinates default to EPSG:4326 unless specified.
- Ambiguous layers, duplicate/null keys, invalid geometries, unsupported geometry encodings, and conflicting CRS assignments fail explicitly. No automatic geometry repair.
- Geometry diffs compare WKB bytes, not topological equivalence or positional tolerances. Schema/CRS changes are reported separately.
- Local SQL sees geometry as WKB. Spatial SQL is an explicit downstream DuckDB Spatial/PostGIS workflow; the core does not download extensions automatically.

## Optional infrastructure

### S3-compatible object storage

```sh
python -m pip install '.[s3]'
moses publish-s3 boroughs my-bucket --prefix city
# For a local or remote S3-compatible service:
moses publish-s3 boroughs my-bucket --endpoint-url http://localhost:8333
```

Credentials use the normal Boto3 environment/profile chain. Each version has an immutable prefix containing GeoParquet, raw captures, and a manifest published last. Readers should discover completed versions through manifests. The adapter requires conditional `PutObject` (`If-None-Match: *`); compatibility varies by S3 service. This is a version bundle publisher, not a query server or a distributed transaction. No external S3 account is required by the test suite.

### DuckLake

```sh
moses publish-ducklake boroughs city.ducklake --data-path lake-files --install-extensions
```

The first explicit `--install-extensions` downloads DuckLake. Later runs can use the cached extension without that flag. Moses publishes a table and its provenance in one DuckLake transaction. The result includes both the Moses version and the native DuckLake snapshot ID. Repeated publications create native snapshots; native snapshot retention is managed by DuckLake.

For shared infrastructure, supply an already configured DuckDB connection with PostgreSQL/S3 credentials:

```python
from moses.destinations.ducklake import DuckLakePublisher

# connection is your DuckDB connection with the required extensions and secrets.
destination = DuckLakePublisher(
    "postgres:dbname=city host=localhost",  # authentication from your connection/environment
    data_path="s3://city-lake/",
    connection=connection,
)
result = destination.publish(warehouse, "boroughs")
```

This adapter stores geometry as **WKB BLOB**, with CRS and provenance in `_moses.versions`. It does not promise native spatial types in every warehouse. PostgreSQL/S3 deployment needs integration testing against your configured services; the supplied integration test exercises DuckLake locally. [DuckLake connection documentation](https://ducklake.select/docs/stable/duckdb/usage/connecting) describes its catalog and storage choices.

To add a destination, implement `publish(catalog, name, version=None) -> dict`. Use `catalog.get_version()` and `catalog.read()` to consume a specific accepted release, and return the backend's identifiers separately. The first adapters are intentionally small; a general plugin registry, dlt integration, Snowflake, BigQuery, and PostGIS are future work.

## Development and limits

```sh
python -m pip install '.[dev,s3]'
python -m pytest
python -m build
```

Optional DuckLake integration, after explicitly caching its extension:

```sh
MOSES_TEST_DUCKLAKE=1 MOSES_EXTENSION_DIRECTORY=/path/to/extensions python -m pytest -m integration
```

Tables, semantic hashes, diffs, and S3 uploads currently materialize data in memory. Start with bounded datasets; citywide building footprints need a streaming follow-up. The catalog serializes local writers. There is no scheduler, web UI, raster pipeline, transformation DAG, cross-engine SQL portability layer, or multi-user catalog service.

Moses history is independent of DuckLake history. The local default deliberately uses SQLite plus immutable GeoParquet so a fresh install can work offline without DuckLake extension bootstrapping. This architecture keeps the normalizer and version contract reusable across future destinations.

MIT licensed. Contributions should include a small reproducible fixture and regression tests for data integrity changes.
