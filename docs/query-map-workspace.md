# Explore: lightweight SQL and map workspace

Status: planned, 2026-10-17. This extends the [service and UI roadmap](service-architecture.md); it does not describe a shipped feature.

## Product outcome

After loading data, a user can browse its columns, run a short SQL query, inspect the result, and place spatial results alongside other datasets on a map. Make the common path work without writing SQL, while keeping SQL visible and editable for analysts. The experience should feel like a compact DuckDB workbench inside Moses.

The first release supports one local warehouse and read-only exploration of accepted versions. It includes joins, filters, grouping, and aggregates through DuckDB SQL; mapping a geometry column does not require spatial SQL or an extension download. Advanced spatial SQL follows as an explicit optional capability.

## Workspace and primary flow

The application has **Load**, **Datasets**, and **Explore** entry points. A successful import offers **Open in Explore** and, for spatial data, **Add to map**. Opening a dataset shows its schema, version, row count, geometry, and CRS before any query runs.

```text
+-------------------+-----------------------------------------------+
| Datasets          | Explore                 [Saved] [Run] [Cancel] |
| Search            | SQL editor                                    |
| > boroughs  v3    | SELECT * FROM boroughs WHERE borocode = '1'    |
|   columns / types |                                               |
| > facilities v8  +-----------------------------------------------+
| + Add data        | [Table] [Map] [Split]   elapsed / rows / limits|
|                   | Results table           | Map                 |
| Map layers        |                         |                     |
| [x] Boroughs      |                         |                     |
| [x] Facilities    |                         |                     |
| + Add layer       |                         |                     |
+-------------------+-------------------------+---------------------+
```

Use resizable panes on wide screens and Table/Map tabs on narrow screens. The table remains usable if map rendering is unavailable. Provide keyboard access, visible focus, labeled controls, and textual feature details as an alternative to map-only interaction.

1. Select a dataset and version. **Preview rows** generates a quoted `SELECT … LIMIT 100` query; **Add to map** creates a bounded dataset layer without requiring SQL.
2. Edit SQL with column/table completion, syntax highlighting, and inline errors. Run the selected single statement, or the whole editor when nothing is selected, with Run or Cmd/Ctrl+Enter. Multi-statement scripts are outside the first release.
3. Review a typed result grid and status: elapsed time, returned rows, whether the result is complete, and the exact input versions. Show nulls distinctly, keep large integers/decimals lossless, and summarize binary geometry rather than dumping WKB.
4. Choose **Add result to map** when geometry is available. Select a geometry column and confirm its CRS when the service cannot establish it. Nonspatial results keep the Table view and explain how coordinate columns can be mapped.
5. Add another accepted dataset or previous query result as a layer; compare them with visibility, order, color, and opacity controls. Clicking a feature shows its properties and highlights its row when that row is in the result grid.
6. Save a named query and its input versions, or save the workspace with layer definitions and map extent. Rerunning is explicit. Opening a saved workspace does not silently execute SQL or update pinned versions.

## First-release scope

| Area | Included behavior |
| --- | --- |
| Dataset browser | Search names; expand columns/types; inspect geometry/CRS; pick current or historical accepted versions; insert correctly quoted table/column names. |
| SQL editor | One editor, syntax highlighting, metadata-based completion, Run/Cancel, editable starter queries for preview/filter/count/group/join, actionable errors. |
| Results | Virtualized rows, paged access to a retained bounded result, column resize/copy, empty/error/loading states, version and truncation badges. Sorting/filtering the complete result is done through SQL; never present a sorted page as a globally sorted result. |
| Export | Download the retained result as CSV or Parquet, labeled as complete or capped. GeoJSON export uses the bounded map preview and reports omissions. Full query-result export is a later bounded job; accepted-source downloads remain a separate existing roadmap operation. |
| Map | Points, lines, polygons and multi-geometries; pan/zoom, fit layer/all, feature details, selected-row highlighting, optional basemap and an offline blank background. |
| Layers | Add dataset version, query result, or a new file through the existing loader; rename, show/hide, reorder, remove, set solid color/opacity and point size/line width. Layer deletion only changes the workspace. |
| Coordinate results | Explicitly select X/Y fields and source CRS to create a display-only point layer. Do not infer or persist geometry from names alone. |
| Persistence | Local saved queries, last 50 query-run metadata entries, and named workspaces. Save SQL, version bindings, geometry choices, styles and viewport, not credentials or result bytes in browser storage. Provide delete/clear actions. |

