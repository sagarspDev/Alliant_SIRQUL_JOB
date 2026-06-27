# Deployment Guide

## Target platform

- OS: Ubuntu 22.04+, Debian 12+, or equivalent Linux distribution
- Python: 3.12 recommended
- Scheduler: cron or systemd timer
- Database: PostgreSQL-compatible connection reachable from the host

## Clone and install

```bash
git clone https://github.com/sagarspDev/Alliant_SIRQUL_JOB.git /opt/fleetlytics
cd /opt/fleetlytics
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Configure the environment

1. Copy the closest template from `config/environments/`.
2. Save the real file outside version control, for example:

```bash
cp config/environments/.env.production.example config/environments/.env.production
```

3. Update credentials, database DSN, output/log/state paths, and scheduling values.
4. Create writable directories referenced by `OUTPUT_DIR`, `LOG_DIR`, and `CRON_*`.

```bash
mkdir -p /opt/fleetlytics/var/output/production
mkdir -p /opt/fleetlytics/var/state/production
mkdir -p /var/log/fleetlytics/production
```

## Manual validation

Run these before enabling a scheduler:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python scripts/smoke_imports.py
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python scripts/check_api_connectivity.py
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python scripts/check_supabase_connection.py
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python -m Fleetlytics.pipeline.cli run-daily --dry-run
```

## Run manually

One-shot fleet pull:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python main.py
```

Daily pipeline:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python -m Fleetlytics.pipeline.cli run-daily
```

Cron-safe entrypoint:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0
```

## Enable cron

Use `Fleetlytics/ops/crontab.example` or install a tailored entry:

```bash
crontab -e
```

Then verify:

```bash
crontab -l
tail -f /var/log/fleetlytics/production/cron_stdout.log
cat /opt/fleetlytics/var/state/production/daily_health.json
```

## Enable systemd

Copy the template from `Fleetlytics/ops/systemd.example`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fleetlytics@production.timer
sudo systemctl list-timers | grep fleetlytics
sudo journalctl -u fleetlytics@production.service -n 100 --no-pager
```

## Troubleshooting

- `Configuration error`: compare the deployed env file against `.env.example`
- `exit_code 75`: another scheduler instance still holds the lock file
- API failure: verify credentials, network egress, DNS, and TLS reachability
- DB failure: verify `SUPABASE_DB_URL`, firewall rules, and database grants
- No output written: confirm `OUTPUT_DIR` and `LOG_DIR` are writable by the service user
