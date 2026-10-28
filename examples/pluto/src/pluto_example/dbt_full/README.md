# PLUTO business process models

Complete SELECT-only transformation at pinned upstream `32bc98f632f15e7182933a17fb61ecf74e853518`. The candidate variable defaults to `26v2m4`.

The project has 38 process models. Source normalization is defined once in [pluto_inputs.sql](macros/pluto_inputs.sql); each process calls that shared policy through named local CTEs. There are no separate input or staging models.

```mermaid
flowchart LR
  inputs[Locked inputs] --> tax[Tax records and allocation]
  tax --> attributes[CAMA and property attributes]
  attributes --> geometry[Parcel geometry]
  geometry --> zoning[Zoning and enrichment]
  zoning --> geography[Political and service geography]
  geography --> mapping[Map flags and shoreline]
  mapping --> decisions[Correction decision ledger]
  decisions --> pluto[Corrected lots and audit outputs]
  pluto --> exports[Tabular and four mapped schemas]
  exports --> qa[Six QA families]
```

| Process | Business rule |
| --- | --- |
| [geocode_attributes](models/tax_records/geocode_attributes.sql) | Clean native geography fields and coordinates. |
| [pts_property_records](models/tax_records/pts_property_records.sql) | Prepare PTS property records and prime billing BBLs. |
| [tax_lot_attributes](models/tax_records/tax_lot_attributes.sql) | Join PTS/geocodes; repair vacancy, lot area and apportionment dates. |
| [allocated_lots](models/allocation/allocated_lots.sql) | Aggregate billing/condominium lots and construction years. |
| [parcel_base](models/attributes/parcel_base.sql) | Create parcel rows, allocate attributes, attach geography and initial land use. |
| [parcel_cama](models/cama/parcel_cama.sql) | Apply CAMA basement, lot type, proximity, area and easement rules. |
| [property_attributes](models/attributes/property_attributes.sql) | Attach environmental designation, owner type and addresses. |
| [tax_lot_geometry](models/geometry/tax_lot_geometry.sql) | Deduplicate condo mappings and union regular/condo tax-lot polygons. |
| [parcel_geometry](models/geometry/parcel_geometry.sql) | Attach geometry and append DTM-only lots with stable serial ids. |
| [zoning](models/zoning/zoning.sql) | Measure district coverage, rank/tie-break assignments, overlays and special districts. |
| [mih](models/enrichment/mih.sql) | Assign mandatory inclusionary housing options by lot overlap. |
| [transit](models/enrichment/transit.sql) | Rank block/lot transit zones and restrict assignments to coverage. |
| [parcel_enriched](models/enrichment/parcel_enriched.sql) | Join FAR, landmark, numeric, coordinate, MIH and transit attributes. |
| [parcel_classification](models/attributes/parcel_classification.sql) | Refine building class/land use and fill missing coordinates. |
| [flood](models/attributes/flood.sql) | Set floodplain flags from parcel/polygon intersections. |
| [political_geography](models/attributes/political_geography.sql) | Validate ids; independently match district/census fields. |
| [service_geography](models/attributes/service_geography.sql) | Independently match schools, council, emergency, health, sanitation and ZIP. |
| [normalized_parcels](models/attributes/normalized_parcels.sql) | Normalize tract suffixes, identifiers, numeric text and sanitation fields. |
| [shoreline_coverage](models/geometry/shoreline_coverage.sql) | Prepare reusable shoreline geometry subdivisions. |
| [map_flags](models/geometry/map_flags.sql) | Set mapped/unmapped status while preserving SQL NULL versus explicit empty geometry. |
| [pluto_geom](models/geometry/pluto_geom.sql) | Clip shoreline geometry and prepare projected mapped geometries. |
| [export_pluto](models/exports/export_pluto.sql) | Publish the typed 99-column tabular candidate. |
| [archive_pluto](models/exports/archive_pluto.sql) | Retain full attributes/geometry for current-release QA. |
| [mappluto](models/exports/mappluto.sql) | Mapped clipped geometry with SHP-compatible text attributes. |
| [mappluto_unclipped](models/exports/mappluto_unclipped.sql) | Mapped unclipped geometry with SHP-compatible text attributes. |
| [mappluto_gdb](models/exports/mappluto_gdb.sql) | Mapped clipped geometry with GDB-compatible numeric attributes. |
| [mappluto_unclipped_gdb](models/exports/mappluto_unclipped_gdb.sql) | Mapped unclipped geometry with GDB-compatible numeric attributes. |
| [qaqc_expected](models/qa/qaqc_expected.sql) | Calculate expected derived values. |
| [qaqc_bbl_diffs](models/qa/qaqc_bbl_diffs.sql) | Compare BBL membership with the locked reference. |
| [qaqc_aggregate](models/qa/qaqc_aggregate.sql) | Calculate aggregate values for mapped/condo variants. |
| [qaqc_mismatch](models/qa/qaqc_mismatch.sql) | Compare 99 attributes for mapped/condo variants. |
| [qaqc_null](models/qa/qaqc_null.sql) | Calculate attribute null counts for mapped/condo variants. |
| [qaqc_outlier](models/qa/qaqc_outlier.sql) | Identify area, floor and unit outliers for mapped/condo variants. |
| [correction_decisions](models/corrections/correction_decisions.sql) | One ordered ledger of automatic, specific-BBL and global research decisions. |
| [pluto_removed_records](models/corrections/pluto_removed_records.sql) | Capture corrected records before each removal phase. |
| [pluto](models/corrections/pluto.sql) | Apply canonical decisions, punctuation rules and both ordered unit-lot removals. |
| [pluto_changes_applied](models/corrections/pluto_changes_applied.sql) | Retain distinct applied events per upstream insertion phase. |
| [pluto_changes_not_applied](models/corrections/pluto_changes_not_applied.sql) | Retain researched mismatches and their found values. |

