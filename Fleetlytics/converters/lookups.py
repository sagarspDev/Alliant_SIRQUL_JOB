"""Read-only lookup helpers used during conversion."""

from __future__ import annotations

from collections.abc import Iterable
import logging
from dataclasses import dataclass
from uuid import UUID

import psycopg

from src.config import get_db_schema, get_db_url


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FleetIdentity:
    """Resolved fleet identity used by score-row mapping."""

    retailer_location_id: int
    company_id: UUID


def resolve_retailer_location_ids_by_internal_id(
    internal_ids: Iterable[str],
) -> dict[str, int]:
    """Resolve ``sirqul_fleet.retailer_location_id`` by ``internal_id``."""

    normalized_ids = sorted(
        {
            str(internal_id).strip()
            for internal_id in internal_ids
            if internal_id is not None and str(internal_id).strip()
        }
    )
    if not normalized_ids:
        return {}

    schema = get_db_schema()
    resolved: dict[str, int] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT internal_id, retailer_location_id FROM {schema}.sirqul_fleet "
                "WHERE internal_id = ANY(%s)",
                (normalized_ids,),
            )
            for internal_id, retailer_location_id in cursor.fetchall():
                if internal_id is None or retailer_location_id is None:
                    continue
                resolved[str(internal_id)] = int(retailer_location_id)

    unresolved_count = len(normalized_ids) - len(resolved)
    if unresolved_count > 0:
        LOGGER.warning(
            "retailer_location_lookup_unresolved_count=%s total_internal_ids=%s",
            unresolved_count,
            len(normalized_ids),
        )
    return resolved


def resolve_fleet_identities_by_internal_id(
    internal_ids: Iterable[str],
) -> dict[str, FleetIdentity]:
    """Resolve both retailer location and company IDs for fleets by ``internal_id``."""

    normalized_ids = sorted(
        {
            str(internal_id).strip()
            for internal_id in internal_ids
            if internal_id is not None and str(internal_id).strip()
        }
    )
    if not normalized_ids:
        return {}

    schema = get_db_schema()
    resolved: dict[str, FleetIdentity] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT internal_id, retailer_location_id, company_id FROM {schema}.sirqul_fleet "
                "WHERE internal_id = ANY(%s)",
                (normalized_ids,),
            )
            for internal_id, retailer_location_id, company_id in cursor.fetchall():
                if internal_id is None or retailer_location_id is None or company_id is None:
                    continue
                resolved[str(internal_id)] = FleetIdentity(
                    retailer_location_id=int(retailer_location_id),
                    company_id=company_id,
                )

    unresolved_count = len(normalized_ids) - len(resolved)
    if unresolved_count > 0:
        LOGGER.warning(
            "fleet_identity_lookup_unresolved_count=%s total_internal_ids=%s",
            unresolved_count,
            len(normalized_ids),
        )
    return resolved
