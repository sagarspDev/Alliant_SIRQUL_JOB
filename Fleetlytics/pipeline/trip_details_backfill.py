"""Historical trip-detail backfill runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Any

import psycopg

try:  # pragma: no cover - execution context dependent
    from ..converters.api import convert_entity
    from ..importers.api import import_entity
    from ..pipeline.pull import _fetch_trip_detail_rows, configure_pull_runtime
    from ..src.config import AppConfig, get_db_schema, get_db_url, load_pull_runtime_config
    from ..src.http_client import build_http_client
    from ..src.logger import configure_logging, get_logger
    from ..writers import OutputWriter, RunPaths
    from ..reporting_api import ReportingAPIClient
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from Fleetlytics.converters.api import convert_entity
    from Fleetlytics.importers.api import import_entity
    from Fleetlytics.pipeline.pull import _fetch_trip_detail_rows, configure_pull_runtime
    from src.config import AppConfig, get_db_schema, get_db_url, load_pull_runtime_config
    from src.http_client import build_http_client
    from src.logger import configure_logging, get_logger
    from writers import OutputWriter, RunPaths
    from reporting_api import ReportingAPIClient

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class TripDetailsBackfillReport:
    """Summary for a historical trip-detail backfill run."""

    run_timestamp: str
    run_dir: Path
    start: str
    end: str
    trip_count: int
    trip_location_count: int
    trip_incident_count: int
    import_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"
    dry_run: bool = False
    duration_ms: int = 0


def run_trip_details_backfill(*, dry_run: bool = False) -> TripDetailsBackfillReport:
    """Backfill trip locations and incidents for a date range from stored trips."""

    started = perf_counter()
    config = load_pull_runtime_config()
    configure_pull_runtime(config)

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_dir = Path(os.getenv("LOG_DIR", "logs")).expanduser()
    configure_logging(log_dir, log_level)

    output_root = Path(os.getenv("OUTPUT_DIR", "output")).expanduser()
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")
    run_paths = RunPaths(
        output_dir=output_root,
        retailer_location_id="trip-details-backfill",
        timestamp=run_timestamp,
    )

    reporting_client = ReportingAPIClient(
        config=config,
        http_client=build_http_client(base_url=config.reporting_api_base_url, config=config),
    )

    trip_rows = _load_trip_rows(config)
    detail_logger = LOGGER

    trip_locations, location_errors = _fetch_trip_detail_rows(
        trip_rows=trip_rows,
        logger=detail_logger,
        report_name="trip_locations",
        fetcher=reporting_client.get_trip_locations_by_trip,
    )
    trip_incidents, incident_errors = _fetch_trip_detail_rows(
        trip_rows=trip_rows,
        logger=detail_logger,
        report_name="trip_incidents",
        fetcher=reporting_client.get_trip_incidents_by_trip,
    )

    writer = OutputWriter(logger=detail_logger)
    writer.write_trip_locations(trip_locations, run_paths)
    writer.write_trip_incidents(trip_incidents, run_paths)

    import_results: list[dict[str, Any]] = []
    errors = list(location_errors) + list(incident_errors)
    for entity in ("trip_locations", "trip_incidents"):
        try:
            convert_entity(entity, run_paths.run_dir)
            import_result = import_entity(entity, run_paths.run_dir, dry_run=dry_run)
            import_results.append(
                {
                    "entity": entity,
                    "status": import_result.status,
                    "rows_inserted": import_result.rows_inserted,
                    "rows_updated": import_result.rows_updated,
                    "rows_skipped": import_result.rows_skipped,
                }
            )
            if import_result.errors:
                errors.extend(f"{entity} import failed: {error}" for error in import_result.errors)
        except Exception as exc:  # pragma: no cover - defensive import path
            errors.append(f"{entity} pipeline failed: {exc}")
            LOGGER.exception("%s pipeline failed", entity)

    status = "ok" if not errors else "partial"
    return TripDetailsBackfillReport(
        run_timestamp=run_timestamp,
        run_dir=run_paths.run_dir,
        start=config.date_range.start.isoformat(sep=" "),
        end=config.date_range.end.isoformat(sep=" "),
        trip_count=len(trip_rows),
        trip_location_count=len(trip_locations),
        trip_incident_count=len(trip_incidents),
        import_results=import_results,
        errors=errors,
        status=status,
        dry_run=dry_run,
        duration_ms=int((perf_counter() - started) * 1000),
    )


def _load_trip_rows(config: AppConfig) -> list[dict[str, Any]]:
    """Read trip identifiers from the canonical trip-score table."""

    query = f"""
        SELECT trip_id, account_id, end_date_datetime
        FROM {get_db_schema()}.sirqul_trip_scores
        WHERE end_date_datetime >= %s
          AND end_date_datetime < %s
        ORDER BY end_date_datetime ASC, trip_id ASC
    """
    trip_rows: list[dict[str, Any]] = []
    seen_trip_ids: set[str] = set()
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (config.date_range.start, config.date_range.end))
            for trip_id, account_id, end_date_datetime in cursor.fetchall():
                trip_id_text = str(trip_id).strip() if trip_id is not None else ""
                if not trip_id_text or trip_id_text in seen_trip_ids:
                    continue
                if account_id is None:
                    LOGGER.warning("Skipping trip without account_id trip_id=%s", trip_id_text)
                    continue
                seen_trip_ids.add(trip_id_text)
                trip_rows.append(
                    {
                        "tripId": trip_id_text,
                        "accountId": account_id,
                        "endDateDatetime": end_date_datetime,
                    }
                )

    LOGGER.info(
        "Loaded trip rows for backfill trip_count=%s date_range=%s -> %s",
        len(trip_rows),
        config.date_range.start.isoformat(),
        config.date_range.end.isoformat(),
    )
    return trip_rows
