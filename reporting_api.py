"""Reporting API client for date-range score, trip, and trip-detail pulls."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - execution context dependent
    from .src.config import AppConfig, load_config
    from .src.http_client import HTTPClient, FleetlyticsAPIError, build_http_client
    from .src.logger import configure_logging, get_logger
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from src.config import AppConfig, load_config
    from src.http_client import HTTPClient, FleetlyticsAPIError, build_http_client
    from src.logger import configure_logging, get_logger

DEFAULT_REPORT_PAGE_LIMIT = 1000

_LOGGER = get_logger(__name__)


@dataclass(slots=True)
class ReportingAPIClient:
    """Client for the Reporting API report endpoint."""

    config: AppConfig
    http_client: HTTPClient

    def _auth_headers(self) -> dict[str, str]:
        """Build per-request headers for Reporting API calls."""

        return {
            "Application-Key": self.config.reporting_api_app_key,
            "Application-Rest-Key": _normalize_rest_key(self.config.reporting_api_rest_key),
        }

    def get_driver_scores(self, start: str, end: str) -> list[dict[str, Any]]:
        """Fetch all score rows for the supplied date range.

        Args:
            start: Inclusive start datetime string.
            end: Inclusive end datetime string.

        Returns:
            A flat list of all rows returned across every page.
        """

        return self._fetch_report_rows(query="GL_REPORT_DATA", parameters={"start": start, "end": end})

    def get_driver_trips(self, start: str, end: str) -> list[dict[str, Any]]:
        """Fetch all trip rows for the supplied date range.

        Args:
            start: Inclusive start datetime string.
            end: Inclusive end datetime string.

        Returns:
            A flat list of all rows returned across every page.
        """

        return self._fetch_report_rows(query="GL_TRIP_DATA", parameters={"start": start, "end": end})

    def get_trip_locations_by_trip(self, *, trip_id: str, account_id: int | str) -> list[dict[str, Any]]:
        """Fetch all trip-location rows for a specific trip."""

        return self._fetch_report_rows(
            query="GL_LOCATION_DATA_BY_TRIP",
            parameters={"tripId": trip_id},
            account_id=account_id,
        )

    def get_trip_incidents_by_trip(self, *, trip_id: str, account_id: int | str) -> list[dict[str, Any]]:
        """Fetch all trip-incident rows for a specific trip."""

        return self._fetch_report_rows(
            query="GL_INCIDENT_DATA_BY_TRIP",
            parameters={"tripId": trip_id},
            account_id=account_id,
        )

    def _fetch_report_rows(
        self,
        *,
        query: str,
        parameters: dict[str, Any],
        account_id: int | str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and paginate report rows for a date range."""

        endpoint = "/api/3.18/report/run"
        rows: list[dict[str, Any]] = []
        page = 1
        offset = 0
        page_size = DEFAULT_REPORT_PAGE_LIMIT

        _LOGGER.info(
            "Entering report fetch query=%s start=%s end=%s",
            query,
            parameters.get("start"),
            parameters.get("end"),
        )

        while True:
            try:
                payload = self.http_client.post_multipart(
                    endpoint,
                    headers=self._auth_headers(),
                    form_data=_build_report_form_data(
                        query=query,
                        app_key=self.config.reporting_api_app_key,
                        parameters=parameters,
                        account_id=account_id,
                        offset=offset,
                        limit=page_size,
                    ),
                )

                page_rows, has_more = _extract_report_page(payload)
                rows.extend(page_rows)
                _LOGGER.info(
                    "Report query=%s page=%s rows_returned=%s total_so_far=%s",
                    query,
                    page,
                    len(page_rows),
                    len(rows),
                )

                if not has_more:
                    break

                if len(page_rows) == 0:
                    _LOGGER.warning(
                        "Report query=%s returned no rows but hasMore is true; stopping pagination",
                        query,
                    )
                    break

                offset += page_size
                page += 1
            except FleetlyticsAPIError as exc:
                _LOGGER.error(
                    "Reporting API error query=%s: %s",
                    query,
                    exc,
                )
                raise
            except Exception as exc:  # pragma: no cover - defensive catch for pagination continuation
                _LOGGER.error(
                    "Unexpected error query=%s: %s",
                    query,
                    exc,
                )
                raise FleetlyticsAPIError(f"Unexpected error query={query}: {exc}") from exc

        _LOGGER.info(
            "Exiting report fetch query=%s total_rows=%s",
            query,
            len(rows),
        )
        return rows


def _extract_report_page(payload: Any) -> tuple[list[dict[str, Any]], bool]:
    """Extract report rows and pagination state from a report response."""

    if not isinstance(payload, dict):
        raise FleetlyticsAPIError("Unexpected report response shape: expected object")

    if payload.get("valid") is False:
        message = payload.get("message") or "Reporting API returned an invalid response"
        error_code = payload.get("errorCode")
        if error_code:
            raise FleetlyticsAPIError(f"{message} (errorCode={error_code})")
        raise FleetlyticsAPIError(str(message))

    raw_rows = payload.get("rows")
    if raw_rows is None:
        raw_rows = payload.get("items", [])

    if not isinstance(raw_rows, list):
        raise FleetlyticsAPIError("Unexpected report response shape: rows is not a list")

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            raise FleetlyticsAPIError("Unexpected report response shape: row is not an object")
        rows.append(row)

    has_more = bool(payload.get("hasMoreResults", payload.get("hasMore", False)))
    return rows, has_more


def _build_report_form_data(
    *,
    query: str,
    app_key: str,
    parameters: dict[str, Any],
    account_id: int | str | None,
    offset: int,
    limit: int,
) -> dict[str, str]:
    """Build the multipart form payload for the reporting endpoint."""

    payload = dict(parameters)
    payload["appKey"] = app_key
    form_data = {
        "query": query,
        "parameters": json.dumps(payload, separators=(",", ":")),
        "start": str(offset),
        "limit": str(limit),
    }
    if account_id is not None:
        form_data["accountId"] = str(account_id)
    return form_data


def _normalize_rest_key(raw_value: str) -> str:
    """Remove a redundant Bearer prefix if the REST key was stored that way."""

    value = raw_value.strip()
    if value.lower().startswith("bearer "):
        return value.split(None, 1)[1]
    return value


if __name__ == "__main__":
    config = load_config()
    configure_logging(config.log_dir, config.log_level)

    reporting_http_client = build_http_client(base_url=config.reporting_api_base_url, config=config)
    reporting_client = ReportingAPIClient(config=config, http_client=reporting_http_client)
    start, end = config.date_range.to_formatted_strings()

    score_rows = reporting_client.get_driver_scores(start, end)
    trip_rows = reporting_client.get_driver_trips(start, end)

    print(f"Score rows: {len(score_rows)}")
    print(f"Trip rows: {len(trip_rows)}")
