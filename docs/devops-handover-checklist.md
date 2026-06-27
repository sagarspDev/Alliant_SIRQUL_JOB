# DevOps Handover Checklist

## Server requirements

- Linux server with outbound access to Sirqul APIs and the target PostgreSQL instance
- Python 3.12
- `python3-venv`, `pip`, `cron` or `systemd`
- A service account with read access to the repo and write access to output/log/state paths
- DNS, firewall, and TLS access to:
  - `FLEET_API_BASE_URL`
  - `REPORTING_API_BASE_URL`
  - PostgreSQL host from `SUPABASE_DB_URL`

## Deployment steps

1. Clone the repository into `/opt/fleetlytics` or another fixed path.
2. Create the virtual environment and install `requirements.txt`.
3. Create the real env file from the appropriate example template.
4. Create the output, log, and state directories referenced in that env file.
5. Run smoke, API, and DB validation commands.
6. Install either cron or systemd scheduling.
7. Verify logs, health file, and first successful execution.

## Validation checklist

- `python scripts/smoke_imports.py` passes
- `python scripts/check_api_connectivity.py` passes
- `python scripts/check_supabase_connection.py` passes
- `python -m Fleetlytics.pipeline.cli run-daily --dry-run` passes
- Scheduler entry is installed and visible
- `CRON_HEALTH_PATH` updates after a scheduled run
- `LOG_DIR` contains current execution logs
- `OUTPUT_DIR` receives fresh run artifacts
