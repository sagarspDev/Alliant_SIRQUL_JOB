"""DEFERRED - not part of the active daily pipeline. See FLEETLYTICS_CONTEXT.md Phase E.

Placeholder loader for multi-fleet company selection.

The future implementation will read target fleet IDs from a ``companies``
table and return the corresponding ``retailerLocationId`` values.
"""

from __future__ import annotations


def load_target_fleets() -> list[int]:
    raise NotImplementedError("TODO: implement after DDL provided")