Defer multiple query tabs, visual query builders, charts/dashboards, collaborative editing, arbitrary database connections, geometry editing, geocoding, raster rendering, external WMS/WFS/URL layers, vector tiles, and publishing query results as accepted datasets. Saving SQL is separate from creating a reproducible transformation with validation and lineage.

## Execution and data contracts

### Query execution

The static UI calls the Moses service; DuckDB runs in a dedicated worker. Reuse the catalog's version-selection semantics, but do not expose `Catalog.query()` directly as an HTTP handler. Today it materializes every selected input and the entire output, and uses a prefix/semicolon check. It does not provide cancellation, resource isolation, result pagination, or geometry lineage.

Before execution, resolve dataset IDs to authorized immutable versions in one catalog snapshot. Create a run-local alias-to-version binding and return it with the result. Only selected datasets enter the worker. A dataset advancing to a new version during a query cannot change that run or an existing layer. The user can explicitly refresh bindings to latest and rerun. Support two versions of one dataset through distinct aliases.

Use parsed single-statement validation and a deliberately narrow query capability. Permit read-only relational queries against registered inputs; block mutation, file/URL readers, attachment, settings changes, arbitrary UDFs, and extension installation/loading. External access and automatic extension loading must be disabled, backed by a restricted worker with no credentials/network and access only to authorized inputs and bounded scratch space. A SQL prefix check or a result `LIMIT` alone does not bound a join, sort, or aggregate. DuckDB documents SQL's access to host resources and the need for application isolation in its [security overview](https://www.duckdb.org/docs/current/operations_manual/securing_duckdb/overview).

Begin with bounded input materialization in the worker. Estimate input size and reject workloads beyond the configured budget with a clear message; enforce a process memory ceiling even when the estimate is wrong. Direct scans of narrowly authorized snapshots are a later optimization, not a reason to enable arbitrary user file reads.

Execute once and retain a bounded Arrow/Parquet result under an opaque result ID. Assign internal row IDs per result, outside the user's SQL columns; use those IDs for stable pagination and table/map selection even when user keys are absent or duplicated. Page tokens address that materialization, never a rerun with `OFFSET`. Input-version pinning does not make nondeterministic SQL repeatable; record the SQL and engine version, and do not promise identical output after a rerun.

The typed response schema must specify JSON encodings for int64, decimal, timestamp/timezone, binary, and nested values; use strings where JSON numbers would lose precision. Include `returned_rows`, `truncated`, `stop_reason`, `elapsed_ms`, schema, version bindings, warnings, and result expiry. Do not display a total matching-row count unless actually computed.

### Map conversion and geometry lineage

Generate bounded GeoJSON previews on the server using the existing Shapely/PyProj stack. The map is a display projection of accepted data or a retained query result; it never changes source WKB or accepted CRS. Proposed renderer: MapLibre GL JS, whose [Map API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/) supplies source/layer management and camera fitting. Bundle UI assets locally and lazy-load the map module.

For a dataset layer, use the manifest's geometry column and CRS. For a query result, inherit CRS only when the backend can prove direct geometry-column lineage; a column called `geometry`, binary type, or matching values is insufficient. Joins, aliases, calculated geometries, and multiple geometry columns need validated lineage or an explicit geometry/CRS selection. Store that selection with the layer. Unknown CRS blocks map conversion but leaves the table usable. An assumed CRS from ingestion remains visibly labeled.

Convert previews to longitude/latitude EPSG:4326 with explicit XY axis order. Count null, empty, invalid, unsupported, and failed-to-transform geometries separately. Skip unrenderable features with visible counts and explanations; do not silently repair them. Preserve a result-row ID on each feature. Handle mixed geometry types with separate rendering layers under one logical UI layer; defer geometry collections with an explicit unsupported count in the first release. Discard Z only in the display copy and disclose that the map is 2D. Test Web Mercator latitude limits and antimeridian cases; a preview that cannot be rendered correctly must report a limitation rather than misleading bounds.

