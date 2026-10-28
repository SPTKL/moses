# PLUTO 26v2 rebuild with dbt and DuckDB

> Historical evidence from the earlier Moses-integrated implementation. For the current standalone commands, start with [the PLUTO example](../README.md).

**Full candidate pipeline:** [Build and review PLUTO 26v2m4](pluto-full-build.md)
documents the complete dbt transformation, readable business-stage SQL, native
source preparation, QA and exports. This page retains the earlier two-stage
runner and acquisition evidence; its original remaining-work sections describe
that increment rather than the current implementation inventory.

The selected comparison target is **26v2**. Moses captures and versions inputs;
dbt-duckdb executes checked-in `SELECT` models; Moses accepts the result after
validation and, when supplied, reference comparison. The model layer contains no
`UPDATE` statements and uses table materialization rather than mutable intermediate
tables. No database server is needed for candidate execution.

This is an executable start to the rewrite, **not a complete PLUTO replacement**.
Two models are implemented. The published 26v2 build manifest identifies commit
`32bc98f632f15e7182933a17fb61ecf74e853518` and build time
`2026-08-08T17:26:18.388525-04:00`. All 38 version selections and the 11 seeds
are now resolved from that evidence. Six normalized artifacts were downloadable;
32 normalized files returned AccessDenied, but full public raw snapshots with
matching version metadata were captured. Those raw selections remain provisional
until their historical normalized lineage is established. Intermediate reference
outputs and full-build parity remain outstanding.

## Implemented models

| Model | Required locked tables | Behavior and contract |
| --- | --- | --- |
| `create_pts` | `pluto_pts` | Maps all 43 PTS fields from upstream `create_pts.sql`; strips plus signs, casts numeric attributes and rounds four dimensions. Preserves repeated BBL/easement records. |
| `landuse` | `pluto`, `pluto_input_landuse_bldgclass` | Assigns the seed's land-use code, preserves existing values for unmatched classes, then applies the vacant-lot `areasource = '4'` rule. Requires unique canonical BBLs. |

These are separate stage entrypoints, not consecutive stages. `landuse` expects
the intermediate PLUTO table at one of its two upstream invocation points.
Supplying published PLUTO demonstrates stage replay only. The missing allocation,
CAMA, geometry and other stages cannot be skipped to connect `create_pts` directly
to `landuse`.

[stages.json](../scripts/stages.json) records 68 static shell SQL call sites
(including both land-use invocations) and 64 upstream dbt models with source
hashes. It is a migration inventory, not an executable dependency graph. Inline
shell SQL, dynamic QA calls, setup and delivery exports also need migration.

## Run locally

From the Moses checkout:

```sh
.venv/bin/python -m pip install -e '.[pluto]'
.venv/bin/python -m moses pluto --help
.venv/bin/python scripts/run_dbt_validation.py
```

The last command runs explicitly synthetic fixtures through actual dbt, saves
inputs and artifacts under `.moses/pluto-dbt-validation/`, and verifies locked
replay. It is offline after dependency installation. PostgreSQL reference checks
are optional and documented by the script's `--help`; the production candidate
always uses DuckDB.

For an existing exact stage input:

```sh
moses --warehouse pluto-26v2 load /absolute/path/pluto_pts.parquet --name pluto_pts
moses --warehouse pluto-26v2 lock pts-inputs.json
moses --warehouse pluto-26v2 pluto run --stage create_pts \
  --lock pts-inputs.json --output dof_pts_propmaster \
  --evidence exact_stage_input --reference /absolute/path/expected-pts.parquet \
  --report pts-run.json
```

For land-use stage replay, load the intermediate table as `pluto`, the seed as
`pluto_input_landuse_bldgclass`, then use `--stage landuse`. The CLI selects only
the stage's required tables from the supplied lock. It never consults current
versions. Output names must differ from input names.

`--evidence synthetic`, `sample` or `exact_stage_input` is an explicit caller
assertion recorded in lineage, not automatic source attestation. Omit `--reference`
only when stage execution is sufficient; the result records `not_supplied` and
makes no reference-parity claim. A mismatching reference returns exit code 2 and
does not advance the output version. Invalid inputs return exit code 1.

## Acquire the production inputs with Moses

The production adapter downloads release metadata, captures all readable versioned
artifacts, discovers prebuild raw snapshots through the public archive, and reads
seeds at the release commit. It requires no 1Password account. It never chooses
current source data as an implicit substitute for the release.

```sh
moses --warehouse .moses/pluto-production/26v2/warehouse pluto fetch-production \
  --release 26v2 --source-repo ../data-engineering \
  --cache .moses/pluto-production/26v2 --extension-directory .extensions
```

Install DuckDB Spatial explicitly into the chosen extension directory first.
The normalizer loads that installed extension without automatic downloads. Use
`--capture-only` to stop after downloads, or `--offline` to verify and ingest
already captured bytes without network or a source checkout. SHA256 receipts,
raw/config selection evidence, normalization reports and catalog locks are saved
under the cache directory; preserve that directory with the warehouse.

