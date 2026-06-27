# Fleetlytics Overview

This file is the compact handoff snapshot for resuming work in a fresh session.

## Current State

- Fleetlytics is still a one-time/daily pull pipeline for Sirqul Fleet Management and Reporting APIs, and the daily runner is now the preferred path for historical backfills.
- The daily runner resolves exact UTC datetime windows, including `rolling_hours`, `rolling_24h`, `rolling_7d`, `since_last_success`, and explicit `DATE_RANGE_START` / `DATE_RANGE_END` env windows.
- The export flow remains:
  1. Fetch fleet details
  2. Fetch the fleet's driver list
  3. Fetch `GL_REPORT_DATA` once for the UTC datetime range and enrich rows from the fleet driver list
  4. Fetch `GL_TRIP_DATA` once for the UTC datetime range and enrich rows from the fleet driver list
  5. Fetch `GL_LOCATION_DATA_BY_TRIP` and `GL_INCIDENT_DATA_BY_TRIP` for every trip row in the window
  6. Write timestamped JSON and CSV outputs for each entity
- `sirqul_driver.driver_id` is the canonical driver join key and is nullable until coverage is complete.
- Trip scores are now the source of truth for dashboard rollups.
- Event incidences and event scores are now rolled up from trip scores at the same daily grain.

## Dashboard Goal

The dashboard needs fast, precomputed performance-group cards and day-level driver metrics.

The important requirements captured so far are:

- Use `sirqul_trip_scores` as the source table.
- Filter to companies subscribed to `FleetLytics Mobile App` via `subscriptions.subscription_name`.
- Include fleet/company/user mapping in the dataset.
- Use `sirqul_driver.driver_id` as the canonical driver join key for report rows.
- Keep both distance units available:
  - meters
  - miles
- Group by day using `end_date_datetime::date`.
- Compute daily rollups:
  - average of `overall_score`
  - sum of `distance_meters`
  - sum of distance in miles
  - trip count
- Apply performance buckets in this order:
  - `Low distance` first if total daily distance is below 50 miles
  - `Excellent` for scores `>= 90`
  - `Fair` for scores `>= 72`
  - `Risky` otherwise
- Track incident totals and event score averages side by side in the daily event rollup.

## Database View Plan

The SQL is stored at:

- [view/048_trip_dashboard_rollup_views.sql](./view/048_trip_dashboard_rollup_views.sql)

It defines five materialized views:

- `public.mv_sirqul_driver_trip_list`
  - One row per trip with the driver display name plus trip-level event data
- `public.mv_sirqul_trip_day_rollup`
  - One row per `company_id + retailer_location_id + driver_id + reporting_day`
  - Contains daily averages, totals, trip counts, start/end timestamps, and the computed bucket
- `public.mv_sirqul_performance_groups`
  - Summary layer for dashboard cards
  - Counts driver-day rows by bucket
- `public.mv_sirqul_trip_event_day_rollup`
  - One row per `company_id + retailer_location_id + driver_id + reporting_day`
  - Contains daily averages, totals, incident counts, event score averages, and start/end timestamps
- `public.mv_sirqul_trip_event_groups`
  - Summary layer for event dashboard cards
  - Counts driver-day rows and totals event incidences and event score samples

Trip detail tables now exist alongside the trip table:

- `public.sirqul_trip_locations`
- `public.sirqul_trip_incidents`

Refresh order after trip imports:

```sql
REFRESH MATERIALIZED VIEW public.mv_sirqul_driver_trip_list;
REFRESH MATERIALIZED VIEW public.mv_sirqul_trip_day_rollup;
REFRESH MATERIALIZED VIEW public.mv_sirqul_performance_groups;
REFRESH MATERIALIZED VIEW public.mv_sirqul_trip_event_day_rollup;
REFRESH MATERIALIZED VIEW public.mv_sirqul_trip_event_groups;
```

## Data Relationships

Current joins assumed by the rollup:

- `public.subscriptions`
  - identify `FleetLytics Mobile App` through `subscription_name`
- `public.company_subscriptions`
  - map companies to subscriptions
- `public.companies`
  - company metadata and filtering through `company_name`
- `public.sirqul_fleet`
  - fleet mapping and retailer location
- `public.sirqul_driver`
  - driver `driver_id` to `user_id`
- `public.users`
  - user identity for dashboard use
- `public.sirqul_trip_scores`
- `public.sirqul_trip_locations`
- `public.sirqul_trip_incidents`
  - raw trip score source

## Assumptions

- The company-subscription mapper table is named `public.company_subscriptions`.
- That mapper table contains `company_id` and `subscription_id`.
- `subscriptions.subscription_name` is the canonical subscription label to match.
- The dashboard counts driver-day rows, not raw trip rows.
- The trip day should be derived from `end_date_datetime::date`.
- The low-distance threshold is still 50 miles, expressed as `80467` meters.
- The event rollup should stay at the same driver-day grain as the trip-day rollup.
- `driverName` and `fleetName` are stored on the report tables and should be used for display before falling back to joins.

## Files To Know

- [README.md](./README.md)
- [FLEETLYTICS_CONTEXT.md](./FLEETLYTICS_CONTEXT.md)
- [view/048_trip_dashboard_rollup_views.sql](./view/048_trip_dashboard_rollup_views.sql)
- [Docs/049_trip_location_table.sql](./Docs/049_trip_location_table.sql)
- [Docs/050_trip_incident_table.sql](./Docs/050_trip_incident_table.sql)
- [Fleetlytics/ops/run_trip_details_backfill.sh](./Fleetlytics/ops/run_trip_details_backfill.sh)

## Next Steps If Resuming Work

1. Confirm the real company-subscription mapper table name in the target database.
2. Run the view SQL in Supabase and verify indexes/materialized view creation.
3. Decide whether the importer pipeline should auto-refresh the two materialized views after trip-score imports.
4. If needed, add a thin dashboard query layer that reads from `mv_sirqul_performance_groups` for card counts, `mv_sirqul_trip_day_rollup` for drill-down, and the new event views for event cards/drill-down.
