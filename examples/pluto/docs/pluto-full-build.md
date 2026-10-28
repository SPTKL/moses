# Full PLUTO candidate build

Moses prepares locked source versions. A separate, ordinary **dbt-duckdb**
project performs the PLUTO transformation. The candidate version is **26v2m4**. Its source rules come from
NYCPlanning/data-engineering commit `32bc98f632f15e7182933a17fb61ecf74e853518`.
The reference checkout is read-only; this workflow never commits or pushes to it.

## Read the SQL

Start with the [dbt project guide](../dbt/README.md).
The project covers tax records, condominium allocation, CAMA, geometry, zoning,
enrichments, corrections, typed exports and six QA report families. Its SQL uses
SELECT models with explicit dependencies. Repeated full-column projections have
been replaced with `* REPLACE`, `* RENAME` and `* EXCLUDE`; shared macros handle
numeric and spatial compatibility. Model headers explain their upstream business
rule and source location. The consolidated design has **38 business models** rather than one model per
SQL operation: 21 source-to-map processes, five correction models, six delivery
models and six QA reports. Named CTEs retain ordered rules inside each process;
`ref()` connects meaningful process boundaries. The two land-use passes remain
separate because zoning affects the later classification.

The 38 business process SQL files sit directly in `dbt/models/`.
Their filenames describe the process, while explicit dbt aliases preserve the
existing database relation names used by exports and QA. For example, select
`qa_expected_derived_values` with `dbt build --select qa_expected_derived_values`;
its published view remains `qaqc_expected`. The full old-to-new identifier map
is in the [dbt model README](../dbt/README.md#renamed-model-identifiers).

Moses recipes define physical input cleanup once; dbt retains PLUTO staging projections. Independent projections are
combined only when their writes and reads permit it. Spatial assignments share
a stable parcel input and small materialized matches, then apply independent
fields together. A common correction ledger drives values and audit reports;
specific-parcel changes precede global value changes. The manifest retains
original statement provenance, including rules replaced by shared logic.

Consolidation is checked against the completed statement-level candidate, not
only against published PLUTO. The verification script compares parcel values and
all three correction-report multisets, retaining duplicate rows and the
CSV distinction between NULL and quoted empty text:

```sh
.venv/bin/python scripts/verify_full_consolidation.py \
  .moses/pluto-build/26v2m2 .moses/pluto-build/26v2m4 \
  --output .moses/pluto-build/26v2m4/consolidation-review
```

`diagnose_consolidation_audits.py` explains audit differences separately from
that exact comparison. It maps only generated current-release labels and, for
removed records, separately reports the internal serial identifier. Historical
research versions and every business value remain unchanged in that comparison.
`diagnose_ambiguous_matches.py` records competing CAMA/ZIP source rows and the
canonical candidate selection. Neither diagnostic alters candidate data.

The maintained project is portable: sources resolve through `source()`, model
links through `ref()`, and the current/previous release labels through dbt vars.
The build also retains its generated project, manifest, compiled SQL and execution
results beside the output database. `provenance.json` records the source code
hashes and each model's dependencies and upstream statement.

## Run

Run these commands from the PLUTO example root. The active workflow has two independent commands. See
[Moses source recipes](../../../docs/source-recipes.md) for the Moses/dlt design and
[the standalone product](../README.md) for its input contract.
Install dependencies and native extensions beforehand.

Prepare the 49 locked source inputs and materialize the 42 consumed tables:

```sh
pluto-example --warehouse .moses/pluto-production/26v2/warehouse \
  prepare recipes/26v2.yml \
  --lock .moses/pluto-production/26v2/production-ingestion.json \
  --output-dir .moses/prepared/pluto-26v2-local \
  --extension-directory .extensions \
  --geosupport-release 26b \
  --geosupport-extension /absolute/path/geosupport.duckdb_extension \
  --geosupport-home /absolute/path/geosupport-bundle-store \
  --geosupport-runtime docker
```

Then run PLUTO with the already prepared database:

```sh
export PLUTO_INPUT_DATABASE="$PWD/.moses/prepared/pluto-26v2-local/prepared.duckdb"
export PLUTO_OUTPUT_DATABASE="$PWD/.moses/pluto-build/26v2-local.duckdb"
export PLUTO_SPATIAL_DIRECTORY="$PWD/.extensions"
dbt build --project-dir dbt --profiles-dir dbt \
  --vars '{pluto_version: 26v2-local, previous_pluto_version: 26v1}'
```

The second command needs no Moses catalog, upstream checkout, source recipe,
SQL compiler, Geosupport or network service. It attaches the input database
read-only and validates its schema before running the 38 business models.
Moses no longer includes a `pluto` command. The example's retired
`pluto-example build` and `pluto-example run` commands return migration guidance
rather than launching acquisition and transformation together.

To migrate a verified completed legacy source cache, preparation accepts
`--legacy-source-build .moses/pluto-build/26v2m4` instead of native runtime
arguments. This explicitly imports source relations, checks their input and
implementation provenance, and applies declared physical cleanup. The manifest
identifies migration and retains the native/source implementation actually used.
It is not a fresh execution of the current source provider.

### Historical combined-run evidence

The citywide evidence below came from the former combined runner. Its completed
candidate, report, input lock and executed implementation snapshots are preserved.
Legacy compiler/runner modules remain for reviewing and reproducing that evidence;
they are not the ordinary product execution path. Old cache fingerprints are not
rewritten when the preparation implementation changes.

### Standalone citywide verification

The separated workflow completed on 2026-10-18 using the verified prepared
sources from `26v2m4`. Ordinary dbt rebuilt all 38 models (26 tables and 12 views)
plus ten hooks in **240.89 seconds**; process wall time was **245.70 seconds**.
No acquisition, native geocoding, upstream checkout or upstream SQL-port generation was part
of that invocation. Export then produced all 13 delivery artifacts.

All 858,284 parcel keys and all 99 compared fields match the prior candidate,
including its candidate version label. The 42 prepared source tables had already
passed exact schema and row-multiset comparisons across 6,288,770 rows. The
prepared database's SHA256 remained unchanged after dbt and export.

Applied corrections (42,955 rows) and rejected corrections (517 rows) match as
exact text/NULL multisets. All 1,810 removed-record rows have different internal
serial IDs; excluding only that generated ID leaves identical business values,
NULLs and duplicate multiplicity. The raw mismatch remains in the verification
report. This does not establish official-release or historical native parity.

Both MapPLUTO exports match the prior candidate's keys, attributes and geometry
WKB exactly (856,687 clipped and 856,906 unclipped rows), with EPSG:2263 metadata
and no null or invalid geometries. All six QA reports match after explicitly
mapping the old `previous_locked` display label to `26v1` and ignoring ordering
inside unordered expected-value/outlier JSON arrays. Raw differences are retained.
The [checked-in evidence summary](../scripts/separation-validation.json)
records hashes, raw versus diagnostic comparisons and remaining limitations.

Local execution evidence is in `.moses/pluto-build/26v2-standalone/`, with source
evidence in `.moses/prepared/pluto-26v2-separation2/`. The earlier failed 1 GiB
preparation attempt is retained separately and has no ready manifest.

## Historical outputs and review

The output directory contains `pluto.csv`, `pluto.parquet`, mapped Parquet
variants, correction CSVs, QA CSVs, per-stage row counts, a source preparation
report, the DuckDB database and the dbt project. `build-report.json` records
status, input lock, runtime versions, hashes, validation and resource measurements.
A failed build does not accept a new Moses output version. A completed build
accepts the validated tabular candidate as `pluto_moses`.

When `--reference` is supplied, `reference-comparison.json` reports added/removed
BBLs, field mismatch counts and bounded examples. Both sides must have unique,
canonical BBLs. Numeric CSV values are adapted to the candidate's declared type;
text and null differences remain visible. This is an explicitly adapted tabular
comparison, not a spatial or native-schema parity proof.

## Fidelity decisions

- Six source captures are published normalized artifacts; 32 are raw
  reconstructions. Their historical normalized lineage remains unattested.
- Shared input macros reproduce PostgreSQL CSV loading's empty-string-to-NULL
  behavior for reconstructed imports. The pinned tabular loader uses
  `csv.writer` and `COPY CSV`; GeoPandas' spatial writer uses the same mechanism.
  The historical installed GeoPandas version is not attested. Whitespace remains unchanged. The five
  directly restored PostgreSQL COPY captures retain their original distinctions
  between empty strings and NULLs.
- Seed adapters use dbt's Agate inference on the pinned CSVs and honor configured
  text columns. Numeric grouping commas are removed only after checking every
  pinned value against Agate's result. Blank and literal `null` values follow
  Agate's null rules; non-null text codes retain their original spelling.
- Geosupport 26B is an explicit reconstruction choice. The historical mutable
  build image does not establish a bundle identity. BL, street-name lookup, 1A,
  1E, BN and TPAD retry stages are materialized once and checkpointed. Building
  input multiplicity is retained when counting lots.
- The captured geocode recipe's latitude/longitude point-axis discrepancy is
  recorded. The original downstream coordinate backfill uses longitude/latitude;
  final tax-lot polygons come from the DOF geometry sources.
- Bare PostgreSQL NUMERIC uses bounded DECIMAL(38,12). Decimal rounding and
  numeric-to-text handling are explicit compatibility rules. Numeric products
  reset to scale 12 after each multiplication, preventing chained scale growth.
  Two scale-12 factors must still fit DuckDB's 38-digit intermediate, including
  at most 14 integer digits. This does not claim
  arbitrary-precision equivalence outside that domain.
- Geometry repair retains the MULTI wrapper of collection inputs, matching
  PostGIS before the upstream zoning geometry-type filters. Census-tract cleanup
  retains the two-digit fractional suffix, including `170.10`. Union aggregation
  of entirely SQL-NULL inputs remains NULL; explicit empty geometries remain
  empty, preserving the upstream map-flag distinction.
- CAMA and ZIP fallback matches use an explicit canonical source ordering when
  several rows are eligible. This is an operational tie-break within the original
  allowed matches, not a claim of business precedence or a rule derived from the
  published result. Source identities precede the remaining payload, with explicit
  NULL ordering. Other upstream updates can still select an unspecified matching
  row; the manifest lists those operations. Complete historical selection and
  deterministic replay across every ambiguous input are not attested.
- Current QA calculations are included. Historical QA accumulator rows are not
  copied into the reports; calculations that need previous PLUTO use its lock.
  Executed QA comparison labels use `previous_locked` for the locked 26v1 data,
  so a pair is labeled `26v2m4 - previous_locked`. This is a compiler label
  fallback, not a different dataset or a dynamically selected release. The
  accepted QA files preserve that label; use the input lock for exact provenance.

Successful execution produces a **candidate**, not an official NYC Planning
release or a claim that every value matches 26v2. Differences and missing
historical evidence remain visible in the reports.

## Execution evidence

Candidate **26v2m4** completed on 2026-10-18 and was accepted into Moses as
`pluto_moses`, version `20261018T124514423825Z-0ffff6c3`. Exports, the executed
project and comparison evidence are in `.moses/pluto-build/26v2m4/`. Earlier
candidates `26v2m1`, `26v2m2` and `26v2m3` remain preserved.

- All **38 dbt models** (26 tables, 12 views) and eight hooks passed, with no
  errors, warnings or skipped models. The transformation took **279.72 seconds**;
  the full attempt, including validation, exports, comparison and ingestion,
  took **439.302 seconds**. Verified native caches were reused, so these are not
  cold extraction/geocoding timings.
- PLUTO contains **858,284 rows, 99 columns and 858,284 distinct non-null BBLs**.
  Published 26v2 has exactly the same parcel keys and column names.
- **97 of 99 columns match published 26v2 completely.** The version label differs
  intentionally. Three latitude values differ by `0.0000001` degrees; every other
  tabular value matches under the declared numeric/CSV comparison policy.
- MapPLUTO contains **856,687 rows**; its unclipped variant contains **856,906**.
  Both exports have zero null or invalid geometries and explicit EPSG:2263
  GeoParquet metadata. No spatial reference artifact was available for parity.
- Parent-process peak RSS was 7,860,633,600 bytes; the largest child's was
  7,140,589,568 bytes. These are separate lifetime peaks, not simultaneous
  combined memory use. The dbt profile uses a 4 GB DuckDB memory limit.

The consolidated candidate also matches the 405-model `26v2m2` baseline on every
parcel value except the intentional version label and one corrected map flag.
The map-flag correction preserves SQL NULL when unioning an entirely NULL group,
which fixes BBL `4158890999` from 3 to 2. This is a documented compatibility fix,
not a consequence hidden inside the consolidation.

Correction audits contain **42,955 applied changes, 517 rejected changes and
1,810 removed records**. Raw text/NULL multiset comparisons remain available.
The 2,082 applied-row differences are solely the generated current-release label;
removed rows differ only in their internal serial id and current-release label.
After those explicitly named diagnostic adjustments, every audit business value,
NULL/empty distinction and duplicate count agrees. Rejected records match exactly
without adjustments. See `consolidation-review/audit-diagnosis.json` alongside
`consolidation-verification.json`.

The intermediate consolidated `26v2m3` exposed unspecified source choices: five
CAMA parcels have conflicting eligible building records, and one ZIP fallback
point lies in two matching polygons. The final candidate uses a source-based
canonical tie-break for ten CAMA assignments and that ZIP assignment. Permutation
fixtures verify stable choices; `consolidation-review/ambiguous-matches.json`
records competing rows and selections. The manifest retains 82 originally
unordered update operations: 22 were rewritten by the correction ledger and
60 remain in active process CTEs. These limits prevent a claim of universal
row-order-independent replay.

Earlier candidates exposed geometry repair removing MULTI wrappers from 25
zoning geometries and numeric-to-text conversion dropping a census-tract trailing
zero. Focused regressions cover both fixes. Earlier attempts also exposed decimal
scale growth, seed inference differences and excessive temporary storage from
nested spatial updates. Their logs remain preserved with the original candidate.

The remaining latitude differences occur just above seven-decimal rounding
thresholds. Current DuckDB and an independent PROJ calculation agree for all
three coordinates. The historical unrounded values and runtime are unavailable,
so the precise historical cause is not established. No reference-driven rounding
adjustment has been applied.

Final verification is recorded in `consolidation-review/final-validation.json`.
The full test run passed 254 tests and skipped six optional checks; its 12
localhost-service setup errors were sandbox socket restrictions. All 12 service
tests passed when rerun with localhost permission. A separate native-extension
run passed all 15 source-preparation tests, including the five native checks
skipped in the general run. Wheel and source distributions build successfully;
both contain exactly 38 SQL models, and the wheel includes all six shared macro
files and the current implementation modules. Parent artifact hashes and database
fingerprints remain unchanged; `data-engineering` is clean and remains reference
material only.

The six QA report families were also compared with the baseline. A separately
labeled diagnostic normalizes current-release labels and unordered JSON arrays
while retaining duplicate values. Expected values, aggregate values, BBL changes
and outlier records agree; mismatch/null count changes follow the documented
single map-flag correction. Original CSVs remain available, and all 12 factored
QA query variants pass token-equivalence checks against pinned source SQL.
