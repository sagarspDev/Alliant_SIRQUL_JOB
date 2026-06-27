# Fleetlytics Commands

This file is the operator-facing command catalog for the implemented Fleetlytics scripts and CLIs.

## Step 1: Environment Setup

Create the virtualenv, install dependencies, and prepare `.env`.

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Step 2: Inspect Available CLI Surfaces

Use these commands first when checking the current flag surface.

```bash
python main.py --help
python writers.py --help
python -m Fleetlytics.converters.cli --help
python -m Fleetlytics.importers.cli --help
python -m Fleetlytics.pipeline.cli --help
python -m Fleetlytics.pipeline.cli discover --help
python -m Fleetlytics.pipeline.cli run-daily --help
python -m Fleetlytics.pipeline.cli cron --help
python -m Fleetlytics.pipeline.cli backfill-trip-details --help
python -m Fleetlytics.pipeline.cron --help
```

## Step 3: Run A One-Shot Fleet Pull

Use the compatibility entrypoint for a single fleet.

```bash
python main.py
```

Override the fleet or date window explicitly:

```bash
python main.py --retailer-location-id 353787
python main.py --start "2026-06-01 00:00:00" --end "2026-06-15 00:00:00"
python main.py --retailer-location-id 353787 --start "2026-06-01 00:00:00" --end "2026-06-15 00:00:00"
```

Note: `python main.py --dry-run` is currently a compatibility flag and still writes pull artifacts.

## Step 4: Replay CSV Output From Existing JSON

Regenerate `fleet.csv` and `drivers.csv` from an existing run directory.

```bash
python writers.py --replay output/<fleet_internal_id>/<run_timestamp>
```

## Step 5: Generate SQL From A Run Directory

Generate SQL for one entity using the latest run for `TARGET_RETAILER_LOCATION_ID`:

```bash
python -m Fleetlytics.converters.cli --entity fleet
python -m Fleetlytics.converters.cli --entity drivers
python -m Fleetlytics.converters.cli --entity driver_scores
python -m Fleetlytics.converters.cli --entity trip_scores
python -m Fleetlytics.converters.cli --entity trip_locations
python -m Fleetlytics.converters.cli --entity trip_incidents
python -m Fleetlytics.converters.cli --entity all
```

Generate SQL from a specific run directory:

```bash
python -m Fleetlytics.converters.cli --entity drivers --run-dir output/<fleet_internal_id>/<run_timestamp>
python -m Fleetlytics.converters.cli --entity all --run-dir output/<fleet_internal_id>/<run_timestamp>
```

## Step 6: Import Generated SQL

Preview SQL execution without committing:

```bash
python -m Fleetlytics.importers.cli --entity fleet --dry-run
python -m Fleetlytics.importers.cli --entity drivers --dry-run
python -m Fleetlytics.importers.cli --entity driver_scores --dry-run
python -m Fleetlytics.importers.cli --entity trip_scores --dry-run
python -m Fleetlytics.importers.cli --entity trip_locations --dry-run
python -m Fleetlytics.importers.cli --entity trip_incidents --dry-run
python -m Fleetlytics.importers.cli --entity all --dry-run
```

Execute imports:

```bash
python -m Fleetlytics.importers.cli --entity fleet
python -m Fleetlytics.importers.cli --entity drivers
python -m Fleetlytics.importers.cli --entity driver_scores
python -m Fleetlytics.importers.cli --entity trip_scores
python -m Fleetlytics.importers.cli --entity trip_locations
python -m Fleetlytics.importers.cli --entity trip_incidents
python -m Fleetlytics.importers.cli --entity all
```

Import from a specific run directory:

```bash
python -m Fleetlytics.importers.cli --entity drivers --run-dir output/<fleet_internal_id>/<run_timestamp>
python -m Fleetlytics.importers.cli --entity all --run-dir output/<fleet_internal_id>/<run_timestamp> --dry-run
```

## Step 7: Run Discovery Only

Run fleet discovery and reconciliation without the full daily pipeline:

```bash
python -m Fleetlytics.pipeline.cli discover
python -m Fleetlytics.pipeline.cli discover --dry-run
```

## Step 8: Run The Daily Pipeline

Dry-run the full daily flow:

```bash
python -m Fleetlytics.pipeline.cli run-daily --dry-run
```

Run the full daily flow:

```bash
python -m Fleetlytics.pipeline.cli run-daily
python -m Fleetlytics.pipeline.cli run-daily --window-hours 1
```

## Step 8b: Run The Trip-Detail Backfill

Backfill trip locations and trip incidents from the trip-score table for an explicit UTC datetime range:

```bash
python -m Fleetlytics.pipeline.cli backfill-trip-details --start "2026-06-01 00:00:00" --end "2026-06-23 00:00:00"
```

Use an exclusive end boundary. For example, to include all data through `2026-06-23 23:59:59` UTC, pass `--end "2026-06-24 00:00:00"`.

The checked-in wrapper script uses the June 1 00:00:00 UTC to yesterday UTC boundary by default:

```bash
bash Fleetlytics/ops/run_trip_details_backfill.sh
```

## Step 9: Run The Cron-Safe Wrapper

Use the wrapper via the multi-command pipeline CLI:

```bash
python -m Fleetlytics.pipeline.cli cron --dry-run
python -m Fleetlytics.pipeline.cli cron --lock-wait-seconds 30
python -m Fleetlytics.pipeline.cli cron --window-hours 2
```

Call the scheduler-facing entrypoint directly:

```bash
python -m Fleetlytics.pipeline.cron --dry-run
python -m Fleetlytics.pipeline.cron --lock-wait-seconds 30
python -m Fleetlytics.pipeline.cron --dry-run --lock-wait-seconds 30
python -m Fleetlytics.pipeline.cron --window-hours 24
```

`--window-hours` switches the daily runner into `rolling_hours` mode and accepts any positive integer.

When executed as a plain script, `Fleetlytics/pipeline/cron.py` prints resolved paths:

```bash
python Fleetlytics/pipeline/cron.py
```

## Step 10: Run Smoke And Verification Checks

Import-only smoke check:

```bash
python scripts/smoke_imports.py
```

Database connectivity check:

```bash
python scripts/check_supabase_connection.py
```

Healthcheck inspection after a cron run:

```bash
cat Fleetlytics/state/daily_health.json
jq . Fleetlytics/state/daily_health.json
jq -e '.status == "ok" or .status == "partial"' Fleetlytics/state/daily_health.json
```

## Step 11: Scheduling Helpers

Reference files for scheduled runs:

```bash
cat Fleetlytics/ops/crontab.example
cat Fleetlytics/ops/systemd.example
```

Run the checked-in cron wrapper shell script directly:

```bash
bash Fleetlytics/ops/run_daily.sh
```

This script now:

1. loads `.env`
2. activates `.venv` when present
3. runs `python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0`
4. lets the cron entrypoint refresh the dashboard materialized views after a successful run

## Step 12: Dashboard View Refresh SQL

The checked-in wrapper performs this automatically after a successful scheduled run. For manual refreshes, use this order:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_sirqul_driver_trip_list;
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_sirqul_trip_day_rollup;
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_sirqul_performance_groups;
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_sirqul_trip_event_day_rollup;
REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_sirqul_trip_event_groups;
```
