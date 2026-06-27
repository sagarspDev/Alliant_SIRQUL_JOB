# Multiple Environment Deployment

Fleetlytics can run `production`, `uat`, and `test` on the same server as long as each environment uses isolated paths and credentials.

## Required isolation

Each environment must have its own values for:

- API credentials
- `SUPABASE_DB_URL`
- `OUTPUT_DIR`
- `LOG_DIR`
- `CRON_LOCK_PATH`
- `CRON_HEALTH_PATH`

## Example env files

- `config/environments/.env.production`
- `config/environments/.env.uat`
- `config/environments/.env.test`

## Example concurrent cron jobs

```cron
CRON_TZ=UTC

0 8 * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.production -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/production/cron_stdout.log 2>&1
15 8 * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.uat -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/uat/cron_stdout.log 2>&1
30 8 * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.test -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/test/cron_stdout.log 2>&1
```

## Example concurrent systemd timers

```bash
sudo systemctl enable --now fleetlytics@production.timer
sudo systemctl enable --now fleetlytics@uat.timer
sudo systemctl enable --now fleetlytics@test.timer
```

## Validation

Run each environment independently:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.uat -- python scripts/check_api_connectivity.py
scripts/run_fleetlytics.sh --env-file config/environments/.env.test -- python scripts/check_supabase_connection.py
```

No environment should share the same lock, health, output, or log path.
