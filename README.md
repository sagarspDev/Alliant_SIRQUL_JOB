# Fleetlytics

Fleetlytics pulls data from Sirqul Fleet and Reporting APIs, writes run artifacts to disk, converts them to SQL, and imports them into PostgreSQL/Supabase-backed tables. The repository also includes a cron-safe daily runner, discovery workflow, historical trip-detail backfill flow, and deployment tooling for running on Linux servers.

This README is the primary operational reference for developers, DevOps engineers, system administrators, and support engineers.

## 1. Project Overview

Fleetlytics currently supports:

- one-shot fleet pulls through `python main.py`
- multi-fleet daily orchestration through `python -m Fleetlytics.pipeline.cli run-daily`
- cron-safe scheduling through `python -m Fleetlytics.pipeline.cron`
- JSON-to-SQL conversion and SQL import CLIs
- historical trip-detail backfill from stored trip-score data

The codebase keeps the existing `Fleetlytics` package and file names unchanged for compatibility.

## 2. Features

- Pulls fleet, driver, driver score, trip score, trip location, and trip incident data
- Writes timestamped run artifacts under `OUTPUT_DIR`
- Converts run artifacts into SQL files for database ingestion
- Imports SQL into PostgreSQL-compatible targets using `psycopg`
- Supports discovery and reconciliation against `sirqul_fleet`
- Supports cron and systemd scheduling
- Uses file locking to prevent overlapping scheduled runs
- Writes health summaries for external monitoring
- Supports separate production, UAT, and test environments on one server

## 3. Architecture Overview

Runtime flow:

1. Load environment variables from `.env` or an explicit env file.
2. Resolve the execution window.
3. Call Fleet and Reporting APIs.
4. Write raw artifacts under `OUTPUT_DIR`.
5. Convert artifacts to SQL.
6. Import SQL into PostgreSQL/Supabase.
7. Write logs and scheduler health summaries.

Primary runtime entrypoints:

- `main.py`: one-shot pull
- `python -m Fleetlytics.pipeline.cli run-daily`: multi-fleet daily pipeline
- `python -m Fleetlytics.pipeline.cron`: cron-safe wrapper with lock and health file
- `python -m Fleetlytics.converters.cli`: JSON-to-SQL conversion
- `python -m Fleetlytics.importers.cli`: SQL import

## 4. Folder Structure

```text
.
├── Fleetlytics/                 # Core pipeline, converters, importers, ops examples, state
├── src/                         # Shared config, logging, HTTP client
├── scripts/                     # Validation and launch helpers
├── Docs/                        # SQL reference and API reference material
├── docs/                        # Deployment and operational documentation
├── config/environments/         # Environment templates
├── main.py                      # One-shot compatibility entrypoint
├── fleet_api.py                 # Fleet API client
├── reporting_api.py             # Reporting API client
├── writers.py                   # Artifact writers
├── cron_examples.md             # Cron schedule quick reference
└── CHANGELOG.md                 # Repo-level change log
```

Runtime-generated directories:

- `output/`
- `logs/`
- `Fleetlytics/state/` runtime files such as locks and health summaries

## 5. Prerequisites

- Linux server or RDC environment with shell access
- Python 3.12 recommended
- Network access to:
  - Fleet API
  - Reporting API
  - PostgreSQL/Supabase
- A service user with permission to write to configured `OUTPUT_DIR`, `LOG_DIR`, and `CRON_*` paths

## 6. Installation

