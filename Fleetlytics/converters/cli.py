"""CLI scaffold for Fleetlytics JSON-to-SQL conversion."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from Fleetlytics.converters.api import ENTITY_ORDER, convert_entity
from src.config import ConfigError, get_company_id, get_latest_run_dir


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
    """Parse CLI arguments for the conversion scaffold."""

    parser = argparse.ArgumentParser(description="Fleetlytics conversion scaffold")
    parser.add_argument("--entity", choices=ENTITY_CHOICES, required=True)
    parser.add_argument("--run-dir", type=Path, help="Optional explicit run directory")
    parser.add_argument("--out", type=Path, help="Optional output directory override")
    return parser.parse_args(argv)


def resolve_run_dir(args: argparse.Namespace) -> Path:
    """Resolve the run directory for the current invocation."""

    if args.run_dir is not None:
        return args.run_dir.expanduser()
    target_retailer_location_id = os.getenv("TARGET_RETAILER_LOCATION_ID", "").strip()
    if not target_retailer_location_id:
        raise SystemExit("TARGET_RETAILER_LOCATION_ID is required when --run-dir is omitted.")
    return get_latest_run_dir(target_retailer_location_id)


def main(argv: Sequence[str] | None = None) -> int:
    """Convert the selected entity and write the SQL output."""

    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        format="%(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)
    run_dir = resolve_run_dir(args)

    entities = list(ENTITY_ORDER) if args.entity == "all" else [args.entity]

    LOGGER.info("resolved_run_dir=%s", run_dir)
    if "fleet" in entities:
        try:
            company_id = get_company_id()
        except ConfigError as exc:
            raise SystemExit(
                "TARGET_COMPANY_ID is required before generating fleet SQL."
            ) from exc
        LOGGER.info("company_id=%s", company_id)
    for entity in entities:
        try:
            result = convert_entity(entity, run_dir)
        except FileNotFoundError as exc:
            if args.entity == "all":
                LOGGER.warning("Skipping %s conversion because the source file is missing: %s", entity, exc)
                continue
            raise
        output_path = result.output_path
        byte_size = output_path.stat().st_size
        LOGGER.info("entity=%s output_sql_path=%s", entity, output_path)
        LOGGER.info("entity=%s output_sql_bytes=%s", entity, byte_size)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
