# Local catalog GUI and API

The read-only service slice of [#3](https://github.com/SPTKL/moses/issues/3) and
catalog GUI [#5](https://github.com/SPTKL/moses/issues/5) are implemented locally
and awaiting review/merge. Populate the warehouse using
`uv run --locked moses load`, then serve accepted versions:

```sh
export MOSES_TOKEN="$(uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run --locked moses --warehouse my-city serve --port 8765
```

The CLI binds to `127.0.0.1`. All API requests require
`Authorization: Bearer <MOSES_TOKEN>`. The token comes from the environment and
is not printed; `--token-env NAME` selects another environment variable. Keep
the same variable in the shell used for requests. Stop the server with Ctrl-C.
Use a freshly generated token for each session when practical.

Open **http://127.0.0.1:8765/** to browse the catalog. Enter the same
`MOSES_TOKEN` value in the connection form. The token stays in browser memory;
refreshing the page or disconnecting clears it. Do not put tokens in URLs.
To copy the generated token on macOS, run `printf %s "$MOSES_TOKEN" | pbcopy`
in the shell where you started the service (before starting it, or while it is
running in the background), then paste it into the form.

The GUI supports dataset search, version history, exact-version row previews,
schema and CRS inspection, a Table/Map switch with feature details, two-version comparison, and authenticated Parquet
downloads. Preview row counts and omitted values are labeled. A dataset with
one version cannot yet be compared. Source/content hashes and capture time are
available; arbitrary provenance and local source paths remain private. Warehouse
row counts alone do not establish complete source coverage. Uploading, ingestion,
SQL and multilayer query workspaces remain separate work; use the CLI to populate the warehouse.

The HTML, CSS and JavaScript are fixed packaged assets served from the same
loopback origin, without CDN dependencies. They contain no token or catalog data.
They can be loaded before signing in; every data request still requires the
bearer token. Static assets retain Host/Origin checks and a restrictive content
security policy. The GUI is local and single-user, not a hosted identity system.

```sh
curl --fail -H "Authorization: Bearer $MOSES_TOKEN" \
  http://127.0.0.1:8765/v1/datasets
```

Use that exact host and port. Requests must carry the listener's `Host` value;
if an `Origin` header is present, it must match `http://127.0.0.1:8765` exactly.
Cross-origin requests are rejected. Remote deployment, multi-user identity and
parser isolation remain separate roadmap work.

## Resource routes

Dataset and version IDs are opaque `ds_...` and `ver_...` identifiers. Discover
them from API responses instead of constructing them from catalog names or
local version strings. IDs persist in `service-resources.sqlite3` in the
warehouse; retain this file with the catalog when backing up or moving it.

| Method and route | Result |
| --- | --- |
| `GET /v1/datasets` | Dataset names, opaque IDs, current version IDs and version counts. |
| `GET /v1/datasets/{dataset_id}/versions` | Accepted versions and safe metadata. |
| `GET /v1/datasets/{dataset_id}/versions/{version_id}` | One exact version's metadata. |
| `GET /v1/datasets/{dataset_id}/versions/{version_id}/preview?limit=10` | Bounded JSON rows from that exact snapshot. |
| `GET /v1/datasets/{dataset_id}/versions/{version_id}/map?limit=500` | Bounded display-only GeoJSON for the exact snapshot. |
| `GET /v1/datasets/{dataset_id}/versions/{version_id}/download` | Streamed Parquet/GeoParquet snapshot. |
| `GET /v1/datasets/{dataset_id}/compare?from={version_id}&to={version_id}` | Added, removed and changed counts plus schema comparison. |

Version IDs are checked against their dataset. Imports that advance the current
version do not change what an older version URL returns. API metadata omits
filesystem locations and arbitrary source provenance. Dataset values are still
the user's data and may themselves contain sensitive content.

Preview accepts 1–100 rows. Row payloads have a 64 KiB budget, and cells larger
than 4 KiB receive a truncation marker. Nested lists/maps over 100 entries use
an `items` or `entries` envelope with `truncated: true` and `omitted_count`.
Schema responses preserve exact field names/types; a schema larger than 64 KiB
returns `413 response_too_large` instead of silently clipping fields.
It reads Parquet in batches rather than
loading the full table for the preview. These output limits are not an operating
system memory sandbox: large Parquet pages or values can still require memory
while decoding. Comparisons are limited to 100,000 combined source rows and
use the existing in-memory diff implementation. Downloads stream an accepted
snapshot; raw capture downloads are not included in this slice.
Comparisons also return `crs_changed`, `old_crs`, and `new_crs`; schema comparison
includes Arrow metadata, so a CRS-only change may also flag `schema_changed`.
Without a dataset key, changed rows are represented as additions/removals rather
than inferred updates.

## Map preview

The wide workspace keeps dataset details on the right and offers Data, Fields,
History and Compare. Data has Table/Map controls; spatial versions open the map,
and unsupported versions return to the table with an explanation. Feature
properties can be selected by clicking geometry or using the keyboard-accessible
feature selector. The inspector can be collapsed; on narrow screens it follows
the main content. Branding is Moses only.

The map route accepts a feature limit of 1–1,000 (default 500). It scans at most
1,000 rows, returns at most 2 MiB of JSON, rejects WKB over 1 MiB before parsing,
and bounds coordinate work to 100,000 total and 20,000 per feature. Properties
are bounded to 8 KiB per feature, cells to 4 KiB, nesting to eight levels and
100 items per container. Large integers are represented as strings. Response
metadata reports scanned, returned, omitted and unscanned counts, omission
reasons, property summaries, limits and bounds of returned geometry. This is a
first-rows preview, not a geographically representative sample.

Known source CRS is converted on a display copy to EPSG:4326 with explicit XY
axis order. Assumed ingestion CRS is labeled. Unknown/invalid CRS returns 422;
no CRS is guessed. Null, invalid, unsupported, oversized, antimeridian-crossing,
nonfinite and out-of-display-range geometry is omitted with counts. Z is dropped
for the 2D display and reported. Snapshots are never rewritten. The limits bound
rows, geometry and output, **not process memory**: Parquet decoding and batch
materialization can allocate large pages/properties before truncation. Remote
parser isolation remains #9.

Leaflet, Inter and Feather assets are pinned and served locally with their
licenses. The default basemap is blank and offline. Choosing OpenStreetMap
explicitly sends the page origin and viewport tile requests to that provider; the UI discloses this
and displays its attribution. Changing dataset/version or rebuilding the view
resets to offline. No external map requests are needed to inspect geometry.
This is the narrow single-version map slice tracked in
[#23](https://github.com/SPTKL/moses/issues/23); SQL, multiple layers and saved
workspaces in #21 remain planned.

Errors have the shape:

```json
{"error":{"code":"not_found","message":"Version not found"}}
```

Typical responses are `400` for malformed requests, `401` for missing/invalid
authentication, `403` for Host/Origin rejection, `404` for unknown resources,
and `413` for configured size limits. Map metadata/CRS failures use `422`. Internal exceptions are not returned to
callers. No SQL or arbitrary server-file route is available.

## Reserved write contracts

The following routes validate the request shape, then return `501` with code
`write_unavailable`. They do not create uploads, inspections, or jobs:

- `POST /v1/uploads`
- `PUT /v1/uploads/{upload_id}/content`
- `POST /v1/uploads/{upload_id}/inspections`
- `GET /v1/inspections/{inspection_id}`
- `POST /v1/ingestions`
- `GET /v1/jobs/{job_id}`

Write contracts require an `Idempotency-Key` header. Their proposed fields are
shown in the [service architecture](service-architecture.md). They accept
resource IDs and file basenames, never local paths or fetch URLs. Upload sealing,
inspection binding, retry semantics, durable state, and ingestion execution
remain [#6](https://github.com/SPTKL/moses/issues/6). A `501` response is not a
successful upload or a job acknowledgement.

## Local GUI validation (2026-10-17)

The integrated Python suite passed 104 tests with one optional integration skip.
The client-state suite passed nine checks covering interrupted refresh, sign-out,
stale dataset/version/map responses and map-to-table fallback. Backend tests
cover historical exact versions, reprojection/XY, unsupported and missing CRS,
invalid/null/oversized/polar geometry, property precision and output budgets.

The initial catalog browser validation covered four bounded real case-study
datasets and a separate synthetic warehouse with historical preview/download,
comparison, literal HTML rendering, invalid token, empty catalog, search,
sign-out and truncation/error states. The redesigned GUI adds real map checks:
the 100-row landmarks snapshot returns 98 points and explicitly omits two null
geometries. See the project-root `design-qa.md` for final visual evidence and
responsive/interaction checks. These are developer checks, not a first-time-user
study, full-city capacity evidence, or production-input parity. Work remains
local and unmerged.