Existing query layers retain their original result ID when the editor runs again. Offer **Replace layer with this result** or **Add as new layer** so overlays do not change unexpectedly. Expired results leave a visible **Rerun required** state. Saving a query layer stores its SQL/version bindings and map settings, allowing explicit reconstruction after expiry.

Dataset-layer previews and query-result layers share the same feature/byte limits. Each layer shows **Preview**, emitted feature count, omitted/limited counts, source version(s), and CRS. The MVP displays a bounded subset rather than promising viewport-complete coverage. Panning does not rerun queries; users can refine SQL and rerun explicitly. Do not imply that an empty area contains no source features when the layer is capped.

External basemaps are optional, operator-configured, attributed, and clearly marked as requiring network access. The blank background works offline after installation. Selecting an online basemap sends map tile requests to its provider; do not send dataset properties or geometry to a third-party rendering service.

### Initial resource budgets

These are proposed defaults to validate in the first implementation spike, not measured capacity guarantees. The service may lower them and exposes effective limits to the UI.

| Resource | Starting budget / behavior |
| --- | --- |
| Query concurrency | One active query per local workspace; additional runs queue and remain cancellable. |
| Query execution | 30 seconds; 512 MiB worker memory; 256 MiB scratch. On memory/timeout failure return no apparently complete result. |
| Retained results | At most 10,000 rows and 20 MiB per result, whichever comes first; fetch at most 500 rows per page. Use bounded incremental serialization and one-row lookahead to determine row truncation. |
| Map preview | At most 5,000 features and 5 MiB GeoJSON per layer, 10 visible layers, and 20 MiB across visible previews. Reject or skip a single oversized feature with an explicit reason. Enforce transformation/coordinate budgets before serialization. |
| Retention | 30-minute idle expiry, bounded to 200 MiB total retained results per workspace. Return expiry/eviction states; do not delete accepted snapshots. Saved definitions survive result expiry. |
| Cancellation | Interrupt the worker, then terminate it if needed; target resource release within two seconds. Ignore late responses by run ID. |

An outer row cap limits returned data, not work. Timeout/memory/scratch enforcement applies during input loading, execution, and preview generation. Differentiate a successfully capped preview from execution failure. Do not expose an incomplete failed run as a successful result.

## Proposed API additions

These extend `/v1` and the same authentication, origin checks, ownership rules, and opaque resource IDs in the service roadmap. They are not implemented endpoints.

| Operation | Contract |
| --- | --- |
| `GET /v1/capabilities` | Query/map availability, effective budgets, supported geometry encodings, and optional spatial SQL capability. |
| `POST /v1/queries` | SQL plus explicit alias/dataset/version bindings; resolve `latest` once, validate access, and return `202` with query/job IDs. Support idempotent retries. |
| `GET /v1/queries/{query_id}` | Queued/running/succeeded/failed/cancelled status, resolved bindings, error details, and result ID on success. |
| `POST /v1/queries/{query_id}/cancel` | Idempotent cancellation; terminal jobs keep their terminal state. |
| `GET /v1/results/{result_id}/rows` | Typed schema and bounded rows using an opaque cursor. |
| `GET /v1/results/{result_id}/download` | Stream the retained result in an allowed format with completeness metadata. |
| `POST /v1/map-previews` | Accept either a dataset/version ID or a result ID, geometry/coordinate selection, and CRS if required; return `202` with a job ID. No arbitrary paths or URLs. |
| `GET /v1/map-previews/{preview_id}` | Bounded GeoJSON, row IDs, display bounds, source/CRS metadata, omissions and limit flags. |
| `GET/POST /v1/workspaces`, `GET/PATCH/DELETE /v1/workspaces/{workspace_id}` | Persist/load/delete workspace definitions; reject stale edits using a revision token. Named queries are entries in a workspace definition. |

