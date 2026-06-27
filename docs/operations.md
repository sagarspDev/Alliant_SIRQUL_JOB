# Operational Guide

## Common commands

Manual one-shot pull:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python main.py
```

Run for yesterday using explicit UTC boundaries:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- \
  python main.py --start "2026-06-26 00:00:00" --end "2026-06-27 00:00:00"
```

Run for today so far:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- \
  python main.py --start "2026-06-27 00:00:00" --end "2026-06-27 23:59:59"
```

Run a custom date range:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- \
  python main.py --start "2026-06-01 00:00:00" --end "2026-06-07 00:00:00"
```

Run the last 7 days through the daily pipeline:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- \
  python -m Fleetlytics.pipeline.cli run-daily --window-hours 168
```

Backfill historical trip details:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- \
  python -m Fleetlytics.pipeline.cli backfill-trip-details --start "2026-06-01 00:00:00" --end "2026-06-24 00:00:00"
```

## Restart after failure

- Fix the underlying API, database, or credential problem.
- Re-run the failed command manually with the same env file.
- Check `CRON_HEALTH_PATH` and the daily log before re-enabling the scheduler.

## Resume interrupted execution

- The cron wrapper prevents overlap with `CRON_LOCK_PATH`.
- Daily window mode `since_last_success` can resume from the last success watermark if that mode is enabled.
- For one-shot reruns, re-run the exact command with the original date window.

## Verify successful execution

- Inspect the exit code from the command or scheduler.
- Inspect `CRON_HEALTH_PATH`.
- Review `LOG_DIR/daily_YYYY-MM-DD.log` and the run-specific `fleetlytics_*.log`.
- Confirm fresh files under `OUTPUT_DIR`.

## Verify database updates

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python scripts/check_supabase_connection.py
```

## Check logs

- Execution logs: `LOG_DIR/fleetlytics_*.log`
- Daily scheduler logs: `LOG_DIR/daily_YYYY-MM-DD.log`
- Cron stdout/stderr: `LOG_DIR/cron_stdout.log`
- Health summary: `CRON_HEALTH_PATH`
