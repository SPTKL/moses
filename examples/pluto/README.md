# Build PLUTO with Moses and dbt

This is a full-release example of using Moses to bring source data into a
project, dbt to turn it into PLUTO, and a small export script to deliver the
results. Start with the recipe and SQL; you do not need to understand the
Python implementation to run the workflow.

| Step | What happens | Command |
| --- | --- | --- |
| Ingest and prepare | Moses and the PLUTO source adapters capture release inputs, record their versions, and prepare typed tables. | `make ingest`, then `make prepare` |
| Transform | dbt builds PLUTO attributes, geometries, corrections, and QA reports. | `make build` |
| Export | The export script reads the completed build and writes delivery files. | `make export` |

These are the full 26v2 inputs and the 38-model PLUTO build, not a sample.
The result is a reconstructed candidate; remaining historical-input and
production-parity limits are documented in the [full-build guide](docs/pluto-full-build.md).

## Set up once

You need:

- **uv and make** to install the locked dependencies and run the commands.
- **A NYCPlanning/data-engineering checkout** containing release commit
  `32bc98f632f15e7182933a17fb61ecf74e853518`, used read-only for the release seeds.
- **Source access** for the release inputs, or an existing complete capture cache
  for offline ingestion. The workflow records unavailable sources and stops on
  ingestion errors.
- **Installed native dependencies:** DuckDB Spatial compatible with the locked
  DuckDB version, plus the Geosupport extension and bundle required for native
  preparation. Supply the release, runtime, and paths explicitly; the build
  does not download or choose a native runtime for you.

From this folder:

```sh
uv sync --locked
cp config.mk.example config.mk
```

Edit `config.mk` with your source checkout and native dependency paths.
The default locations are `.moses/captures/26v2`, `.moses/warehouse`,
`.moses/prepared/26v2`, `.moses/build/pluto.duckdb`, and `.moses/exports/26v2`.
The template lets you override these paths. It is local configuration and is ignored by Git. Use
absolute paths when reusing an existing warehouse or capture cache.

If you need to install Spatial in the default extension directory, run:

```sh
uv run --locked moses spatial install --extension-directory .extensions
```

Geosupport is a separate prerequisite; select an already installed bundle and
its matching native extension in `config.mk`.

## Run the full workflow

```sh
make ingest
make prepare
make build
make export
```

`make ingest` captures the release's 38 sources and 11 seeds and imports them
through Moses. It writes the exact input lock to `CACHE/production-ingestion.json`.
`make prepare` applies [the recipe](recipes/26v2.yml), including native geocoding,
and publishes the 42 tables consumed by dbt.

`make build` runs ordinary dbt against those prepared tables. It attaches the
input database read-only, checks its schema, and builds the PLUTO outputs.
The candidate and previous-release labels are explicit settings in `config.mk`;
changing labels does not select different source data from the lock.

`make export` writes tabular CSV/Parquet, correction and QA CSVs, and clipped and
unclipped GeoParquet in EPSG:2263: 13 data files plus an export manifest. It checks
that the full dbt build succeeded and that the prepared input identity matches.

Each command is independent. Running `make build` again does not fetch inputs
or rerun geocoding. For a complete existing capture cache, use
`make ingest OFFLINE=1`. If you already have a prepared database, configure its
`PREPARED_DIR` and start at `make build`. Preparation requires a new output
directory; export refuses existing files. Choose new output paths for a new run.

`make help` lists the steps. The [Makefile](Makefile) contains the underlying
`uv run` commands, so you can run each tool directly or adapt the workflow.
The [full-build guide](docs/pluto-full-build.md) also covers migration from a
verified legacy source cache and detailed validation evidence.

## What to change

- **Inputs and physical cleanup:** [recipes/26v2.yml](recipes/26v2.yml).
- **PLUTO business rules:** [dbt/models](dbt/models), with shared SQL in
  [dbt/macros](dbt/macros). See the [model guide](dbt/README.md).
- **Delivery formats:** [export.py](export.py).

`src/pluto_example` contains the existing source adapters and compatibility
code. `scripts`, `tests`, and `docs` retain diagnostics, regression checks, and
build evidence. The embedded dbt projects under `src` support historical
workflows; `make build` uses only the top-level `dbt/` project.

Input locks, preparation receipts, and [model provenance](dbt/provenance.json)
keep the data and transformations traceable. The current build still uses
DuckDB files. DuckLake with a DuckDB metadata catalog is the intended default,
but that storage migration has not been implemented here.
