-- =========================================================================
-- 5. sirqul trip dashboard rollups
--    Source of truth: public.sirqul_trip_scores
--    Assumed subscription mapper table: public.company_subscriptions
--    Assumed columns on mapper table: company_id, subscription_id
--
--    This script builds:
--      1) sirqul_trip_day_rollup
--         One row per company + fleet + driver + day.
--      2) sirqul_performance_groups
--         One row per company + fleet + day + performance bucket.
--      3) sirqul_driver_trip_list
--         One row per trip with driver display name for dashboard tables.
--
--    Trip day = end_date_datetime::date
--    Distance is exposed in both meters and miles.
-- =========================================================================

-- =========================================================================
-- 6. sirqul trip event dashboard rollups
--    Source of truth: public.sirqul_trip_scores
--    Assumed subscription mapper table: public.company_subscriptions
--    Assumed columns on mapper table: company_id, subscription_id
--
--    This script builds:
--      1) sirqul_trip_event_day_rollup
--         One row per company + fleet + driver + day.
--      2) sirqul_trip_event_groups
--         One row per company + fleet + day.
--
--    Trip day = end_date_datetime::date
--    Event incidences and event scores are exposed side by side.
-- =========================================================================

DROP MATERIALIZED VIEW IF EXISTS public.sirqul_trip_event_groups;
DROP MATERIALIZED VIEW IF EXISTS public.sirqul_trip_event_day_rollup;
DROP MATERIALIZED VIEW IF EXISTS public.sirqul_performance_groups;
DROP MATERIALIZED VIEW IF EXISTS public.sirqul_trip_day_rollup;
DROP MATERIALIZED VIEW IF EXISTS public.sirqul_driver_trip_list;

CREATE MATERIALIZED VIEW public.sirqul_trip_day_rollup AS
WITH eligible_subscription AS (
    SELECT s.id
    FROM public.subscriptions AS s
    WHERE s.subscription_name = 'FleetLytics Mobile App'
    LIMIT 1
),
eligible_companies AS (
    SELECT DISTINCT csm.company_id
    FROM public.company_subscriptions AS csm
    JOIN eligible_subscription AS es
        ON es.id = csm.subscription_id
),
trip_day_data AS (
    SELECT
        t.company_id,
        c.company_name AS company_name,
        t.retailer_location_id,
        t.fleet_id AS fleet_internal_id,
        t.fleet_name,
        t.driver_id,
        t.account_id AS driver_account_id,
        d.user_id,
        u.email AS user_email,
        t.end_date_datetime::date AS reporting_day,
        COUNT(*)::bigint AS trip_count,
        COUNT(t.distance_meters)::bigint AS distance_sample_count,
        COUNT(t.overall_score)::bigint AS score_sample_count,
        SUM(t.distance_meters) AS raw_total_distance_meters,
        AVG(t.overall_score) AS raw_average_overall_score,
        MIN(t.start_date_datetime) AS first_trip_start_datetime,
        MAX(t.end_date_datetime) AS last_trip_end_datetime
    FROM public.sirqul_trip_scores AS t
    JOIN eligible_companies AS ec
        ON ec.company_id = t.company_id
    JOIN public.companies AS c
        ON c.id = t.company_id
    JOIN public.sirqul_driver AS d
        ON d.driver_id = t.driver_id
    JOIN public.users AS u
        ON u.id = d.user_id
    WHERE t.end_date_datetime IS NOT NULL
    GROUP BY
        t.company_id,
        c.company_name,
        t.retailer_location_id,
        t.fleet_id,
        t.fleet_name,
        t.driver_id,
        t.account_id,
        d.user_id,
        u.email,
        t.end_date_datetime::date
)
SELECT
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    driver_id,
    driver_account_id,
    user_id,
    user_email,
    reporting_day,
    trip_count,
    distance_sample_count,
    score_sample_count,
    COALESCE(raw_total_distance_meters, 0)::bigint AS total_distance_meters,
    ROUND(COALESCE(raw_total_distance_meters, 0)::numeric / 1609.344, 3) AS total_distance_miles,
    ROUND(COALESCE(raw_average_overall_score, 0)::numeric, 3) AS average_overall_score,
    first_trip_start_datetime,
    last_trip_end_datetime,
    CASE
        WHEN distance_sample_count > 0 AND raw_total_distance_meters < 80467 THEN 'Low distance'
        WHEN COALESCE(raw_average_overall_score, 0) >= 90 THEN 'Excellent'
        WHEN COALESCE(raw_average_overall_score, 0) >= 72 THEN 'Fair'
        ELSE 'Risky'
    END AS performance_bucket
