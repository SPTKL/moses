.DEFAULT_GOAL := help
.PHONY: help setup check-config ingest prepare build export

-include config.mk

RELEASE ?= 26v2
CANDIDATE_VERSION ?= 26v2m4
PREVIOUS_RELEASE ?= 26v1
OFFLINE ?= 0
WAREHOUSE ?= $(CURDIR)/.moses/warehouse
CACHE ?= $(CURDIR)/.moses/captures/26v2
INPUT_LOCK ?= $(CACHE)/production-ingestion.json
PREPARED_DIR ?= $(CURDIR)/.moses/prepared/26v2
OUTPUT_DATABASE ?= $(CURDIR)/.moses/build/pluto.duckdb
EXPORT_DIR ?= $(CURDIR)/.moses/exports/26v2
EXTENSION_DIRECTORY ?= $(CURDIR)/.extensions

# Quote a configuration value as one POSIX shell argument, including spaces and apostrophes.
q = '$(subst ','"'"',$(1))'

help:
	@printf '%s\n' \
	  'PLUTO full release (26v2): copy config.mk.example to config.mk and fill required settings.' \
	  'make setup    Install example dependencies from the shared lockfile.' \
	  'make ingest   Capture and ingest the complete published release with Moses.' \
	  'make prepare Publish locked, normalized inputs for dbt.' \
	  'make build   Run the standalone PLUTO dbt project.' \
	  'make export  Export completed PLUTO and QA files (optional).' \
	  'Set OFFLINE=1 on ingest to replay previously captured sources.'

setup:
	@uv sync --locked

check-config:
	@test -f config.mk || { echo 'Create config.mk from config.mk.example and fill required settings.' >&2; exit 2; }

ingest: check-config
	@set -eu; \
	test -n $(call q,$(WAREHOUSE)) && test -n $(call q,$(CACHE)) || { echo 'Set WAREHOUSE and CACHE.' >&2; exit 2; }; \
	test -n $(call q,$(EXTENSION_DIRECTORY)) && test -d $(call q,$(EXTENSION_DIRECTORY)) || { echo 'EXTENSION_DIRECTORY must exist.' >&2; exit 2; }; \
	test $(call q,$(RELEASE)) = 26v2 || { echo 'The checked-in recipe requires RELEASE=26v2.' >&2; exit 2; }; \
	case $(call q,$(OFFLINE)) in 0|1) ;; *) echo 'OFFLINE must be 0 or 1.' >&2; exit 2;; esac; \
	if test $(call q,$(OFFLINE)) = 1; then \
	  test -f $(call q,$(CACHE)/release/build_metadata.json) && test -f $(call q,$(CACHE)/acquisition-report.json) || { echo 'OFFLINE=1 needs previously captured release metadata and acquisition report in CACHE.' >&2; exit 2; }; \
	  set -- --offline; \
	else \
	  test -n $(call q,$(SOURCE_REPO)) && test -d $(call q,$(SOURCE_REPO)) || { echo 'Set SOURCE_REPO to the upstream data-engineering checkout.' >&2; exit 2; }; \
	  git -C $(call q,$(SOURCE_REPO)) cat-file -e '32bc98f632f15e7182933a17fb61ecf74e853518^{commit}' || { echo 'SOURCE_REPO must contain the pinned 26v2 commit.' >&2; exit 2; }; \
	  set -- --source-repo $(call q,$(SOURCE_REPO)); \
	fi; \
	uv run --locked pluto-example --warehouse $(call q,$(WAREHOUSE)) fetch-production \
	  --release $(call q,$(RELEASE)) --cache $(call q,$(CACHE)) \
	  --extension-directory $(call q,$(EXTENSION_DIRECTORY)) "$$@"

