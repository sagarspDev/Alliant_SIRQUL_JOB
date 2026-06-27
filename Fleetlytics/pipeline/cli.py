"""CLI entrypoints for Fleetlytics pipeline helpers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Sequence

from dotenv import load_dotenv

from Fleetlytics.pipeline import cron as cron_module
from Fleetlytics.pipeline.discovery import ReconciliationResult, discover_and_reconcile_fleets
from Fleetlytics.pipeline.runner import DailyReport, run_daily
from Fleetlytics.pipeline.trip_details_backfill import TripDetailsBackfillReport, run_trip_details_backfill
from src.config import ConfigError
from src.logger import configure_logging, get_logger


LOGGER = get_logger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse pipeline CLI arguments."""

    parser = argparse.ArgumentParser(description="Fleetlytics pipeline utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Run fleet discovery and reconciliation")
    discover_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery without committing DB writes",
    )
    run_daily_parser = subparsers.add_parser("run-daily", help="Run the daily multi-fleet pipeline")
    run_daily_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery and imports without committing DB writes",
    )
    run_daily_parser.add_argument(
        "--window-hours",
        type=int,
        help="Override DAILY_WINDOW_HOURS and use rolling_hours mode",
    )
    cron_parser = subparsers.add_parser("cron", help="Run the cron-safe daily wrapper")
    cron_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery and imports without committing DB writes",
    )
    cron_parser.add_argument(
        "--lock-wait-seconds",
        type=int,
        default=0,
        metavar="N",
        help="Wait up to N seconds for the cron lock before exiting 75",
    )
    cron_parser.add_argument(
        "--window-hours",
        type=int,
        help="Override DAILY_WINDOW_HOURS and use rolling_hours mode",
    )
    backfill_parser = subparsers.add_parser(
        "backfill-trip-details",
        help="Backfill trip locations and incidents from stored trip scores",
    )
    backfill_parser.add_argument(
        "--start",
        help="Override DATE_RANGE_START from .env (format: YYYY-MM-DD HH:MM:SS)",
    )
    backfill_parser.add_argument(
        "--end",
        help="Override DATE_RANGE_END from .env (format: YYYY-MM-DD HH:MM:SS)",
    )
    backfill_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the backfill and imports without committing DB writes",
    )

    return parser.parse_args(argv)


def _compute_run_timestamp() -> str:
    """Return the timestamp used for discovery diagnostics."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC")


def _format_discovery_summary(result: ReconciliationResult, dry_run: bool) -> str:
    """Render the discovery summary line."""

    return (
        "[discovery] "
        f"seen={result.total_seen()} "
        f"known={len(result.known)} "
        f"inserted={len(result.inserted)} "
        f"pending={len(result.pending)} "
        f"errors={len(result.errors)} "
        f"dry_run={dry_run}"
    )


def _format_daily_summary(report: DailyReport) -> str:
    totals = report.totals
    return (
        "[daily] "
        f"fleets_total={totals.get('fleets_total', 0)} "
        f"fleets_ok={totals.get('fleets_ok', 0)} "
        f"fleets_partial={totals.get('fleets_partial', 0)} "
        f"fleets_error={totals.get('fleets_error', 0)} "
        f"fleets_skipped={totals.get('fleets_skipped', 0)} "
        f"sql_inserted={totals.get('sql_inserted', 0)} "
        f"sql_updated={totals.get('sql_updated', 0)} "
        f"sql_skipped={totals.get('sql_skipped', 0)} "
        f"trip_location_count={totals.get('trip_location_count', 0)} "
        f"trip_incident_count={totals.get('trip_incident_count', 0)} "
        f"discovery_errors={totals.get('discovery_errors', 0)} "
        f"dry_run={report.dry_run} "
        f"exit_code={report.exit_code}"
    )


def _format_trip_details_summary(report: TripDetailsBackfillReport) -> str:
    return (
        "[trip-details-backfill] "
        f"status={report.status} "
        f"trip_count={report.trip_count} "
        f"trip_location_count={report.trip_location_count} "
        f"trip_incident_count={report.trip_incident_count} "
        f"duration_ms={report.duration_ms} "
        f"errors={len(report.errors)} "
        f"dry_run={report.dry_run}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch Fleetlytics pipeline subcommands."""

    load_dotenv()
    args = parse_args(argv)

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_dir = Path(os.getenv("LOG_DIR", "logs")).expanduser()
    configure_logging(log_dir, log_level)

    if args.command == "discover":
        output_root = Path(os.getenv("OUTPUT_DIR", "output")).expanduser()
        result = discover_and_reconcile_fleets(
            output_root=output_root,
            run_timestamp=_compute_run_timestamp(),
            dry_run=bool(args.dry_run),
        )
        summary = _format_discovery_summary(result, bool(args.dry_run))
        print(summary)
        LOGGER.info(summary)
        return 0 if not result.errors else 2
    if args.command == "run-daily":
        _apply_window_override(args.window_hours)
        try:
            report = run_daily(dry_run=bool(args.dry_run))
        except (ConfigError, ValueError) as exc:
            print(f"Configuration error: {exc}", file=sys.stderr)
            return 2
        summary = _format_daily_summary(report)
        print(summary)
        LOGGER.info(summary)
        return report.exit_code
    if args.command == "cron":
        _apply_window_override(args.window_hours)
        cron_argv: list[str] = []
        if args.dry_run:
            cron_argv.append("--dry-run")
        cron_argv.extend(["--lock-wait-seconds", str(args.lock_wait_seconds)])
        return cron_module.main(cron_argv)
    if args.command == "backfill-trip-details":
        if args.start is not None:
            os.environ["DATE_RANGE_START"] = str(args.start).strip()
        if args.end is not None:
            os.environ["DATE_RANGE_END"] = str(args.end).strip()
        report = run_trip_details_backfill(dry_run=bool(args.dry_run))
        summary = _format_trip_details_summary(report)
        print(summary)
        LOGGER.info(summary)
        return 0 if report.status == "ok" else 1

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


def _apply_window_override(window_hours: int | None) -> None:
    """Apply an optional rolling-hours override before dispatching the run."""

    if window_hours is None:
        return
    if window_hours <= 0:
        raise SystemExit("--window-hours must be a positive integer")
    os.environ["DAILY_WINDOW_MODE"] = "rolling_hours"
    os.environ["DAILY_WINDOW_HOURS"] = str(window_hours)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
