"""Read-only database lookup helpers used during conversion."""

from __future__ import annotations

import psycopg
from collections.abc import Iterable
from uuid import UUID

from src.config import get_db_url


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