FROM trip_day_data
WITH NO DATA;

CREATE MATERIALIZED VIEW public.sirqul_driver_trip_list AS
WITH eligible_subscription AS (
    SELECT s.id
    FROM public.subscriptions AS s
    WHERE s.subscription_name = 'FleetLytics Mobile App'
    LIMIT 1
),
eligible_companies AS (
    SELECT DISTINCT csm.company_id
    FROM public.company_subscriptions AS csm
    JOIN eligible_subscription AS es
        ON es.id = csm.subscription_id
)
SELECT
    t.company_id,
    t.driver_id,
    t.account_id AS driver_account_id,
    COALESCE(
        NULLIF(BTRIM(t.driver_name), ''),
        NULLIF(BTRIM(COALESCE(u.display_name, CONCAT_WS(' ', u.first_name, u.last_name))), ''),
        NULLIF(BTRIM(CONCAT_WS(' ', u.first_name, u.last_name)), '')
    ) AS driver_display_name,
    t.fleet_id AS fleet_internal_id,
    t.fleet_name,
    t.trip_id,
    t.start_date_datetime,
    t.end_date_datetime,
    ROUND(COALESCE(t.distance_meters, 0)::numeric / 1609.344, 3) AS distance_miles,
    ROUND(
        EXTRACT(EPOCH FROM (t.end_date_datetime - t.start_date_datetime))::numeric / 60.0,
        3
    ) AS duration_minutes,
    t.overall_score,
    COALESCE(t.accel_incidents, 0)::bigint AS accel_incidents,
    COALESCE(t.brake_incidents, 0)::bigint AS brake_incidents,
    COALESCE(t.collision_incidents, 0)::bigint AS collision_incidents,
    COALESCE(t.phone_incidents, 0)::bigint AS phone_incidents,
    COALESCE(t.speed_incidents, 0)::bigint AS speed_incidents,
    COALESCE(t.turn_incidents, 0)::bigint AS turn_incidents,
    COALESCE(t.accel_incidents, 0)::bigint
        + COALESCE(t.brake_incidents, 0)::bigint
        + COALESCE(t.collision_incidents, 0)::bigint
        + COALESCE(t.phone_incidents, 0)::bigint
        + COALESCE(t.speed_incidents, 0)::bigint
        + COALESCE(t.turn_incidents, 0)::bigint AS total_event_incidents,
    t.accel_score,
    t.brake_score,
    t.collision_score,
    t.phone_score,
    t.speed_score,
    t.turn_score,
    CASE
        WHEN COALESCE(t.overall_score, 0) >= 90 THEN 'Excellent'
        WHEN COALESCE(t.overall_score, 0) >= 72 THEN 'Fair'
        ELSE 'Risky'
    END AS performance_class,
    t.geo->>'startDescription' AS geo_start_description,
    t.geo->>'endDescription' AS geo_end_description,
    (t.weather->>'weatherWind')::double precision AS weather_wind,
    (t.weather->>'weatherTempLow')::double precision AS weather_temp_low,
    (t.weather->>'weatherTempHigh')::double precision AS weather_temp_high,
    t.last_speed_incident_datetime,
    t.last_accel_incident_datetime,
    t.last_brake_incident_datetime,
    t.last_phone_incident_datetime,
    t.last_turn_incident_datetime,
    t.last_collision_incident_datetime
FROM public.sirqul_trip_scores AS t
JOIN eligible_companies AS ec
    ON ec.company_id = t.company_id
JOIN public.sirqul_driver AS d
    ON d.driver_id = t.driver_id
