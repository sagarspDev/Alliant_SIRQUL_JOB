"""Programmatic import entrypoints shared by the CLI and daily runner."""

from __future__ import annotations

from pathlib import Path

from Fleetlytics.importers.base import ImportResult
from Fleetlytics.importers.driver_scores import import_driver_scores
from Fleetlytics.importers.drivers import import_drivers
from Fleetlytics.importers.fleet import import_fleet
from Fleetlytics.importers.trip_incidents import import_trip_incidents
from Fleetlytics.importers.trip_locations import import_trip_locations
from Fleetlytics.importers.trip_scores import import_trip_scores


ENTITY_ORDER = ("fleet", "drivers", "driver_scores", "trip_scores", "trip_locations", "trip_incidents")
ENTITY_SQL_FILENAMES = {
    "fleet": "001_fleet.sql",
    "drivers": "002_drivers.sql",
    "driver_scores": "003_driver_scores.sql",
    "trip_scores": "004_trip_scores.sql",
    "trip_locations": "005_trip_locations.sql",
    "trip_incidents": "006_trip_incidents.sql",
}


def import_entity(entity: str, run_dir: Path, *, dry_run: bool = False) -> ImportResult:
    """Import one entity SQL file for a specific run directory."""

    resolved_run_dir = Path(run_dir).expanduser()
    sql_path = resolved_run_dir / "sql" / _sql_filename_for_entity(entity)

    if entity == "fleet":
        return import_fleet(sql_path, dry_run=dry_run)
    if entity == "drivers":
        return import_drivers(sql_path, dry_run=dry_run)
    if entity == "driver_scores":
        return import_driver_scores(sql_path, dry_run=dry_run)
    if entity == "trip_scores":
        return import_trip_scores(sql_path, dry_run=dry_run)
    if entity == "trip_locations":
        return import_trip_locations(sql_path, dry_run=dry_run)
    if entity == "trip_incidents":
        return import_trip_incidents(sql_path, dry_run=dry_run)
    raise ValueError(f"Unsupported importer entity: {entity!r}")


def _sql_filename_for_entity(entity: str) -> str:
    try:
        return ENTITY_SQL_FILENAMES[entity]
    except KeyError as exc:
        raise ValueError(f"Unsupported importer entity: {entity!r}") from exc
