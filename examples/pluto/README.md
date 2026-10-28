# PLUTO

This standalone PLUTO example lives at `examples/pluto` in the Moses repository and remains a separately installable Python package. It includes an ordinary DuckDB dbt project and transforms prepared inputs into PLUTO
attributes, mapped geometries, correction audits and QA outputs through 38 business
process models. The dbt models do not acquire data or run native geocoding.

From the Moses repository root, change to `examples/pluto`. Install this package, its Moses dependency, and the pinned dbt versions. Until `moses-geo` is published, supply a built Moses wheel to pip.

```sh
python -m pip install /absolute/path/to/moses_geo-0.1.0-py3-none-any.whl
python -m pip install -e .
python -m pip install -r dbt/requirements.txt
```

Provide an installed DuckDB Spatial extension compatible with that DuckDB version. Builds do not install packages or download extensions.

Prepare the locked release from this root using your captured source warehouse and lock:

```sh
pluto-example --warehouse /absolute/path/to/warehouse \
  prepare recipes/26v2.yml \
  --lock /absolute/path/to/inputs.lock.json \
  --output-dir /absolute/path/to/prepared \
  --extension-directory /absolute/path/to/installed/extensions
```

Native geocoding needs the release and Geosupport options described in the [full-build guide](docs/pluto-full-build.md). Existing Moses `.moses/` warehouses and `.extensions/` installations stay in place during migration: pass their absolute paths to `--warehouse`, `--lock`, and `--extension-directory`. Historical manifests keep their recorded source paths and provenance; copying those directories is not part of this example.

```sh
export PLUTO_INPUT_DATABASE=/absolute/path/to/prepared/prepared.duckdb
export PLUTO_OUTPUT_DATABASE=/absolute/path/to/pluto-output.duckdb
export PLUTO_SPATIAL_DIRECTORY=/absolute/path/to/installed/extensions

dbt build --project-dir dbt --profiles-dir dbt
```

The prepared database is attached read-only as `prepared`. Results are written to
the separate output database. The first hook validates all 42 source tables and
650 column names, types and positions against
[contract.yml](dbt/models/contract.yml). It rejects a writable input attachment,
missing tables and incompatible schemas before business models execute.
The input also contains one `preparation.identity` row with an immutable
`input_id` and `descriptor_sha256`. PLUTO example preparation writes this receipt; another preparation tool can
provide the same contract without installing Moses.

Preparation owns physical source cleaning, seed typing, native geocoding and
input locks. The dbt project retains PLUTO staging projections and business rules.
Once the prepared database exists, dbt needs no Moses catalog, upstream checkout, or network service.

Set `pluto_version` and `previous_pluto_version` explicitly when building a release:

```sh
dbt build --project-dir dbt --profiles-dir dbt \
  --vars '{pluto_version: 26v2m4, previous_pluto_version: 26v1}'
```

`export_pluto` contains the typed tabular result; `mappluto` and
`mappluto_unclipped` contain geometry outputs. Applied/rejected corrections,
removed records and six `qaqc_*` relations remain available in the output database.
See [the process guide](dbt/README.md) for the business DAG and model descriptions.

CAMA matches and the ZIP fallback use documented canonical identity/payload
ordering. Other upstream unordered choices remain a replay limitation. Numeric
and spatial compatibility policies are recorded in [provenance.json](dbt/provenance.json).

Optional file exports read the completed output database without running models:

```sh
python export.py --output-dir /absolute/path/to/exports
```

This writes tabular CSV/Parquet, correction and QA CSVs, and two GeoParquet files
with explicit EPSG:2263 metadata. Existing files require `--overwrite`.
Exports require a successful full 38-model invocation and the same prepared
publication identity recorded by that invocation. A partial `--select` build
does not certify a complete export. Identity prevents accidental warehouse
mix-ups; the preparation manifest's database SHA256 is the separate content
integrity check for copies or externally modified files.

The [full-build guide](docs/pluto-full-build.md) records the current split workflow. The other [evidence documents](docs/) describe earlier Moses-based runs; their recorded paths and commands are historical. [Case-study scripts](scripts/README.md) are optional diagnostics.
