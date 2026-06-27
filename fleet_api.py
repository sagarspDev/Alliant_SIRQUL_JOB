"""Fleet Management API client for Fleetlytics."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

try:  # pragma: no cover - execution context dependent
    from .src.config import AppConfig, load_config
    from .src.http_client import HTTPClient, FleetlyticsAPIError, build_http_client
    from .src.logger import get_logger
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from src.config import AppConfig, load_config
    from src.http_client import HTTPClient, FleetlyticsAPIError, build_http_client
    from src.logger import get_logger

DEFAULT_DRIVER_PAGE_LIMIT = 20
DEFAULT_FLEET_SEARCH_LIMIT = 10000

_LOGGER = get_logger(__name__)


@dataclass(slots=True)
class FleetAPIClient:
    """Client for Fleet Management API endpoints."""

    config: AppConfig
    http_client: HTTPClient

    def _auth_headers(self) -> dict[str, str]:
        """Build per-request headers for Fleet Management API calls."""

        return {
            "Application-Key": self.config.fleet_api_app_key,
            "Authorization": f"Bearer {self.config.fleet_api_auth_token}",
        }

    def get_fleet(self, retailer_location_id: int | str) -> dict[str, Any]:
        """Fetch the full fleet record for a retailer location."""

        endpoint = f"/fleets/{retailer_location_id}"
        _LOGGER.info("Entering get_fleet endpoint=%s retailerLocationId=%s", endpoint, retailer_location_id)

        try:
            payload = self.http_client.get(
                endpoint,
                headers=self._auth_headers(),
            )
        except FleetlyticsAPIError as exc:
            raise FleetlyticsAPIError(
                f"GET {endpoint} failed for retailerLocationId={retailer_location_id}: {exc}",
                status_code=exc.status_code,
                body=exc.body,
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive re-wrap
            raise FleetlyticsAPIError(
                f"GET {endpoint} failed for retailerLocationId={retailer_location_id}: {exc}"
            ) from exc

        fleet = _extract_fleet_item(payload)
        _LOGGER.info("Exiting get_fleet endpoint=%s retailerLocationId=%s", endpoint, retailer_location_id)
        return fleet

    def list_drivers(self, retailer_location_id: int | str) -> list[dict[str, Any]]:
        """Fetch every driver for a retailer location, handling pagination."""

        endpoint = "/fleets/drivers/search"
        _LOGGER.info(
            "Entering list_drivers endpoint=%s retailerLocationId=%s",
            endpoint,
            retailer_location_id,
        )

        drivers: list[dict[str, Any]] = []
        start = 0
        page = 1
        limit = DEFAULT_DRIVER_PAGE_LIMIT

        while True:
            try:
                payload = self.http_client.get(
                    endpoint,
                    headers=self._auth_headers(),
                    params={
                        "retailerLocationId": str(retailer_location_id),
                        "start": start,
                        "limit": limit,
                    },
                )
            except FleetlyticsAPIError as exc:
                raise FleetlyticsAPIError(
                    "GET /fleets/drivers/search failed "
                    f"for retailerLocationId={retailer_location_id}, start={start}, limit={limit}: {exc}",
                    status_code=exc.status_code,
                    body=exc.body,
                ) from exc
            except Exception as exc:  # pragma: no cover - defensive re-wrap
                raise FleetlyticsAPIError(
                    "GET /fleets/drivers/search failed "
                    f"for retailerLocationId={retailer_location_id}, start={start}, limit={limit}: {exc}"
                ) from exc

            items, has_more = _extract_driver_page(payload)
            drivers.extend(items)
            _LOGGER.info(
                "Fetched page %s (start=%s, returned=%s, total_so_far=%s)",
                page,
                start,
                len(items),
                len(drivers),
            )

            if not has_more or len(items) < limit:
                break

            start += limit
            page += 1

        _LOGGER.info(
            "Exiting list_drivers endpoint=%s retailerLocationId=%s total_drivers=%s",
            endpoint,
            retailer_location_id,
            len(drivers),
        )
        return drivers


def _extract_fleet_item(payload: Any) -> dict[str, Any]:
    """Extract the fleet object from an API response payload."""

    if isinstance(payload, dict):
        item = payload.get("item", payload)
        if isinstance(item, dict):
            return item
    raise FleetlyticsAPIError("Unexpected fleet response shape: missing item object")


def _extract_driver_page(payload: Any) -> tuple[list[dict[str, Any]], bool]:
    """Extract driver items and pagination state from a search response."""

    if not isinstance(payload, dict):
        raise FleetlyticsAPIError("Unexpected driver search response shape: expected object")

    items = payload.get("items", [])
    if not isinstance(items, list):
        raise FleetlyticsAPIError("Unexpected driver search response shape: items is not a list")

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized_items.append(item)
        else:
            raise FleetlyticsAPIError("Unexpected driver search response shape: item is not an object")

    has_more = bool(payload.get("hasMoreResults"))
    return normalized_items, has_more


def _extract_driver_account_ids(drivers: list[dict[str, Any]]) -> list[int]:
    """Extract top-level `accountId` values from driver records."""

    account_ids: list[int] = []
    for driver in drivers:
        account_id = driver.get("accountId")
        if account_id is None:
            continue

        try:
            account_ids.append(int(account_id))
        except (TypeError, ValueError) as exc:
            raise FleetlyticsAPIError(f"Invalid driver accountId value: {account_id!r}") from exc
    return account_ids


def search_fleets() -> list[dict[str, Any]]:
    """
    Call POST /fleets/search and return the raw list of fleet dicts from the response.
    Uses the same auth + error handling pattern as the existing fleet-detail call.
    Logs the count returned at INFO level.
    Raises on HTTP/transport errors (let the caller decide policy).
    """

    config = load_config()
    http_client = build_http_client(base_url=config.fleet_api_base_url, config=config)
    client = FleetAPIClient(config=config, http_client=http_client)
    endpoint = "/fleets/search"
    limit = DEFAULT_FLEET_SEARCH_LIMIT
    _LOGGER.info("Entering search_fleets endpoint=%s", endpoint)

    try:
        # NOTE: No saved /fleets/search request sample exists in-repo. Use an empty JSON body
        # until the canonical request payload is confirmed from a real sample or API spec.
        payload = client.http_client.post_json(
            endpoint,
            headers=client._auth_headers(),
            params={"limit": limit},
            json_body={},
        )
    except FleetlyticsAPIError as exc:
        raise FleetlyticsAPIError(
            f"POST {endpoint} failed: {exc}",
            status_code=exc.status_code,
            body=exc.body,
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive re-wrap
        raise FleetlyticsAPIError(f"POST {endpoint} failed: {exc}") from exc

    fleets = _extract_fleet_search_items(payload)
    _LOGGER.info("Exiting search_fleets endpoint=%s fleet_count=%s", endpoint, len(fleets))
    return fleets


def _extract_fleet_search_items(payload: Any) -> list[dict[str, Any]]:
    """Extract fleet rows from the /fleets/search response shape."""

    if isinstance(payload, list):
        return _normalize_fleet_search_items(payload)

    if isinstance(payload, dict):
        for key in ("items", "results", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return _normalize_fleet_search_items(value)
        item = payload.get("item")
        if isinstance(item, list):
            return _normalize_fleet_search_items(item)

    raise FleetlyticsAPIError("Unexpected fleet search response shape: missing fleet list")


def _normalize_fleet_search_items(items: list[Any]) -> list[dict[str, Any]]:
    """Validate that every fleet search row is an object."""

    normalized_items: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized_items.append(item)
        else:
            raise FleetlyticsAPIError("Unexpected fleet search response shape: item is not an object")
    return normalized_items


if __name__ == "__main__":  # pragma: no cover - smoke example only
    print(inspect.signature(search_fleets))
    print(search_fleets.__doc__ or "")
