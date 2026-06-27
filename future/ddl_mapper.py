"""DEFERRED - not part of the active daily pipeline. See FLEETLYTICS_CONTEXT.md Phase E.

Placeholder DDL-driven mappers for Supabase row shaping.

The CSV exports already use the canonical DB column names from
``Docs/045_create_sirqul_fleet_driver_tables.sql``, so these future helpers can
remain near-1:1 dict pass-throughs once the user provides the Supabase DDL.
"""

from __future__ import annotations

from typing import Any


def map_fleet_to_row(fleet_dict: dict[str, Any]) -> dict[str, Any]:
    """Map a DDL-aligned fleet CSV row to its Supabase row representation.

    The CSV column names already match the DB column names, so this future
    mapper should be a near-1:1 pass-through.
    """

    # Awaiting DDL file from user.
    raise NotImplementedError("TODO: implement after DDL provided")


def map_driver_to_row(driver_dict: dict[str, Any]) -> dict[str, Any]:
    """Map a DDL-aligned driver CSV row to its Supabase row representation.

    The CSV column names already match the DB column names, so this future
    mapper should be a near-1:1 pass-through.
    """

    # Awaiting DDL file from user.
    raise NotImplementedError("TODO: implement after DDL provided")


def map_driver_score_to_row(account_id: int | str, score_dict: dict[str, Any]) -> dict[str, Any]:
    """Map a driver score payload to a future Supabase row.

    The CSV/DDL alignment established in the writer layer keeps the eventual
    mapping near-1:1 once the DDL is provided.
    """

    # Awaiting DDL file from user.
    raise NotImplementedError("TODO: implement after DDL provided")


def map_trip_to_row(account_id: int | str, trip_dict: dict[str, Any]) -> dict[str, Any]:
    """Map a trip score payload to a future Supabase row.

    The CSV/DDL alignment established in the writer layer keeps the eventual
    mapping near-1:1 once the DDL is provided.
    """

    # Awaiting DDL file from user.
    raise NotImplementedError("TODO: implement after DDL provided")