`production-ingestion.json` separates captured/imported coverage from normalized
readiness. Raw candidates enter `raw__<alias>` datasets; only the six readable
normalized artifacts use their production aliases. CSV lexical/null policies and
unsupported steps remain explicit. Invalid geometries are retained as WKB blobs
with CRS/status metadata, without automatic repair or a claim of accepted spatial
quality. Legacy SQL captures are parsed as COPY data, never executed in a server.
All reconstruction operations run as DuckDB SELECT/COPY statements. The existing
Moses catalog retains its metadata implementation; PLUTO has no PostgreSQL runtime.

Exit 0 means capture/import coverage succeeded, not full-build readiness.
`build_ready` and `production_parity` remain false until the remaining contracts,
transformations and reference comparisons pass. Repeated runs verify cached bytes
and resume completed catalog imports. Failures are checkpointed per input and
excluded from the input lock.

## Metadata-only planning and local artifact import

The earlier planner remains available for supplied manifests. The following
`release-26v2.json` is an intentionally unresolved planning fixture, not the
production acquisition entrypoint:

```sh
moses pluto plan --inventory scripts/inventory.json \
  --config scripts/release-26v2.json --report plan-26v2.json
```

The supplied configuration intentionally leaves source pins unresolved. Exit code
2 means required inputs or seeds remain unresolved, and each row provides an
action. Planning does not create a warehouse or download data. `ready` means
source metadata is complete; `build_ready` additionally requires seed metadata.
Neither means the complete transformation pipeline is implemented or that local
files have been read. Acquisition verifies the files separately.

Populate release metadata from the approved 26v2 build manifest, not today's
latest endpoints. Major planning resolves each source from an explicitly supplied
`latest_version` pointer. Minor planning inherits versions from
`previous_release.inputs` except the upstream recipe's explicit refresh entries.
`dcp_pluto` is always aliased to `previous_pluto` and requires `version_prev`.
The target version and previous version are separate selections.

One source entry in `available` looks like this (placeholders are not valid pins):

```json
{
  "pluto_pts": {
    "latest_version": "EXACT_UPSTREAM_VERSION",
    "versions": {
      "EXACT_UPSTREAM_VERSION": {
        "artifacts": [{
          "path": "/absolute/path/normalized-pts.parquet",
          "sha256": "SHA256_OF_THE_FILE",
          "kind": "full",
          "representation": "normalized_recipe",
          "normalization_status": "ready"
        }]
      }
    }
  }
}
```

For a ZIP, pin the archive hash and an exact `member` path. Retained archive and
selected-member hashes are separate. A plain Shapefile is refused because its
sidecars are not pinned; use a ZIP containing the required sidecars. Optional
`ingest_options` can specify `key`, `types`, `format`, `layer`, `x`, `y` and `crs`.
Seeds use `seeds[name] = {"path": "/absolute/path/seed.csv", "sha256": "..."}`,
with optional import options. CSV identifiers remain text by default.

```sh
moses --warehouse pluto-26v2 pluto acquire --plan plan-26v2.json \
  --report acquired-26v2.json
```

Acquisition stages and hashes every requested file before ingesting verified
copies, captures ready seeds, retains archives and records exact catalog versions.
This older command accepts local normalized artifacts. Use `fetch-production`
for remote capture and DuckDB raw normalization. Missing access stays visible. Individual imports are atomic, but a multi-source acquisition is not one
transaction: a later parser failure can leave earlier verified inputs accepted.
Re-running unchanged inputs is safe. Preserve the whole warehouse, acquisition
report and transform-run artifacts for replay.

## Comparison and numeric policy

```sh
moses pluto compare candidate.parquet reference.parquet --report comparison.json
```

The standalone comparison matches unique BBLs and checks all column names/order,
types, nullability, schema and field metadata, exact values and added/removed
records. `--column` requests an explicitly labeled subset. It never equates
blanks with nulls. PTS stage comparison uses row multisets because BBLs may repeat;
it checks duplicate multiplicity without inventing a unique key. Geometry bytes
are not a spatial-equivalence test.

The land-use model consumes exact numeric-zero predicates prepared using Python
Decimal, avoiding float underflow for tiny nonzero values. The business rule
itself remains in dbt SQL. Invalid numeric strings fail before publication.
PTS requires finite representable doubles and uses `DECIMAL(38,2)` for the four
dimensions, rounded half away from zero. This deliberately narrows PostgreSQL's
unconstrained numeric domain: unsupported overflow/underflow and nonfinite values
fail explicitly. Reference numeric representation must be documented; a schema
adaptation is not strict native-type parity.

Inputs must have explicit Arrow types, even when a whole column is null. An
untyped `null` column is rejected with its dataset/field name instead of allowing
DuckDB to infer an integer column. Typed all-null strings are supported. The
land-use model preserves the input field metadata and nullability and rejects
outputs that violate a declared non-null field.

Each run records input versions/content hashes, model/project/runner checksums,
upstream SQL checksums, reference table hash when supplied and exact engine
versions. Compiled SQL, dbt manifest, run results and execution logs remain under
`<warehouse>/transform_runs/`. `dbt build` runs the selected table and its tests in
an isolated subprocess with an explicit temporary profile, one thread and
external access/automatic extension installation disabled. This is a trusted
local CLI workflow, not a remote arbitrary-SQL service or resource sandbox.

