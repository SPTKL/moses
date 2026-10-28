# Source recipes

Moses acquires and prepares source data, then publishes immutable, versioned warehouse inputs. A consuming project owns its recipes and decides how to transform those inputs.

## Install and use Moses in any repository

The primary product is an installable Python package and CLI. A user owns their
project and recipes; they do not need a Moses checkout, a prescribed repository
layout, or a specific product project. Hosted catalogs and publishing are optional later
capabilities built on the same ingestion contracts.

Target user experience (proposed commands, not all implemented):

```sh
pip install moses
cd my-project
moses init --recipes ./recipes
moses prepare boroughs
# An explicit recipe path also works, including outside this repository:
moses prepare /path/to/shared-recipes/boroughs.yml
```

`moses init` without options should configure `./recipes` and `.moses/` as the
defaults. `--recipes ./ingest_templates` can point to an existing directory;
directory names do not determine recipe format. Planning or NYCDB definitions
still need explicit conversion to the Moses schema. Initialization must be
idempotent, preserve existing files, and perform no downloads or ingestion.

The proposed project layout is:

```text
my-project/
  config.toml          committed project settings and recipe location
  recipes/            user-owned YAML recipes; any configured location works
  inputs.lock.json    optional committed exact input lock
  .moses/             local catalog, captures and accepted snapshots
```

Keep project settings separate from warehouse state. `config.toml` records a
configuration version, recipe directory and warehouse directory; it contains
no credentials. Initialization adds only the generated local warehouse directory
to `.gitignore`, preserving existing rules. Recipes and project configuration
remain version controlled. A lock identifies retained artifacts; committing the
lock alone does not distribute data to another machine.

Resolve project settings from the nearest `config.toml` containing a `[moses]`
table in the current directory or its parents, so commands from a project
subdirectory use the same warehouse. Ignore unrelated config files; preserve
other tools' sections when initializing an existing file.
An explicit project-config path for CI remains planned. Project-relative paths
resolve against that configuration file; relative user-wide warehouse paths use
the active project root or working directory. Explicit CLI file paths resolve
against the working directory; source paths inside a recipe resolve beside it.
Explicit warehouse options override project defaults. Existing commands without
project configuration retain their current working-directory behavior.

`moses prepare boroughs` should select exactly one recipe in the configured
directory. Missing or ambiguous names must fail with actionable candidates.
An explicit path remains available without registration. Running an entire
directory requires an explicit `--all` operation with a validated execution plan
and per-dataset results; initialization or a missing recipe argument must never
implicitly ingest everything. Keep multi-source collection preparation explicit rather than treating it as an ordinary single recipe.

Local file and direct Socrata ingestion should work with the standard install.
Keep dlt, dbt, cloud publication and native geocoding as optional capabilities;
recipes that require them must identify the missing dependency before fetching
data. Ordinary recipes must run from an installed wheel without importing from
the Moses source checkout. Trusted custom extractors are explicit installed
Python modules, not automatically executed files discovered in the user's repo.

**Current implementation:** `moses init` creates a warehouse, and
`moses prepare /path/to/recipe.yml` already accepts external YAML recipes with
recipe-relative source paths. User/project TOML discovery is implemented for
warehouse location, column naming, fallback CRS and existing export formats.
Recipe-path configuration, `init --recipes`,
recipe-name lookup and directory execution are proposed additions. The current
distribution metadata is `moses-geo`; the desired `pip install moses` command
requires resolving the package name and publishing a release. Changing the
README or package metadata alone does not make that installation available.

Release acceptance must install the built wheel into a clean environment and
exercise init, capture, repeated preparation and exact-version retrieval in an
unrelated temporary repository. Also check execution from subdirectories,
external recipe paths, non-destructive reinitialization, missing/ambiguous recipe
errors and isolation between two projects. These are separate from source-tree
tests and from the eventual live Socrata connector acceptance checks.

## Project configuration and output defaults

**Implemented categories.** User-wide and nearest-project `config.toml` files
share the same versioned `[moses]` schema. Keep shared defaults here and
dataset-specific sources, keys, layers and field mappings in recipes. Keep
credentials in environment references. The four supported categories are:

| Category | Implemented settings | Responsibility |
| --- | --- | --- |
| `project` | `warehouse` | Local catalog, captured inputs and accepted versions |
| `normalization` | `column_names` | Common field naming policy |
| `spatial` | `default_crs` | Fallback source CRS assignment |
| `export` | `format` | Default existing delivery writer |

Working example (also available as [config.example.toml](../config.example.toml)):

```toml
[moses]
config_version = 1

[moses.project]
warehouse = "./.moses"

[moses.normalization]
column_names = "snake_case" # or "preserve"

[moses.spatial]
# Set only when sources without CRS metadata are known to use this projection:
# default_crs = "EPSG:2263"

[moses.export]
format = "parquet" # parquet | geoparquet | filegdb
```