prepare: check-config
	@set -eu; \
	test -n $(call q,$(WAREHOUSE)) && test -d $(call q,$(WAREHOUSE)) || { echo 'WAREHOUSE must be an ingested Moses warehouse.' >&2; exit 2; }; \
	test -n $(call q,$(INPUT_LOCK)) && test -f $(call q,$(INPUT_LOCK)) || { echo 'INPUT_LOCK must point to cache/production-ingestion.json.' >&2; exit 2; }; \
	test -n $(call q,$(PREPARED_DIR)) && test ! -e $(call q,$(PREPARED_DIR)) || { echo 'PREPARED_DIR must be a new directory.' >&2; exit 2; }; \
	test -n $(call q,$(EXTENSION_DIRECTORY)) && test -d $(call q,$(EXTENSION_DIRECTORY)) || { echo 'EXTENSION_DIRECTORY must exist.' >&2; exit 2; }; \
	test -n $(call q,$(GEOSUPPORT_RELEASE)) || { echo 'Set GEOSUPPORT_RELEASE to the installed native release.' >&2; exit 2; }; \
	test -n $(call q,$(GEOSUPPORT_EXTENSION)) && test -f $(call q,$(GEOSUPPORT_EXTENSION)) || { echo 'GEOSUPPORT_EXTENSION must be an installed native extension file.' >&2; exit 2; }; \
	test -n $(call q,$(GEOSUPPORT_HOME)) && test -d $(call q,$(GEOSUPPORT_HOME)) || { echo 'GEOSUPPORT_HOME must be an existing bundle directory.' >&2; exit 2; }; \
	case $(call q,$(GEOSUPPORT_RUNTIME)) in local|docker) ;; *) echo 'Set GEOSUPPORT_RUNTIME to local or docker.' >&2; exit 2;; esac; \
	uv run --locked pluto-example --warehouse $(call q,$(WAREHOUSE)) prepare recipes/26v2.yml \
	  --lock $(call q,$(INPUT_LOCK)) --output-dir $(call q,$(PREPARED_DIR)) \
	  --extension-directory $(call q,$(EXTENSION_DIRECTORY)) \
	  --geosupport-release $(call q,$(GEOSUPPORT_RELEASE)) \
	  --geosupport-extension $(call q,$(GEOSUPPORT_EXTENSION)) \
	  --geosupport-home $(call q,$(GEOSUPPORT_HOME)) \
	  --geosupport-runtime $(call q,$(GEOSUPPORT_RUNTIME))

build: check-config
	@set -eu; \
	test -n $(call q,$(PREPARED_DIR)) && test -f $(call q,$(PREPARED_DIR)/prepared.duckdb) || { echo 'PREPARED_DIR needs a completed prepared.duckdb.' >&2; exit 2; }; \
	test -n $(call q,$(OUTPUT_DATABASE)) || { echo 'Set OUTPUT_DATABASE.' >&2; exit 2; }; \
	test -n $(call q,$(EXTENSION_DIRECTORY)) && test -d $(call q,$(EXTENSION_DIRECTORY)) || { echo 'EXTENSION_DIRECTORY must exist.' >&2; exit 2; }; \
	case $(call q,$(CANDIDATE_VERSION)) in ''|*[!A-Za-z0-9_.-]*) echo 'Invalid CANDIDATE_VERSION.' >&2; exit 2;; esac; \
	case $(call q,$(PREVIOUS_RELEASE)) in ''|*[!A-Za-z0-9_.-]*) echo 'Invalid PREVIOUS_RELEASE.' >&2; exit 2;; esac; \
	mkdir -p "$$(dirname $(call q,$(OUTPUT_DATABASE)))"; \
	vars=$$(printf '{"pluto_version":"%s","previous_pluto_version":"%s"}' $(call q,$(CANDIDATE_VERSION)) $(call q,$(PREVIOUS_RELEASE))); \
	PLUTO_INPUT_DATABASE=$(call q,$(PREPARED_DIR)/prepared.duckdb) \
	PLUTO_OUTPUT_DATABASE=$(call q,$(OUTPUT_DATABASE)) \
	PLUTO_SPATIAL_DIRECTORY=$(call q,$(EXTENSION_DIRECTORY)) \
	uv run --locked dbt build --project-dir dbt --profiles-dir dbt --vars "$$vars"

export: check-config
	@set -eu; \
	test -n $(call q,$(PREPARED_DIR)) && test -f $(call q,$(PREPARED_DIR)/prepared.duckdb) || { echo 'PREPARED_DIR needs a completed prepared.duckdb.' >&2; exit 2; }; \
	test -n $(call q,$(OUTPUT_DATABASE)) && test -f $(call q,$(OUTPUT_DATABASE)) || { echo 'OUTPUT_DATABASE needs a completed dbt database.' >&2; exit 2; }; \
	test -n $(call q,$(EXPORT_DIR)) && test ! -e $(call q,$(EXPORT_DIR)) || { echo 'EXPORT_DIR must be a new directory.' >&2; exit 2; }; \
	test -n $(call q,$(EXTENSION_DIRECTORY)) && test -d $(call q,$(EXTENSION_DIRECTORY)) || { echo 'EXTENSION_DIRECTORY must exist.' >&2; exit 2; }; \
	uv run --locked python export.py --database $(call q,$(OUTPUT_DATABASE)) \
	  --input-database $(call q,$(PREPARED_DIR)/prepared.duckdb) \
	  --output-dir $(call q,$(EXPORT_DIR)) \
	  --extension-directory $(call q,$(EXTENSION_DIRECTORY))
