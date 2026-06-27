"""Import every active Fleetlytics module and print ``ok``."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


MODULES = [
    "main",
    "fleet_api",
    "reporting_api",
    "writers",
    "src.config",
    "src.http_client",
    "src.logger",
    "Fleetlytics.converters.api",
    "Fleetlytics.converters.cli",
    "Fleetlytics.converters.fleet",
    "Fleetlytics.converters.drivers",
    "Fleetlytics.converters.driver_scores",
    "Fleetlytics.converters.trip_scores",
    "Fleetlytics.converters.trip_locations",
    "Fleetlytics.converters.trip_incidents",
    "Fleetlytics.converters.snapshot",
    "Fleetlytics.converters.lookups",
    "Fleetlytics.importers.api",
    "Fleetlytics.importers.cli",
    "Fleetlytics.importers.fleet",
    "Fleetlytics.importers.drivers",
    "Fleetlytics.importers.driver_scores",
    "Fleetlytics.importers.trip_scores",
    "Fleetlytics.importers.trip_locations",
    "Fleetlytics.importers.trip_incidents",
    "Fleetlytics.importers.reporting",
    "Fleetlytics.pipeline.cli",
    "Fleetlytics.pipeline.cron",
    "Fleetlytics.pipeline.discovery",
    "Fleetlytics.pipeline.paths",
    "Fleetlytics.pipeline.pull",
    "Fleetlytics.pipeline.trip_details_backfill",
    "Fleetlytics.pipeline.runner",
    "Fleetlytics.pipeline.types",
    "Fleetlytics.pipeline.window",
]


for module_name in MODULES:
    importlib.import_module(module_name)

print("ok")
