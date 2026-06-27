# Cron Examples

All examples assume the repository is deployed to `/opt/fleetlytics`, uses the shared launcher at `scripts/run_fleetlytics.sh`, and runs in UTC.

## Every 15 Minutes

- Expression: `*/15 * * * *`
- Executes: every 15 minutes
- Use case: near-real-time UAT validation or small rolling windows
- Expected behavior: runs the cron-safe wrapper, acquires the environment-specific lock, updates `daily_health.json`, and appends cron stdout/stderr to the configured log

```cron
*/15 * * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.uat -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/uat/cron_stdout.log 2>&1
```

## Every Hour

- Expression: `0 * * * *`
- Executes: at minute 0 of every hour
- Use case: hourly synchronization in UAT or low-volume production environments
- Expected behavior: one run per hour with lock protection against overlap

```cron
0 * * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.uat -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/uat/cron_stdout.log 2>&1
```

## Daily

- Expression: `0 8 * * *`
- Executes: every day at 08:00 UTC
- Use case: standard production daily rollup
- Expected behavior: runs discovery, pull, convert, import, writes the daily report, and refreshes the health file

```cron
0 8 * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.production -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/production/cron_stdout.log 2>&1
```

## Weekly

- Expression: `0 2 * * 1`
- Executes: every Monday at 02:00 UTC
- Use case: lower-frequency reconciliation or manual backfill environments
- Expected behavior: same pipeline behavior with a weekly cadence

```cron
0 2 * * 1 /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.uat -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/uat/cron_stdout.log 2>&1
```

## Monthly

- Expression: `0 3 1 * *`
- Executes: on the first day of each month at 03:00 UTC
- Use case: low-frequency validation or historical maintenance jobs
- Expected behavior: same pipeline behavior with a monthly cadence

```cron
0 3 1 * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.test -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/test/cron_stdout.log 2>&1
```

## Cron Operations

- Install: `crontab Fleetlytics/ops/crontab.example`
- Update: `crontab -e`
- Remove: `crontab -r`
- Verify installed jobs: `crontab -l`
- Verify execution: inspect `LOG_DIR/daily_YYYY-MM-DD.log`, `cron_stdout.log`, and `CRON_HEALTH_PATH`
- Troubleshoot:
  - use absolute paths only
  - confirm the env file exists and is readable
  - confirm the virtualenv exists if the launcher relies on `.venv`
  - check lock contention when exit code `75` appears
  - run the exact command manually with the same env file