LEFT JOIN public.users AS u
    ON u.id = d.user_id
WHERE t.end_date_datetime IS NOT NULL
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_driver_trip_list_trip_id
    ON public.sirqul_driver_trip_list (trip_id);

CREATE INDEX IF NOT EXISTS idx_sirqul_driver_trip_list_driver_end
    ON public.sirqul_driver_trip_list (company_id, driver_id, end_date_datetime DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_trip_day_rollup
    ON public.sirqul_trip_day_rollup (
        company_id,
        retailer_location_id,
        driver_id,
        reporting_day
    );

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_day_rollup_company_day
    ON public.sirqul_trip_day_rollup (company_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_day_rollup_fleet_day
    ON public.sirqul_trip_day_rollup (retailer_location_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_day_rollup_bucket
    ON public.sirqul_trip_day_rollup (performance_bucket);

CREATE MATERIALIZED VIEW public.sirqul_performance_groups AS
SELECT
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    reporting_day,
    performance_bucket,
    COUNT(*)::bigint AS driver_day_count,
    SUM(trip_count)::bigint AS total_trip_count,
    SUM(total_distance_meters)::bigint AS total_distance_meters,
    ROUND(SUM(total_distance_meters)::numeric / 1609.344, 3) AS total_distance_miles,
    ROUND(AVG(average_overall_score)::numeric, 3) AS average_daily_overall_score
FROM public.sirqul_trip_day_rollup
GROUP BY
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    reporting_day,
    performance_bucket
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_performance_groups
    ON public.sirqul_performance_groups (
        company_id,
        retailer_location_id,
        reporting_day,
        performance_bucket
    );

CREATE INDEX IF NOT EXISTS idx_sirqul_performance_groups_company_day
    ON public.sirqul_performance_groups (company_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_performance_groups_fleet_day
    ON public.sirqul_performance_groups (retailer_location_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_performance_groups_bucket
    ON public.sirqul_performance_groups (performance_bucket);

CREATE MATERIALIZED VIEW public.sirqul_trip_event_day_rollup AS
WITH eligible_subscription AS (
    SELECT s.id
    FROM public.subscriptions AS s
    WHERE s.subscription_name = 'FleetLytics Mobile App'
    LIMIT 1
),
eligible_companies AS (
    SELECT DISTINCT csm.company_id
    FROM public.company_subscriptions AS csm
    JOIN eligible_subscription AS es
        ON es.id = csm.subscription_id
),
trip_event_day_data AS (
    SELECT
        t.company_id,
        c.company_name AS company_name,
        t.retailer_location_id,
        t.fleet_id AS fleet_internal_id,
        t.fleet_name,
        t.driver_id,
        t.account_id AS driver_account_id,
        d.user_id,
        u.email AS user_email,
        t.end_date_datetime::date AS reporting_day,
        COUNT(*)::bigint AS trip_count,
        COUNT(t.distance_meters)::bigint AS distance_sample_count,
        COUNT(t.overall_score)::bigint AS score_sample_count,
        SUM(t.distance_meters) AS raw_total_distance_meters,
        AVG(t.overall_score) AS raw_average_overall_score,
        SUM(COALESCE(t.accel_incidents, 0)) AS raw_total_accel_incidents,
        SUM(COALESCE(t.brake_incidents, 0)) AS raw_total_brake_incidents,
        SUM(COALESCE(t.collision_incidents, 0)) AS raw_total_collision_incidents,
        SUM(COALESCE(t.phone_incidents, 0)) AS raw_total_phone_incidents,
        SUM(COALESCE(t.speed_incidents, 0)) AS raw_total_speed_incidents,
        SUM(COALESCE(t.turn_incidents, 0)) AS raw_total_turn_incidents,
        COUNT(t.accel_score)::bigint AS accel_score_sample_count,
        COUNT(t.brake_score)::bigint AS brake_score_sample_count,
        COUNT(t.collision_score)::bigint AS collision_score_sample_count,
        COUNT(t.phone_score)::bigint AS phone_score_sample_count,
        COUNT(t.speed_score)::bigint AS speed_score_sample_count,
        COUNT(t.turn_score)::bigint AS turn_score_sample_count,
        AVG(t.accel_score) AS raw_average_accel_score,
        AVG(t.brake_score) AS raw_average_brake_score,
        AVG(t.collision_score) AS raw_average_collision_score,
        AVG(t.phone_score) AS raw_average_phone_score,
        AVG(t.speed_score) AS raw_average_speed_score,
        AVG(t.turn_score) AS raw_average_turn_score,
        MIN(t.start_date_datetime) AS first_trip_start_datetime,
        MAX(t.end_date_datetime) AS last_trip_end_datetime
    FROM public.sirqul_trip_scores AS t
    JOIN eligible_companies AS ec
        ON ec.company_id = t.company_id
    JOIN public.companies AS c
        ON c.id = t.company_id
    JOIN public.sirqul_driver AS d
        ON d.driver_id = t.driver_id
    JOIN public.users AS u
        ON u.id = d.user_id
    WHERE t.end_date_datetime IS NOT NULL
    GROUP BY
        t.company_id,
        c.company_name,
        t.retailer_location_id,
        t.fleet_id,
        t.fleet_name,
        t.driver_id,
        t.account_id,
        d.user_id,
        u.email,
        t.end_date_datetime::date
)
SELECT
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    driver_id,
    driver_account_id,
    user_id,
    user_email,
    reporting_day,
    trip_count,
    distance_sample_count,
    score_sample_count,
    COALESCE(raw_total_distance_meters, 0)::bigint AS total_distance_meters,
    ROUND(COALESCE(raw_total_distance_meters, 0)::numeric / 1609.344, 3) AS total_distance_miles,
    ROUND(COALESCE(raw_average_overall_score, 0)::numeric, 3) AS average_overall_score,
    COALESCE(raw_total_accel_incidents, 0)::bigint AS total_accel_incidents,
    COALESCE(raw_total_brake_incidents, 0)::bigint AS total_brake_incidents,
    COALESCE(raw_total_collision_incidents, 0)::bigint AS total_collision_incidents,
    COALESCE(raw_total_phone_incidents, 0)::bigint AS total_phone_incidents,
    COALESCE(raw_total_speed_incidents, 0)::bigint AS total_speed_incidents,
    COALESCE(raw_total_turn_incidents, 0)::bigint AS total_turn_incidents,
    COALESCE(raw_total_accel_incidents, 0)::bigint
        + COALESCE(raw_total_brake_incidents, 0)::bigint
        + COALESCE(raw_total_collision_incidents, 0)::bigint
        + COALESCE(raw_total_phone_incidents, 0)::bigint
        + COALESCE(raw_total_speed_incidents, 0)::bigint
        + COALESCE(raw_total_turn_incidents, 0)::bigint AS total_event_incidents,
    accel_score_sample_count,
    brake_score_sample_count,
    collision_score_sample_count,
    phone_score_sample_count,
    speed_score_sample_count,
    turn_score_sample_count,
    ROUND(COALESCE(raw_average_accel_score, 0)::numeric, 3) AS average_accel_score,
    ROUND(COALESCE(raw_average_brake_score, 0)::numeric, 3) AS average_brake_score,
    ROUND(COALESCE(raw_average_collision_score, 0)::numeric, 3) AS average_collision_score,
    ROUND(COALESCE(raw_average_phone_score, 0)::numeric, 3) AS average_phone_score,
    ROUND(COALESCE(raw_average_speed_score, 0)::numeric, 3) AS average_speed_score,
    ROUND(COALESCE(raw_average_turn_score, 0)::numeric, 3) AS average_turn_score,
    first_trip_start_datetime,
    last_trip_end_datetime
FROM trip_event_day_data
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_trip_event_day_rollup
    ON public.sirqul_trip_event_day_rollup (
        company_id,
        retailer_location_id,
        driver_id,
        reporting_day
    );

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_event_day_rollup_company_day
    ON public.sirqul_trip_event_day_rollup (company_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_event_day_rollup_fleet_day
    ON public.sirqul_trip_event_day_rollup (retailer_location_id, reporting_day DESC);

CREATE MATERIALIZED VIEW public.sirqul_trip_event_groups AS
SELECT
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    reporting_day,
    COUNT(*)::bigint AS driver_day_count,
    SUM(trip_count)::bigint AS total_trip_count,
    SUM(distance_sample_count)::bigint AS distance_sample_count,
    SUM(score_sample_count)::bigint AS score_sample_count,
    SUM(total_distance_meters)::bigint AS total_distance_meters,
    ROUND(SUM(total_distance_meters)::numeric / 1609.344, 3) AS total_distance_miles,
    ROUND(AVG(average_overall_score)::numeric, 3) AS average_daily_overall_score,
    SUM(total_accel_incidents)::bigint AS total_accel_incidents,
    SUM(total_brake_incidents)::bigint AS total_brake_incidents,
    SUM(total_collision_incidents)::bigint AS total_collision_incidents,
    SUM(total_phone_incidents)::bigint AS total_phone_incidents,
    SUM(total_speed_incidents)::bigint AS total_speed_incidents,
    SUM(total_turn_incidents)::bigint AS total_turn_incidents,
    SUM(total_event_incidents)::bigint AS total_event_incidents,
    SUM(accel_score_sample_count)::bigint AS accel_score_sample_count,
    SUM(brake_score_sample_count)::bigint AS brake_score_sample_count,
    SUM(collision_score_sample_count)::bigint AS collision_score_sample_count,
    SUM(phone_score_sample_count)::bigint AS phone_score_sample_count,
    SUM(speed_score_sample_count)::bigint AS speed_score_sample_count,
    SUM(turn_score_sample_count)::bigint AS turn_score_sample_count,
    ROUND(AVG(average_accel_score)::numeric, 3) AS average_daily_accel_score,
    ROUND(AVG(average_brake_score)::numeric, 3) AS average_daily_brake_score,
    ROUND(AVG(average_collision_score)::numeric, 3) AS average_daily_collision_score,
    ROUND(AVG(average_phone_score)::numeric, 3) AS average_daily_phone_score,
    ROUND(AVG(average_speed_score)::numeric, 3) AS average_daily_speed_score,
    ROUND(AVG(average_turn_score)::numeric, 3) AS average_daily_turn_score
FROM public.sirqul_trip_event_day_rollup
GROUP BY
    company_id,
    company_name,
    retailer_location_id,
    fleet_internal_id,
    fleet_name,
    reporting_day
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_trip_event_groups
    ON public.sirqul_trip_event_groups (
        company_id,
        retailer_location_id,
        reporting_day
    );

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_event_groups_company_day
    ON public.sirqul_trip_event_groups (company_id, reporting_day DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_event_groups_fleet_day
    ON public.sirqul_trip_event_groups (retailer_location_id, reporting_day DESC);

-- Refresh order after trip-score loads/imports:
--   REFRESH MATERIALIZED VIEW public.sirqul_driver_trip_list;
--   REFRESH MATERIALIZED VIEW public.sirqul_trip_day_rollup;
--   REFRESH MATERIALIZED VIEW public.sirqul_performance_groups;
--   REFRESH MATERIALIZED VIEW public.sirqul_trip_event_day_rollup;
--   REFRESH MATERIALIZED VIEW public.sirqul_trip_event_groups;


-- =========================================================================
-- 7. sirqul_driver_activity (normal view)
--    Real-time active vs inactive driver status.
--    Joins sirqul_driver → users (is_active) and sirqul_fleet (company_id).
--    Only includes drivers assigned to a fleet.
-- =========================================================================

CREATE OR REPLACE VIEW public.sirqul_driver_activity AS
SELECT
  sd.account_id,
  sd.driver_id,
  sd.user_id,
  sd.retailer_location_id,
  sf.company_id,
  u.is_active
FROM public.sirqul_driver sd
JOIN public.users u ON u.id = sd.user_id AND u.deleted_at IS NULL
JOIN public.sirqul_fleet sf ON sf.retailer_location_id = sd.retailer_location_id;

GRANT SELECT ON public.sirqul_driver_activity TO authenticated, anon, service_role;
