-- =========================================================================
-- 0. Shared trigger function
-- =========================================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================================================================
-- 1. sirqul_fleet
--    Source: Get Fleet (https://fleetshare.bmrang.com:3003)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.sirqul_fleet (
    -- Identity
    retailer_location_id  BIGINT       PRIMARY KEY,
    company_id            UUID         NOT NULL,
    internal_id           TEXT         NOT NULL,        -- = fleetId in reporting APIs
    name                  TEXT         NOT NULL,

    -- Flat scalars
    location_type         TEXT,
    public_location       BOOLEAN,
    qr_code_url           TEXT,
    location_token        TEXT,
    active                BOOLEAN      NOT NULL DEFAULT true,
    latitude              NUMERIC(9,6),
    longitude             NUMERIC(9,6),

    -- Nested blobs from API
    manager               JSONB,
    categories            JSONB,
    filters               JSONB,
    billable_entity       JSONB,
    retailer              JSONB,
    offers                JSONB,
    meta_data             JSONB,
    contact               JSONB,
    stats                 JSONB,        -- favorite, favoriteCount, noteCount, sharedCount, likeCount, dislikeCount, hasRatings
    -- Audit
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_synced_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- FKs
    CONSTRAINT fk_sirqul_fleet_company
        FOREIGN KEY (company_id)
        REFERENCES public.companies (id)
        ON DELETE RESTRICT,

    -- Sanity
    CONSTRAINT chk_sirqul_fleet_lat CHECK (latitude  IS NULL OR latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_sirqul_fleet_lng CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sirqul_fleet_company_id   ON public.sirqul_fleet (company_id);
CREATE INDEX IF NOT EXISTS idx_sirqul_fleet_active       ON public.sirqul_fleet (active);
CREATE INDEX IF NOT EXISTS idx_sirqul_fleet_internal_id  ON public.sirqul_fleet (internal_id);
CREATE INDEX IF NOT EXISTS idx_sirqul_fleet_manager_gin  ON public.sirqul_fleet USING GIN (manager);

CREATE TRIGGER trg_sirqul_fleet_updated_at
    BEFORE UPDATE ON public.sirqul_fleet
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.sirqul_fleet ENABLE ROW LEVEL SECURITY;


-- =========================================================================
-- 2. sirqul_driver
--    Source: Get Driver (https://fleetshare.bmrang.com:3003)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.sirqul_driver (
    -- Identity
    account_id            BIGINT       PRIMARY KEY,
    driver_id             TEXT         NOT NULL UNIQUE,
    user_id               UUID         NOT NULL,
    retailer_location_id  BIGINT,                        -- FK to sirqul_fleet
    display               TEXT,
    username              TEXT         UNIQUE,
    account_type          TEXT,
    contact_email         TEXT,

    -- Flat scalars
    location_display      TEXT,
    active                BOOLEAN      NOT NULL DEFAULT true,
    latitude              NUMERIC(9,6),
    longitude             NUMERIC(9,6),
    location_count        INTEGER,

    -- Nested blobs from API
    manager               JSONB,
    contact               JSONB,
    employer              JSONB,        -- holds retailerLocationId / internalId of fleet
    app_info              JSONB,
    locations             JSONB,

    -- Audit
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_synced_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- FKs
    CONSTRAINT fk_sirqul_driver_user
        FOREIGN KEY (user_id)
        REFERENCES public.users (id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_sirqul_driver_fleet
        FOREIGN KEY (retailer_location_id)
        REFERENCES public.sirqul_fleet (retailer_location_id)
        ON DELETE SET NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_user_id              ON public.sirqul_driver (user_id);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_retailer_location_id ON public.sirqul_driver (retailer_location_id);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_active               ON public.sirqul_driver (active);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_username             ON public.sirqul_driver (username);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_email                ON public.sirqul_driver (contact_email);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_employer_gin         ON public.sirqul_driver USING GIN (employer);
CREATE INDEX IF NOT EXISTS idx_sirqul_driver_manager_gin          ON public.sirqul_driver USING GIN (manager);

CREATE TRIGGER trg_sirqul_driver_updated_at
    BEFORE UPDATE ON public.sirqul_driver
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.sirqul_driver ENABLE ROW LEVEL SECURITY;
