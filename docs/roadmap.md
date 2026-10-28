# Moses roadmap

GitHub is the delivery source of truth. The architecture remains in [service-architecture.md](service-architecture.md).

[Project and delivery board](https://github.com/users/SPTKL/projects/1) · [Pinned roadmap tracker](https://github.com/SPTKL/moses/issues/1)

Release dates and GitHub assignees remain unset. The tabular foundation, no-op inference fix and explicit primitive import recipes are implemented locally and await review/merge. The authenticated read-only API slice is also implemented locally; the read-only catalog GUI is implemented locally, while durable uploads/jobs, guided loading and remaining capabilities are planned. The [local service contract](local-service.md) identifies the implemented routes and reserved write contracts. These are working-tree updates, not merged or released milestones.

## [M1 — Local guided loading](https://github.com/SPTKL/moses/milestone/1)

| Issue | Priority | Local implementation status |
| --- | --- | --- |
| [#2 — Finish and release the local tabular inspection foundation](https://github.com/SPTKL/moses/issues/2) | P0 | In progress |
| [#3 — Add a versioned local service API with safe resource identifiers](https://github.com/SPTKL/moses/issues/3) | P0 | Read-only slice implemented locally; write execution awaits #6 |
| [#4 — Add explicit schema recipes, safe format detection, and CRS review](https://github.com/SPTKL/moses/issues/4) | P0 | YAML source recipes, optional dlt REST and trusted Python implemented and reviewed on branch; awaiting merge |
| [#5 — Build catalog browsing, history, preview, and diff screens](https://github.com/SPTKL/moses/issues/5) | P1 | Catalog GUI implemented and validated locally; awaiting merge |
| [#6 — Make upload and ingestion jobs durable and commits short](https://github.com/SPTKL/moses/issues/6) | P0 | Todo |
| [#7 — Implement guided immutable upload, review, validation, and commit](https://github.com/SPTKL/moses/issues/7) | P0 | Todo |

## [M2 — Deployable service and thin client](https://github.com/SPTKL/moses/milestone/2)

| Issue | Priority | Initial status |
| --- | --- | --- |
| [#8 — Publish a thin HTTP client without geospatial native dependencies](https://github.com/SPTKL/moses/issues/8) | P1 | Todo |
| [#9 — Enforce authentication and parser resource boundaries before remote exposure](https://github.com/SPTKL/moses/issues/9) | P0 | Todo |
| [#10 — Package a single-instance non-root service with persistent local storage](https://github.com/SPTKL/moses/issues/10) | P1 | Todo |

## [M3 — Authenticated remote access and MCP](https://github.com/SPTKL/moses/milestone/3)

| Issue | Priority | Initial status |
| --- | --- | --- |
| [#11 — Add per-user OIDC identity and owner-scoped resources](https://github.com/SPTKL/moses/issues/11) | P0 | Todo |
| [#12 — Add a root-constrained local MCP upload bridge](https://github.com/SPTKL/moses/issues/12) | P1 | Todo |
| [#13 — Expose authenticated remote MCP over Streamable HTTP](https://github.com/SPTKL/moses/issues/13) | P1 | Todo |

## [M4 — Scale, recovery, and reproducible transforms](https://github.com/SPTKL/moses/milestone/4)

| Issue | Priority | Initial status |
| --- | --- | --- |
| [#14 — Bound memory for parsing, hashing, and version diffs](https://github.com/SPTKL/moses/issues/14) | P1 | Todo |
| [#15 — Define recoverable backups, retention, and audit operations](https://github.com/SPTKL/moses/issues/15) | P1 | Todo |
| [#16 — Run approved transformations from locked inputs with lineage](https://github.com/SPTKL/moses/issues/16) | P1 | Product-specific runner extracted to a consumer example; generic service/resource isolation remains planned |

## Explore and foundation fixes

| Issue | Priority | Status |
| --- | --- | --- |
| [#21 — Version-pinned Explore query/map workflow](https://github.com/SPTKL/moses/issues/21) | P1 | Single-version map child #23 implemented locally; remaining Explore work planned |
| [#23 — Bounded exact-version catalog map](https://github.com/SPTKL/moses/issues/23) | P1 | Implemented locally; awaiting review/merge |
| [#22 — Avoid redundant Parquet versions from no-op inference](https://github.com/SPTKL/moses/issues/22) | P1 | Fixed locally; awaiting review |

Explore's local analyst flow precedes remote MCP as specified in its design.

Each issue includes scope, acceptance criteria, validation, and prerequisite links. GitHub issues and project fields carry ongoing status; this file is the roadmap index.

PLUTO adoption work (#17–#20) now belongs to the
[standalone example project](../examples/pluto/README.md), including its
[delivery plan](../examples/pluto/docs/pluto-delivery-plan.md) and full-build
evidence. Its recipe, release-specific preparation, transformations, tests and
dependencies are outside the Moses distribution. This local extraction does not
close or transfer GitHub issues, establish production parity, or satisfy #16's
service/resource-isolation requirements.

## Ingestion direction and Socrata migration

Optional [snake_case column naming](source-recipes.md#column-naming) extends the
#4 schema-recipe foundation locally: CLI inspection/loading and YAML recipes
normalize names explicitly, retain mappings, and reject collisions. Existing
names remain the built-in default. User-wide and nearest-project TOML naming
defaults, explicit overrides and `moses config show` are implemented locally.
Configuration is grouped into project storage, normalization, spatial defaults
and export format, with each value inheriting independently across scopes.
This local implementation does not
close or update the GitHub issue.

The primary entry point is [installing Moses in any repository](source-recipes.md#install-and-use-moses-in-any-repository):
`pip install moses`, project initialization, and user-owned recipe paths. Project
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
target vector calculation engine. Add explicit extension provisioning/loading,
calculation CRS and units, and a shared execution layer before migrating current
Python geometry operations. Verify reader/writer and geometry-policy parity
before removing Shapely, PyProj or Pyogrio. Basic local Spatial capability was
checked; the backend migration and capacity/performance validation remain planned.

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
slice. This work is unmerged and unreleased.

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

The existing open issues were reviewed on 2026-10-28; none specifically tracks
the Socrata connector or replacement program. These additions remain local
design scope pending dedicated delivery tickets and project prioritization;
no GitHub issue or project status changed with this documentation update.

The [source recipe design](source-recipes.md) separates Moses acquisition and
homogenization from the [standalone PLUTO project](../examples/pluto/README.md).
dlt supplies an optional REST extraction adapter; Moses retains immutable input
acceptance and geospatial policies. No issue is closed by this local refactor.
