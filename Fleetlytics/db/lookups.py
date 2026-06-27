"""Read-only database lookup helpers used during conversion."""

from __future__ import annotations

from collections.abc import Iterable
import logging
from uuid import UUID

import psycopg

from src.config import get_db_url


LOGGER = logging.getLogger(__name__)


def resolve_company_ids_by_retailer_location_id(
    retailer_location_ids: Iterable[int | str],
) -> dict[int, UUID]:
    """Resolve ``public.companies.id`` by ``focus_data.eventInfo.flAccountId``."""

    normalized_ids = sorted(
        {
            str(retailer_location_id).strip()
            for retailer_location_id in retailer_location_ids
            if retailer_location_id is not None and str(retailer_location_id).strip()
        }
    )
    if not normalized_ids:
        return {}

    resolved: dict[int, UUID] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, focus_data->'eventInfo'->>'flAccountId'
                FROM public.companies
                WHERE focus_data->'eventInfo'->>'flAccountId' = ANY(%s)
                """,
                (normalized_ids,),
            )
            for company_id, fl_account_id in cursor.fetchall():
                if company_id is None or fl_account_id is None:
                    continue
                try:
                    retailer_location_id = int(str(fl_account_id).strip())
                except (TypeError, ValueError):
                    LOGGER.warning(
                        "invalid_company_fl_account_id company_id=%s flAccountId=%r",
                        company_id,
                        fl_account_id,
                    )
                    continue
                if retailer_location_id in resolved and resolved[retailer_location_id] != company_id:
                    LOGGER.warning(
                        "duplicate_company_fleet_mapping retailer_location_id=%s existing_company_id=%s new_company_id=%s",
                        retailer_location_id,
                        resolved[retailer_location_id],
                        company_id,
                    )
                    continue
                resolved[retailer_location_id] = company_id

    unresolved_count = len(normalized_ids) - len(resolved)
    if unresolved_count > 0:
        LOGGER.info(
            "company_fleet_lookup_unresolved_count=%s total_retailer_location_ids=%s",
            unresolved_count,
            len(normalized_ids),
        )
    return resolved


def resolve_user_ids_by_email(emails: list[str]) -> dict[str, UUID]:
    """Resolve user IDs for the provided email addresses.

    The lookup is case-insensitive and returns a mapping keyed by the
    lowercased email address.
    """

    normalized_emails = sorted({email.strip().lower() for email in emails if email and email.strip()})
    if not normalized_emails:
        return {}

    resolved: dict[str, UUID] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, email FROM public.users WHERE lower(email) = ANY(%s)",
                (normalized_emails,),
            )
            for user_id, email in cursor.fetchall():
                if email is None:
                    continue
                resolved[str(email).strip().lower()] = user_id
    return resolved


def resolve_user_ids_by_focus_driver_id(driver_ids: list[str]) -> dict[str, UUID]:
    """Resolve user IDs for the provided ``focus_data.DriverId`` values."""

    normalized_driver_ids = sorted(
        {driver_id.strip() for driver_id in driver_ids if driver_id and driver_id.strip()}
    )
    if not normalized_driver_ids:
        return {}

    resolved: dict[str, UUID] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, focus_data->>'DriverId' FROM public.users "
                "WHERE focus_data->>'DriverId' = ANY(%s)",
                (normalized_driver_ids,),
            )
            for user_id, driver_id in cursor.fetchall():
                if driver_id is None:
                    continue
                resolved[str(driver_id).strip()] = user_id
    return resolved


def resolve_driver_ids(driver_ids: Iterable[str]) -> set[str]:
    """Resolve which driver identities already exist in ``sirqul_driver``."""

    normalized_ids = sorted(
        {
            str(driver_id).strip()
            for driver_id in driver_ids
            if driver_id is not None and str(driver_id).strip()
        }
    )
    if not normalized_ids:
        return set()

    resolved: set[str] = set()
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT driver_id FROM public.sirqul_driver WHERE driver_id = ANY(%s)",
                (normalized_ids,),
            )
            for (driver_id,) in cursor.fetchall():
                if driver_id is None:
                    continue
                resolved.add(str(driver_id))
    return resolved


def resolve_driver_account_ids(account_ids: Iterable[int | str]) -> set[str]:
    """Backward-compatible alias for older call sites."""

    return resolve_driver_ids(account_ids)
