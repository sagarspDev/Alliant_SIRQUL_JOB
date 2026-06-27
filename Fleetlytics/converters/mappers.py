"""Shared JSON-to-row mappers.

Active today:
- ``map_fleet`` for fleet conversion
- ``map_driver`` for driver conversion

Deferred helpers remain in this module for future row-level mapper expansion in
Phase E and later.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping
from uuid import UUID

from src.config import get_company_id

from .base import SQLExpression
from .coercers import to_float, to_int


LOGGER = logging.getLogger(__name__)


def _jsonb_value(value: Any) -> Any:
    """Return a JSON-serialisable value for a jsonb column."""

    if value is None:
        return None
    if isinstance(value, (dict, list, bool, int, float, str)):
        return value
    return json.loads(json.dumps(value, ensure_ascii=False))


def _parse_meta_data(value: Any) -> Any:
    """Parse the API metaData field into JSON-compatible data."""

    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            LOGGER.warning("Invalid fleet metaData JSON; storing raw payload")
            return {"raw": value}
    return {"raw": str(value)}


def _parse_app_blob(app_info: Any) -> dict[str, Any]:
    """Parse ``appInfo.appBlob`` into a JSON-compatible mapping."""

    if app_info is None or app_info == "":
        return {}
    if not isinstance(app_info, Mapping):
        return {}

    app_blob = app_info.get("appBlob")
    if app_blob is None or app_blob == "":
        return {}
    if isinstance(app_blob, Mapping):
        return dict(app_blob)
    if isinstance(app_blob, str):
        try:
            parsed = json.loads(app_blob)
        except json.JSONDecodeError:
            LOGGER.warning("Invalid appInfo.appBlob JSON; ignoring driver identity")
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def map_fleet(item: Mapping[str, Any]) -> dict[str, Any]:
    """Map a fleet JSON item to a database row."""

    return {
        "retailer_location_id": item.get("retailerLocationId"),
        "company_id": get_company_id(),
        "internal_id": item.get("internalId"),
        "name": item.get("name"),
        "location_type": item.get("locationType"),
        "public_location": item.get("publicLocation"),
        "qr_code_url": item.get("qrCodeUrl"),
        "location_token": item.get("locationToken"),
        "active": item.get("active"),
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "manager": _jsonb_value(item.get("manager")),
        "categories": _jsonb_value(item.get("categories")),
        "filters": _jsonb_value(item.get("filters")),
        "billable_entity": _jsonb_value(item.get("billableEntity")),
        "retailer": _jsonb_value(item.get("retailer")),
        "offers": _jsonb_value(item.get("offers")),
        "meta_data": _parse_meta_data(item.get("metaData")),
        "contact": _jsonb_value(item.get("contact")),
        "stats": {
            "favorite": item.get("favorite"),
            "favoriteCount": item.get("favoriteCount"),
            "noteCount": item.get("noteCount"),
            "sharedCount": item.get("sharedCount"),
            "likeCount": item.get("likeCount"),
            "dislikeCount": item.get("dislikeCount"),
            "hasRatings": item.get("hasRatings"),
        },
        "last_synced_at": SQLExpression("now()"),
    }


def map_fleet_row(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map a fleet JSON record to a database row."""

    return map_fleet(record)


def map_driver_row(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map a driver JSON record to a database row."""

    raise NotImplementedError("Driver row mapping is not implemented yet.")


def _extract_driver_retailer_location_id(
    driver: Mapping[str, Any],
    default_retailer_location_id: int,
) -> int:
    """Resolve the driver retailer location ID with a fallback."""

    locations = driver.get("locations")
    if isinstance(locations, list) and locations:
        first_location = locations[0]
        if isinstance(first_location, Mapping):
            retailer_location_id = to_int(first_location.get("retailerLocationId"))
            if retailer_location_id is not None:
                return retailer_location_id
    return default_retailer_location_id


def _extract_driver_contact_email(driver: Mapping[str, Any]) -> str | None:
    """Return the best available driver contact email."""

    top_level = driver.get("contactEmail")
    if isinstance(top_level, str) and top_level.strip():
        return top_level.strip()

    contact = driver.get("contact")
    if isinstance(contact, Mapping):
        contact_info = contact.get("contactInfo")
        if isinstance(contact_info, Mapping):
            nested_email = contact_info.get("emailAddress")
            if isinstance(nested_email, str) and nested_email.strip():
                return nested_email.strip()
    return None


def map_driver(
    driver: Mapping[str, Any],
    *,
    user_id: UUID,
    default_retailer_location_id: int,
) -> dict[str, Any]:
    """Map a driver JSON item to a database row."""

    app_info = _jsonb_value(driver.get("appInfo"))
    parsed_app_blob = _parse_app_blob(driver.get("appInfo"))
    driver_id = parsed_app_blob.get("driverId")
    driver_id_text = str(driver_id).strip() if driver_id is not None else ""

    return {
        "account_id": to_int(driver.get("accountId")),
        "driver_id": driver_id_text or None,
        "user_id": user_id,
        "retailer_location_id": _extract_driver_retailer_location_id(
            driver, default_retailer_location_id
        ),
        "display": driver.get("display"),
        "username": driver.get("username"),
        "account_type": driver.get("accountType"),
        "contact_email": _extract_driver_contact_email(driver),
        "location_display": driver.get("locationDisplay"),
        "active": driver.get("active"),
        "latitude": to_float(driver.get("latitude")),
        "longitude": to_float(driver.get("longitude")),
        "location_count": to_int(driver.get("locationCount")),
        "manager": _jsonb_value(driver.get("manager")),
        "contact": _jsonb_value(driver.get("contact")),
        "employer": _jsonb_value(driver.get("employer")),
        "app_info": app_info,
        "locations": _jsonb_value(driver.get("locations")),
        "last_synced_at": SQLExpression("now()"),
    }


def map_driver_score_row(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map a driver score JSON record to a database row."""

    raise NotImplementedError("Driver score row mapping is not implemented yet.")


def map_trip_score_row(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map a trip score JSON record to a database row."""

    raise NotImplementedError("Trip score row mapping is not implemented yet.")
