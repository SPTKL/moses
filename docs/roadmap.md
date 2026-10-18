# Moses roadmap

GitHub is the delivery source of truth. The architecture remains in [service-architecture.md](service-architecture.md).

[Project and delivery board](https://github.com/users/SPTKL/projects/1) · [Pinned roadmap tracker](https://github.com/SPTKL/moses/issues/1)

Release dates and GitHub assignees remain unset. The tabular foundation, bounded PLUTO case study, no-op inference fix and explicit primitive import recipes are implemented locally and await review/merge. The authenticated read-only API slice is also implemented locally; the read-only catalog GUI is implemented locally, while durable uploads/jobs, guided loading and remaining capabilities are planned. The [local service contract](local-service.md) identifies the implemented routes and reserved write contracts. These are working-tree updates, not merged or released milestones. The [PLUTO delivery plan](pluto-delivery-plan.md) records the evidence, PM assessment and next dependency waves.

## [M1 — Local guided loading](https://github.com/SPTKL/moses/milestone/1)

| Issue | Priority | Local implementation status |
| --- | --- | --- |
| [#2 — Finish and release the local tabular inspection foundation](https://github.com/SPTKL/moses/issues/2) | P0 | In progress |
| [#3 — Add a versioned local service API with safe resource identifiers](https://github.com/SPTKL/moses/issues/3) | P0 | Read-only slice implemented locally; write execution awaits #6 |
| [#4 — Add explicit schema recipes, safe format detection, and CRS review](https://github.com/SPTKL/moses/issues/4) | P0 | Primitive recipes/signatures implemented locally; awaiting review/merge |
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
| [#16 — Run approved transformations from locked inputs with lineage](https://github.com/SPTKL/moses/issues/16) | P1 | Full local dbt candidate runner implemented with locked inputs, resumable models and code snapshots; service/resource isolation remains |

## PLUTO adoption and Explore

| Issue | Priority | Status |
| --- | --- | --- |
| [#17 — PLUTO case study and adoption readiness](https://github.com/SPTKL/moses/issues/17) | P0 | Implemented locally; awaiting review |
| [#18 — Resolve PLUTO source releases into an input manifest](https://github.com/SPTKL/moses/issues/18) | P0 | Published 26v2 manifest resolved; 38 full source captures + 11 seeds obtained; raw reconstruction/lineage pending |
| [#20 — PLUTO source contracts](https://github.com/SPTKL/moses/issues/20) | P0 | PTS/land-use stage contracts implemented; spatial/other source contracts remain |
| [#19 — Reference-build parity and staged transforms](https://github.com/SPTKL/moses/issues/19) | P1 | Consolidated 405 models into 38 business processes; citywide candidate produces 858,284 parcels; full-build guide records comparison evidence and source ambiguity policies; historical input/native and spatial parity remain unattested |
| [#21 — Version-pinned Explore query/map workflow](https://github.com/SPTKL/moses/issues/21) | P1 | Single-version map child #23 implemented locally; remaining Explore work planned |
| [#23 — Bounded exact-version catalog map](https://github.com/SPTKL/moses/issues/23) | P1 | Implemented locally; awaiting review/merge |
| [#22 — Avoid redundant Parquet versions from no-op inference](https://github.com/SPTKL/moses/issues/22) | P1 | Fixed locally; awaiting review |

The PLUTO evidence raises #4 to P0 and #16 to P1. The complete local candidate now supplies citywide scale evidence; source-contract fidelity, remaining ambiguous source choices and service/isolation prerequisites still need resolution. Explore's local analyst flow precedes remote MCP as specified in its design.

Each issue includes scope, acceptance criteria, validation, and prerequisite links. GitHub issues and project fields carry ongoing status; this file is the roadmap index.

The [full PLUTO candidate build](pluto-full-build.md) is the active PLUTO path. Trusted
local fixed-model execution can proceed independently of remote jobs, but does
not satisfy #16's service or resource-isolation acceptance criteria. All local
work remains unmerged and unreleased; completed candidate execution does not
establish official-release or historical production parity.
