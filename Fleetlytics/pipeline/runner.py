"""Daily orchestration for discovery, pull, convert, import, and reporting."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
from time import perf_counter
from typing import Any, Iterator

from dotenv import load_dotenv
import psycopg
from psycopg import sql

from Fleetlytics.converters.api import ENTITY_ORDER as CONVERT_ENTITY_ORDER
from Fleetlytics.converters.api import convert_entity
from Fleetlytics.importers.api import import_entity
from Fleetlytics.pipeline.discovery import ReconciliationResult, discover_and_reconcile_fleets
from Fleetlytics.pipeline.pull import configure_pull_runtime, pull_one_fleet
from Fleetlytics.pipeline.types import PullRequest
from Fleetlytics.pipeline.window import DateWindow, get_watermark_path, resolve_daily_window
from src.config import AppConfig, format_datetime, get_db_schema, get_db_url, load_pull_runtime_config
from src.logger import configure_logging, get_logger


LOGGER = get_logger(__name__)


@dataclass(slots=True)
class DailyFleetOutcome:
    fleet_internal_id: str
    retailer_location_id: int | None
    pull_status: str
    convert_status: dict[str, str] = field(default_factory=dict)
    import_status: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "drivers": 0,
            "driver_scores": 0,
            "trip_scores": 0,
            "trip_locations": 0,
            "trip_incidents": 0,
            "sql_inserted": 0,
            "sql_updated": 0,
            "sql_skipped": 0,
        }
    )
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass(slots=True)
class DailyReport:
    run_timestamp: str
    window: DateWindow
    discovery: dict[str, Any]
    fleets: list[DailyFleetOutcome]
    totals: dict[str, int]
    started_at: str
    ended_at: str
    duration_ms: int
    dry_run: bool
    exit_code: int


@dataclass(frozen=True, slots=True)
class _RosterFleet:
    retailer_location_id: int | None
    internal_id: str
    name: str
    active: bool


class _DailyLogPrefixFilter(logging.Filter):
    """Prefix emitted log lines with the daily run timestamp."""

    def __init__(self, run_timestamp: str) -> None:
        super().__init__()
        self.prefix = f"[daily run_ts={run_timestamp}] "

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging plumbing
        message = record.getMessage()
        if not message.startswith(self.prefix):
            record.msg = f"{self.prefix}{message}"
            record.args = ()
        return True


def run_daily(*, dry_run: bool = False) -> DailyReport:
    """
    Full daily pipeline:
      1. Resolve date window + shared run_timestamp.
      2. Discovery + reconciliation (unless DAILY_SKIP_DISCOVERY=true).
      3. Load fleet roster from sirqul_fleet (post-reconciliation).
      4. Pull, convert, and import each fleet.
      5. Aggregate a DailyReport.
      6. Persist the report and update the success watermark when allowed.
    """

    load_dotenv()
    started = perf_counter()
    started_at = _utc_now_iso()
    output_root = Path(os.getenv("OUTPUT_DIR", "output")).expanduser()
    run_timestamp = _compute_run_timestamp()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_dir = Path(os.getenv("LOG_DIR", "logs")).expanduser()
    configure_logging(log_dir, log_level)

    with _prefixed_daily_logging(run_timestamp):
        window = resolve_daily_window()
        _apply_window_env(window)
        configure_pull_runtime(_load_daily_pull_runtime_config())

        fail_policy = _resolve_fail_policy()
        skip_discovery = _env_bool("DAILY_SKIP_DISCOVERY", default=False)
        max_fleets = _resolve_daily_max_fleets()

        discovery_result: ReconciliationResult | None = None
        discovery_summary: dict[str, Any]
        if skip_discovery:
            discovery_summary = {"skipped": True}
        else:
            discovery_result = discover_and_reconcile_fleets(
                output_root=output_root,
                run_timestamp=run_timestamp,
                dry_run=dry_run,
            )
            discovery_summary = _condense_discovery_result(discovery_result, dry_run=dry_run)
            if fail_policy == "fail_fast" and discovery_result.errors:
                ended_at = _utc_now_iso()
                report = DailyReport(
                    run_timestamp=run_timestamp,
                    window=window,
                    discovery=discovery_summary,
                    fleets=[],
                    totals=_compute_totals([], discovery_errors=len(discovery_result.errors)),
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=int((perf_counter() - started) * 1000),
                    dry_run=dry_run,
                    exit_code=2,
                )
                _persist_daily_outputs(report, output_root=output_root)
                return report

        roster = _load_roster(max_fleets=max_fleets)
        if not roster:
            LOGGER.error("No active fleets found in sirqul_fleet.")
            ended_at = _utc_now_iso()
            discovery_errors = len(discovery_result.errors) if discovery_result is not None else 0
            report = DailyReport(
                run_timestamp=run_timestamp,
                window=window,
                discovery=discovery_summary,
                fleets=[],
                totals=_compute_totals([], discovery_errors=discovery_errors),
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=int((perf_counter() - started) * 1000),
                dry_run=dry_run,
                exit_code=2,
            )
            _persist_daily_outputs(report, output_root=output_root)
            return report

        fleet_outcomes: list[DailyFleetOutcome] = []
        fail_fast_triggered = False
        remaining_roster: list[_RosterFleet] = []

        for index, roster_fleet in enumerate(roster):
            outcome = _process_one_fleet(
                roster_fleet=roster_fleet,
                output_root=output_root,
                run_timestamp=run_timestamp,
                window=window,
                dry_run=dry_run,
            )
            fleet_outcomes.append(outcome)
            if fail_policy == "fail_fast" and outcome.pull_status != "ok":
                fail_fast_triggered = True
                remaining_roster = roster[index + 1 :]
                break

        if fail_fast_triggered:
            for roster_fleet in remaining_roster:
                fleet_outcomes.append(
                    DailyFleetOutcome(
                        fleet_internal_id=roster_fleet.internal_id,
                        retailer_location_id=roster_fleet.retailer_location_id,
                        pull_status="skipped",
                    )
                )

        discovery_errors = len(discovery_result.errors) if discovery_result is not None else 0
        totals = _compute_totals(fleet_outcomes, discovery_errors=discovery_errors)
        exit_code = _resolve_exit_code(
            fleet_outcomes,
            fail_policy=fail_policy,
            fail_fast_triggered=fail_fast_triggered,
            roster_empty=False,
        )

        report = DailyReport(
            run_timestamp=run_timestamp,
            window=window,
            discovery=discovery_summary,
            fleets=fleet_outcomes,
            totals=totals,
            started_at=started_at,
            ended_at=_utc_now_iso(),
            duration_ms=int((perf_counter() - started) * 1000),
            dry_run=dry_run,
            exit_code=exit_code,
        )
        _persist_daily_outputs(report, output_root=output_root)
        if not dry_run:
            _refresh_dashboard_materialized_views()
        if report.exit_code == 0 and not dry_run:
            _write_success_watermark(window)
        return report


def _process_one_fleet(
    *,
    roster_fleet: _RosterFleet,
    output_root: Path,
    run_timestamp: str,
    window: DateWindow,
    dry_run: bool,
) -> DailyFleetOutcome:
    fleet_started = perf_counter()
    outcome = DailyFleetOutcome(
        fleet_internal_id=roster_fleet.internal_id,
        retailer_location_id=roster_fleet.retailer_location_id,
        pull_status="error",
    )
    req = PullRequest(
        fleet_internal_id=str(roster_fleet.internal_id),
        retailer_location_id=roster_fleet.retailer_location_id,
        date_range_start=window.start,
        date_range_end=window.end,
        output_root=output_root,
        run_timestamp=run_timestamp,
    )

    pull_result = pull_one_fleet(req)
    outcome.pull_status = pull_result.status
    outcome.counts["drivers"] = pull_result.driver_count
    outcome.counts["driver_scores"] = pull_result.driver_score_count
    outcome.counts["trip_scores"] = pull_result.trip_score_count
    outcome.counts["trip_locations"] = pull_result.trip_location_count
    outcome.counts["trip_incidents"] = pull_result.trip_incident_count
    outcome.errors.extend(pull_result.errors)

    if pull_result.status == "error":
        outcome.duration_ms = int((perf_counter() - fleet_started) * 1000)
        return outcome

    for entity in CONVERT_ENTITY_ORDER:
        outcome.convert_status.setdefault(entity, "skipped")
        outcome.import_status.setdefault(entity, "skipped")

    drivers_convert_failed = False
    for entity in CONVERT_ENTITY_ORDER:
        if drivers_convert_failed and entity in {"driver_scores", "trip_scores"}:
            outcome.convert_status[entity] = "skipped"
            outcome.import_status[entity] = "skipped"
            continue

        try:
            convert_entity(entity, pull_result.run_dir)
            outcome.convert_status[entity] = "ok"
        except Exception as exc:
            outcome.convert_status[entity] = "error"
            outcome.import_status[entity] = "skipped"
            outcome.errors.append(f"{entity} convert failed: {exc}")
            LOGGER.exception("Entity conversion failed entity=%s run_dir=%s", entity, pull_result.run_dir)
            if entity == "drivers":
                drivers_convert_failed = True
            continue

        try:
            import_result = import_entity(entity, pull_result.run_dir, dry_run=dry_run)
        except Exception as exc:
            outcome.import_status[entity] = "error"
            outcome.errors.append(f"{entity} import failed: {exc}")
            LOGGER.exception("Entity import failed entity=%s run_dir=%s", entity, pull_result.run_dir)
            continue

        outcome.import_status[entity] = "error" if import_result.status == "error" else "ok"
        if import_result.errors:
            outcome.errors.extend(f"{entity} import failed: {error}" for error in import_result.errors)
        outcome.counts["sql_inserted"] += import_result.rows_inserted
        outcome.counts["sql_updated"] += import_result.rows_updated
        outcome.counts["sql_skipped"] += import_result.rows_skipped

    if outcome.errors:
        if any(status == "error" for status in outcome.convert_status.values()) or any(
            status == "error" for status in outcome.import_status.values()
        ):
            outcome.pull_status = "error" if pull_result.status == "error" else "partial"
        elif outcome.pull_status == "ok":
            outcome.pull_status = "partial"

    outcome.duration_ms = int((perf_counter() - fleet_started) * 1000)
    return outcome


def _load_roster(*, max_fleets: int | None) -> list[_RosterFleet]:
    schema = get_db_schema()
    query = sql.SQL(
        """
        SELECT retailer_location_id, internal_id, name, active
        FROM {}.sirqul_fleet
        WHERE active = TRUE
          AND EXISTS (
              SELECT 1
              FROM public.companies c
              WHERE c.focus_data->'eventInfo'->>'flAccountId' = {}.sirqul_fleet.retailer_location_id::text
          )
        ORDER BY retailer_location_id
        """
    ).format(sql.Identifier(schema), sql.Identifier(schema))

    roster: list[_RosterFleet] = []
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            for retailer_location_id, internal_id, name, active in cursor.fetchall():
                roster.append(
                    _RosterFleet(
                        retailer_location_id=retailer_location_id,
                        internal_id=str(internal_id),
                        name=str(name),
                        active=bool(active),
                    )
                )

    if max_fleets is not None:
        roster = roster[:max_fleets]
    return roster


def _persist_daily_outputs(report: DailyReport, *, output_root: Path) -> None:
    daily_dir = Path(output_root) / "_daily" / report.run_timestamp
    latest_dir = Path(output_root) / "_daily" / "latest"
    daily_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    report_payload = _serialize_daily_report(report)
    report_path = daily_dir / "daily_report.json"
    report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copyfile(report_path, latest_dir / "daily_report.json")


def _serialize_daily_report(report: DailyReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["window"] = {
        "start": report.window.start.isoformat(timespec="seconds"),
        "end": report.window.end.isoformat(timespec="seconds"),
        "source": report.window.source,
    }
    return payload


def _write_success_watermark(window: DateWindow) -> None:
    watermark_path = get_watermark_path()
    watermark_path.parent.mkdir(parents=True, exist_ok=True)
    watermark_path.write_text(
        json.dumps(
            {
                "last_success_end": window.end.isoformat(timespec="seconds"),
                "last_run_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _refresh_dashboard_materialized_views() -> None:
    """Refresh the dashboard materialized views after a completed import run."""

    schema = get_db_schema()
    statements = [
        sql.SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}.{}").format(
            sql.Identifier(schema),
            sql.Identifier(view_name),
        )
        for view_name in (
            "sirqul_driver_trip_list",
            "sirqul_trip_day_rollup",
            "sirqul_performance_groups",
            "sirqul_trip_event_day_rollup",
            "sirqul_trip_event_groups",
        )
    ]

    LOGGER.info("Refreshing dashboard materialized views schema=%s", schema)
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
                LOGGER.info("Refreshed materialized view statement=%s", statement)


def _condense_discovery_result(result: ReconciliationResult, *, dry_run: bool) -> dict[str, Any]:
    return {
        "skipped": False,
        "dry_run": dry_run,
        "fetched_at": result.fetched_at.isoformat(),
        "counts": {
            "seen": result.total_seen(),
            "known": len(result.known),
            "inserted": len(result.inserted),
            "pending": len(result.pending),
            "errors": len(result.errors),
        },
        "known": [asdict(fleet) for fleet in result.known],
        "inserted": [asdict(fleet) for fleet in result.inserted],
        "pending": [asdict(fleet) for fleet in result.pending],
        "errors": list(result.errors),
    }


def _compute_totals(fleets: list[DailyFleetOutcome], *, discovery_errors: int) -> dict[str, int]:
    return {
        "fleets_total": len(fleets),
        "fleets_ok": sum(1 for fleet in fleets if fleet.pull_status == "ok"),
        "fleets_partial": sum(1 for fleet in fleets if fleet.pull_status == "partial"),
        "fleets_error": sum(1 for fleet in fleets if fleet.pull_status == "error"),
        "fleets_skipped": sum(1 for fleet in fleets if fleet.pull_status == "skipped"),
        "driver_count": sum(fleet.counts.get("drivers", 0) for fleet in fleets),
        "driver_score_count": sum(fleet.counts.get("driver_scores", 0) for fleet in fleets),
        "trip_score_count": sum(fleet.counts.get("trip_scores", 0) for fleet in fleets),
        "trip_location_count": sum(fleet.counts.get("trip_locations", 0) for fleet in fleets),
        "trip_incident_count": sum(fleet.counts.get("trip_incidents", 0) for fleet in fleets),
        "sql_inserted": sum(fleet.counts.get("sql_inserted", 0) for fleet in fleets),
        "sql_updated": sum(fleet.counts.get("sql_updated", 0) for fleet in fleets),
        "sql_skipped": sum(fleet.counts.get("sql_skipped", 0) for fleet in fleets),
        "discovery_errors": discovery_errors,
    }


def _resolve_exit_code(
    fleets: list[DailyFleetOutcome],
    *,
    fail_policy: str,
    fail_fast_triggered: bool,
    roster_empty: bool,
) -> int:
    if roster_empty:
        return 2
    if fail_fast_triggered:
        return 1
    attempted = [fleet for fleet in fleets if fleet.pull_status != "skipped"]
    if not attempted:
        return 0
    if any(fleet.pull_status in {"ok", "partial"} for fleet in attempted):
        return 0
    return 1


def _load_daily_pull_runtime_config() -> AppConfig:
    return load_pull_runtime_config()


def _apply_window_env(window: DateWindow) -> None:
    os.environ["DATE_RANGE_START"] = format_datetime(window.start)
    os.environ["DATE_RANGE_END"] = format_datetime(window.end)


def _resolve_fail_policy() -> str:
    policy = os.getenv("DAILY_FAIL_POLICY", "continue").strip().lower() or "continue"
    if policy not in {"continue", "fail_fast"}:
        raise ValueError("DAILY_FAIL_POLICY must be one of: continue, fail_fast")
    return policy


def _resolve_daily_max_fleets() -> int | None:
    raw_value = os.getenv("DAILY_MAX_FLEETS", "").strip()
    if not raw_value:
        return None
    max_fleets = int(raw_value)
    if max_fleets <= 0:
        raise ValueError("DAILY_MAX_FLEETS must be a positive integer when set")
    return max_fleets


def _env_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean-like value")


def _compute_run_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def _prefixed_daily_logging(run_timestamp: str) -> Iterator[None]:
    root_logger = logging.getLogger()
    log_filter = _DailyLogPrefixFilter(run_timestamp)
    attached_handlers: list[logging.Handler] = []

    for handler in root_logger.handlers:
        handler.addFilter(log_filter)
        attached_handlers.append(handler)

    try:
        yield
    finally:
        for handler in attached_handlers:
            handler.removeFilter(log_filter)


if __name__ == "__main__":  # pragma: no cover - smoke example only
    empty_outcome = DailyFleetOutcome(
        fleet_internal_id="demo-fleet",
        retailer_location_id=101,
        pull_status="skipped",
    )
    empty_report = DailyReport(
        run_timestamp="2026-06-15_120000",
        window=DateWindow(start=datetime(2026, 6, 14, tzinfo=timezone.utc).date(), end=datetime(2026, 6, 15, tzinfo=timezone.utc).date(), source="rolling_24h"),
        discovery={"skipped": True},
        fleets=[empty_outcome],
        totals=_compute_totals([empty_outcome], discovery_errors=0),
        started_at="2026-06-15T12:00:00Z",
        ended_at="2026-06-15T12:00:01Z",
        duration_ms=1000,
        dry_run=True,
        exit_code=0,
    )
    print(empty_outcome)
    print(empty_report)
