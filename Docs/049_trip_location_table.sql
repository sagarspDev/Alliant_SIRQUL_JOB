-- =========================================================================
-- 5. sirqul_trip_locations
--    Source: GL_LOCATION_DATA_BY_TRIP (https://fleetshare.bmrang.com/api/3.18)
--    One row per trip location point.
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.sirqul_trip_locations (
    id                              BIGSERIAL    PRIMARY KEY,
    trip_id                         TEXT         NOT NULL,
    account_id                      BIGINT       NOT NULL,
    timestamp_ms                    BIGINT       NOT NULL,
    latitude                        DOUBLE PRECISION NOT NULL,
    longitude                       DOUBLE PRECISION NOT NULL,

    timestamp_datetime              TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
        to_timestamp(timestamp_ms::double precision / 1000.0) AT TIME ZONE 'UTC'
    ) STORED,

    created_at                      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_synced_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_sirqul_trip_locations_trip
        FOREIGN KEY (trip_id)
        REFERENCES public.sirqul_trip_scores (trip_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_sirqul_trip_locations_point
        UNIQUE (trip_id, account_id, timestamp_ms, latitude, longitude)
);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_locations_trip_id
    ON public.sirqul_trip_locations (trip_id);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_locations_account_id
    ON public.sirqul_trip_locations (account_id);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_locations_timestamp
    ON public.sirqul_trip_locations (timestamp_ms DESC);

CREATE INDEX IF NOT EXISTS idx_sirqul_trip_locations_updated_at
    ON public.sirqul_trip_locations (updated_at DESC);

CREATE TRIGGER trg_sirqul_trip_locations_updated_at
    BEFORE UPDATE ON public.sirqul_trip_locations
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.sirqul_trip_locations ENABLE ROW LEVEL SECURITY;
