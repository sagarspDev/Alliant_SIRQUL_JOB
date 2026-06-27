"""Reusable per-fleet pull callable for Fleetlytics."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import inspect
import json
import logging
from time import perf_counter
from typing import Any, Iterator

try:  # pragma: no cover - execution context dependent
    from fleet_api import FleetAPIClient
    from reporting_api import ReportingAPIClient
    from Fleetlytics.converters.drivers import DriverConverter
    from Fleetlytics.db.lookups import resolve_user_ids_by_email, resolve_user_ids_by_focus_driver_id
    from src.config import AppConfig, format_datetime
    from src.http_client import HTTPClient, build_http_client
    from src.logger import get_logger
    from writers import OutputWriter, RunPaths
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from fleet_api import FleetAPIClient
    from reporting_api import ReportingAPIClient
    from Fleetlytics.converters.drivers import DriverConverter
    from Fleetlytics.db.lookups import resolve_user_ids_by_email, resolve_user_ids_by_focus_driver_id
    from src.config import AppConfig, format_datetime
    from src.http_client import HTTPClient, build_http_client
    from src.logger import get_logger
    from writers import OutputWriter, RunPaths

from .paths import build_run_dir
from .types import PullRequest, PullResult

LOGGER = get_logger(__name__)
_RUNTIME_CONFIG: AppConfig | None = None


def configure_pull_runtime(config: AppConfig) -> None:
    """Store shared runtime dependencies for later per-fleet pulls."""

    global _RUNTIME_CONFIG
    _RUNTIME_CONFIG = config


def _require_runtime_config() -> AppConfig:
    if _RUNTIME_CONFIG is None:
        raise RuntimeError("Fleetlytics pull runtime has not been configured.")
    return _RUNTIME_CONFIG


class _FleetLogPrefixFilter(logging.Filter):
    """Prefix every emitted log message with the active fleet identifier."""

    def __init__(self, fleet_internal_id: str) -> None:
        super().__init__()
        self.prefix = f"[fleet={fleet_internal_id}] "

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging plumbing
        message = record.getMessage()
        if not message.startswith(self.prefix):
            record.msg = f"{self.prefix}{message}"
            record.args = ()
        return True


@contextmanager
def _prefixed_fleet_logging(fleet_internal_id: str) -> Iterator[None]:
    """Temporarily prefix all root-handler log output for one fleet."""

    root_logger = logging.getLogger()
    fleet_filter = _FleetLogPrefixFilter(fleet_internal_id)
    attached_handlers: list[logging.Handler] = []

    for handler in root_logger.handlers:
        handler.addFilter(fleet_filter)
        attached_handlers.append(handler)

    try:
        yield
    finally:
        for handler in attached_handlers:
            handler.removeFilter(fleet_filter)


def _to_utc_datetime(value: date | datetime) -> datetime:
    """Normalize date-like values to UTC datetimes for API formatting."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _format_range_value(value: date | datetime) -> str:
    """Format a request range value using the project canonical datetime shape."""

    return format_datetime(_to_utc_datetime(value))


def _to_date(value: date | datetime) -> date:
    """Normalize a date-like value to its UTC calendar date."""

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(timezone.utc).date()
    return value


def _iter_daily_dates(start: date | datetime, end: date | datetime) -> Iterator[date]:
    """Yield each UTC calendar date touched by the supplied range."""

    current = _to_date(start)
    final_day = _to_date(end)
    while current <= final_day:
        yield current
        current += timedelta(days=1)


