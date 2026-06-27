"""Programmatic conversion entrypoints shared by the CLI and daily runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Fleetlytics.converters.driver_scores import DriverScoreConverter
from Fleetlytics.converters.drivers import DriverConverter
from Fleetlytics.converters.fleet import FleetConverter
from Fleetlytics.converters.trip_incidents import TripIncidentConverter
from Fleetlytics.converters.trip_locations import TripLocationConverter
from Fleetlytics.converters.trip_scores import TripScoreConverter


ENTITY_ORDER = ("fleet", "drivers", "driver_scores", "trip_scores", "trip_locations", "trip_incidents")


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """Summary of one entity conversion."""

    entity: str
    run_dir: Path
    output_path: Path
    status: str = "ok"


def convert_entity(entity: str, run_dir: Path) -> ConvertResult:
    """Convert one entity for a specific run directory."""

    converter = _converter_for_entity(entity)
    resolved_run_dir = Path(run_dir).expanduser()
    output_path = converter.write_run_sql(resolved_run_dir)
    return ConvertResult(
        entity=entity,
        run_dir=resolved_run_dir,
        output_path=output_path,
        status="ok",
    )


def _converter_for_entity(entity: str):
    if entity == "fleet":
        return FleetConverter()
    if entity == "drivers":
        return DriverConverter()
    if entity == "driver_scores":
        return DriverScoreConverter()
    if entity == "trip_scores":
        return TripScoreConverter()
    if entity == "trip_locations":
        return TripLocationConverter()
    if entity == "trip_incidents":
        return TripIncidentConverter()
    raise ValueError(f"Unsupported converter entity: {entity!r}")
