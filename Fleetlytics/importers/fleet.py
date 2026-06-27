"""Fleet SQL importer."""

from __future__ import annotations

from pathlib import Path

from .base import ImportResult, SQLFileImporter


def import_fleet(sql_path: Path, *, dry_run: bool) -> ImportResult:
    """Import the generated fleet SQL file."""

    importer = SQLFileImporter()
    return importer.run(Path(sql_path), dry_run=dry_run)

