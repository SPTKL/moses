# Generic source recipes

From the repository root, run `uv run --locked moses prepare recipes/examples/points.yml` for
local XY construction. `catalog-normalize.yml` requires an existing exact
catalog version. `address-points.yml` requires the explicit installed native
extension digest, bundle ID and runtime paths; its placeholder values do not
select or install a runtime automatically.

`dlt-rest.yml` uses the optional `moses-geo[dlt]` extra (`uv sync --locked --extra dlt`), tested with dlt 1.31.0.
The `client`, `resource_defaults` and `resources` configuration follows
[dlt REST resources](https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic).
`source.resource` selects one resource; recipe `name` maps it to a Moses dataset.
Explicit paginator and data selector are required. This initial adapter supports
GET and flat records, without incremental state, custom sessions, serialized
callables, response actions or dlt loading. Nested record payloads require a
more specific selector or trusted Python returning an explicit Arrow schema.

Credentials use environment references, never plaintext YAML, for example:

```yaml
source:
  kind: dlt_rest_api
  resource: records
  config:
    client:
      base_url: https://api.example.com/
      auth: {type: bearer}
    resources:
      - name: records
        endpoint:
          path: records
          data_selector: data
          paginator: {type: single_page}
  secrets:
    client.auth.token: {env: MY_API_TOKEN}
```

For API keys, `auth` also accepts nonsecret `name` and `location` selectors;
the key itself uses a `client.auth.api_key` reference. HTTP basic credentials
use `client.auth.username` and `client.auth.password` references. Resolved values
are kept out of recipe reports; remote/custom exception details are suppressed.
Source data returned by the API remains source data and may itself contain
sensitive fields. Credential-bearing file URL queries are rejected.

Run the custom example with
`PYTHONPATH=recipes/examples uv run --locked moses prepare recipes/examples/trusted-python.yml`.
A named `module:function` source receives keyword `parameters` and returns
records or an Arrow table. Processing functions receive the Arrow table first,
then keyword parameters. They run as trusted Python, with ordinary process
permissions. Optional `code_sha256` pins their module file; reports record code,
package and Python identities. Secrets references address parameter names for
sources and steps, rather than REST config paths. There is no inline eval.

Execution order is acquisition/capture, rename, optional snake_case, null/trim policy, primitive
types, ordered custom processing, declared geometry or Geosupport, key checks,
then catalog publication. Set `import.column_names: snake_case` for lowercase
ASCII letters, digits and underscores; conflicting names fail rather than being
silently suffixed. Import types, keys and geometry fields refer to final names. Captured
record fields with explicit types retain a lexical representation until import
policies run, including mixed numeric/string identifiers and initially-null
pages. Other schema changes across capture batches fail visibly. Decimal and
geometry metadata can be supplied through an explicit Arrow table.

REST and Python acquisition save a content-hashed Parquet capture before
processing. This is a snapshot of parsed records, not an HTTP response archive.
The report's `source.capture_path` is relative to the catalog root; use that
file as `source.kind: local` with its reported `sha256` to replay without dlt,
network access or Python source execution. Keep the same import policies and
required processing steps for an equivalent prepared output. No version is
published until every step succeeds.
