# PLUTO source case study

Run from the PLUTO example root after installing its dependencies:

```sh
python scripts/run_case_study.py
```

This captures 100 real rows/features from each of three public NYC Open Data datasets and loads a complete 221-row PLUTO lookup seed from the adjacent `data-engineering` checkout. The live PLUTO CSV sample is an alternate public representation, **not** the previous-release input required by a PLUTO build. LPC is the exact recipe raw GeoJSON endpoint; GreenThumb is its alternate CSV representation. This is not a full build or a test of three connector families.

Use `--seed-only` for an offline run, `--data-engineering PATH` for another checkout, `--limit 1..1000` for a different remote row bound, and `--output PATH` to preserve the committed evidence report. `--offline-from PATH/TO/captures` reuses hash-verified captures and their original retrieval provenance. It does not redownload the sources.

Raw captures, local warehouse, exports and lockfiles live only under ignored `.moses/pluto-case-study/`. [results.json](results.json) records the measured checks and hashes without committing raw data. [The results document](../docs/pluto-integration-results.md) explains evidence, limitations, replay and product implications.
