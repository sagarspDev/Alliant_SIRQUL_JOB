"""Trip-location SQL importer."""

from __future__ import annotations

from pathlib import Path

from .base import ImportResult, SQLFileImporter


def import_trip_locations(sql_path: Path, *, dry_run: bool) -> ImportResult:
    """Import the generated trip-location SQL file."""

    importer = SQLFileImporter()
    return importer.run(Path(sql_path), dry_run=dry_run)
