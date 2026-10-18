# PLUTO foundation release review

Reviewed 2026-10-17 against the preexisting local foundation changes for [issue #2](https://github.com/SPTKL/moses/issues/2). The initial review added this report only. A follow-up fixed the demonstrated no-op inference version issue in `src/moses/catalog.py` and added four regression cases in `tests/test_foundation_cli.py`; other foundation implementation changes predated this review. The integration case study has separate evidence for real source downloads. The fixtures below are deliberately synthetic operator scenarios, not PLUTO production data.

## Release judgment

The local tabular/inspection foundation is ready for a reviewed PR within issue #2's stated scope. Its existing suite passes, its distribution builds, the built wheel runs outside the repository, and a warehouse created by committed HEAD retains its accepted CSV version after upgrading to the worktree implementation. No release-blocking regression was demonstrated in that scope.

This does **not** establish readiness to reproduce the full PLUTO build. Domain validation, explicit source recipes, acquisition provenance, large-source performance, transformation lineage, and parity against an accepted PLUTO release remain separate gates. A generic immutable file loader can accept rows that are unsuitable as production tax-lot inputs.

## Verification performed

Commands were run from the repository using `.venv/bin/python`:

| Check | Evidence |
| --- | --- |
| `python -m pytest -q` | 65 passed, 1 skipped, 1.29 seconds at review baseline. The skip is optional DuckLake integration, so this is no assertion of DuckLake/S3 service compatibility. |
| `python -m build --no-isolation` | Built `moses_geo-0.1.0.tar.gz` and `moses_geo-0.1.0-py3-none-any.whl`. |
| Built-wheel smoke test | Installed the wheel with `--no-deps --no-index --target` into a temporary directory; ran from outside the repository with that package on `PYTHONPATH`. Verified the imported package path was the temporary install. The environment reused existing dependencies. |
| Wheel behavior | Bundled `demo` created two EPSG:4326 points; SQL counted two rows; TSV inspection preserved ID `001` as string and inferred amount `2` as int64. New `inspection` and `config` modules were importable. |
| Existing-warehouse upgrade | Extracted committed HEAD's package into a temporary directory, ingested a CSV with leading-zero IDs, empty attribute, and X/Y coordinates, then ingested the same source with the current implementation. `unchanged=true`, identical content hash, identical accepted version. |
| Locked input replay | Loaded CSV version A with blank `units`, saved `Catalog.lock()`, loaded version B with `units=7`. Current query returned `7`; the same query with the saved lock returned the original blank. Diff reported one changed row. |
| Failed-input isolation | A subsequent CSV containing duplicate BBL values failed validation; the current version stayed at B. |
| No-op inference regression | Both Parquet flag-toggle cases failed before the fix; CSV/TSV semantic-change cases passed. After the fix the full working-tree suite passed: 70 passed, 1 optional DuckLake skip, 1.30 seconds (includes the integration agent's case-study test). |
| No-op inference upgrade | Built a temporary package with the pre-fix option handling, created a Parquet version with inference enabled, then reopened it with the fixed implementation. Historical reads and locked queries succeeded; one normalized release was created, and the next flag toggle was unchanged. |

Existing tests cover conservative full-column inference, empty-string and leading-zero preservation, plain Parquet types, non-mutating inspection, CRS configuration precedence, conflicting explicit CRS, and exact-set lock registration. The follow-up tests cover the new option-normalization boundary and verify CSV/TSV inference still creates a version when types change, while the prior string version remains readable and lock-queryable.

## PLUTO operator findings

### Source contracts must distinguish blank keys from SQL nulls

Reproduction input:

```csv
bbl,units,x,y
1000010001,,987000,201000
,12,987001,201001
```

`Catalog.ingest(..., name="lots", key="bbl")` accepts both rows. Read-back BBL values are `["1000010001", ""]`. The current key contract checks uniqueness and Python/Arrow nulls, not blank strings. This follows the existing preservation policy and is not a regression in issue #2. It is insufficient for a PLUTO recipe that requires populated identifiers.

Likewise, `SELECT count(*) FROM lots WHERE units IS NULL` returns zero, while `WHERE units = ''` returns one. A transform must explicitly normalize approved blank/sentinel values before numeric casts or missingness checks. It must not silently treat a missing measurement as zero. A source-specific recipe should also state whether its grain is one row per BBL, whether repeated BBLs are valid, and which composite keys are required. A successful import with an arbitrary unique key does not establish the correct grain.

Recommended acceptance for the schema/validation work: preserve captured bytes, offer explicit per-column null-token and type policy, validate required/nonblank keys and expected cardinality, report failing row examples/counts before publishing, and record the applied recipe with the version. Keep generic string preservation available.

### State Plane coordinates require an explicit recipe decision

Inspecting the same input with `x="x", y="y"` and no default or explicit CRS returns `EPSG:4326`, `crs_source="legacy_csv_default"`, and a warning. Coordinates such as `(987000, 201000)` are not valid longitude/latitude values; valid WKB construction alone cannot establish a usable map.

The legacy fallback and warning are intentional compatibility behavior. For sources documented as New York State Plane feet, configure their documented CRS explicitly (commonly EPSG:2263); do not choose a projection solely from coordinate magnitudes or field names. Sources with longitude/latitude need their own source-specific decision rather than inheriting a warehouse-wide State Plane default.

Recommended acceptance for [issue #4](https://github.com/SPTKL/moses/issues/4): a strict recipe can require explicit/embedded CRS, reject or quarantine coordinates outside the declared geographic domain, count missing/partial/zero-sentinel coordinates, and retain an explanation of assignment versus reprojection. An assumed CRS should remain visible in preview and acceptance summaries. This is a production correctness gate, not a request to break the existing CLI fallback in issue #2.

### Input locking is useful but is not a complete build record

The observed replay result verifies that locks bind datasets to specific snapshots after current versions advance. It does not record SQL, build code revision, source release selection, geocoder/reference-data versions, output acceptance tests, or output lineage. A local lock also requires retaining the corresponding warehouse files.

For a first PLUTO slice, save the input lock, source provenance, explicit transformation recipe, engine/runtime versions, and validation results together. [Issue #16](https://github.com/SPTKL/moses/issues/16) should prove one deterministic transform can publish a derived version with those references and reproduce it after its source's latest pointer advances.

### Acquisition provenance is less accessible from the CLI than Python

Python ingestion accepts a `provenance` dictionary; `moses load` has no equivalent argument. An operator manually downloading a release can preserve source bytes and hashes but cannot supply its publisher URL, upstream release, retrieval timestamp, archive member, or completeness designation through that command. `moses nyc` records request provenance for its specific GeoJSON route, which does not solve all source formats.

The source acquisition/recipe workflow should expose these facts without requiring operators to write custom ingestion code. Mark bounded samples prominently so a successful sample load cannot be mistaken for a complete production source. Provide actionable next steps when a source needs a different adapter, archive-member selection, or access credentials.

### Fixed: no-op inference created distracting release history

Before the fix, loading a native Parquet file, then reloading identical bytes with `infer_types=True`, created a new version even though the reader left native types unchanged. The catalog hashed the supplied inference option. The fix includes inference in the effective recipe only for CSV/TSV, the formats where the reader applies it. Toggling the flag for native Parquet now records an unchanged observation without a new version; real CSV/TSV type changes still create versions. Other options and observation metadata are unchanged.

Compatibility: existing snapshots, manifests, and hashes are not rewritten. Historical reads and locks still work. A pre-fix non-CSV/TSV version that stored `infer_types=true` can create one new release on its first post-fix reimport because the effective-options hash is now normalized. Subsequent imports deduplicate normally. Versions originally loaded without that irrelevant flag keep their existing identity. This avoids migration or mutation of accepted historical versions.

## Senior PM prioritization

The next usable product milestone is an analyst completing a documented source-to-validated-output slice with explainable results. A broader hosted surface alone will not demonstrate that milestone.

1. Finish issue #2 review/release and run the bounded real-source case study. Preserve the distinction between successful samples and full-source coverage.
2. Deliver source recipes and validation with the case study: source release selection, grain/key rules, null policy, explicit types/CRS, provenance, and completeness. Extend issue #4 rather than creating duplicate generic schema tickets; create source-specific acquisition tickets where adapters are actually missing.
3. Pull a narrow locked-input transformation/lineage slice from issue #16 forward so the team can compare a useful PLUTO intermediate with a reference result. This does not require implementing the entire PLUTO build first.
4. Gate full-source adoption on representative memory/time measurements. Inspection reads an entire source; ingestion reads it twice, materializes rows for hashing, and holds a write transaction during parsing. Small fixtures provide no citywide capacity evidence. Coordinate [issues #6](https://github.com/SPTKL/moses/issues/6) and [#14](https://github.com/SPTKL/moses/issues/14) around measured limits.
5. Build the guided review screens around these real decisions: which upstream release, complete versus sampled, rows accepted/rejected, missing keys, type changes, CRS origin, and which locked inputs produced an output. A large JSON manifest is useful developer evidence but does not itself answer those operator questions clearly.

The immediate foundation can ship as the documented local MVP. The PLUTO reproduction milestone should remain open until source coverage, transformation parity, and production-scale evidence are demonstrated.
