# PLUTO real-source integration results

On October 17, 2026, Moses successfully normalized and versioned four real inputs related to NYCPlanning's PLUTO workflow. This validates the local source lifecycle on bounded public captures and a complete lookup seed. It does **not** reproduce a PLUTO build, validate production recipe transformations, or establish citywide performance.

The executable evidence is [results.json](../examples/pluto/results.json); the [runner](../examples/pluto/run_case_study.py) records retrieval times, source URLs/queries, capture and content hashes, schemas, runtime versions, source-code hashes, accepted versions, and SQL results. The NYCPlanning evidence checkout was `5b849eebf4afbe282f30944cfbedd918bc51ad81`. The Moses checkout contains work in progress; the report records source hashes rather than implying its Git commit alone reproduces the implementation.

| Input exercised | Capture | Result | Relationship to production PLUTO |
|---|---:|---|---|
| `pluto_public_sample` | 100 CSV rows from Socrata `64uk-42ks` | Passed; rows report publisher version `26v2` | Alternate live PLUTO distribution. **Not** the versioned DCP ZIP or the required previous-release `VERSION_PREV` input; no point geometry created. |
| `lpc_landmarks` | 100 GeoJSON features from `ncre-qhxs` | Passed; geometry retained as WKB with EPSG:4326 | Exact public raw endpoint/format in `ingest_templates/lpc_landmarks.yml`; production rename and date coercion are not applied. |
| `dpr_greenthumb` | 100 CSV rows from `p78i-pat6` | Passed as attributes | Same public dataset as `ingest_templates/dpr_greenthumb.yml`, with a CSV representation instead of the recipe GeoJSON; no spatial parity claim. |
| `pluto_input_landuse_bldgclass` | All 221 rows from the repository seed | Passed; text land-use codes retain `01` | Exact complete local seed documented by `products/pluto/seeds/_seeds.yml`. |

For each input, the runner inspected the schema, ingested the captured bytes, reingested the identical capture, queried its row count, and exported the accepted version through the CLI. Each repeat produced a second observation without a new version. Each Parquet export matched the accepted Arrow table. The runner saved a lockfile and reproduced the PLUTO-to-seed join through the CLI using its pinned versions. All 100 sampled PLUTO building classes matched the seed; there were no blank/null sampled PLUTO BBLs.

LPC's 100 sampled features contain only 99 distinct BBLs. This supports the template's warning that multiple landmark records may belong to one parcel: a PLUTO-friendly join field is not necessarily a valid dataset key. The LPC and GreenThumb imports deliberately omit a key rather than inventing uniqueness. This leaves their row diffs unable to infer keyed updates.

The samples use stable Socrata `:id` ordering, not random or representative sampling. The CSV helper limits each request and caps its response at 10 MB; the GeoJSON request uses Moses's existing limited Socrata downloader. The GeoJSON downloader itself has no response-byte cap, so a single oversized feature remains a bounded-row, unbounded-byte limitation. Source snapshots are not transactionally consistent across requests. These checks do not test changed upstream data, spatial joins, reprojection, S3/DuckLake destinations, full-city memory use, or output parity against an accepted PLUTO release. They exercise Socrata representations and local files, not three different connector families.

## Repeat the checks

From the Moses checkout, with its dependencies installed and an adjacent `data-engineering` checkout:

```sh
.venv/bin/python examples/pluto/run_case_study.py
.venv/bin/python examples/pluto/run_case_study.py --seed-only --output .moses/pluto-case-study/seed-only-results.json
.venv/bin/python -m pytest tests/test_pluto_case_study.py -q
```

The first command uses public network access and defaults to 100 records per remote dataset. `--limit` accepts 1–1000. No credentials are used. The seed-only command performs the entire lifecycle and locked seed aggregation without network access. The regression test passed and also verifies that tampering with a cached capture fails its provenance hash check; it skips explicitly when the real adjacent NYCPlanning seed is absent.

Every run creates a new directory under ignored `.moses/pluto-case-study/`. Its `captures/` contains raw inputs and provenance sidecars, `warehouse/` contains the complete catalog, raw files and snapshots, `exports/` contains verified Parquet files, and `inputs.lock.json` pins the local versions. Preserve that entire run directory for local replay. Neither a lockfile nor the committed report alone contains the data needed to reproduce a run.

To repeat a specific capture without another network request, replace the example run directory with `work_directory` from the report:

```sh
.venv/bin/python examples/pluto/run_case_study.py --offline-from .moses/pluto-case-study/run-EXAMPLE/captures --output .moses/pluto-case-study/offline-results.json
```

Offline capture replay was also run successfully across all four inputs. A future live run can yield different content or fail because publisher schemas or endpoints changed; the runner preserves per-input failures and exits nonzero rather than calling a partial run successful.

## Product decisions from the case study

1. Make source identity, publisher release, capture date, row limit, representation, and normalization status visible before accepting a version. A successful import of current public PLUTO must never look like an accepted production `previous_pluto` release. Track the release/recipe resolver in [#18](https://github.com/SPTKL/moses/issues/18).
2. Profile candidate keys before ingestion and offer “no unique key” explicitly. LPC supplies a real counterexample to a blanket BBL-key default. Show blank identifiers and repeated keys separately, and preserve leading-zero lookup codes.
3. Keep this case study as a fast acceptance gate in [#17](https://github.com/SPTKL/moses/issues/17), then test one actual versioned HTTP ZIP and one ArcGIS source. Do not infer those transports work from the Socrata checks.
4. Gate PLUTO replication on a fixed source-release manifest, production normalization contracts, transformation execution, and row/geometry comparison against an accepted output. The [parity harness in #19](https://github.com/SPTKL/moses/issues/19) should define that evidence before a full-build claim.

No core Moses defect was observed in these exercised paths. The missing recipe execution, production source adapters, profile guidance, and full-build parity are roadmap gaps, not completed capabilities.