def _clamp_report_window(
    score_day: date,
    *,
    request_start: datetime,
    request_end: datetime,
) -> tuple[str, str]:
    """Return the report window for one day clamped to the requested range."""

    day_start = datetime.combine(score_day, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    clamped_start = max(request_start, day_start)
    clamped_end = min(request_end, day_end)
    return _format_range_value(clamped_start), _format_range_value(clamped_end)


def _driver_display_name(driver: dict[str, Any]) -> str | None:
    """Return the best available human-readable driver name."""

    display = driver.get("display")
    if isinstance(display, str) and display.strip():
        return display.strip()

    contact = driver.get("contact")
    if isinstance(contact, dict):
        first_name = contact.get("firstName")
        last_name = contact.get("lastName")
        parts = [part.strip() for part in [first_name, last_name] if isinstance(part, str) and part.strip()]
        if parts:
            return " ".join(parts)

        contact_info = contact.get("contactInfo")
        if isinstance(contact_info, dict):
            email = contact_info.get("emailAddress")
            if isinstance(email, str) and email.strip():
                return email.strip()

    contact_email = driver.get("contactEmail")
    if isinstance(contact_email, str) and contact_email.strip():
        return contact_email.strip()

    username = driver.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()

    return None


def _driver_lookup_key(driver: dict[str, Any]) -> str | None:
    """Return the driver report identity from ``appInfo.appBlob.driverId``."""

    app_info = driver.get("appInfo")
    if not isinstance(app_info, dict):
        return None

    app_blob = app_info.get("appBlob")
    if isinstance(app_blob, str):
        try:
            app_blob = json.loads(app_blob)
        except json.JSONDecodeError:
            return None

    if not isinstance(app_blob, dict):
        return None

    driver_id = app_blob.get("driverId")
    if isinstance(driver_id, str) and driver_id.strip():
        return driver_id.strip()
    if driver_id is not None:
        driver_id_text = str(driver_id).strip()
        return driver_id_text or None
    return None


def _build_driver_lookup(drivers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index fleet drivers by report identity, keeping only drivers present in users."""

    focus_driver_ids: list[str] = []
    emails: list[str] = []
    for driver in drivers:
        focus_driver_id = DriverConverter._extract_focus_driver_id(driver)
        if focus_driver_id:
            focus_driver_ids.append(focus_driver_id)
        contact_email = DriverConverter._extract_contact_email(driver)
        if contact_email:
            emails.append(contact_email)

    user_ids_by_focus_driver_id = resolve_user_ids_by_focus_driver_id(focus_driver_ids)
    user_ids_by_email = resolve_user_ids_by_email(emails)

    lookup: dict[str, dict[str, Any]] = {}
    skipped_driver_ids: set[str] = set()
    for driver in drivers:
        driver_id = _driver_lookup_key(driver)
        if not driver_id:
            continue
        focus_driver_id = DriverConverter._extract_focus_driver_id(driver)
        contact_email = DriverConverter._extract_contact_email(driver)
        user_id = None
        if focus_driver_id:
            user_id = user_ids_by_focus_driver_id.get(focus_driver_id)
        if user_id is None and contact_email:
            user_id = user_ids_by_email.get(contact_email.lower())
        if user_id is None:
            skipped_driver_ids.add(driver_id)
            continue
        lookup[driver_id] = {
            "driver_id": driver_id,
            "driver_name": _driver_display_name(driver),
            "driver_account_id": driver.get("accountId"),
        }

    if skipped_driver_ids:
        LOGGER.warning(
            "drivers skipped because no user match was found driver_ids=%s",
            sorted(skipped_driver_ids),
        )
    return lookup


def _enrich_report_rows(
    *,
    rows: list[dict[str, Any]],
    fleet_internal_id: str,
    fleet_name: str,
    driver_lookup: dict[str, dict[str, Any]],
    logger: logging.Logger,
    report_name: str,
) -> list[dict[str, Any]]:
    """Keep rows for the active fleet and enrich them with driver/fleet names."""

    enriched_rows: list[dict[str, Any]] = []
    unresolved_driver_ids: set[str] = set()
    filtered_rows = 0

    for row in rows:
        row_fleet_id = row.get("fleetId")
        if str(row_fleet_id).strip() != str(fleet_internal_id).strip():
            filtered_rows += 1
            continue

        third_party_id = row.get("thirdPartyId")
        if third_party_id is None:
            logger.warning("%s row missing thirdPartyId fleetId=%s", report_name, row_fleet_id)
            continue
        driver_id = str(third_party_id).strip()
        if not driver_id:
            logger.warning("%s row has blank thirdPartyId fleetId=%s", report_name, row_fleet_id)
            continue

        driver_info = driver_lookup.get(driver_id)
        if driver_info is None:
            unresolved_driver_ids.add(driver_id)
            continue

        enriched_row = dict(row)
        enriched_row["driverId"] = driver_info["driver_id"]
        enriched_row["driverName"] = driver_info.get("driver_name")
        enriched_row["fleetName"] = fleet_name
        enriched_row["fleetInternalId"] = fleet_internal_id
        enriched_row["driverAccountId"] = driver_info.get("driver_account_id")
        enriched_rows.append(enriched_row)

    if filtered_rows:
        logger.info(
            "%s rows filtered to fleet_id=%s filtered_rows=%s",
            report_name,
            fleet_internal_id,
            filtered_rows,
        )
    if unresolved_driver_ids:
        logger.warning(
            "%s rows skipped because no driver match was found driver_ids=%s",
            report_name,
            sorted(unresolved_driver_ids),
        )

    return enriched_rows


def _fetch_trip_detail_rows(
    *,
    trip_rows: list[dict[str, Any]],
    logger: logging.Logger,
    report_name: str,
    fetcher: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fetch and flatten per-trip detail rows for a report."""

    detail_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for trip_row in trip_rows:
        trip_id = trip_row.get("tripId")
        account_id = trip_row.get("accountId")
        trip_id_text = str(trip_id).strip() if trip_id is not None else ""
        if not trip_id_text:
            logger.warning("%s row missing tripId; skipping detail lookup", report_name)
            continue
        if account_id is None or str(account_id).strip() == "":
            logger.warning("%s row missing accountId tripId=%s; skipping detail lookup", report_name, trip_id_text)
            continue

        try:
            fetched_rows = fetcher(trip_id=trip_id_text, account_id=account_id)
        except Exception as exc:  # pragma: no cover - exercised by API failure paths
            message = f"{report_name} fetch failed tripId={trip_id_text}: {exc}"
            errors.append(message)
            logger.exception(message)
            continue

        detail_rows.extend(fetched_rows)

    logger.info(
        "%s detail rows fetched trip_count=%s row_count=%s error_count=%s",
        report_name,
        len(trip_rows),
        len(detail_rows),
        len(errors),
    )
    return detail_rows, errors


def _build_clients(config: AppConfig) -> tuple[FleetAPIClient, ReportingAPIClient]:
    """Create the HTTP-backed API clients for the current runtime."""

    fleet_http_client = build_http_client(base_url=config.fleet_api_base_url, config=config)
    reporting_http_client = build_http_client(base_url=config.reporting_api_base_url, config=config)
    return (
        FleetAPIClient(config=config, http_client=fleet_http_client),
        ReportingAPIClient(config=config, http_client=reporting_http_client),
    )


def _resolve_api_retailer_location_id(req: PullRequest) -> int | str:
    """Return the retailer location identifier used by the Fleet API."""

    if req.retailer_location_id is not None:
        return req.retailer_location_id
    return req.fleet_internal_id


def pull_one_fleet(req: PullRequest) -> PullResult:
    """
    Run the full one-shot pull for a single fleet:
        fleet detail -> drivers -> driver_scores -> trip_scores -> trip locations -> trip incidents
    Writes the same JSON + CSV outputs as main.py into:
        <output_root>/<fleet_internal_id>/<run_timestamp>/
    Returns a PullResult describing what happened.
    """

    config = _require_runtime_config()
    run_dir = build_run_dir(req.output_root, req.fleet_internal_id, req.run_timestamp)
    result = PullResult(fleet_internal_id=req.fleet_internal_id, run_dir=run_dir)
    started = perf_counter()

    with _prefixed_fleet_logging(req.fleet_internal_id):
        logger = LOGGER
        api_retailer_location_id = _resolve_api_retailer_location_id(req)
        request_start = _to_utc_datetime(req.date_range_start)
        request_end = _to_utc_datetime(req.date_range_end)
        logger.info(
            "Pull start run_dir=%s retailer_location_id=%s date_range=%s -> %s",
            run_dir,
            api_retailer_location_id,
            format_datetime(request_start),
            format_datetime(request_end),
        )

        try:
            fleet_client, reporting_client = _build_clients(config)
            writer = OutputWriter(logger=logger)
            run_paths = RunPaths(
                output_dir=req.output_root,
                retailer_location_id=req.fleet_internal_id,
                timestamp=req.run_timestamp,
            )

            fleet: dict[str, Any]
            drivers: list[dict[str, Any]]

            try:
                fleet = fleet_client.get_fleet(api_retailer_location_id)
                result.fleet_ok = True
                writer.write_fleet(fleet, run_paths)
            except Exception as exc:  # pragma: no cover - exercised by API failure paths
                result.errors.append(f"fleet lookup failed: {exc}")
                logger.exception("Fleet lookup failed")
                result.status = "error"
                return result

            try:
                drivers = fleet_client.list_drivers(api_retailer_location_id)
                result.drivers_ok = True
                result.driver_count = len(drivers)
                writer.write_drivers(drivers, run_paths)
            except Exception as exc:  # pragma: no cover - exercised by API failure paths
                result.errors.append(f"driver lookup failed: {exc}")
                logger.exception("Driver lookup failed")
                result.status = "error"
                return result

            driver_lookup = _build_driver_lookup(drivers)
            logger.info(
                "Extracted driver report identities driver_count=%s report_driver_count=%s",
                len(drivers),
                len(driver_lookup),
            )

            try:
                score_rows = []
                for score_day in _iter_daily_dates(request_start, request_end):
                    daily_start, daily_end = _clamp_report_window(
                        score_day,
                        request_start=request_start,
                        request_end=request_end,
                    )
                    if daily_start == daily_end:
                        continue
                    daily_rows = reporting_client.get_driver_scores(
                        daily_start,
                        daily_end,
                    )
                    for row_index, row in enumerate(daily_rows, start=1):
                        enriched_row = dict(row)
                        enriched_row["snapshotDate"] = score_day.isoformat()
                        enriched_row["sourceGroupKey"] = f"GL_REPORT_DATA:{score_day.isoformat()}"
                        enriched_row["sourceRowIndex"] = row_index
                        score_rows.append(enriched_row)
                result.driver_scores_ok = True
            except Exception as exc:  # pragma: no cover - exercised by API failure paths
                result.driver_scores_ok = False
                result.errors.append(f"driver_scores fetch failed: {exc}")
                logger.exception("Driver score fetch failed")
                score_rows = []

            date_start = _format_range_value(req.date_range_start)
            date_end = _format_range_value(req.date_range_end)
            try:
                trip_rows = reporting_client.get_driver_trips(date_start, date_end)
                result.trip_scores_ok = True
            except Exception as exc:  # pragma: no cover - exercised by API failure paths
                result.trip_scores_ok = False
                result.errors.append(f"trip_scores fetch failed: {exc}")
                logger.exception("Driver trip fetch failed")
                trip_rows = []

            fleet_name = str(fleet.get("name") or req.fleet_internal_id)
            score_rows = _enrich_report_rows(
                rows=score_rows,
                fleet_internal_id=req.fleet_internal_id,
                fleet_name=fleet_name,
                driver_lookup=driver_lookup,
                logger=logger,
                report_name="driver_scores",
            )
            trip_rows = _enrich_report_rows(
                rows=trip_rows,
                fleet_internal_id=req.fleet_internal_id,
                fleet_name=fleet_name,
                driver_lookup=driver_lookup,
                logger=logger,
                report_name="trip_scores",
            )

            result.driver_score_count = len(score_rows)
            result.trip_score_count = len(trip_rows)

            trip_locations, location_errors = _fetch_trip_detail_rows(
                trip_rows=trip_rows,
                logger=logger,
                report_name="trip_locations",
                fetcher=reporting_client.get_trip_locations_by_trip,
            )
            trip_incidents, incident_errors = _fetch_trip_detail_rows(
                trip_rows=trip_rows,
                logger=logger,
                report_name="trip_incidents",
                fetcher=reporting_client.get_trip_incidents_by_trip,
            )

            result.trip_locations_ok = not location_errors
            result.trip_incidents_ok = not incident_errors
            result.trip_location_count = len(trip_locations)
            result.trip_incident_count = len(trip_incidents)

            writer.write_driver_scores(score_rows, run_paths)
            writer.write_trip_scores(trip_rows, run_paths)
            writer.write_trip_locations(trip_locations, run_paths)
            writer.write_trip_incidents(trip_incidents, run_paths)

            result.errors.extend(location_errors)
            result.errors.extend(incident_errors)

            if result.errors:
                result.status = "partial"
            else:
                result.status = "ok"
        except Exception as exc:  # pragma: no cover - defensive top-level catch
            if not result.errors:
                result.errors.append(f"unexpected pull failure: {exc}")
            result.status = "error"
            logger.exception("Unexpected pull failure")
        finally:
            result.duration_ms = int((perf_counter() - started) * 1000)
            logger.info(
                "Pull complete fleet=%s status=%s driver_count=%s driver_score_count=%s trip_score_count=%s trip_location_count=%s trip_incident_count=%s duration_ms=%s errors=%s",
                result.fleet_internal_id,
                result.status,
                result.driver_count,
                result.driver_score_count,
                result.trip_score_count,
                result.trip_location_count,
                result.trip_incident_count,
                result.duration_ms,
                len(result.errors),
            )
    return result


if __name__ == "__main__":  # pragma: no cover - smoke example only
    print(inspect.signature(pull_one_fleet))
    print(pull_one_fleet.__doc__ or "")
