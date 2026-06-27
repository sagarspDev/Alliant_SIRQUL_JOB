"""DEFERRED - not part of the active daily pipeline. See FLEETLYTICS_CONTEXT.md Phase E.

Supabase sink placeholder for future Fleetlytics ingestion.

Planned behavior:
- This sink will be triggered alongside the existing file writers.
- It will require Supabase credentials provided through ``.env``.
- It will rely on DDL-driven row mapping via ``ddl_mapper.py``.

The implementation is intentionally deferred until the DDL file is provided.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

try:  # pragma: no cover - execution context dependent
    from ..writers import EntityWriteResult, RunPaths
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from writers import EntityWriteResult, RunPaths


class SupabaseSink:
    """Placeholder sink that mirrors the OutputWriter interface."""

    def write_fleet(self, fleet_dict: Mapping[str, Any], run_paths: RunPaths) -> EntityWriteResult:
        raise NotImplementedError("TODO: implement after DDL provided")

    def write_drivers(self, drivers_list: Sequence[Mapping[str, Any]], run_paths: RunPaths) -> EntityWriteResult:
        raise NotImplementedError("TODO: implement after DDL provided")

    def write_driver_scores(
        self,
        scores_by_driver: Mapping[int | str, Sequence[Mapping[str, Any]]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        raise NotImplementedError("TODO: implement after DDL provided")

    def write_trip_scores(
        self,
        trips_by_driver: Mapping[int | str, Sequence[Mapping[str, Any]]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        raise NotImplementedError("TODO: implement after DDL provided")
