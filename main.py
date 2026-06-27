"""Fleetlytics orchestration entry point."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Sequence

try:  # pragma: no cover - execution context dependent
    from .pipeline.pull import configure_pull_runtime, pull_one_fleet
    from .pipeline.types import PullRequest, PullResult
    from .src.config import ConfigError, DATE_FORMAT, load_config
    from .src.logger import configure_logging, get_logger
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from Fleetlytics.pipeline.pull import configure_pull_runtime, pull_one_fleet
    from Fleetlytics.pipeline.types import PullRequest, PullResult
    from src.config import ConfigError, DATE_FORMAT, load_config
    from src.logger import configure_logging, get_logger


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse Fleetlytics CLI arguments."""

    parser = argparse.ArgumentParser(description="Run the Fleetlytics one-time data pull pipeline")
    parser.add_argument(
        "--retailer-location-id",
        dest="retailer_location_id",
        help="Override TARGET_RETAILER_LOCATION_ID from .env",
    )
    parser.add_argument(
        "--start",
        help=f"Override DATE_RANGE_START from .env (format: {DATE_FORMAT.replace('%', '%%')})",
    )
    parser.add_argument(
        "--end",
        help=f"Override DATE_RANGE_END from .env (format: {DATE_FORMAT.replace('%', '%%')})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all API calls but skip file writes",
    )
    return parser.parse_args(argv)


def apply_cli_overrides(args: argparse.Namespace) -> None:
    """Apply CLI overrides before loading the .env-backed configuration."""

    if args.retailer_location_id:
        os.environ["TARGET_RETAILER_LOCATION_ID"] = str(args.retailer_location_id).strip()

    if args.start is not None:
        os.environ["DATE_RANGE_START"] = str(args.start).strip()

    if args.end is not None:
        os.environ["DATE_RANGE_END"] = str(args.end).strip()


def _compute_run_timestamp() -> str:
    """Return the timestamp used for run-scoped output directories."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")


def _format_result_summary(result: PullResult) -> str:
    """Render a one-line summary for the completed pull."""

    return (
        "Fleetlytics pull "
        f"fleet={result.fleet_internal_id} "
        f"status={result.status} "
        f"fleet_ok={result.fleet_ok} "
        f"drivers_ok={result.drivers_ok} "
        f"driver_scores_ok={result.driver_scores_ok} "
        f"trip_scores_ok={result.trip_scores_ok} "
        f"trip_locations_ok={result.trip_locations_ok} "
        f"trip_incidents_ok={result.trip_incidents_ok} "
        f"driver_count={result.driver_count} "
        f"driver_score_count={result.driver_score_count} "
        f"trip_score_count={result.trip_score_count} "
        f"trip_location_count={result.trip_location_count} "
        f"trip_incident_count={result.trip_incident_count} "
        f"duration_ms={result.duration_ms} "
        f"errors={len(result.errors)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the Fleetlytics one-time pipeline."""

    args = parse_args(argv)
    apply_cli_overrides(args)

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    log_file = configure_logging(config.log_dir, config.log_level)
    logger = get_logger(__name__)
    configure_pull_runtime(config)

    run_timestamp = _compute_run_timestamp()
    # NOTE: TARGET_RETAILER_LOCATION_ID still carries the fleet identifier for backward compatibility.
    req = PullRequest(
        fleet_internal_id=str(config.target_retailer_location_id),
        retailer_location_id=None,
        date_range_start=config.date_range.start,
        date_range_end=config.date_range.end,
        output_root=Path(config.output_dir).expanduser(),
        run_timestamp=run_timestamp,
    )

    logger.info(
        "RUN STARTED fleet=%s run_timestamp=%s date_range=%s -> %s planned_output_dir=%s log_file=%s dry_run=%s",
        req.fleet_internal_id,
        req.run_timestamp,
        config.date_range.start,
        config.date_range.end,
        Path(config.output_dir).expanduser() / req.fleet_internal_id / req.run_timestamp,
        log_file,
        args.dry_run,
    )

    result = pull_one_fleet(req)
    summary = _format_result_summary(result)
    print(summary)
    logger.info(summary)

    return 0 if result.status in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
