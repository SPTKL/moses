# Moses roadmap

GitHub is the delivery source of truth. The architecture remains in [service-architecture.md](service-architecture.md).

[Project and delivery board](https://github.com/users/SPTKL/projects/1) · [Pinned roadmap tracker](https://github.com/SPTKL/moses/issues/1)

## Delivery checkpoint — 2026-10-28

The simplified full-release PLUTO example is pushed on `main` at `7c5fb46`.
[PR #24](https://github.com/SPTKL/moses/pull/24) merged the local API,
recipes, catalog UI, bounded map and standalone PLUTO project;
[PR #32](https://github.com/SPTKL/moses/pull/32) merged the first DuckDB
Spatial installation/lifecycle slice. Both are merged implementation, not a
packaged release or acceptance of every parent issue. No GitHub release exists.

The latest [CI run 40795454217](https://github.com/SPTKL/moses/actions/runs/40795454217)
completed with failure: its three Windows Python 3.11–3.13 full-suite jobs
failed, while six Linux/macOS full-suite jobs, all three base jobs, and the
PLUTO job passed. The previous [main run 40793101152](https://github.com/SPTKL/moses/actions/runs/40793101152)
failed the same Windows jobs. [#25](https://github.com/SPTKL/moses/issues/25)
remains a P0 release-readiness gate until a complete main matrix passes.

The immediate PLUTO adoption outcome is a **full 26v2 release workflow**:
Moses captures and ingests all required pinned inputs, publishes locked and
normalized preparation, dbt builds the PLUTO business models, then an optional
export writes deliverables. The [example Makefile](../examples/pluto/Makefile)
exposes these independent phases. [#17](https://github.com/SPTKL/moses/issues/17)
retains its bounded case-study evidence and review scope. The separate
[#34](https://github.com/SPTKL/moses/issues/34) is P1 Now: run the actual full-release targets with
required pinned inputs and native runtime, verify recovery and provenance,
and record output and limitations across the 49 sources/seeds, 42 prepared
tables, 38 models and 13 exported data files. The earlier citywide candidate
is historical evidence; it does not prove this operator path has run or reached
production parity.

[#33](https://github.com/SPTKL/moses/issues/33) is a separate P1 Now feasibility and compatibility gate for a
DuckLake local default with a DuckDB metadata catalog. Current examples still
use DuckDB files. [#26](https://github.com/SPTKL/moses/issues/26) is P1 Next
for generic installed-project onboarding. Durable jobs [#6](https://github.com/SPTKL/moses/issues/6)
and guided loading [#7](https://github.com/SPTKL/moses/issues/7) follow; PLUTO
source contracts [#18](https://github.com/SPTKL/moses/issues/18)/[#20](https://github.com/SPTKL/moses/issues/20),
parity [#19](https://github.com/SPTKL/moses/issues/19) and remaining Spatial
work in reopened [#28](https://github.com/SPTKL/moses/issues/28) retain their acceptance
gates. Hosted access and MCP remain later, after usable local workflows and
their security requirements. Release dates and human assignees remain unset.

GitHub issues and the project board carry live status; this is a dated
checkpoint. Merged code, local validation and historical evidence are distinct
from reviewed acceptance and release.

## [M1 — Local guided loading](https://github.com/SPTKL/moses/milestone/1)

| Issue | Priority | Delivery checkpoint |
| --- | --- | --- |
| [#2 — Finish and release the local tabular inspection foundation](https://github.com/SPTKL/moses/issues/2) | P0 | In progress |
| [#3 — Add a versioned local service API with safe resource identifiers](https://github.com/SPTKL/moses/issues/3) | P0 | Read-only slice merged in PR #24; write execution awaits #6 |
| [#4 — Add explicit schema recipes, safe format detection, and CRS review](https://github.com/SPTKL/moses/issues/4) | P0 | Recipes, grouped defaults, column naming and FileGDB merged in PR #24; acceptance/release pending |
| [#5 — Build catalog browsing, history, preview, and diff screens](https://github.com/SPTKL/moses/issues/5) | P1 | Catalog GUI merged in PR #24; acceptance/release pending |
| [#6 — Make upload and ingestion jobs durable and commits short](https://github.com/SPTKL/moses/issues/6) | P0 | Todo |
| [#7 — Implement guided immutable upload, review, validation, and commit](https://github.com/SPTKL/moses/issues/7) | P0 | Todo |

## [M2 — Deployable service and thin client](https://github.com/SPTKL/moses/milestone/2)

| Issue | Priority | Delivery checkpoint |
| --- | --- | --- |
| [#8 — Publish a thin HTTP client without geospatial native dependencies](https://github.com/SPTKL/moses/issues/8) | P1 | Todo |
| [#9 — Enforce authentication and parser resource boundaries before remote exposure](https://github.com/SPTKL/moses/issues/9) | P0 | Todo |
| [#10 — Package a single-instance non-root service with persistent local storage](https://github.com/SPTKL/moses/issues/10) | P1 | Todo |

## [M3 — Authenticated remote access and MCP](https://github.com/SPTKL/moses/milestone/3)

| Issue | Priority | Delivery checkpoint |
| --- | --- | --- |
| [#11 — Add per-user OIDC identity and owner-scoped resources](https://github.com/SPTKL/moses/issues/11) | P0 | Todo |
| [#12 — Add a root-constrained local MCP upload bridge](https://github.com/SPTKL/moses/issues/12) | P1 | Todo |
| [#13 — Expose authenticated remote MCP over Streamable HTTP](https://github.com/SPTKL/moses/issues/13) | P1 | Todo |

## [M4 — Scale, recovery, and reproducible transforms](https://github.com/SPTKL/moses/milestone/4)

| Issue | Priority | Delivery checkpoint |
| --- | --- | --- |
| [#14 — Bound memory for parsing, hashing, and version diffs](https://github.com/SPTKL/moses/issues/14) | P1 | Todo |
| [#15 — Define recoverable backups, retention, and audit operations](https://github.com/SPTKL/moses/issues/15) | P1 | Todo |
| [#16 — Run approved transformations from locked inputs with lineage](https://github.com/SPTKL/moses/issues/16) | P1 | Todo: generic isolated runner; standalone PLUTO evidence does not complete this scope |

## Explore and foundation fixes

| Issue | Priority | Status |
| --- | --- | --- |
| [#21 — Version-pinned Explore query/map workflow](https://github.com/SPTKL/moses/issues/21) | P1 | In progress: #23 slice merged in PR #24; remaining Explore planned |
| [#23 — Bounded exact-version catalog map](https://github.com/SPTKL/moses/issues/23) | P1 | Merged in PR #24; issue acceptance pending |
| [#22 — Avoid redundant Parquet versions from no-op inference](https://github.com/SPTKL/moses/issues/22) | P1 | Fix merged in PR #24; issue acceptance pending |

Explore's local analyst flow precedes remote MCP as specified in its design.

Each issue includes scope, acceptance criteria, validation, and prerequisite links. GitHub issues and project fields carry ongoing status; this file is the roadmap index.

PLUTO adoption work (#17–#20) uses the [standalone example](../examples/pluto/README.md)
and its [delivery plan](../examples/pluto/docs/pluto-delivery-plan.md). The
example retains its recipes, preparation code, dbt models, tests and optional
export separately from the default Moses installation. The Makefile simplifies
its full-release operator path; it does not establish production parity or
satisfy #16's service/resource-isolation requirements.

## Ingestion direction and Socrata migration

Optional [snake_case column naming](source-recipes.md#column-naming) extends the
#4 schema-recipe foundation locally: CLI inspection/loading and YAML recipes
normalize names explicitly, retain mappings, and reject collisions. Existing
names remain the built-in default. User-wide and nearest-project TOML naming
defaults, explicit overrides and `moses config show` are implemented locally.
Configuration is grouped into project storage, normalization, spatial defaults
and export format, with each value inheriting independently across scopes.
Current implementation evidence is recorded in #2/#4; both remain open pending acceptance.

The intended entry point is [installing Moses in any repository](source-recipes.md#install-and-use-moses-in-any-repository):
`uv add moses`, project initialization, and user-owned recipe paths. Project
initialization, recipe discovery and a published package are delivery gaps;
the current local package is provisionally named `moses-geo`. Package/project
onboarding belongs with the local foundation and recipes (#2/#4), independently
of the optional thin remote client (#8) or a hosted catalog. Acceptance requires
an installed-wheel exercise in an unrelated repository. Existing external-path
recipe execution is implemented; the proposed initialization options are not.

Project defaults live in [`config.toml`](source-recipes.md#project-configuration-and-output-defaults)
under `moses.project`, `moses.normalization`, `moses.spatial` and `moses.export`.
Warehouse location, field naming, source CRS fallback and the existing export
formats are implemented. The former `moses.input.column_names` remains an alias;
legacy JSON CRS defaults remain a lower-priority fallback. Output reprojection,
compression, additional writers, recipe discovery and persistent DuckDB storage
remain planned. Source CRS defaults only describe otherwise unknown coordinates.

[DuckDB Spatial](source-recipes.md#duckdb-spatial-as-the-geospatial-engine) is the
target vector calculation engine. The first local migration slice moves
Shapely, PyProj and Pyogrio into an optional `spatial` extra and adds explicit
extension provisioning/status and a shared loading lifecycle. Base tabular work
does not require that extra. Current spatial operations still use the Python
adapters. Calculation CRS/units, operation migration, reader/writer and
geometry-policy parity, and capacity/performance validation remain required
before removing the adapters entirely. This first slice merged in PR #32 but is unreleased.

The [conversion and type-preservation contract](source-recipes.md#format-conversion-and-source-type-preservation)
requires metadata-based CRS discovery, preserved source schema, conservative
GeoJSON string handling, exactness checks and explicit policies for lossy output
formats. Bounded conversion/CRS/type probes passed locally; full reader/writer
parity remains part of migration acceptance.

[File Geodatabase support](source-recipes.md#file-geodatabases) is implemented
locally for directory/ZIP ingestion, explicit layer selection, typed Arrow
snapshots, complete raw capture and exact-version single-layer export. The
existing GDAL adapter supplies layer and CRS metadata; this is independent of
the Spatial migration. Synthetic regression coverage includes malformed ZIPs,
source preservation and export fidelity checks. Full ArcGIS semantics, ZIP
export, multi-layer delivery, raster data, `.mdb` and `.sde` remain outside this
slice. This work merged in PR #24 but is unreleased.

The [community registry design](source-recipes.md#community-recipe-registry)
adds a proposed `moses[registry]` extra for a separately versioned curated recipe
pack, plus independently installed organization packs. Implement installed-pack
discovery, qualified recipe names, copy/customization and recipe locks after
project initialization. Registry recipes use the existing validation and
acceptance contracts. No extra, registry command or recipe pack is published or
implemented by this design update; hosted registry search is a later option.

The [source recipe design](source-recipes.md#design-references-from-nycdb-and-nyc-planning)
now references NYCDB dataset contracts and Planning ingest templates alongside
dlt. Its [direct Socrata connector contract](source-recipes.md#direct-socrata-connector-design)
and [platform migration stages](source-recipes.md#path-toward-replacing-socrata)
are proposed scope, not implemented capabilities or completed milestones.

The next connector slice is full capture plus metadata, validation, immutable
acceptance and offline replay. Reuse #4's recipe foundation; durable scheduled
refresh depends on #6, remote acquisition on #9, and full-scale acceptance on
#14. Preserve #18/#20 release and source contracts: a current Socrata dataset
must not replace a pinned PLUTO input silently. Incremental refresh follows a
transactional state and deletion contract. Independent publishing and eventual
Socrata replacement are a subsequent product track, including catalog/search,
public APIs, publisher workflows and consumer migration.

## Additional delivery tickets

| Issue | Priority | Sequence / acceptance boundary |
| --- | --- | --- |
| [#25 — Windows CI repair](https://github.com/SPTKL/moses/issues/25) | P0 | Now; fix three failing Windows Python jobs and pass the complete main matrix |
| [#34 — Full-release operator trial](https://github.com/SPTKL/moses/issues/34) | P1 | Now; run the 49→42→38→13 workflow with pinned inputs, native runtime, recovery and provenance evidence |
| [#33 — DuckLake local default](https://github.com/SPTKL/moses/issues/33) | P1 | Now; feasibility and compatibility gate for the DuckDB metadata catalog and existing PLUTO files |
| [#26 — Installed-project initialization and recipe discovery](https://github.com/SPTKL/moses/issues/26) | P1 | Next; M1; non-destructive init and unrelated-repository wheel exercise |
| [#27 — Socrata capture, metadata and offline replay](https://github.com/SPTKL/moses/issues/27) | P1 | Next acquisition slice after #4/#26; separate from #6/#7 |
| [#28 — Shared DuckDB Spatial engine](https://github.com/SPTKL/moses/issues/28) | P1 | Reopened after PR #32's installation/lifecycle slice; operation migration, CRS/units, differential parity and capacity gates remain |
| [#29 — Export reprojection, compression and writers](https://github.com/SPTKL/moses/issues/29) | P2 | Later; choose a bounded writer slice and explicit loss policy |
| [#30 — Installed recipe packs and locks](https://github.com/SPTKL/moses/issues/30) | P2 | Later; depends on #26; no published registry is claimed |
| [#31 — Publishing and consumer migration discovery](https://github.com/SPTKL/moses/issues/31) | P2 | Later discovery; distinct from connector delivery and no platform cutover promise |

#27/#29/#30/#31 have no committed release milestone. Existing detailed acceptance
and dependency contracts remain in force. DuckLake as the local default is proposed in [#33](https://github.com/SPTKL/moses/issues/33), with a DuckDB
metadata catalog and explicit migration/compatibility acceptance. It is not
implemented by the current DuckDB-file example.

The [source recipe design](source-recipes.md) separates Moses acquisition and
homogenization from the [standalone PLUTO project](../examples/pluto/README.md).
dlt supplies an optional REST extraction adapter; Moses retains immutable input
acceptance and geospatial policies. The full-release Makefile is merged; the actual operator run belongs to [#34](https://github.com/SPTKL/moses/issues/34), while #17 retains its bounded case-study scope.