User configuration is `$XDG_CONFIG_HOME/moses/config.toml`, falling back to
`~/.config/moses/config.toml`. Project discovery selects the nearest ancestor
`config.toml` containing `[moses]` from the working directory. Merge values by
setting: a project specifying only a warehouse still inherits user naming and
export defaults. The legacy `[moses.input].column_names` alias remains accepted;
conflicting alias and canonical values in the same file fail. Unknown settings
and invalid values fail rather than being silently ignored.

Project warehouse paths resolve relative to the project config. Relative global
warehouse paths resolve relative to that project root, or the working directory
when no project config exists. The built-in `.moses` uses that same base. An
absolute global warehouse path intentionally shares storage. An explicit
`--warehouse` overrides configuration and resolves relative to the working
directory. `Catalog(root)` continues to use the explicit Python argument.

`spatial.default_crs` assigns a fallback only when source geometry has no embedded
CRS and no explicit recipe/CLI assignment. It never changes coordinates or
overrides embedded metadata. Conflicting explicit assignments must fail. An
unset fallback leaves unknown geometry CRS unknown; existing legacy CSV
coordinate behavior remains explicitly labeled until separately migrated.

`export.format` selects an existing writer; it does not change stored snapshots.
FileGDB still requires an explicit output layer and exact accepted version.
Destinations remain command arguments, and existing paths are never overwritten.
The default remains Parquet. `moses config show` reports categories, effective
values, per-setting origins and discovered config paths without creating storage.

Explicit CLI/API settings take precedence, followed by recipe settings where
applicable, existing environment defaults, project TOML, user TOML and built-in
defaults. For source CRS, legacy `<warehouse>/config.json` supplies a fallback
after TOML and before the built-in unknown CRS. `MOSES_COLUMN_NAMES` and
`MOSES_DEFAULT_CRS` remain supported. Embedded CRS is authoritative; this
configuration hierarchy cannot replace known source metadata. Legacy files are
read in place, never rewritten as part of discovery.

### Planned configuration extensions

`moses init` generating a project config, recipe-directory discovery, a persistent
DuckDB database, and additional export controls remain planned. These options
are not accepted keys yet. Extend the categories above as capabilities land,
rather than adding unrelated settings to a general-purpose input section.
For export, planned `export.crs` is the target for an actual coordinate transformation.
An omitted value preserves the accepted source CRS, subject to the selected
format's requirements. Reject reprojection when the source CRS is unknown or
the required transformation cannot be resolved; never merely relabel coordinates.
Record the source CRS, target CRS, axis convention, selected transformation and
runtime identity in export provenance. Do not download transformation grids
implicitly. Nonspatial datasets do not acquire geometry from these defaults.

Output settings affect delivery files, not the catalog's immutable
Parquet/GeoParquet snapshots. Exporting a version to another format or projection
does not mutate the accepted input. Preserve the current GeoParquet export
behavior when no new output configuration or options are supplied.

| Proposed output format | Compression choices | Delivery contract |
| --- | --- | --- |
| `geojson` | `none`, `gzip` | One `.geojson` or `.geojson.gz` file; RFC 7946 coordinates |
| `shapefile` | `none`, `zip` | Complete sidecar set in a destination directory, or one ZIP containing that set |
| `geoparquet` / `parquet` | `none`, `snappy`, `zstd` | Internal column compression, rather than an outer archive |
| `csv` | `none`, `gzip` | Tabular delivery; geometry requires an explicit encoding or omission policy |

These are target capabilities, subject to writer support. Compression is an enum,
not a boolean: its meaning depends on the format. Validate format, codec, CRS and
destination suffix together before writing. A codec inherited from a default
that is incompatible with a format override must produce a clear error, not be
silently ignored. Setting `compression = "none"` explicitly disables compression.

