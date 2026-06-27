-- =========================================================================
-- sirqul_driver migration
-- Adds the canonical report identity column used by driver/trip score joins.
-- =========================================================================

ALTER TABLE public.sirqul_driver
    ADD COLUMN IF NOT EXISTS driver_id TEXT;

UPDATE public.sirqul_driver
SET driver_id = NULLIF(
    COALESCE(
        CASE
            WHEN jsonb_typeof(app_info->'appBlob') = 'object' THEN app_info->'appBlob'->>'driverId'
            WHEN jsonb_typeof(app_info->'appBlob') = 'string' THEN (app_info->>'appBlob')::jsonb->>'driverId'
            ELSE NULL
        END,
        app_info->>'driverId'
    ),
    ''
)
WHERE driver_id IS NULL OR BTRIM(driver_id) = '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sirqul_driver_driver_id
    ON public.sirqul_driver (driver_id);

-- Keep driver_id nullable for now because not all existing drivers have a report identity yet.
