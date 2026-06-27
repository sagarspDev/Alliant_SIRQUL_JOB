# Fleetlytics Context

Read this file first in every future Codex session working on Fleetlytics. For a shorter resume-friendly snapshot, also read [overview.md](./overview.md).

## Project State

Fleetlytics currently supports a single-company, roster-driven daily pipeline for Sirqul Fleet Management and Reporting APIs. The active flow is: optional fleet discovery and reconciliation, per-fleet pull of fleet/drivers/driver scores/trip scores, JSON and CSV artifact writes, SQL generation, SQL import, and a cron-safe wrapper that maintains a daily report, healthcheck, lock file, and success watermark.

The daily runner resolves exact UTC datetime windows. It supports `rolling_24h`, `rolling_7d`, `rolling_hours`, `since_last_success`, and explicit `DATE_RANGE_START` / `DATE_RANGE_END` windows.

## Active Surface

Core runtime modules:
- `main.py` - one-shot per-fleet compatibility entrypoint
- `fleet_api.py` - Fleet Management API client plus `/fleets/search`
- `reporting_api.py` - Reporting API client for score and trip pulls
- `writers.py` - JSON/CSV artifact writers
- `src/config.py` - environment loading, validation, path helpers
- `src/http_client.py` - shared HTTP transport
- `src/logger.py` - shared logging setup

Converters:
- `Fleetlytics.converters.api` - `convert_entity(entity, run_dir)`
- `Fleetlytics.converters.cli` - converter CLI entrypoint
- `Fleetlytics.converters.fleet` - writes `sql/001_fleet.sql`
- `Fleetlytics.converters.drivers` - writes `sql/002_drivers.sql` and `sql/002_drivers.skipped.json`
- `Fleetlytics.converters.driver_scores` - writes `sql/003_driver_scores.sql`
- `Fleetlytics.converters.trip_scores` - writes `sql/004_trip_scores.sql`
- `Fleetlytics.converters.lookups` - fleet and driver lookup helpers
- `Fleetlytics.converters.snapshot` - score snapshot date resolution
- `Fleetlytics.converters.mappers` - active `map_fleet` and `map_driver` helpers; remaining row-level stubs are deferred

Importers:
- `Fleetlytics.importers.api` - `import_entity(entity, run_dir, dry_run=False)`
- `Fleetlytics.importers.cli` - importer CLI entrypoint
- `Fleetlytics.importers.fleet`
- `Fleetlytics.importers.drivers`
- `Fleetlytics.importers.driver_scores`
- `Fleetlytics.importers.trip_scores`
- `Fleetlytics.importers.trip_locations`
- `Fleetlytics.importers.trip_incidents`
- `Fleetlytics.importers.base` - shared SQL execution helpers
- `Fleetlytics.importers.reporting` - writes `import_report.json` for importer CLI runs

Daily pipeline:
- `Fleetlytics.pipeline.pull` - `configure_pull_runtime(config)`, `pull_one_fleet(req)`
- `Fleetlytics.pipeline.trip_details_backfill` - historical trip-location / trip-incident backfill from `sirqul_trip_scores`
- `Fleetlytics.pipeline.discovery` - `discover_and_reconcile_fleets(output_root, run_timestamp, dry_run=False)`
- `Fleetlytics.pipeline.window` - `resolve_daily_window()`, success-watermark helpers
- `Fleetlytics.pipeline.runner` - `run_daily(dry_run=False)`
- `Fleetlytics.pipeline.cron` - cron-safe wrapper, healthcheck, lock handling
- `Fleetlytics.pipeline.cli` - `discover`, `run-daily`, `backfill-trip-details`, and `cron` subcommands
- `Fleetlytics.pipeline.paths`, `Fleetlytics.pipeline.types` - filesystem and typed request/result helpers

Operational artifacts:
- `Fleetlytics/ops/crontab.example`
- `Fleetlytics/ops/run_daily.sh` - cron wrapper plus materialized-view refresh
- `Fleetlytics/ops/systemd.example`
- `scripts/smoke_imports.py`
- `scripts/check_supabase_connection.py`
- `view/048_trip_dashboard_rollup_views.sql`

## Daily Pipeline (Phase D)

- D1: `Fleetlytics.pipeline.pull.pull_one_fleet(req)` runs one fleet pull and writes fleet, drivers, driver scores, trip scores, trip locations, and trip incidents into one run directory.
- D2: `Fleetlytics.pipeline.discovery.discover_and_reconcile_fleets(...)` calls `POST /fleets/search`, compares results to `sirqul_fleet`, upserts numeric-ID fleets when resolvable, and writes discovery diagnostics.
- D3: `Fleetlytics.pipeline.runner.run_daily(...)` resolves the UTC datetime window, optionally runs discovery, loads the active roster, performs pull -> convert -> import per fleet, writes `daily_report.json`, and updates `last_success.json` on successful non-dry runs.
- D4: `Fleetlytics.pipeline.cron.main(argv)` wraps `run_daily()` with a single-instance `fcntl` lock, UTC-dated daily log, and `daily_health.json` heartbeat. The checked-in shell launcher then refreshes dashboard materialized views after a successful run.