[RFC 7946 GeoJSON](https://www.rfc-editor.org/rfc/rfc7946) uses WGS 84 longitude,
latitude coordinates in degrees. When GeoJSON is explicitly chosen with no
output CRS, derive that target and report it; reject a conflicting configured
projected CRS rather than silently replacing it. For `EPSG:4326` GeoJSON output,
serialize longitude first regardless of the CRS authority's axis ordering.

[Shapefile](https://gdal.org/en/stable/drivers/vector/shapefile.html) consists of
multiple files and has attribute/geometry restrictions. Validate field-name
mapping, widths, types, encoding and geometry compatibility before export;
require explicit loss policies instead of silently truncating or dropping data.
Stage the complete set in a new directory or ZIP and publish that artifact only
after validation. `overwrite = false` is the default; never leave a partially
updated shapefile set after a failed export.

For configurable settings, use explicit CLI options first, then explicit recipe
settings, supported environment defaults, project settings, user settings and built-in defaults.
Embedded source CRS is authoritative and sits outside this fallback hierarchy.
Recipe-defined source CRS and geometry contracts therefore cannot be replaced by
a global fallback. Reject unknown keys within `[moses]`, unsupported config
versions and invalid values; unrelated TOML tables belong to their owning tools.

Extend the implemented `moses config show` command as new settings are supported.
Record effective settings with runs
and exports so editing defaults cannot change the meaning of a historical
artifact. Resolve configured output directories relative to `config.toml`;
explicit command-line destinations remain relative to the working directory.

**Implementation boundary:** the four-category example above is accepted
configuration. Output reprojection, additional writers and compression options
are planned. Legacy JSON CRS settings continue to work below TOML in the stated
precedence order. No files are automatically migrated or rewritten.

Acceptance requires configuration precedence and origin reporting, subdirectory
discovery, non-destructive initialization/migration, known-coordinate projection
checks, unknown/conflicting CRS failures, each supported format/codec combination,
shapefile sidecar completeness, loss-policy failures, no partial outputs, and
unchanged accepted catalog versions after export.

## DuckDB Spatial as the geospatial engine

**Target architecture:** use DuckDB with its `spatial` extension as the primary
engine for vector calculations. Moses owns acquisition, recipe validation,
configuration, execution and immutable publication; DuckDB executes relational
and spatial operations together. Consumer projects retain their business rules.
This keeps spatial work close to the tables instead of moving every row through
Python geometry objects.

Use the [Spatial function surface](https://duckdb.org/docs/1.5/core_extensions/spatial/functions)
for geometry construction/validation, spatial predicates and joins, buffers,
intersection/union, area/length/distance and coordinate transformation. Execute
reviewed operations through a shared spatial execution layer. Declarative source
recipes should select named operations and validated arguments; this does not
authorize arbitrary SQL or filesystem access through remotely submitted recipes.

Keep three CRS decisions distinct: the source CRS describes existing coordinates;
the calculation CRS determines appropriate units and distortion for planar
operations; the output CRS determines delivery coordinates. An output default
must not silently choose the units of a buffer or area calculation. Require an
appropriate projected CRS for planar measurements, or an explicitly supported
geodesic operation with its own axis/units contract. EPSG:2263 is an NYC-specific
choice measured in US survey feet, not a global default. Preserve recipe-specific
choices and reject operations whose CRS/units are unresolved.

For transformations, use explicit source and destination CRS and a defined XY
axis convention (`always_xy := true` when coordinates use longitude/easting
first). DuckDB's PROJ database is bundled with Spatial, so record engine and
extension identities and any grid requirements; do not assume another installed
PROJ runtime yields identical results. Do not apply geometry repair implicitly.

Use [Spatial's GDAL integration](https://duckdb.org/docs/1.5/core_extensions/spatial/gdal)
for supported vector readers/writers after checking actual driver capabilities.
`ST_Read` handles input and GDAL `COPY` handles exports. The `COPY` CRS/SRS option
sets metadata only: transform geometry with `ST_Transform` before writing when
the output CRS differs. Moses still enforces format/compression compatibility,
attribute-loss policies, bounded local paths and atomic output publication.
Raster workflows remain separate from this vector engine.

Proposed optional configuration:

```toml
[moses.spatial]
extension_directory = "./.moses/extensions"
# Project-specific default for planar calculations, when appropriate:
# calculation_crs = "EPSG:2263"
```

Spatial is required for the migrated spatial operations, independently of the
recipe-registry extra. Python package installation alone does not install the
DuckDB extension binary. Add a proposed `moses init --install-spatial` setup path
that installs the official extension compatible with the actual DuckDB version
and platform into the configured cache. Support an existing offline cache too.
Normal runs load the verified installed extension and report missing/incompatible
versions clearly, without downloading or silently falling back to another
geometry engine. Tabular work remains usable without Spatial. DuckDB documents
separate [installation and loading](https://duckdb.org/docs/1.5/core_extensions/spatial/overview).

Migrate the current Shapely/PyProj calculations in stages, then evaluate whether
Pyogrio can also be replaced for the supported vector formats. Keep existing
adapters until schema, CRS, NULL/empty/invalid geometry, dimensionality, export
and error-handling parity pass. Dependency removal is an outcome of that evidence,
not a prerequisite. Geosupport address geocoding remains a separate adapter.
WKB/GeoParquet storage and explicit CRS metadata remain the accepted artifact
contract; DuckDB's internal geometry representation is not a portable file format.

Measure representative joins, overlays and aggregations with memory/time limits;
do not assume every spatial operation spills to disk. Use query-plan evidence
before claiming index acceleration: [R-tree index support](https://duckdb.org/docs/1.5/core_extensions/spatial/r-tree_indexes)
has predicate and query-shape restrictions. The existing service isolation and
resource limits still apply.

**Current evidence:** a local offline smoke check on 2026-10-28 loaded Spatial
`04270fe` with DuckDB `1.5.6`, calculated a synthetic square's area as 100, returned
true for an interior-point intersection, and transformed a longitude/latitude
point from EPSG:4326 to EPSG:2263. This confirms basic local capability, not engine
migration, numerical parity or citywide capacity. Moses still uses Shapely,
PyProj and Pyogrio today; no dependency or execution backend changed here. The
references use DuckDB 1.5 to match the package's current `>=1.5,<2` constraint;
an upgrade requires separate compatibility validation.

## Format conversion and source type preservation

DuckDB Spatial can underpin file conversion through `ST_Read` and GDAL `COPY`,
with capability checks against the installed drivers. Moses must validate what
the destination can represent; format conversion alone is not proof of a
lossless round trip. Use the typed accepted snapshot as the conversion source,
preserve original captures, and retain source schema and reader options in
provenance. GeoParquet remains the canonical spatial snapshot format.

### Projection discovery

Use [ST_Read_Meta](https://duckdb.org/docs/1.5/core_extensions/spatial/functions#st_read_meta)
to inspect the selected layer's geometry fields and CRS before reading or
transforming. Preserve full CRS definitions, authority/code when available and
the evidence source; a valid custom CRS need not have an EPSG match. Shapefile
projection comes from its `.prj` sidecar, GeoPackage from its spatial metadata,
and GeoParquet from its geometry metadata through the appropriate reader.
RFC 7946 GeoJSON uses WGS 84 longitude/latitude by specification; label this as
format-defined rather than an independently measured projection. Legacy GeoJSON
with CRS declarations needs an explicit compatibility policy.

Automatic discovery reads metadata or applies documented format semantics. It
must not guess a projection from coordinate ranges, location, filenames or the
shape of the data. Missing or conflicting evidence requires a recipe assignment
or a labeled configured fallback. Unknown CRS can remain in storage, but blocks
reprojection and CRS-dependent operations. Reading a CRS and transforming
coordinates are separate steps.

### Attribute and geometry types

Default to preserving source values and types without optional coercion:

- Shapefile: capture DBF field types, widths, decimal scales and encoding as well
  as the resulting DuckDB/Arrow schema. Preserve text identifiers, dates, null
  behavior and available numeric precision. A DBF numeric field read as a double
  is not proof of exact decimal preservation; use exact decoding or reject a
  precision-sensitive mapping when the normal reader cannot meet the contract.
- GeoJSON: preserve JSON strings, booleans, numbers, arrays, objects and nulls
  subject to explicit representability checks. JSON has no date type or declared
  SQL integer width/decimal scale. Disable date-string inference with the
  GeoJSON driver's `DATE_AS_STRING=YES` option by default; an explicit recipe can
  request date conversion. Do not stringify everything or treat digit strings
  such as `"001"` as numbers. See the [GDAL GeoJSON reader](https://gdal.org/en/stable/drivers/vector/geojson.html).
- Mixed types, nested properties, missing versus null properties, large integers
  and precision-sensitive numbers need a lossless representation or an explicit
  mapping/error. Full-input checks must catch information already lost during
  reader inference; checking only the post-read table is insufficient. Retained
  raw bytes support replay, but do not make a lossy accepted table acceptable.
- Preserve geometry subtype, multipart structure and supported Z/M dimensions;
  fail or use an explicit supported representation for unsupported dimensions.
  Reader-generated feature IDs are identified separately from publisher fields
  and must not silently become business keys or leak into exports as source data.

Before export, produce a source-to-output schema mapping. In strict mode, reject
unrepresentable fields, precision loss, truncation, incompatible geometry and
unsupported null semantics. An explicitly selected conversion policy may map
fields or encode nested values, with every change recorded. Do not promise
universal type preservation when writing GeoJSON or Shapefile: their type systems
differ. Reopen completed exports to verify values, schema mapping, geometry and
CRS before publication, using declared numeric tolerances only where approved.

### File Geodatabases

Esri File Geodatabase ingestion is implemented locally for `.gdb` directories
and ZIPs containing exactly one root `.gdb` directory. The existing Pyogrio/GDAL
adapter uses the [OpenFileGDB driver](https://gdal.org/en/stable/drivers/vector/openfilegdb.html);
this does not migrate ingestion to DuckDB Spatial. `inspect` and `load` accept
`--layer`; multiple layers require an explicit selection and errors list the
available names. Each selected feature class or nonspatial table becomes a
separate dataset, with its source layer recorded. Native field types and embedded
CRS pass through the existing Arrow/geometry validation contract.

Directory imports capture every regular member with relative paths and a
deterministic bundle checksum, then read the captured copy. ZIP imports retain
the original archive. Validation rejects symlinks, unsafe or conflicting archive
paths, and archives containing multiple geodatabases. Both forms are bounded to
100,000 members and 20 GiB uncompressed; ZIP members also have a 1,000:1
compression-ratio limit. These are input bounds, not memory guarantees: parsing
still materializes the selected layer. S3 publication preserves directory-member
paths and publishes the version manifest last.

An external project can prepare a layer with this recipe:

```yaml
schema_version: 1
name: parcels
source:
  kind: local
  path: ../data/city.gdb
import:
  format: FileGDB
  layer: parcels
key: parcel_id
```

Paths are relative to the recipe. The same recipe can reference `city.gdb.zip`;
do not select an individual internal member. A local directory's optional
`source.sha256` hashes sorted relative POSIX names (8-byte big-endian name length,
UTF-8 name, then binary member SHA256); the root directory name is excluded.
ZIP checksums hash the archive bytes. Captures record the checksum method for
directories and remain available for replay.

`moses export NAME DEST.gdb --format FileGDB --layer LAYER --version VERSION_ID`
writes one exact accepted version to a new staged directory. It requires an
explicit layer and version, preserves CRS without reprojection, targets
`ARCGIS_PRO_3_2_OR_LATER`, validates supported fields/geometries, and checks the
staged readback before publication. Existing destinations are refused. ZIP output
and multi-layer delivery assembly remain planned.

Preserve representable attribute/geometry types and original metadata, but do
not equate vector conversion with a full ArcGIS geodatabase clone. Domains,
subtypes, aliases, relationships, attachments, topology, curves, coordinate
precision and Z/M semantics need separate fidelity checks; GDAL support does
not mean every feature is exposed through DuckDB's SQL interface. Unsupported
features require separate support. FileGDB creation compatibility settings can change
64-bit integer/date/time storage, so choose a declared target ArcGIS version
and reject unapproved coercion. Enterprise geodatabases (`.sde` connections),
personal `.mdb` geodatabases and raster content are separate capabilities.

The local installed Spatial driver advertises OpenFileGDB open/create support.
A synthetic single-layer creation/readback check on 2026-10-28 preserved a text
identifier `"001"` and an integer. `ST_Read` reported an EPSG:2263 geometry type,
but `ST_Read_Meta` returned no metadata rows for this fixture; full CRS/layer
discovery therefore needs further validation or a dedicated metadata adapter.
Writing required an explicit geometry type. This is DuckDB driver capability
evidence; the implemented Moses reader uses Pyogrio for layer/CRS discovery.
Synthetic Moses tests cover native string/int64/date fields, directory and ZIP
capture, explicit layer selection, recipes, S3 member paths and staged export.
They do not establish full geodatabase parity or citywide capacity.

### Bounded verification

On 2026-10-28, an offline synthetic check using DuckDB 1.5.6 and the installed
Spatial extension wrote and reread GeoPackage and Shapefile. Both retained
`"001"` as text, an integer, a double-valued number and a date, and reported
EPSG:4326. Removing the generated Shapefile `.prj` caused metadata inspection to
return an unknown CRS. A separate GeoJSON check retained integer and boolean
types; its date-looking string was inferred as DATE by default and stayed
VARCHAR with `DATE_AS_STRING=YES`. These checks cover small fixtures, not full
format fidelity or arbitrary numeric precision. The preservation and conversion
policies above remain planned Moses backend work.

## Community recipe registry

**Proposed distribution model; no registry extra or recipe packages are published
yet.** Keep the Moses engine, community recipes and consumer projects separately
versioned. The standard install handles local recipes; `pip install
"moses[registry]"` should additionally install a curated community recipe pack
and any optional registry dependencies. This makes published recipes available
without copying a source repository or installing a product such as PLUTO.

[Python extras](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#extras)
declare additional package dependencies. An extra can depend on a recipe pack;
it does not dynamically discover every package in a registry. Define `registry`
as a curated default bundle, with other community or organization packs installed
as separate distributions. Pack releases within the declared compatibility range
can evolve without a new Moses engine release. Package names below are proposed,
not claims of availability or ownership.

Target workflow, after publishing and implementing registry support:

```sh
pip install "moses[registry]"
cd my-project
moses init
moses recipes list
moses prepare community/nyc/boroughs

# Another independently maintained pack:
pip install moses-recipes-nycplanning
moses prepare nycplanning/transit-zones

# Make a project-owned editable copy when customization is needed:
moses recipes copy community/nyc/boroughs --to recipes/boroughs.yml
moses prepare recipes/boroughs.yml
```

Start with installed recipe packs and their bundled indexes; a hosted search
catalog can follow when needed. Listing and inspecting installed recipes should
work offline and should not fetch datasets or import arbitrary pack code. A
separate package, provisionally `moses-recipes-community`, contains YAML recipes,
descriptive metadata, licenses, documentation and small fixtures. Its manifest
declares a namespace, pack version, supported Moses/recipe-schema versions,
recipe resource paths and required connectors. Read declared package resources
without requiring editable installs or a particular working directory.

Resolve qualified names explicitly and reject namespace collisions. Local file
paths continue to work without registry support; never silently substitute a
community recipe for a missing local file. Use the same recipe validation and
acceptance pipeline for both. Installed packs are read-only inputs; `recipes
copy` copies the selected recipe and declared relative resources, records their
origin, and refuses to overwrite existing project files. A customized copy is
project-owned and is not silently overwritten on a pack upgrade.

Record the resolved distribution version, recipe/resource hashes, source origin,
connector requirements and effective parameters in project recipe locks and
accepted provenance. Keep those recipe locks separate from exact captured-data
locks: the same recipe can retrieve changing upstream data. Normal execution
must not upgrade locked recipes implicitly. Missing locked resources require an
explicit restore or update; offline replay still needs retained data captures.

Curated packs require maintainers, licensing/attribution, schema validation,
fixture tests and dated live-source checks with clear status. Begin with
declarative recipes over built-in connectors. Custom Python dependencies remain
explicit trusted plugins under the existing source-recipe contract; browsing a
registry must not execute them. Installing a Python distribution has normal pip
trust semantics and is not a sandboxed YAML download.

This follows dlt's separation of generic core sources from community-maintained
sources, while choosing package distribution for reusable Moses recipes. In
[dlt's documented workflow](https://dlthub.com/docs/dlt-ecosystem/verified-sources),
verified sources live in a separate repository and `dlt init` downloads their
Python code into the consumer's working directory. Moses should support both
running an installed recipe and copying it for project-specific changes.

Implementation follows project initialization and recipe discovery. Acceptance
must cover a wheel-installed pack in an unrelated repository, offline listing,
compatibility/collision errors, package-relative resources, explicit updates,
copy-without-overwrite and replay of locked recipes. No PLUTO build dependency
belongs in the registry extra; a consumer project may use these packs itself.

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
A consuming project chooses its own transformation dependencies.

YAML is the recipe format because nested resources, field mappings and ordered
procedures remain readable. TOML works well for application settings, and dlt
uses it for configuration, but that does not require Moses recipes to use TOML.
The validated schema and execution contracts matter more than serialization.
Recipes use safe data loading, reject unknown fields and duplicate keys, and
do not embed Python, SQL or shell expressions.

## Design references from NYCDB and NYC Planning

The ingestion direction also draws from [NYCDB](https://github.com/nycdb/nycdb)
and [Planning's ingest templates](https://github.com/NYCPlanning/data-engineering/tree/main/ingest_templates).
Use a shared connector implementation with declarative dataset recipes so that
adding an ordinary dataset requires configuration and validation, not another
custom ingestion program. Keep product transformations in independent projects.

| Reference | Observed pattern | Moses design choice |
| --- | --- | --- |
| [NYCDB dataset definition](https://github.com/nycdb/nycdb/blob/main/src/nycdb/datasets/hpd_violations.yml) | Files, destination names, typed fields, verification count and SQL references in one dataset definition | Reuse the explicit dataset contract and verification pattern; retain product SQL in dbt |
| [NYCDB dataset execution](https://github.com/nycdb/nycdb/blob/main/src/nycdb/dataset.py) | Separate download, load and verify operations; dependency checks and batched imports | Make capture, preparation, validation and acceptance independently inspectable and replayable |
| [Planning PLUTO template](https://github.com/NYCPlanning/data-engineering/blob/5b849eebf4afbe282f30944cfbedd918bc51ad81/ingest_templates/dcp_pluto.yml) | Publisher metadata, versioned URL/archive member, string parsing and XY geometry | Resolve release parameters before capture; record the resolved recipe and explicit type/geometry policies |
| [Planning Transit Zones template](https://github.com/NYCPlanning/data-engineering/blob/5b849eebf4afbe282f30944cfbedd918bc51ad81/ingest_templates/dcp_transit_zones.yml) | Socrata organization and dataset ID, format, ordered cleanup and column definitions | Add a dedicated Socrata source kind behind the common preparation and acceptance contract |

The Planning references above match the local reference checkout at
`5b849eebf4afbe282f30944cfbedd918bc51ad81`. Its
[Socrata extraction implementation](https://github.com/NYCPlanning/data-engineering/blob/5b849eebf4afbe282f30944cfbedd918bc51ad81/python/connectors/dcpy/connectors/socrata/extract.py)
already supplies metadata lookup and CSV/geospatial downloads. It uses the date
derived from `rowsUpdatedAt` as a version proxy and buffers the download response.
Moses should retain the complete observed timestamp, stream captures, and identify
captured content by checksum. A publisher date is not an immutable source release.

Template migration should produce a reviewable Moses recipe with the upstream
commit and field mapping recorded. Unsupported steps must fail explicitly.
Do not execute upstream SQL, expressions or Python merely because a template
references them. A minimum row count is a useful warning, not sufficient proof
of completeness; validate schema, declared keys, null policy and geometry too.

## Direct Socrata connector design

**Proposed as of 2026-10-28; not implemented.** The existing generic REST adapter
supports GET extraction and captures decoded records as Parquet. It does not yet
provide the metadata, raw response capture, consistency checks or API negotiation
described here. Add Socrata as a first-class source adapter while retaining the
common Moses preparation, acceptance and replay pipeline.

The operator supplies an NYC Open Data URL or domain and dataset ID, reviews the
resolved title, publisher, source kind, schema and geometry, and selects a full
capture. Discovery and previews do not accept a dataset. After complete
validation, show the accepted version, capture time, changes and provenance;
on failure, retain the previous accepted version and explain the recovery action.

The proposed recipe contract includes the domain, dataset ID, explicit API mode,
output representation, selection/filter policy, refresh mode, optional secret
environment reference and dataset-specific schema/key/geometry expectations.
Use a stable Moses dataset identity with `(domain, dataset ID)` as an external
identifier. Business keys are separately declared and verified; Socrata row IDs
and BBL are not universal business keys. These fields require a versioned recipe
schema change and are not valid additions to today's schema-version-1 recipes.

1. **Inspect and resolve.** Capture source metadata, machine field names and
   display labels, descriptions, attribution, available license information,
   geometry and update markers. Distinguish tables, derived views, geospatial
   assets and linked files; report unsupported assets instead of treating every
   catalog item as a queryable table. Verify metadata against the actual selected
   dataset, rather than trusting a template's descriptive URL.
2. **Choose a supported transport.** Prefer a verified bulk export for a full
   capture; use query extraction when selection or the asset requires it.
   Current [SODA3 documentation](https://dev.socrata.com/docs/queries/) describes
   POST queries at `/api/v3/views/{id}/query.json`, separate exports and a required
   app token or authenticated user. Support explicit SODA 2.x compatibility when
   verified for that dataset. Record the selected API/representation and fail
   clearly on unavailable capabilities; do not silently change a pinned recipe.
   Keep credentials in environment-backed headers, out of manifests and logs.
3. **Capture completely.** Stream raw response bodies or export bytes and source
   metadata to staging with checksums, request parameters, page order, timestamps
   and safe response headers. Bound retries, timeouts, bytes and concurrency;
   handle throttling with backoff. Use a total ordering with a unique tie-breaker
   for paging. Prefer validated keyset traversal over deep offsets where the
   source supports it; [Socrata warns that deep paging slows down](https://dev.socrata.com/docs/queries/page.html).
   A sample or user-imposed row cap must never be labeled a complete capture.
4. **Check consistency and prepare.** Compare available source update markers
   and schema before and after extraction; if they change, quarantine or retry.
   Stable markers and counts are checks, not proof of an upstream transactional
   snapshot. Record that limitation unless the source provides a verified
   revision guarantee. Preserve numeric precision, leading-zero identifiers,
   timestamp semantics, nulls and geometry; unsupported mappings require review.
   Validate all rows and reject incomplete or incompatible captures before
   publishing an accepted version. Resume only against a verified stable source
   revision; otherwise restart extraction while retaining diagnostic captures.
5. **Accept and replay.** Commit the accepted version and refresh state together
   only after validation. Retain raw capture identity separately from normalized
   content identity so a repeat observation can record provenance without
   forcing a new identical data version. Locks identify the captured artifact,
   recipe and adapter version; offline replay must not query Socrata again.

Start with full snapshots and periodic full reconciliation. Incremental mode is
a later, dataset-specific capability: require stable keys, documented update
semantics, a watermark plus tie-breaker, an overlap/replay policy and an explicit
deletion strategy. A timestamp query alone misses deleted records. Socrata's
[system-field documentation](https://dev.socrata.com/docs/system-fields.html)
also notes that a full replacement can mark every row as updated. Never advance
a cursor before the corresponding accepted publication succeeds.

The first acceptance set covers one complete small table, one complete spatial
dataset and a bounded large-dataset exercise clearly labeled as a sample. Check
multiple pages, throttling/retry, interrupted captures, schema changes, duplicate
keys, source mutation during capture, unchanged refresh, offline replay and
failure without advancing the accepted version. Large-scale acceptance also
requires measured full-dataset memory, disk and runtime evidence. NYC dataset
API capabilities remain to be verified in live connector tests.

## Path toward replacing Socrata

Treat Socrata as an upstream adapter and, later, an optional publishing
destination. Moses owns dataset identity, metadata, immutable versions and public
delivery contracts. This allows a dataset to move from Socrata acquisition to an
agency feed without changing its downstream identity or pinned historical inputs.

| Stage | User outcome | Acceptance gate |
| --- | --- | --- |
| Import | Analysts capture and reproduce NYC Open Data inputs directly | Complete captures, metadata, validation, refresh failure recovery and offline replay |
| Serve independently | Consumers browse a Moses catalog, query accepted versions and download open formats without contacting Socrata | Stable IDs, metadata search, documented bounded APIs, provenance, accessible previews and operational recovery |
| Publish directly | Agencies submit, validate, review and publish datasets into Moses | Publisher ownership, permissions, audit history, approvals, scheduled refresh, rollback and support procedures; optional outward Socrata publication |
| Migrate consumers | Selected datasets and their consumers move to Moses | Dataset/consumer inventory, metadata and data parity, ID mapping, URL/API migration, measured service levels, rollback and publisher sign-off |

Replacing the public platform is a broader product track than building a source
connector. Decide explicitly which existing query/API behaviors need a
compatibility layer; do not promise universal SoQL compatibility. Begin with
selected datasets and observable adoption before proposing a portal-wide cutover.
Publisher-facing features remain downstream of durable jobs, hosted identity,
resource isolation, backups and recovery in the service roadmap.

## Use a recipe

### Column naming

`import.column_names: snake_case` enables optional ASCII name normalization.
The default `preserve` leaves names unchanged. Normalization splits camelCase
and acronym boundaries, replaces punctuation/whitespace with underscores,
collapses and trims underscores, and lowercases the result. Only `a-z`, `0-9`
and `_` remain. Digit-leading names receive `column_`; empty results and
duplicate normalized names are errors, including collisions with the canonical
geometry column. There is no automatic suffixing or column removal.

```yaml
schema_version: 1
name: parcels
source:
  kind: local
  path: parcels.csv
import:
  rename:
    Tax Lot Number: Parcel ID
  column_names: snake_case
  types:
    parcel_id: string
key: parcel_id
```

Explicit renames run first, then snake_case, then null/type policies. Recipe
keys, types and geometry settings address the final names. CLI `inspect` and
`load` accept `--column-names snake_case`; their key/type/coordinate arguments
address source names. Python reader/catalog APIs accept `column_names="snake_case"`.
The mapping is recorded alongside normalization/inspection metadata, while raw
captures remain unchanged.

Set a user-wide default in `$XDG_CONFIG_HOME/moses/config.toml`, falling back to
`~/.config/moses/config.toml` when XDG_CONFIG_HOME is unset:

```toml
[moses.normalization]
column_names = "snake_case"
```

Use the same structure in a project `config.toml` to override the user default.
Discovery starts at the working directory and selects the nearest ancestor
config containing `[moses]`, ignoring unrelated TOML files. External recipe
paths do not change the selected project; explicit recipe settings travel with
the recipe. Naming belongs in `[moses.normalization]`; the earlier
`[moses.input].column_names` alias remains accepted for compatibility.
The other supported categories are described in the configuration section above.
Unrelated top-level tables are allowed; unknown Moses settings and invalid
values fail explicitly.

Precedence: explicit CLI/API choice, recipe `import.column_names`, nonempty
`MOSES_COLUMN_NAMES`, project TOML, user TOML, built-in `preserve`. An explicit
`preserve` is an override, not an absent setting. `prepare --column-names` can
override a recipe for one run. `Catalog.ingest`, `inspect_source` and recipe
preparation resolve these defaults; low-level `read_vector` stays explicit so
internal reads and export verification are unaffected by user settings.
Recipes record the effective rule before execution, and prepared results are
not normalized a second time during acceptance. Config file locations do not
become dataset identity. `moses config show` reports the effective naming policy
and its origin alongside the other configuration categories without creating a
warehouse. Configuration extensions marked planned above remain unimplemented.

### Running recipes

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
| Product | Consumer-owned joins, calculations, validation and outputs |

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

## PLUTO example

The [standalone PLUTO example](../examples/pluto/README.md) owns its release-specific recipe, preparation command, dbt contract, and build evidence. Moses accepts external recipe paths and prepares immutable source inputs; those generic contracts apply to other projects as well.
