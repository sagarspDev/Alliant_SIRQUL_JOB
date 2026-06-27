# Sirqul Backfill Plan

## Current Status

- `sirqul_driver` has been recreated with `driver_id` as a nullable unique column.
- Driver and report pull code now uses `appInfo.appBlob.driverId` as the canonical report identity.
- Driver import now resolves `users.id` from `users.focus_data->>'DriverId'` first, with email as a fallback only when needed for compatibility.
- Report APIs are fetched once per UTC datetime range.
- The remaining work is operational: run the backfill, validate joins, and refresh the materialized views.

## Stage Checklist

### Stage 1: Schema and view setup

- [x] Recreate `sirqul_driver`
- [x] Apply updated report tables
- [x] Apply materialized view SQL

### Stage 2: Driver load

- [ ] Load `sirqul_driver` rows from the current driver API payloads
- [ ] Verify `driver_id` is populated where Sirqul exposes `appInfo.appBlob.driverId`
- [ ] Confirm rows without a resolvable driver identity are skipped, not forced

### Stage 3: Report backfill

- [ ] Pull `GL_REPORT_DATA` once for the requested UTC datetime range
- [ ] Pull `GL_TRIP_DATA` once for the requested UTC datetime range
- [ ] Confirm report rows are enriched with `driverId`, `driverName`, and `fleetName`
- [ ] Import driver scores and trip scores into Postgres

### Stage 4: Validation

- [ ] Run one fleet end to end
- [ ] Confirm SQL upserts populate the new tables cleanly
- [ ] Refresh the materialized views
- [ ] Check dashboard rollups against the imported data

## Run Notes

- Use the daily runner for the historical backfill window.
- Set `DAILY_WINDOW_MODE=env`.
- Set `DATE_RANGE_START="2026-06-01 00:00:00"`.
- Set `DATE_RANGE_END="<exclusive UTC datetime>"`.
- If you want a fixed rolling window instead, use `DAILY_WINDOW_MODE=rolling_hours` with `DAILY_WINDOW_HOURS=<positive integer>`.
- Keep `REPORTING_ACCOUNT_ID` unset unless a legacy path still requires it for a separate operator flow.