Generic `GET /v1/jobs/{job_id}` reports map-preview completion with its preview ID. Query records reference the same durable job system rather than introducing a second scheduler. Every result, preview, saved definition, and download must be authorized independently, including after access changes. Expired derived resources return `410` to authorized callers with a rerun action. API responses expose no catalog paths.

## Delivery sequence and acceptance gates

| Slice | Work and dependency | Done when |
| --- | --- | --- |
| E0: prove contracts | Depends on the catalog; establish geometry metadata rules, restricted worker feasibility, typed result encoding, budgets, and renderer spike. | Synthetic fixtures exercise point/line/polygon data, projected CRS, a nonspatial join, unknown CRS, and oversize geometry; record memory/render measurements and finalize defaults. |
| E1: browse and map | Extends roadmap Phase 1; build the shared Explore shell, version browser, dataset preview API and basic layer controls. | A user loads two datasets, overlays them, changes visibility/order/style, inspects properties, and works offline with a blank background; projected data align without modifying snapshots. |
| E2: query and results | Follows roadmap Phase 2 service foundation; add isolated jobs, Run/Cancel, completion, starter SQL, retained results and typed grid. | Filter/join/group queries work; new imports cannot change an active run; cancellation and limits release resources; denied SQL cannot escape its inputs. |
| E3: query layers and persistence | Depends on E1/E2; map retained results, link row/feature selection, export previews, save query/workspace definitions. | A filtered result and a second dataset display together; reruns do not overwrite existing layers; reloading restores definitions with correct pinned versions and explicit rerun states. |
| E4: hosted readiness and scale | Hosted ownership builds on roadmap Phase 3; larger-data optimizations build on Phase 4. | Cross-owner query/result/preview/workspace access fails; representative large datasets meet measured budgets or fail clearly. Add viewport filtering/vector tiles only after profiling. |

E1–E3 define the first complete Explore release and are prioritized before remote MCP. They depend on the shared loader/service work and should not create a separate upload path or query server. Keep basic map preview shippable with E1 while execution isolation is developed for E2.

Optional spatial SQL is a follow-up after E3: explicitly provision a compatible DuckDB Spatial extension, expose supported functions through capability discovery, define WKB/native geometry conversion and output CRS contracts, and re-test the worker boundary. The [DuckDB Spatial overview](https://duckdb.org/docs/lts/core_extensions/spatial/overview) documents the extension; pin and validate the actual supported DuckDB version during implementation. Never have the editor install extensions automatically.

## Verification plan

- **End-to-end:** load synthetic borough polygons and facility points; open Explore; overlay layers; run an attribute filter and join; map the result; save/reopen; export a clearly bounded result. Assert source hashes and current-version pointers are unchanged.
- **Version integrity:** publish a new dataset version during a query, page through results, and rerender layers. All retain their original bindings. Refresh-to-latest requires an explicit rerun.
- **Geometry correctness:** fixtures in EPSG:4326 and EPSG:2263 align at known coordinates. Cover aliases, multiple geometry columns, absent CRS, null/empty/invalid WKB, mixed types, collections, 3D, oversized features and coordinate conversion failures.
- **Result semantics:** preserve large integer IDs, decimals, nulls and timestamps; keep duplicate user keys selectable via internal row IDs; distinguish zero rows, row/byte caps, expiry, SQL errors and resource failure.
- **Worker boundary:** attempt stacked statements, file/URL reads, extension loading, writes, unauthorized version bindings, large joins and pathological geometry. Confirm denied access and bounded cancellation; sanitized errors contain no paths or secrets.
- **UI behavior:** test keyboard flow and narrow screens; click rows/features across result pages; remove layers without deleting data; lose/recover connectivity; handle WebGL failure and unavailable basemaps. User-facing sample/omission badges remain visible.

Before calling the feature lightweight, measure bundled JavaScript and startup on the chosen development machine, keep map code lazy-loaded, and demonstrate a usable editor/table without loading the map. The initial renderer/editor choice is an implementation decision to confirm in E0; there is no need to embed DuckDB's own UI or run a second browser-side query engine.