Report pull behavior:
- `GL_REPORT_DATA` is fetched once per datetime window and enriched with `appInfo.appBlob.driverId`
- `GL_TRIP_DATA` is fetched once per datetime window and enriched with `appInfo.appBlob.driverId`
- `GL_LOCATION_DATA_BY_TRIP` and `GL_INCIDENT_DATA_BY_TRIP` are fetched per trip row after trip scores are available
- `sirqul_driver.driver_id` is the canonical driver join key for report rows and rollups

Public entrypoints:
- `python main.py`
- `python -m Fleetlytics.converters.cli --entity {fleet|drivers|driver_scores|trip_scores|trip_locations|trip_incidents|all}`
- `python -m Fleetlytics.importers.cli --entity {fleet|drivers|driver_scores|trip_scores|trip_locations|trip_incidents|all}`
- `python -m Fleetlytics.pipeline.cli backfill-trip-details [--start YYYY-MM-DD HH:MM:SS] [--end YYYY-MM-DD HH:MM:SS] [--dry-run]`
- `python -m Fleetlytics.pipeline.cli discover [--dry-run]`
- `python -m Fleetlytics.pipeline.cli run-daily [--dry-run]`
- `python -m Fleetlytics.pipeline.cli cron [--dry-run] [--lock-wait-seconds N]`
- `python -m Fleetlytics.pipeline.cron [--dry-run] [--lock-wait-seconds N]`

## Env Vars

| env var | required | default | notes |
| --- | --- | --- | --- |
| `FLEET_API_BASE_URL` | yes | none | Fleet Management API base URL |
| `FLEET_API_APP_KEY` | yes | none | Fleet Management API application key |
| `FLEET_API_AUTH_TOKEN` | yes | none | Fleet Management API bearer token |
| `FLEET_NETWORK_UID` | yes | none | validated as required runtime config |
| `REPORTING_API_BASE_URL` | yes | none | Reporting API base URL |
| `REPORTING_API_APP_KEY` | yes | none | Reporting API application key |
| `REPORTING_API_REST_KEY` | yes | none | Reporting API rest key |
| `REPORTING_ACCOUNT_ID` | no | blank | optional request identity for legacy flows; report pulls no longer require it |
| `TARGET_RETAILER_LOCATION_ID` | one-shot/converter/importer fallback | none | one-shot fleet selector; also converter/importer latest-run resolver |
| `DATE_RANGE_START` | conditional | blank | required with `DATE_RANGE_END` for one-shot explicit windows and `DAILY_WINDOW_MODE=env`; use full UTC datetimes |
| `DATE_RANGE_END` | conditional | blank | required with `DATE_RANGE_START`; also snapshot-date source when `SCORE_SNAPSHOT_DATE_MODE=end_date`; use full UTC datetimes |
| `OUTPUT_DIR` | no | `output` | root for pull, discovery, and daily artifacts |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_DIR` | no | `logs` | run log directory |
| `SUPABASE_DB_URL` | converter/importer/discovery DB paths | none | Postgres connection URL |
| `SUPABASE_SCHEMA` | no | `public` | schema for discovery queries and SQL imports |
| `TARGET_COMPANY_ID` | fleet conversion and discovery inserts | none | UUID in `public.companies.id` |
| `SCORE_SNAPSHOT_DATE_MODE` | no | `end_date` | `end_date`, `run_date`, or `custom` |
| `SCORE_SNAPSHOT_DATE_CUSTOM` | conditional | blank | required when `SCORE_SNAPSHOT_DATE_MODE=custom` |
| `DAILY_WINDOW_MODE` | no | `rolling_24h` | `rolling_24h`, `rolling_7d`, `rolling_hours`, `since_last_success`, `env` |
| `DAILY_WINDOW_HOURS` | conditional | blank | positive integer used when `DAILY_WINDOW_MODE=rolling_hours` |
| `DAILY_MAX_FLEETS` | no | blank | positive integer cap on roster size |
| `DAILY_FAIL_POLICY` | no | `continue` | `continue` or `fail_fast` |
| `DAILY_SKIP_DISCOVERY` | no | `false` | skip `/fleets/search` reconciliation and use `sirqul_fleet` as-is |
| `CRON_LOCK_PATH` | no | `Fleetlytics/state/daily.lock` | single-instance lock file |
| `CRON_HEALTH_PATH` | no | `Fleetlytics/state/daily_health.json` | cron healthcheck file |
| `CRON_LOG_RETENTION_DAYS` | no | `30` | retained UTC-dated daily logs |

## CLI Reference

- `python main.py` - one-shot compatibility pull for one fleet using `TARGET_RETAILER_LOCATION_ID`
- `python -m Fleetlytics.converters.cli` - generate SQL from a run directory
- `python -m Fleetlytics.importers.cli` - execute generated SQL or inspect it with `--dry-run`
- `python -m Fleetlytics.pipeline.cli discover` - discovery and reconciliation only
- `python -m Fleetlytics.pipeline.cli run-daily` - full daily discovery/pull/convert/import/report flow
- `python -m Fleetlytics.pipeline.cli cron` - same daily flow behind the cron-safe wrapper
- `python -m Fleetlytics.pipeline.cron` - scheduler-facing wrapper entrypoint
- `python scripts/smoke_imports.py` - import-only smoke check for the active Python surface
- `python scripts/check_supabase_connection.py` - manual DB connectivity probe

## Exit Code Matrix

| code | meaning | source |
| --- | --- | --- |
| `0` | success, including partial fleet failures under `continue` as long as at least one attempted fleet finished `ok` or `partial` | `run_daily()`, one-shot `main.py` |
| `1` | `fail_fast` stopped the run, all attempted fleets failed, or the cron wrapper crashed | `run_daily()`, `pipeline.cron` |
| `2` | discovery failed under `fail_fast`, active roster was empty, or a CLI-level configuration error was raised | `run_daily()`, `pipeline.cli`, `main.py` |
| `75` | cron lock contention | `pipeline.cron` |

## Output Layout

One-shot and daily fleet pulls write into `OUTPUT_DIR/<fleet_internal_id>/<run_timestamp>/`. Daily discovery and rollup artifacts write into `_discovery` and `_daily` siblings under the same `OUTPUT_DIR`.

```text
output/
  <fleet_internal_id>/
    <run_timestamp>/
      fleet.json
      fleet.csv
      drivers.json
      drivers.csv
      driver_scores.json
      driver_scores.csv
      trip_scores.json
      trip_scores.csv
      trip_locations.json
      trip_locations.csv
      trip_incidents.json
      trip_incidents.csv
      sql/
        001_fleet.sql
        002_drivers.sql
        002_drivers.skipped.json
        003_driver_scores.sql
        004_trip_scores.sql
        005_trip_locations.sql
        006_trip_incidents.sql
      import_report.json          # importer CLI only
  _discovery/
    <run_timestamp>/
      fleets_search_raw.json
      reconciliation_summary.json
      pending_fleets.json
  _daily/
    <run_timestamp>/
      daily_report.json
    latest/
      daily_report.json

