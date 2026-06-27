# Configuration Reference

All datetimes are UTC and use `YYYY-MM-DD HH:MM:SS` unless noted otherwise.

| Variable | Purpose | Required | Default | Example |
| --- | --- | --- | --- | --- |
| `FLEET_API_BASE_URL` | Fleet Management API base URL | Yes | None | `https://fleetshare.bmrang.com:3003` |
| `FLEET_API_APP_KEY` | Fleet Management API application key | Yes | None | `prod-fleet-app-key` |
| `FLEET_API_AUTH_TOKEN` | Fleet Management API bearer token | Yes | None | `eyJhbGciOi...` |
| `FLEET_NETWORK_UID` | Fleet network UID used by Fleet API flows | Yes | None | `network-123` |
| `REPORTING_API_BASE_URL` | Reporting API base URL | Yes | None | `https://fleetshare.bmrang.com` |
| `REPORTING_API_APP_KEY` | Reporting API application key | Yes | None | `prod-reporting-app-key` |
| `REPORTING_API_REST_KEY` | Reporting API REST key | Yes | None | `reporting-rest-key` |
| `REPORTING_ACCOUNT_ID` | Optional legacy reporting account identity | No | Blank | `353787` |
| `TARGET_RETAILER_LOCATION_ID` | Default fleet selector for one-shot pulls and latest-run resolution | Conditional | Blank | `353787` |
| `DATE_RANGE_START` | Explicit start datetime for one-shot or `DAILY_WINDOW_MODE=env` | Conditional | Blank | `2026-06-01 00:00:00` |
| `DATE_RANGE_END` | Explicit end datetime for one-shot or `DAILY_WINDOW_MODE=env` | Conditional | Blank | `2026-06-02 00:00:00` |
| `DAILY_WINDOW_MODE` | Daily window calculation mode | No | `rolling_24h` | `utc_day` |
| `DAILY_WINDOW_HOURS` | Window length when `DAILY_WINDOW_MODE=rolling_hours` | Conditional | Blank | `6` |
| `DAILY_MAX_FLEETS` | Max fleets processed in one daily run | No | Blank | `25` |
| `DAILY_FAIL_POLICY` | Daily pipeline failure strategy | No | `continue` | `fail_fast` |
| `DAILY_SKIP_DISCOVERY` | Skip fleet discovery phase | No | `false` | `true` |
| `OUTPUT_DIR` | Root directory for pulled artifacts and reports | No | `output` | `/opt/fleetlytics/var/output/production` |
| `LOG_DIR` | Root directory for application and scheduler logs | No | `logs` | `/var/log/fleetlytics/production` |
| `LOG_LEVEL` | Log verbosity | No | `INFO` | `DEBUG` |
| `CRON_LOCK_PATH` | Lock file path used by the cron-safe wrapper | No | `Fleetlytics/state/daily.lock` | `/opt/fleetlytics/var/state/production/daily.lock` |
| `CRON_HEALTH_PATH` | Health summary JSON path | No | `Fleetlytics/state/daily_health.json` | `/opt/fleetlytics/var/state/production/daily_health.json` |
| `CRON_LOG_RETENTION_DAYS` | Retention count for UTC-dated daily cron logs | No | `30` | `14` |
| `RUN_LOG_MAX_BYTES` | Max size of each run log before rotation | No | `5242880` | `10485760` |
| `RUN_LOG_BACKUP_COUNT` | Number of rotated run logs to retain | No | `3` | `5` |
| `HTTP_TIMEOUT_SECONDS` | Timeout per HTTP request | No | `30` | `45` |
| `HTTP_RETRY_COUNT` | HTTP retry count for API calls | No | `3` | `5` |
| `HTTP_BACKOFF_FACTOR` | HTTP retry backoff factor | No | `0.5` | `1.0` |
| `SUPABASE_DB_URL` | PostgreSQL/Supabase DSN | Conditional | None | `postgresql://user:pass@db-host:5432/dbname` |
| `SUPABASE_SCHEMA` | Target schema name | No | `public` | `public` |
| `SCORE_SNAPSHOT_DATE_MODE` | Driver score snapshot date source | No | `end_date` | `custom` |
| `SCORE_SNAPSHOT_DATE_CUSTOM` | Snapshot date used when snapshot mode is `custom` | Conditional | Blank | `2026-06-27` |

Conditional guidance:

- `TARGET_RETAILER_LOCATION_ID` is required when running `python main.py` without `--retailer-location-id` and when converter/importer commands omit `--run-dir`.
- `DATE_RANGE_START` and `DATE_RANGE_END` must be set together or both omitted.
- `SUPABASE_DB_URL` is required for DB connectivity checks, discovery, conversion lookups, import, and trip-detail backfill.
- `DAILY_WINDOW_MODE=utc_day` resolves each run to `00:00:00 UTC` through `00:00:00 UTC` of the next day.
- Company-to-fleet mapping is resolved from `public.companies.focus_data->'eventInfo'->>'flAccountId'`; fleets without a matching company are skipped.
