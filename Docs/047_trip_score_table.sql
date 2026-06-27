  -- =========================================================================
  -- 4. sirqul_trip_scores
  --    Source: GL_TRIP_DATA (https://fleetshare.bmrang.com/api/3.18)
  --    One row per trip (idempotent by tripId).
  -- =========================================================================
  CREATE TABLE IF NOT EXISTS public.sirqul_trip_scores (
      -- Identity
      id                              BIGSERIAL    PRIMARY KEY,
      driver_id                       TEXT         NOT NULL,        -- FK → sirqul_driver.driver_id
      company_id                      UUID         NOT NULL,        -- FK → companies.id (resolved from sirqul_fleet.company_id by fleet_id)

      -- Source identifiers (denormalized from API)
      account_id                      BIGINT,                       -- = API accountId (request/source context)
      fleet_id                        TEXT,                         -- = API fleetId (= sirqul_fleet.internal_id)
      fleet_name                      TEXT,
      retailer_location_id            BIGINT,                       -- resolved from fleet_id; nullable for now
      third_party_id                  TEXT,                         -- = API thirdPartyId
      driver_name                     TEXT,
      trip_id                         TEXT         NOT NULL,        -- = API tripId (UUID-style)
      trip_type                       TEXT,                         -- = API tripType (e.g. "driver")

      -- Context
      distance_meters                 BIGINT,

      -- Scores
      overall_score                   DOUBLE PRECISION,
      accel_score                     DOUBLE PRECISION,
      brake_score                     DOUBLE PRECISION,
      collision_score                 DOUBLE PRECISION,
      phone_score                     DOUBLE PRECISION,
      speed_score                     DOUBLE PRECISION,
      turn_score                      DOUBLE PRECISION,

      -- Incident counts
      accel_incidents                 DOUBLE PRECISION,
      brake_incidents                 DOUBLE PRECISION,
      collision_incidents             DOUBLE PRECISION,
      phone_incidents                 DOUBLE PRECISION,
      speed_incidents                 DOUBLE PRECISION,
      turn_incidents                  DOUBLE PRECISION,

      -- Last-incident timestamps: raw ms BIGINT (as-is from API)
      last_accel_incident             BIGINT,
      last_brake_incident             BIGINT,
      last_collision_incident         BIGINT,
      last_phone_incident             BIGINT,
      last_speed_incident             BIGINT,
      last_turn_incident              BIGINT,

      -- Last-incident timestamps: UTC wall-clock timestamps (generated)
      last_accel_incident_datetime     TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_accel_incident IS NULL THEN NULL
               ELSE to_timestamp(last_accel_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,
      last_brake_incident_datetime     TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_brake_incident IS NULL THEN NULL
               ELSE to_timestamp(last_brake_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,
      last_collision_incident_datetime TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_collision_incident IS NULL THEN NULL
               ELSE to_timestamp(last_collision_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,
      last_phone_incident_datetime     TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_phone_incident IS NULL THEN NULL
               ELSE to_timestamp(last_phone_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,
      last_speed_incident_datetime     TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_speed_incident IS NULL THEN NULL
               ELSE to_timestamp(last_speed_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,
      last_turn_incident_datetime      TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          CASE WHEN last_turn_incident IS NULL THEN NULL
               ELSE to_timestamp(last_turn_incident::double precision / 1000.0) AT TIME ZONE 'UTC' END
      ) STORED,

      -- Trip window: raw ms BIGINT
      start_date                      BIGINT       NOT NULL,
      end_date                        BIGINT       NOT NULL,

      -- Trip window: UTC wall-clock timestamps (generated)
      start_date_datetime              TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          to_timestamp(start_date::double precision / 1000.0) AT TIME ZONE 'UTC'
      ) STORED,
      end_date_datetime                TIMESTAMP WITHOUT TIME ZONE GENERATED ALWAYS AS (
          to_timestamp(end_date::double precision / 1000.0) AT TIME ZONE 'UTC'
      ) STORED,

      -- Trip duration (seconds, generated from raw ms columns)
      duration_seconds                INTEGER      GENERATED ALWAYS AS (
          ((end_date - start_date) / 1000)::INTEGER
      ) STORED,

      -- Geo endpoints (startLatitude, startLongitude, startDescription, endLatitude, endLongitude, endDescription)
      geo                             JSONB,

      -- Weather (weatherCode, weatherTempLow, weatherTempHigh, weatherWind)
      weather                         JSONB,

      -- Audit
      created_at                      TIMESTAMPTZ  NOT NULL DEFAULT now(),
      updated_at                      TIMESTAMPTZ  NOT NULL DEFAULT now(),
      last_synced_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),

      -- FKs
      CONSTRAINT fk_sirqul_trip_scores_driver
          FOREIGN KEY (driver_id)
          REFERENCES public.sirqul_driver (driver_id)
          ON DELETE CASCADE,

      CONSTRAINT fk_sirqul_trip_scores_company
          FOREIGN KEY (company_id)
          REFERENCES public.companies (id)
          ON DELETE RESTRICT,

      CONSTRAINT fk_sirqul_trip_scores_fleet
          FOREIGN KEY (retailer_location_id)
          REFERENCES public.sirqul_fleet (retailer_location_id)
          ON DELETE SET NULL,

      -- Idempotency: a trip is uniquely identified by its tripId
      CONSTRAINT uq_sirqul_trip_scores_trip_id
          UNIQUE (trip_id),

      -- Sanity
      CONSTRAINT chk_sirqul_trip_scores_window
          CHECK (end_date >= start_date)
  );

  -- Indexes
  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_driver_start
      ON public.sirqul_trip_scores (driver_id, start_date_datetime DESC);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_company_start
      ON public.sirqul_trip_scores (company_id, start_date_datetime DESC);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_fleet_id
      ON public.sirqul_trip_scores (fleet_id);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_retailer_location_id
      ON public.sirqul_trip_scores (retailer_location_id);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_start_date
      ON public.sirqul_trip_scores (start_date_datetime DESC);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_overall_score
      ON public.sirqul_trip_scores (overall_score DESC NULLS LAST);

  CREATE INDEX IF NOT EXISTS idx_sirqul_trip_scores_updated_at
      ON public.sirqul_trip_scores (updated_at DESC);

  CREATE TRIGGER trg_sirqul_trip_scores_updated_at
      BEFORE UPDATE ON public.sirqul_trip_scores
      FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

  ALTER TABLE public.sirqul_trip_scores ENABLE ROW LEVEL SECURITY;
