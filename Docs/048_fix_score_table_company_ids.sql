-- =========================================================================
-- 048. Fix score table company_id values
-- =========================================================================
--
-- Use this once after the trip-score / driver-score company mapping fix.
-- It aligns existing score rows to the company_id already stored on sirqul_fleet
-- for the same fleet_id / internal_id.
--
-- Safe to re-run: both UPDATEs are idempotent.

UPDATE public.sirqul_trip_scores AS ts
SET company_id = sf.company_id
FROM public.sirqul_fleet AS sf
WHERE sf.internal_id = ts.fleet_id
  AND ts.company_id IS DISTINCT FROM sf.company_id;

UPDATE public.sirqul_driver_scores AS ds
SET company_id = sf.company_id
FROM public.sirqul_fleet AS sf
WHERE sf.internal_id = ds.fleet_id
  AND ds.company_id IS DISTINCT FROM sf.company_id;

-- Optional verification:
-- SELECT fleet_id, company_id, COUNT(*) FROM public.sirqul_trip_scores GROUP BY 1,2 ORDER BY 1,2;
-- SELECT fleet_id, company_id, COUNT(*) FROM public.sirqul_driver_scores GROUP BY 1,2 ORDER BY 1,2;
