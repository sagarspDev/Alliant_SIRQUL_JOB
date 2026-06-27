-- =========================================================================
-- sirqul_driver_scores migration
-- Switch the idempotency key from source-row identity to fleet-aware identity.
-- =========================================================================

ALTER TABLE public.sirqul_driver_scores
    DROP CONSTRAINT IF EXISTS uq_sirqul_driver_scores_source_row;

ALTER TABLE public.sirqul_driver_scores
    ADD CONSTRAINT uq_sirqul_driver_scores_snapshot_fleet_driver
        UNIQUE (snapshot_date, fleet_id, driver_id);

-- Optional pre-check if this ALTER fails:
-- SELECT snapshot_date, fleet_id, driver_id, COUNT(*)
-- FROM public.sirqul_driver_scores
-- GROUP BY 1, 2, 3
-- HAVING COUNT(*) > 1;

