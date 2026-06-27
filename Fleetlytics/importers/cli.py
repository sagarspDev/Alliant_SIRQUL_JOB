"""CLI scaffold for Fleetlytics SQL import into Supabase."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Sequence

from dotenv import load_dotenv

from Fleetlytics.importers.api import ENTITY_ORDER, import_entity
from Fleetlytics.importers.reporting import ImportReport
from src.config import get_latest_run_dir


ENTITY_CHOICES = (
    "fleet",
    "drivers",
    "driver_scores",
    "trip_scores",
    "trip_locations",
    "trip_incidents",
    "all",
)
LOGGER = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the import scaffold."""

    parser = argparse.ArgumentParser(description="Fleetlytics import scaffold")
    parser.add_argument("--entity", choices=ENTITY_CHOICES, required=True)
    parser.add_argument("--run-dir", type=Path, help="Optional explicit run directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect SQL files without executing them",
    )
    return parser.parse_args(argv)


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Resolve the run directory for the current invocation."""

    if args.run_dir is not None:
        return args.run_dir.expanduser()
    target_retailer_location_id = os.getenv("TARGET_RETAILER_LOCATION_ID", "").strip()
    if not target_retailer_location_id:
        raise SystemExit("TARGET_RETAILER_LOCATION_ID is required when --run-dir is omitted.")
    return get_latest_run_dir(target_retailer_location_id)


def resolve_sql_files(run_dir: Path, entity: str) -> list[Path]:
    """Resolve the SQL files for a run directory and entity selection."""

    sql_dir = run_dir / "sql"
    if not sql_dir.exists():
        return []
    all_files = sorted(sql_dir.glob("*.sql"))
    if entity == "all":
        return all_files
    return [path for path in all_files if entity in path.stem]


def load_skipped_records(sql_path: Path) -> list[dict[str, Any]]:
    """Load the sibling skipped-driver diagnostics for a SQL file."""

    skipped_path = sql_path.with_suffix(".skipped.json")
    if not skipped_path.exists():
        return []
    try:
        raw_text = skipped_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return []
        payload = json.loads(raw_text)
    except Exception as exc:
        LOGGER.warning("Failed to read skipped diagnostics from %s: %s", skipped_path, exc)
        return []
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    """Import the selected SQL file(s) into Supabase."""

    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        format="%(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)
    run_dir = resolve_run_dir(args)
    sql_files = resolve_sql_files(run_dir, args.entity)
    if not sql_files:
        raise SystemExit(f"No SQL files found for entity {args.entity!r} in {run_dir / 'sql'}.")
    LOGGER.info("resolved_run_dir=%s", run_dir)
    LOGGER.info("resolved_sql_files=%s", [str(path) for path in sql_files])
    LOGGER.info("dry_run=%s", args.dry_run)

    report = ImportReport(run_dir=run_dir)
    entities = list(ENTITY_ORDER) if args.entity == "all" else [args.entity]
    for entity in entities:
        result = import_entity(entity, run_dir, dry_run=args.dry_run)
        sql_path = result.file_path
        report.add_result(result)
        skipped_records = load_skipped_records(sql_path)
        if skipped_records:
            report.add_skipped_records(skipped_records)
        LOGGER.info(
            "sql_path=%s rows_inserted=%s rows_updated=%s rows_skipped=%s skipped_records=%s",
            sql_path,
            result.rows_inserted,
            result.rows_updated,
            result.rows_skipped,
            len(skipped_records),
        )
    report_path = report.write()
    LOGGER.info("import_report_path=%s", report_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
