# PLUTO-led delivery plan

As of 2026-10-18. [Roadmap](https://github.com/SPTKL/moses/issues/1) ·
[Project board](https://github.com/users/SPTKL/projects/1) ·
[Case-study tracker #17](https://github.com/SPTKL/moses/issues/17).

## Product decision

**Current direction (2026-10-18):** the user selected PLUTO **26v2** and a
**dbt rewrite without UPDATE statements**, then requested consolidation around
business processes, with readability taking priority over execution speed.
The [full candidate guide](pluto-full-build.md) supersedes the earlier two-stage
sequencing for the trusted local transform path. The transformation now has
**38 SELECT models**, reduced from 405: 21 source-to-map processes, five correction
models, six delivery models and six QA reports. Shared macros define source
cleanup, corrections and repeated QA calculations once; ordered local CTEs retain
business-rule dependencies. The full guide records citywide results and exact
comparison evidence, including source ambiguities and candidate-specific policy.

A source planner covers 38 inputs and 11 seeds. Six normalized artifacts and
32 provisionally matched raw captures are local. Native source preparation
completed with 1,163,616 geocode rows and 817,321 building-count rows using the
explicitly selected 26B bundle. Historical normalized-input, native-runtime and
spatial reference parity remain outstanding. Remote service/isolation
prerequisites remain in force for remotely exposed execution. This is local work,
not a merged or released PLUTO replacement.

Use a PLUTO analyst's source-to-reproducible-output task to guide the next Moses
releases. The current CLI is usable for bounded developer-led imports and exact
input snapshots. It is not yet a self-service analyst application or a replacement
for the PLUTO build. The full reference pipeline needs 38 recipe inputs, 11 local
seeds, PostgreSQL/PostGIS, dbt, shell stages, geocoding and correction logic.

The first useful outcome is a reviewed source manifest plus one validated,
reproducible PLUTO transformation. Develop the shared service and guided review
flow alongside this work. Hosted access and MCP remain downstream of working
local workflows and their security requirements.

## Parallel work executed in this session

| Session role | Owned work | Result |
| --- | --- | --- |
| Source/build inventory agent | `docs/pluto-source-inventory.md`, `examples/pluto/inventory.json` | All 38 inputs and 11 seeds mapped; major/minor policies, raw versus normalized inputs, build dependencies and blockers documented. Cross-reviewed integration source choices. |
| Integration agent | `examples/pluto/` except inventory, integration test, results report | Repeatable bounded real-source capture, inspection, ingestion, repeat observation, query, lock/replay and export checks. |
| Foundation reviewer | Foundation review, narrowly scoped catalog fix and regression tests | Baseline suite/build/upgrade checks passed; fixed inapplicable Parquet inference causing redundant versions (#22). |
| Coordinator | Tickets, project fields, roadmap, working agreement and final integration review | Reprioritized dependencies, added evidence-backed work and checked that sample success is not reported as build parity. |

These are actual delegated session tasks. They are not human assignees or ongoing
background workers. No completion status implies review, merge or release.

## Evidence and immediate findings

Read the [source inventory](pluto-source-inventory.md),
[integration results](pluto-integration-results.md), and
[foundation review](pluto-foundation-review.md) for reproducible details.

- 100 PLUTO rows through an alternate live public CSV representation, 100 LPC
  GeoJSON features from its declared recipe endpoint, 100 GreenThumb CSV rows
  through an alternate representation, and all 221 land-use seed rows passed the
  case-study checks. The public PLUTO sample reports publisher version 26v2.
- All 100 sampled PLUTO building classes matched the land-use seed. This is a
  bounded compatibility check; it is not transformation/output parity.
- LPC's 100 features contain 99 distinct BBLs, consistent with its declared
  multiple-designations-per-lot grain. Do not assign a universal BBL key.
- Major builds select latest available inputs, while minor builds inherit the
  prior release with explicit updates. `VERSION_PREV`/`previous_pluto` needs
  explicit resolution before capture. A catalog lock alone does not do this.
- CAMA availability and ignored upstream errors need an explicit missing-input
  policy. The geocode template's apparent axis reversal needs a known-coordinate
  check before reuse. These are documented source risks, not claims of a corrupt
  published PLUTO release.
- Native Parquet ignored `infer_types` during reading but included it in the
  version hash. The local #22 fix normalizes that effective option. Older versions
  remain readable; a previously flagged version can produce one normalized
  release on its next import.

## Backlog sequencing and parallel capacity

### Local implementation update — 2026-10-17

The next dependency wave now has an authenticated read-only loopback service
(#3 slice) and explicit primitive import recipes with conservative signature
checks (#4). [Local service usage and limits](local-service.md) describes opaque
IDs, exact-version retrieval and reserved write routes. Durable ingestion,
upload sealing and short catalog commits remain #6; a `501` write response must
not be presented as a completed guided loader.

Work followed the repository's saved model policy: one Astra supervisor
reviewed the contracts and acceptance findings, with two Sol workers owning
separate service and recipe files. The coordinator integrated CLI/documentation
changes. No GitHub issues were closed, and nothing was merged or released.

From the product perspective, developers can retrieve accepted catalog versions
without exposing host paths and select explicit primitive types before local
ingestion. Full-row failures identify the field and row, and non-string blank
conversion is recorded in the recipe. Analysts still need a CLI; this is not a
first-time-user UI study or evidence of full PLUTO source compatibility. The
next gates remain durable jobs, source resolution (#18), and source-specific
contracts (#20), followed by the guided screens.

Validation for this wave: the final integrated suite passed 87 tests with one
optional DuckLake integration skipped; `python -m build --no-isolation` built
the wheel and source archive; `git diff --check` passed. A built-wheel smoke
test outside the repository checked imports, the serve CLI contract, explicit
CSV type choices, leading-zero preservation and unchanged reimport behavior.
Astra reviewed the final fixes and accepted this scope. The new regression
fixtures are synthetic; these checks do not establish production PLUTO parity
or remote parser isolation.

Reviewed all original issues #1–#16, their dependencies and the existing Explore
design. Keep implementation prerequisites; early design/measurement does not
mean dependent functionality has shipped.

| Wave | Parallel lane A | Parallel lane B | Parallel lane C | Exit gate |
| --- | --- | --- | --- | --- |
| Current | #17 inventory | #17 real-source runner | #2 review and #22 regression fix | Local artifacts and evidence reviewed; ready for a reviewed PR. |
| Next | #3 versioned local API after #2 | #4 recipes, then #18 source resolution and #20 domain contracts | #21 E0 feasibility and #14 baseline profiling | Stable API/import contracts; actionable source plan; measured limits. |
| Guided local use | #6 durable uploads/jobs after #3/#4 | #5 catalog UI after #3, then #7 loader after its prerequisites | #8 thin client and #9 isolation after #3/#6 | Operator can inspect, accept, recover and retrieve exact versions. |
| Reproducible PLUTO slice | #16 approved transforms after #4/#6/#9; #19 parity after #18/#16 | #21 E1–E3 Explore using shared service/jobs | #14 bounded memory; #10 deployment after #6/#8/#9 | One reference-matched transform with complete lineage; usable local analyst flow. |
| Operations/remote | #15 backup/retention after #6/#10 | #11 identity after #9; #12 bridge after #8/#9 | #13 remote MCP after #11/#12 | Recovery and access controls verified; local workflow already usable. |

#1 remains the overall tracker. #4 is promoted P1 → P0 because imports need
explicit recipes before PLUTO source contracts can be trusted. #16 is promoted
P2 → P1 to deliver a small lineage-backed transform earlier; this does not remove
its isolation prerequisites. #14 stays P1, with baseline measurement pulled
forward and streaming implementation still dependent on the job architecture.

## New tickets

| Issue | Priority | Deliverable |
| --- | --- | --- |
| [#17](https://github.com/SPTKL/moses/issues/17) | P0 | Real-input case study and adoption evidence, implemented locally pending review. |
| [#18](https://github.com/SPTKL/moses/issues/18) | P0 | Resolve major/minor release inputs into a reproducible manifest; plan access before running. |
| [#20](https://github.com/SPTKL/moses/issues/20) | P0 | Source-specific identifiers, missingness, CRS and axis-order contracts. |
| [#19](https://github.com/SPTKL/moses/issues/19) | P1 | Reference-build comparison harness and staged migration. |
| [#21](https://github.com/SPTKL/moses/issues/21) | P1 | Previously designed Explore workflow, now tracked with delivery slices. |
| [#22](https://github.com/SPTKL/moses/issues/22) | P1 | Redundant native-format versions from no-op inference; fixed locally pending review. |

## PM review rubric

Every meaningful implementation review must answer these questions with evidence:

1. Can the operator identify the upstream release and whether the input is a
   complete source, sample, alternate representation or synthetic fixture?
2. Can they understand and correct key, type, blank/null, geometry and CRS choices
   before acceptance, with failures identifying the field and next action?
3. Can they trust that a failed import leaves their accepted version intact and
   that repeated unchanged data does not create misleading release history?
4. Can they explain a changed result using exact inputs, recipe/code and engine
   versions, rather than a mutable latest pointer?
5. Does the workflow remain usable within measured data limits, including clear
   progress, failure, retry and sample/omission indicators?

The current evidence is CLI/API verification and source review. No browser UI or
first-time-user usability study was conducted. #5/#7/#21 must validate those
experiences when implemented. Create focused tickets for observed gaps, extend
existing tickets when appropriate, and state suspected findings as hypotheses.

## Full PLUTO replication gate

Select one approved reference release and obtain its complete pinned inputs.
Validate source contracts, then port and compare stages incrementally: deterministic
attribute mappings, joins/enrichments, geometry assembly, corrections, geocoding,
QA and final exports. Compare keyed attributes and schema with explicit null and
numeric rules; compare geometry using agreed CRS/tolerances separately from WKB
byte equality. Measure full-source memory and runtime before claiming citywide
support. Required unavailable inputs or unexplained mismatches block parity.

This session starts that path and supplies the evidence harness. It does not
reproduce or replace a production PLUTO build.