Local CTEs retain rule names and pinned statement comments. Safe adjacent projections are fused only when writes are disjoint and later expressions/guards do not read earlier writes. Original casts and NULL behavior remain at their semantic points.

The generated graph uses 197 operation CTEs after 13 pure projection fusions; 12 spatial projections share stable bases. The correction ledger replaces 70 imperative correction operations; 17 unreachable operations are omitted. The manifest records each original operation, source hash, owning process and rewrite/fusion status.

Spatial matches are compact MATERIALIZED key/value CTEs, followed by one projection of the parcel rows. Political and service assignments have separate capacity checkpoints. Serial assignment and reused arbitrary matches are evaluated once; a required id gate rejects NULL/duplicate ids.

[pluto_corrections.sql](macros/pluto_corrections.sql) applies specific-BBL decisions before global decisions, preserves per-phase audit DISTINCT and NULL matching, and performs both removal phases in order. Removed lots remain in the audit ledger.

Mismatch and null diagnostics each define one explicit field/expression list, shared across four mapped/condo invocations. Outlier rules also share one body across those variants. Zoning is the largest process because intersection areas, coverage thresholds, ranking and priority ties are distinct business rules.

Compatibility macros preserve PostGIS collection repair, SQL NULL union aggregates, projected CRS handling and geography area. Bare NUMERIC uses bounded DECIMAL(38,12); arbitrary PostgreSQL precision and historical production parity are not claimed.

CAMA UPDATE matches and the ZIP spatial fallback use a canonical identity/payload order with explicit NULLS LAST. This is a documented operational replay policy, not inferred business precedence. The manifest lists every scoped operation and all remaining unordered UPDATE choices.

Regenerate with `compile_full_project` and `write_review_project`. `full_manifest.json` includes all model and macro hashes; changing a shared macro invalidates cached models. Historical QA accumulator rows are not imported.