Fleetlytics/state/
  last_success.json
  daily.lock
  daily_health.json

logs/
  fleetlytics_<timestamp>.log
  daily_YYYY-MM-DD.log
  cron_stdout.log                # only when using the shell wrapper redirect
```

Notes:
- `main.py` uses `YYYY-MM-DD_HH-MM-SS_UTC` run timestamps.
- `run_daily()` currently uses `YYYY-MM-DD_HHMMSS` run timestamps for fleet, discovery, and daily output directories.
- Importer `--dry-run` does not write to the database, but it still reads generated SQL and may write `import_report.json`.

## Deferred / Scaffold

Intentionally deferred files:
- `src/main.py`
- `future/scheduler.py`
- `future/companies_loader.py`
- `future/supabase_sink.py`
- `future/ddl_mapper.py`

Partially deferred:
- `Fleetlytics/converters/mappers.py` is active for `map_fleet` and `map_driver`. The unimplemented row-level helper stubs remain deferred for later phases.

Do not expand the deferred surface unless a later phase explicitly asks for it.

## Operational Notes

- Discovery insert policy: new fleets are auto-upserted only when `TARGET_COMPANY_ID` resolves to an existing `public.companies.id` row and the discovered `internal_id` is numeric so it can be cast to `retailer_location_id`.
- Non-numeric discovered fleet IDs are written to `pending_fleets.json`; the reconciler does not invent a synthetic primary key.
- `since_last_success` uses `Fleetlytics/state/last_success.json` and caps lookback at 30 days.
- `last_success.json` is only updated when `run_daily()` exits `0` and `dry_run=False`.
- `daily_health.json` is overwritten after every cron-wrapper invocation, including `locked` and `crashed` outcomes.
- `pipeline.cron` uses `fcntl.flock` against `CRON_LOCK_PATH` and returns `75` when the lock deadline expires.
- The cron wrapper adds `logs/daily_YYYY-MM-DD.log`; normal non-cron entrypoints use `logs/fleetlytics_<timestamp>.log`.
- `Fleetlytics/ops/run_daily.sh` is the checked-in cron launcher; its shell redirection is what produces `logs/cron_stdout.log` in the example crontab.
- After a successful cron pipeline run, `Fleetlytics/ops/run_daily.sh` refreshes the five dashboard materialized views with `REFRESH MATERIALIZED VIEW CONCURRENTLY ...` using `SUPABASE_DB_URL`.

## Open Questions / Next Phase Candidates

- Multi-company support: `TARGET_COMPANY_ID` is currently single-valued; the daily pipeline assumes one company.
- `retailer_location_id` derivation policy (D2): the `int(internal_id)` fallback is brittle; revisit when canonical mapping is known.
- Alerting on `daily_health.json` (email/Slack/PagerDuty webhook).
- Backfill mode: re-pull a historical UTC datetime range across all fleets without disturbing the watermark.
- `since_last_success` window mode hasn't been exercised in anger; add an integration test once a real schedule is running.

## Changelog

- Phase D closeout: consolidated runtime docs around the active daily pipeline, added `scripts/smoke_imports.py`, cleaned `.env.example`, and labeled deferred scaffolding.
