# Source recipes and the PLUTO boundary

Moses acquires and homogenizes data, then publishes versioned warehouse inputs.
PLUTO is a separate dbt project that reads those inputs. Preparing data never
invokes PLUTO, and building PLUTO never downloads data or invokes Geosupport.

```text
Files / APIs / custom Python
            ↓
Moses source recipes
  extraction → types/nulls → geometry or Geosupport → accepted snapshot
            ↓
Prepared input database and manifest
            ↓
Standalone PLUTO dbt project → PLUTO, MapPLUTO, audits and QA
```

## Design reference: dlt

The design follows dlt's [sources](https://dlthub.com/docs/general-usage/source),
[resources](https://dlthub.com/docs/general-usage/resource) and
[declarative REST configuration](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic).
A source describes an external system; resources describe the datasets extracted
from it. Shared client settings and resource defaults avoid repeating endpoint
configuration. Custom Python handles sources or preparation procedures that the
built-in operations cannot express clearly.

Moses uses dlt as an optional REST extraction adapter. It does not use dlt to
write into the Moses catalog. Moses retains responsibility for acceptance,
immutable versions, exact input locks, null/type policies, CRS and geometry.
The adapter does not become a dependency of the PLUTO dbt project.

YAML is the recipe format because nested resources, field mappings and ordered
procedures remain readable. TOML works well for application settings, and dlt
uses it for configuration, but that does not require Moses recipes to use TOML.
The validated schema and execution contracts matter more than serialization.
Recipes use safe data loading, reject unknown fields and duplicate keys, and
do not embed Python, SQL or shell expressions.

## Use a recipe

Install the optional REST backend when needed:

```sh
python -m pip install -e '.[dlt]'
moses --warehouse .moses prepare recipes/examples/points.yml
moses --warehouse .moses prepare recipes/examples/dlt-rest.yml
PYTHONPATH=recipes/examples moses prepare recipes/examples/trusted-python.yml
```

The REST example contacts a public API; the point and Python examples run
locally. [The example guide](../recipes/examples/README.md) documents fields,
secret references, processing order and capture replay. The initial dlt adapter
supports GET endpoints producing flat records, with explicit response selection
and pagination. POST requests, nested-record shaping and unusual authentication
can use a named Python source; they are not silently approximated by the adapter.

## Recipe responsibilities

| Layer | Responsibility |
| --- | --- |
| Source | Local file, downloaded file, exact catalog version, REST resources or a named Python extractor |
| Preparation | Explicit renaming, null handling, types, custom procedures, XY geometry or Geosupport |
| Publication | Schema/key validation, source and recipe identity, immutable catalog version |
| Product | PLUTO joins, parcel rules, calculations, corrections and final outputs in dbt |

Ordinary REST extraction should not require writing Python. The REST adapter
reuses dlt's client, resource defaults, endpoint, authentication, pagination and
response selection vocabulary. A recipe selects one resource for its output;
related resources may support extraction dependencies. Every output is accepted
individually, rather than promising an atomic multi-resource load.

Custom Python is an explicit trusted `package.module:function` reference with
declared parameters. A source function produces records or an Arrow table; a
preparation function receives a table and returns records or a table. This is
ordinary local code, not a sandbox. The recipe records the function's identity
and code or package provenance, so the escape hatch remains inspectable.

REST credentials are environment references, not values saved in recipes or
manifests. Extracted records are captured as Parquet and can be replayed without
contacting the API again; these are not archives of raw HTTP responses.
Incremental REST cursors are initially unsupported: they need a transactional
state contract so failed publication cannot advance a cursor past missing data.
See dlt's [state model](https://dlthub.com/docs/general-usage/state).

## PLUTO source collection

[The 26v2 collection](../recipes/pluto/26v2.yml) lists all 38 upstream inputs
and 11 seeds. Exact versions resolve from the supplied input lock. It explicitly
identifies the 42 source tables consumed by dbt and the seven retained inputs
that this transformation does not read.

The collection keeps seed type conversion and physical null cleanup in Moses.
Its NYC provider preserves the release's existing source normalization and
native geocoding behavior. The provider is still in the legacy source module;
it has no dependency on dbt or the SQL compiler. Declarative acquisition for
arbitrary sources is independent of that release-specific provider.

The prepared output contains physical tables, not views that depend on local
capture paths. The manifest records source versions, preparation policy,
runtime identity and provisional lineage. The standalone dbt project validates
42 tables and 650 columns before applying business rules.

For migration, a completed legacy build can supply already prepared source
relations through an explicit option. That mode verifies the old source cache
and records its actual source implementation and native runtime. It does not
claim that the current preparation implementation ran, and it does not reuse
the old PLUTO business results as inputs.

New generic point recipes use X=longitude and Y=latitude for EPSG:4326. The
legacy 26v2 provider explicitly records its historical geocode-axis convention
so a migration does not silently change the validated candidate's behavior.
Published-reference and historical native-runtime parity remain separate from
verifying this architectural separation.

The 26v2 migration was checked against the legacy source-cleaning queries using
exact column names/order/types and bidirectional `EXCEPT ALL`: all 42 tables,
650 columns and 6,288,770 rows matched, including duplicates and NULLs. The
prepared database is about 0.66 GiB and contains physical input tables. Its
legacy source database SHA256 was unchanged after preparation. The first attempt
exceeded a 1 GiB memory cap and published no ready warehouse; the successful
publisher uses a 4 GiB limit and does not preserve insertion order.

Repeat that source comparison with:

```sh
python examples/pluto/verify_prepared_inputs.py \
  --prepared .moses/prepared/pluto-26v2-separation2 \
  --legacy .moses/pluto-build/26v2m4 \
  --extension-directory .extensions \
  --output /tmp/prepared-input-comparison.json
```

See [the standalone PLUTO instructions](../products/pluto/README.md) for the
transformation command and [the full candidate evidence](pluto-full-build.md)
for the existing citywide comparison and its limitations.

Validation completed with 330 integrated tests passing and one optional DuckLake
test skipped; the 12 loopback service tests also passed. The source recipe slice
includes 40 focused tests using actual dlt 1.31.0 with mocked HTTP, captured-data
replay, trusted Python, explicit types, geometry and native registration checks.
The built wheel also ran local point and Python recipes outside the checkout.
This remains reviewed branch work, not a merged or released service capability.