```bash
git clone https://github.com/sagarspDev/Alliant_SIRQUL_JOB.git /opt/fleetlytics
cd /opt/fleetlytics
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If Python 3.12 is not the default interpreter on the host, use the explicit binary path provided by your OS package or runtime manager.

## 7. Environment Variables

Core API variables:

- `FLEET_API_BASE_URL`: Fleet API base URL, required
- `FLEET_API_APP_KEY`: Fleet API application key, required
- `FLEET_API_AUTH_TOKEN`: Fleet API bearer token, required
- `FLEET_NETWORK_UID`: Fleet network identifier, required
- `REPORTING_API_BASE_URL`: Reporting API base URL, required
- `REPORTING_API_APP_KEY`: Reporting API application key, required
- `REPORTING_API_REST_KEY`: Reporting API REST key, required
- `REPORTING_ACCOUNT_ID`: optional legacy account identity

Run selection:

- `TARGET_RETAILER_LOCATION_ID`: required for one-shot pulls and converter/importer auto-resolution
- `DATE_RANGE_START`: optional explicit UTC datetime, must be paired with `DATE_RANGE_END`
- `DATE_RANGE_END`: optional explicit UTC datetime, must be paired with `DATE_RANGE_START`

Daily orchestration:

- `DAILY_WINDOW_MODE`: `rolling_24h`, `rolling_7d`, `rolling_hours`, `since_last_success`, or `env`
- `DAILY_WINDOW_HOURS`: required when `DAILY_WINDOW_MODE=rolling_hours`
- `DAILY_MAX_FLEETS`: optional positive integer cap
- `DAILY_FAIL_POLICY`: `continue` or `fail_fast`
- `DAILY_SKIP_DISCOVERY`: `true` or `false`

Database and conversion:

- `SUPABASE_DB_URL`: PostgreSQL connection string, required for DB connectivity, discovery, and imports
- `SUPABASE_SCHEMA`: schema name, default `public`
- `TARGET_COMPANY_ID`: required for fleet conversion and discovery inserts
- `SCORE_SNAPSHOT_DATE_MODE`: `end_date`, `run_date`, or `custom`
- `SCORE_SNAPSHOT_DATE_CUSTOM`: required when snapshot mode is `custom`

Output, logging, scheduler:

- `OUTPUT_DIR`: artifact root, default `output`
- `LOG_DIR`: log root, default `logs`
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, or `ERROR`
- `CRON_LOCK_PATH`: file lock path for scheduled runs
- `CRON_HEALTH_PATH`: JSON status file written after cron runs
- `CRON_LOG_RETENTION_DAYS`: daily log retention for the cron wrapper
- `RUN_LOG_MAX_BYTES`: per-run log file rotation size, default `5242880`
- `RUN_LOG_BACKUP_COUNT`: number of rotated run logs to keep, default `3`

HTTP behavior:

- `HTTP_TIMEOUT_SECONDS`: request timeout, default `30`
- `HTTP_RETRY_COUNT`: retry count, default `3`
- `HTTP_BACKOFF_FACTOR`: retry backoff factor, default `0.5`

See `.env.example` for the full template. For deployment-ready examples, see:

- `config/environments/.env.production.example`
- `config/environments/.env.uat.example`
- `config/environments/.env.test.example`
- `docs/configuration.md`

## 8. Configuration

Recommended production pattern:

1. Keep local development on `.env` if needed.
2. Use named env files under `config/environments/` for deployed environments.
3. Use unique `OUTPUT_DIR`, `LOG_DIR`, `CRON_LOCK_PATH`, and `CRON_HEALTH_PATH` per environment.
4. Use UTC consistently in all schedules and explicit date windows.

Create a real production env file:

```bash
cp config/environments/.env.production.example config/environments/.env.production
```

## 9. Running the Script

One-shot pull:

```bash
python main.py
python main.py --retailer-location-id 353787
python main.py --start "2026-06-01 00:00:00" --end "2026-06-07 00:00:00"
```

Daily pipeline:

```bash
python -m Fleetlytics.pipeline.cli run-daily
python -m Fleetlytics.pipeline.cli run-daily --dry-run
python -m Fleetlytics.pipeline.cli run-daily --window-hours 6
```

Backfill trip details:

```bash
python -m Fleetlytics.pipeline.cli backfill-trip-details --start "2026-06-01 00:00:00" --end "2026-06-24 00:00:00"
```

Env-file launcher:

```bash
scripts/run_fleetlytics.sh --env-file config/environments/.env.production -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0
```

## 10. Running with Cron

Cron-safe entrypoint:

```bash
python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0
```

Recommended production pattern:

```cron
CRON_TZ=UTC
0 8 * * * /opt/fleetlytics/scripts/run_fleetlytics.sh --env-file /opt/fleetlytics/config/environments/.env.production -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0 >> /var/log/fleetlytics/production/cron_stdout.log 2>&1
```

See:

- `cron_examples.md`
- `Fleetlytics/ops/crontab.example`

## 11. Running Multiple Environments

Example environments:

- `config/environments/.env.production`
- `config/environments/.env.uat`
- `config/environments/.env.test`

UAT and Test can run simultaneously on the same host as long as they do not share:

- API credentials
- database DSN
- output path
- log path
- lock path
- health path

See `docs/multi-environment.md` for side-by-side cron and systemd examples.

## 12. Logging

Logging outputs:

- Run logs: `LOG_DIR/fleetlytics_YYYYMMDD_HHMMSS.log`
- Cron daily logs: `LOG_DIR/daily_YYYY-MM-DD.log`
- Cron stdout/stderr: usually redirected to `LOG_DIR/cron_stdout.log`
- Health file: `CRON_HEALTH_PATH`

Log behavior:

- Run logs use rotating files controlled by `RUN_LOG_MAX_BYTES` and `RUN_LOG_BACKUP_COUNT`
- Cron daily logs are retained based on `CRON_LOG_RETENTION_DAYS`
- Scheduled runs write a JSON health summary for monitoring

## 13. Troubleshooting

- `Configuration error`: compare deployed env values with `.env.example`
- `exit_code 75`: a previous scheduled run still holds `CRON_LOCK_PATH`
- API call failures: verify credentials, host resolution, firewall rules, and TLS reachability
- DB failures: verify `SUPABASE_DB_URL`, schema access, and grants
- Empty outputs: verify date window, active fleets, and `OUTPUT_DIR` permissions
- Missing logs: verify `LOG_DIR` permissions and cron/systemd stdout redirection

## 14. Common Commands

Inspect CLI help:

```bash
python main.py --help
python -m Fleetlytics.pipeline.cli --help
python -m Fleetlytics.pipeline.cron --help
python -m Fleetlytics.converters.cli --help
python -m Fleetlytics.importers.cli --help
```

Validation commands:

```bash
python scripts/smoke_imports.py
python scripts/check_api_connectivity.py
python scripts/check_supabase_connection.py
scripts/validate_installation.sh
```

Conversion and import:

```bash
python -m Fleetlytics.converters.cli --entity all
python -m Fleetlytics.importers.cli --entity all --dry-run
```

## 15. Deployment Guide

Full Linux deployment instructions are in `docs/deployment.md`.

Recommended deployment order:

1. Clone the repository.
2. Create the virtualenv.
3. Install dependencies.
4. Create the real env file from a template.
5. Create output, log, and state directories.
6. Run validation commands.
7. Enable cron or systemd.
8. Verify the health file, logs, and first successful run.

## 16. DevOps Notes

- Both cron and systemd are supported equally.
- Use absolute paths in all scheduler entries.
- Keep environment files outside version control and restrict file permissions.
- Prefer per-environment directories under `/opt/fleetlytics/var/` and `/var/log/fleetlytics/`.
- Keep UTC as the standard for schedules and date windows.

## 17. FAQ

Q: Should production use `.env` directly?

A: Local development can use `.env`, but production should prefer named env files under `config/environments/` and call the app through `scripts/run_fleetlytics.sh`.

Q: Can test and UAT run on the same host?

A: Yes, if each environment uses different credentials, database targets, logs, output directories, lock files, and health files.

Q: How do I confirm a scheduler run succeeded?

A: Check the command exit code, `CRON_HEALTH_PATH`, `LOG_DIR/daily_YYYY-MM-DD.log`, and recent files under `OUTPUT_DIR`.

Q: Which scheduler should I choose?

A: Use whichever fits the host standard. Cron and systemd are both supported in this repository.

## 18. Maintenance Guide

Routine maintenance:

- Review and rotate secrets periodically
- Review dependency updates and pin reviewed versions
- Remove stale output artifacts based on retention policy
- Review scheduler health and daily logs
- Validate database connectivity after credential or network changes

Supporting documents:

- `docs/deployment.md`
- `docs/operations.md`
- `docs/multi-environment.md`
- `docs/devops-handover-checklist.md`
- `docs/production-readiness-review.md`
- `docs/risk-assessment.md`
- `docs/best-practices.md`
- `cron_examples.md`

## Additional References

- `commands.md`: command catalog
- `FLEETLYTICS_CONTEXT.md`: implementation context and current assumptions
- `overview.md`: compact architecture snapshot
