# Moses

**Local-first, versioned geospatial ELT.** Turn vector files and NYC Open Data into queryable tables, keep their history, and publish accepted versions when you need shared infrastructure.

Moses starts with an ordinary directory. No Docker, database server, cloud account, or DuckDB extension download is needed for local ingestion, history, SQL, or export. Python dependencies include native wheels; installing those dependencies requires internet access or a prepared wheelhouse.

This is an early, working MVP. The distribution is provisionally named `moses-geo`, with Python import and CLI name `moses`. It has **not been published to PyPI**, and name availability has not been reserved.

The intended workflow is **install Moses, initialize any project, and point it at
your own recipes**. Recipes belong to the consuming repository and can also live
at an external path; using Moses does not require keeping this source checkout.
The [project initialization design](docs/source-recipes.md#install-and-use-moses-in-any-repository)
defines the target `pip install moses` experience and distinguishes planned
project settings from the existing warehouse initialization and recipe commands.

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

Use an actual unique, non-null identifier in your source. Omit `--key` when none exists; diffs will then count added and removed rows without inferring updates. CSV/TSV attributes remain strings by default to protect identifiers such as `001`.

## Inspect and load tabular data

CSV, TSV, and ordinary Parquet work without geometry. Parquet retains its native types; a column named `geometry` alone does not make it spatial. Inspect a file before accepting a version:

```sh
moses inspect records.csv --infer-types --preview-rows 10
moses load records.csv --name records --key id --infer-types
moses load records.tsv --name other_records
moses load records.parquet --name typed_records
moses inspect records.csv --type id=string --type count=int64
moses load records.csv --name reviewed_records --type id=string --type count=int64
```

`inspect` reports a structured schema, row count, bounded preview, coordinate-column suggestions, CRS origin, and warnings without creating a warehouse or version. **It reads the full source into memory**; `--preview-rows` (0–100) limits output, not memory or parsing time. Format selection checks supported extensions against conservative content signatures before reader validation. Use `--format CSV`, `TSV`, `Parquet`, `GeoJSON`, `GeoPackage`, `Shapefile`, or `FileGDB` to explicitly choose a supported reader; contradictory content still fails. Coordinate suggestions do not create geometry automatically.

`--infer-types` scans complete CSV/TSV columns for booleans, int64 integers, and finite float64 numbers. Leading-zero identifiers, mixed types, dates, columns containing empty cells, integer overflow, and decimals that fail a decimal round-trip check stay text. Empty strings are preserved rather than converted to null. Floating-point results still use binary float64, not exact decimal arithmetic. Raw source bytes are retained.

Repeat `--type FIELD=TYPE` to select `string`, `bool`, `int64`, or `float64` explicitly. These choices take precedence over inference and validate every row, including rows beyond the preview. Invalid values report the field and row; failed loads leave the accepted version current. Explicit numeric/bool overrides convert empty strings to null; string overrides preserve them, and whitespace is not treated as an empty value. An explicit integer override can remove leading zeroes, so keep identifier fields as strings. Accepted versions record a versioned recipe with the effective format, types, blank/null policy, coordinates, and CRS origin. Existing historical manifests remain readable without being rewritten.

Set lowercase snake_case names once for all your projects in
`~/.config/moses/config.toml` (or `$XDG_CONFIG_HOME/moses/config.toml`):

```toml
[moses.normalization]
column_names = "snake_case"
```

The same setting in a project's `config.toml` overrides your user-wide default.
Moses finds the nearest project configuration from the working directory upward,
so it also works from subdirectories. Settings are grouped by responsibility:

| Section | Current settings | Purpose |
| --- | --- | --- |
| `moses.project` | `warehouse` | Location of this project's catalog and captures |
| `moses.normalization` | `column_names` | Consistent imported field names |
| `moses.spatial` | `default_crs` | Fallback for geometry missing CRS metadata |
| `moses.export` | `format` | Default Parquet, GeoParquet or FileGDB delivery writer |

See [config.example.toml](config.example.toml) for a complete working example.
Each project setting overrides only that setting; other user defaults remain in
effect. Project-relative warehouse paths resolve beside the project config.
Relative user-wide paths resolve at the active project root, or the working
directory when no project config exists. Explicit `--warehouse` paths stay
relative to the working directory. This keeps the default database storage local
to each project.

Check the effective categories and where each value came from:

```sh
moses config show
```

Precedence is explicit CLI/Python option, recipe setting, `MOSES_COLUMN_NAMES`,
project config, user config, then the built-in `preserve` default. An explicit
`preserve` overrides inherited `snake_case`. These settings apply to inspection,
loading and recipe preparation; the low-level `read_vector` reader remains
explicit. `[moses] config_version = 1` versions the configuration. The earlier
`[moses.input].column_names` spelling is still accepted; conflicting old/new
spellings in one file fail. Source URLs, keys, layers and field-specific rules
belong in recipes. Output reprojection, compression, additional writers and a
persistent DuckDB database remain planned.

You can also select a naming rule for one inspection or load:

```sh
moses inspect records.csv --column-names snake_case
moses load records.csv --name records --key "Parcel ID" --column-names snake_case
```

For example, `Parcel ID` becomes `parcel_id`, `OwnerName` becomes `owner_name`,
and `ZIP-Code` becomes `zip_code`. Names contain only ASCII letters, digits and
underscores. Punctuation becomes a separator; leading/trailing separators are
removed. Digit-leading names receive a `column_` prefix. Names with no usable
characters and collisions such as `Lot ID` / `Lot-ID` fail explicitly. Raw
captures retain the source names, and inspection/version metadata records the
mapping. Without an option or configured default, Moses preserves names. CLI key, type and coordinate
arguments still refer to source column names.

YAML recipes use `import.column_names: snake_case`. Explicit `import.rename`
runs first, followed by normalization; recipe types, geometry fields and keys
refer to the final names. Python callers can pass `column_names="snake_case"`
to `Catalog.ingest` or `inspect_source`.

Set a fallback source projection per warehouse or process:

```sh
moses --warehouse my-city init --default-crs EPSG:2263
MOSES_DEFAULT_CRS=EPSG:3857 moses --warehouse my-city inspect points.csv --x x --y y
```

`init --default-crs` retains the legacy `<warehouse>/config.json` setting. For
shared defaults, use `[moses.spatial] default_crs` in TOML. A nonempty
`MOSES_DEFAULT_CRS` takes precedence, followed by project TOML, user TOML and
legacy warehouse JSON. Defaults apply only to geometry without embedded or
explicit CRS. Explicit `--crs` assigns a missing CRS and fails if it conflicts
with source metadata. A default never reprojects data or applies to a nonspatial
table. CSV/TSV coordinates retain the legacy EPSG:4326 fallback when no CRS is
supplied; inspection and new manifests label that assumption with a warning.
Coordinate ranges cannot reliably identify a projected CRS.

The [local service](docs/local-service.md) provides a browser catalog GUI and authenticated read-only API with opaque resource IDs. Run `moses --warehouse my-city serve --port 8765` with `MOSES_TOKEN` set, open `http://127.0.0.1:8765/`, and enter the token to browse datasets, history, schemas, bounded table/map previews, feature details, comparisons, and Parquet downloads. The [service architecture and rollout](docs/service-architecture.md) describes the remaining guided loader, durable upload jobs, lightweight client, container deployment, and MCP bridge. The [Explore feature plan](docs/query-map-workspace.md) adds a lightweight SQL editor, results table, and geospatial map with multiple layers, saved queries, and version-pinned previews. Single-version dataset mapping is implemented locally; the full query workspace follows the service foundation and precedes hosted access/MCP.

Track delivery in the [Moses GitHub project](https://github.com/users/SPTKL/projects/1), the [pinned roadmap issue](https://github.com/SPTKL/moses/issues/1), and the [milestone index](docs/roadmap.md). Implementation tickets include acceptance criteria and prerequisite links; GitHub carries the current delivery status.

The [standalone PLUTO example](examples/pluto/README.md) lives in this repository under `examples/pluto`. It demonstrates locked source preparation, a 38-model dbt build, and publication from an independently installable project. Its [full-build guide](examples/pluto/docs/pluto-full-build.md) records the candidate evidence and remaining parity limits.

## File Geodatabases

Read an Esri File Geodatabase directory or a ZIP containing one root `.gdb`
directory. Select a layer explicitly when the source contains multiple layers;
an ambiguous selection reports the available names.

```sh
moses inspect city.gdb --layer parcels
moses load city.gdb --layer parcels --name parcels --key parcel_id
moses load city.gdb.zip --layer parcels --name parcels --key parcel_id
```

Imports preserve the selected layer's reader-provided attribute types and CRS.
Moses captures every file in a directory, or the complete original ZIP, before
accepting a version. ZIP validation rejects unsafe paths, symlinks, multiple
geodatabases, and excessive expansion. Input bundles are limited to 100,000
members and 20 GiB uncompressed; ZIP members also have a 1,000:1 compression-ratio
limit. Parsing still reads the selected layer into memory.

Recipes can use `source.kind: local`, a `.gdb` directory or ZIP path, and
`import.format: FileGDB` with `import.layer`. See the
[File Geodatabase contract](docs/source-recipes.md#file-geodatabases).

Export one exact accepted version to a new directory, using the version ID
reported by `load` or `history`:

```sh
moses export parcels delivery.gdb --format FileGDB --layer parcels --version VERSION_ID
```

Export targets ArcGIS Pro 3.2 or later, preserves source CRS, and refuses to
overwrite an existing destination. Unsupported field/geometry types or failed
readback checks fail before publication. FileGDB coordinate precision can
quantize coordinates. This is selected-layer conversion: domains, relationships,
attachments and other ArcGIS behavior are not recreated. Enterprise `.sde`,
personal `.mdb`, raster geodatabases and ZIP export are not supported.

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
  config.json           optional warehouse defaults
  catalog.sqlite3       version and observation index
  raw/                  captured originals, sidecars and complete FileGDB bundles
  snapshots/            immutable Parquet / GeoParquet versions
  .staging/             temporary imports
```

Move or back up the **entire directory** while no writes are running. Raw captures, snapshots, and the catalog belong together. There is no automatic expiration or garbage collection yet. Failures can leave unreferenced files but cannot publish an incomplete snapshot through the catalog. Power-loss durability and distributed filesystems are not certified.

## Geometry contract

- GeoJSON, GeoPackage, Shapefile (including ZIP), File Geodatabase (directory or ZIP), WKB GeoParquet, and CSV/TSV coordinates are supported, alongside nonspatial CSV/TSV, Parquet and FileGDB tables.
- One geometry column becomes binary WKB named `geometry`, with GeoParquet 1.1 metadata. Attribute types from vector readers are preserved.
- Source CRS is preserved. `--crs` assigns a missing CRS; it does not reproject or silently override an existing CRS. Configured defaults apply only to missing spatial CRS; CSV/TSV coordinates otherwise fall back to EPSG:4326 with a warning.
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

Repository agent instructions live in [AGENTS.md](AGENTS.md). They require Astra
supervision and task-based model routing to limit token cost, alongside the
delivery and product-review rules.

```sh
python -m pip install '.[dev,s3]'
python -m pytest
python -m build
```

Optional DuckLake integration, after explicitly caching its extension:

```sh
MOSES_TEST_DUCKLAKE=1 MOSES_EXTENSION_DIRECTORY=/path/to/extensions python -m pytest -m integration
```

Tables, semantic hashes, diffs, and S3 uploads currently materialize data in memory. Start with bounded datasets; citywide building footprints need a streaming follow-up. The catalog serializes local writers. There is no scheduler, guided upload UI, raster pipeline, transformation DAG, cross-engine SQL portability layer, or multi-user catalog service.

Moses history is independent of DuckLake history. The local default deliberately uses SQLite plus immutable GeoParquet so a fresh install can work offline without DuckLake extension bootstrapping. This architecture keeps the normalizer and version contract reusable across future destinations.

MIT licensed. Contributions should include a small reproducible fixture and regression tests for data integrity changes.