## Validation evidence — 2026-10-17

The integrated suite passed **165 tests**, with one optional DuckLake integration
skipped. The wheel and source archive built successfully; a wheel extracted
outside the checkout ran the CLI, selected required versions from a larger lock,
executed the packaged dbt project and accepted the expected output. `git diff
--check` passed. Existing HTTP-service tests required loopback permission after
the sandbox initially denied their server socket; the final full suite passed
with that permission.

[Recorded stage evidence](../scripts/dbt-validation-results.json) compares
the original upstream SQL executed in **PostgreSQL 16.15** with actual dbt builds
on DuckDB 1.5.6, dbt-duckdb 1.11.0 and dbt-core 1.12.6. Twelve synthetic land-use
rows and three PTS rows across all 43 fields matched. Both locked replays matched
after newer inputs were accepted. The PTS comparison explicitly represents
unconstrained PostgreSQL numeric dimensions as `DECIMAL(38,2)` within the tested
range. The evidence checksum matches the final runner. The temporary PostgreSQL
container was stopped and removed after validation.

Astra reviewed the architecture, implementation and regression fixes. This
evidence establishes the documented stage behavior on synthetic fixtures;
`production_parity` remains false. Neither a first-time analyst usability study
nor a citywide capacity test has been performed. The local CLI is useful to an
engineer with exact inputs; the full self-service analyst workflow remains on
the service/UI roadmap. No changes have been committed, merged or released.

## Production-source execution evidence — 2026-10-17

The full normalized PTS source passed the dbt-duckdb `create_pts` stage:
1,167,836 rows and 43 columns, retaining all 4,517 easement-suffixed identifiers.
The production run exposed and corrected a synthetic-fixture blind spot: PTS
`parid` may be a ten-digit parcel ID plus an easement letter matching `ease`.
The landuse model still requires canonical parcel identifiers. No published
intermediate-stage reference was available for this run, so it establishes
full-source execution, not production parity.

All 38 source datasets and 11 seeds are ingested into Moses and locked to 49
verified catalog versions. The lock includes six normalized artifacts, 32
provisional raw candidates and 11 seeds. All 32 raw snapshots converted through
DuckDB with 6,123,166 rows retained.
Seven CSV captures have explicit parser/null-compatibility dependencies; native
geocoding and its subsequent recipe steps are pending. The five legacy captures
converted as COPY data without executing PostgreSQL statements.

The published 26v2 final CSV is also captured for comparison: 858,284 data rows.
Its ZIP SHA256 is
`0b1448b189c97e3d301df7b69017f8794afd0ad57dbe49b25021d3a96e33ccd8`;
the CSV member SHA256 is
`c65fac81cdc119ac4528fc78d11474419cd50d0fde1a1b06be42ba8961d24cf9`.
Publication-prefix and version-marker linkage is recorded; the build metadata
does not cryptographically attest the final ZIP. It is a comparison artifact,
not an input used to manufacture a matching result.

Validation: 201 tests passed, one optional DuckLake integration skipped; wheel
and source builds passed, as did an outside-checkout wheel smoke test for the
production CLI, imports and packaged dbt resources. Astra reviewed the acquisition
implementation and PTS contract correction. Local changes are not merged/released.

## Geosupport and remaining work

[duckdb-geosupport](https://github.com/SPTKL/duckdb-geosupport) provides a viable
DuckDB geocoding path. Inspection of the local sibling repository found a native
macOS extension for DuckDB 1.5.6, an existing Linux worker image, and cached 26B
and 26C data bundles. This supersedes the initial public v0.2.0/1.4.4 compatibility
assessment; these local runtime artifacts have not yet been exercised here.

PLUTO needs explicit `gs_call` stages: BL → D street lookup → 1A regular plus 1E
extended, with the upstream merge/error/fallback policy. Building counts require
BN regular, TPAD retry, then row-grain-preserving aggregation. A single `gs_bbl`
or `gs_address` call cannot substitute for those recipes. Each native-call stage
should be materialized to prevent duplicate evaluation.

The historical ingestion workflow uses mutable `build-geosupport:latest`; the
published metadata does not establish which Geosupport bundle actually ran.
The historical Python wrapper commit also differs from the local extension's
reference layouts. Parser/error compatibility and historical runtime evidence
remain required. The captured geocode recipe declares x=latitude, y=longitude;
that axis discrepancy remains explicit and has not been silently corrected.
No geocoding result is fabricated or substituted in this rewrite.

The next transformation work is PTS/geocode staging, vacant-lot and area
allocation, condominium handling and CAMA before geometry/zoning, enrichments,
corrections, QA and exports. Full 26v2 acceptance requires its approved pinned
inputs and code revision, all stages, attribute and spatial reference checks,
and measured citywide memory/runtime. Raw normalization uses a 1 GB DuckDB limit
and disk spill; Moses catalog ingestion still materializes Arrow tables in memory.
