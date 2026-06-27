"""Cron-facing wrapper for the daily Fleetlytics pipeline."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from pathlib import Path
import socket
import time
import traceback as traceback_module
from typing import Iterator, Sequence

from dotenv import load_dotenv

from Fleetlytics.pipeline.runner import DailyReport, run_daily
from src.logger import configure_logging, get_logger


LOGGER = get_logger(__name__)

_LOCKED_EXIT_CODE = 75


class _UtcDailyFileHandler(TimedRotatingFileHandler):
    """Write to one UTC-dated log file per day and prune old daily logs."""

    def __init__(self, log_dir: Path, *, backup_count: int) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(
            filename=str(self._current_log_path()),
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8",
            utc=True,
        )
        self._prune_old_logs()

    def _current_log_path(self) -> Path:
        return self.log_dir / f"daily_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    def doRollover(self) -> None:  # pragma: no cover - runtime logging plumbing
        if self.stream:
            self.stream.close()
            self.stream = None

        self.baseFilename = os.fspath(self._current_log_path())
        if not self.delay:
            self.stream = self._open()

        current_time = int(time.time())
        self.rolloverAt = self.computeRollover(current_time)
        self._prune_old_logs()

    def _prune_old_logs(self) -> None:
        if self.backupCount <= 0:
            return
        candidates = sorted(self.log_dir.glob("daily_????-??-??.log"))
        for stale_path in candidates[:-self.backupCount]:
            try:
                stale_path.unlink()
            except FileNotFoundError:
                continue


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse cron wrapper arguments."""

    parser = argparse.ArgumentParser(description="Fleetlytics cron wrapper")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery and imports without committing DB writes",
    )
    parser.add_argument(
        "--lock-wait-seconds",
        type=int,
        default=0,
        metavar="N",
        help="Wait up to N seconds for the cron lock before exiting 75",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        help="Override DAILY_WINDOW_HOURS and use rolling_hours mode",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Cron entrypoint. Returns the exit code to be propagated to the shell.
    """

    load_dotenv()
    args = parse_args(argv)
    _apply_window_override(args.window_hours)
    started_monotonic = time.perf_counter()
    started_at = _utc_now_iso()
    run_timestamp = _compute_run_timestamp()
    lock_path = _resolve_lock_path()
    health_path = _resolve_health_path()
    log_dir = _resolve_log_dir()
    log_path = log_dir / f"daily_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    try:
        if args.lock_wait_seconds < 0:
            raise ValueError("--lock-wait-seconds must be >= 0")

        retention_days = _resolve_retention_days()
        configure_logging(log_dir, _resolve_log_level())
        log_path = _attach_cron_file_handler(log_dir, retention_days=retention_days)

        with _acquire_lock(lock_path, wait_seconds=args.lock_wait_seconds):
            report = run_daily(dry_run=bool(args.dry_run))
            _write_healthcheck(
                health_path,
                _build_report_healthcheck(
                    report,
                    dry_run=report.dry_run,
                    started_at=report.started_at,
                    ended_at=report.ended_at,
                    duration_ms=int((time.perf_counter() - started_monotonic) * 1000),
                ),
            )
            return report.exit_code
    except _LockUnavailable:
        ended_at = _utc_now_iso()
        LOGGER.error("Daily cron wrapper could not acquire lock path=%s", lock_path)
        _safe_write_healthcheck(
            health_path,
            {
                "status": "locked",
                "exit_code": _LOCKED_EXIT_CODE,
                "run_timestamp": run_timestamp,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": int((time.perf_counter() - started_monotonic) * 1000),
                "dry_run": bool(args.dry_run),
                "host": socket.gethostname(),
                "pid": os.getpid(),
                "lock_path": str(lock_path),
                "log_path": str(log_path),
            },
        )
        return _LOCKED_EXIT_CODE
    except Exception as exc:
        ended_at = _utc_now_iso()
        LOGGER.critical("Cron wrapper crashed", exc_info=True)
        _safe_write_healthcheck(
            health_path,
            {
                "status": "crashed",
                "exit_code": 1,
                "run_timestamp": run_timestamp,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": int((time.perf_counter() - started_monotonic) * 1000),
                "dry_run": bool(args.dry_run),
                "host": socket.gethostname(),
                "pid": os.getpid(),
                "exception": f"{type(exc).__name__}: {exc}",
                "traceback": traceback_module.format_exc()[:4096],
                "lock_path": str(lock_path),
                "health_path": str(health_path),
                "log_path": str(log_path),
            },
        )
        return 1


def _resolve_lock_path() -> Path:
    return Path(os.getenv("CRON_LOCK_PATH", "Fleetlytics/state/daily.lock")).expanduser()


def _resolve_health_path() -> Path:
    return Path(os.getenv("CRON_HEALTH_PATH", "Fleetlytics/state/daily_health.json")).expanduser()


def _resolve_log_dir() -> Path:
    return Path(os.getenv("LOG_DIR", "logs")).expanduser()


def _resolve_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"


def _apply_window_override(window_hours: int | None) -> None:
    if window_hours is None:
        return
    if window_hours <= 0:
        raise ValueError("--window-hours must be a positive integer")
    os.environ["DAILY_WINDOW_MODE"] = "rolling_hours"
    os.environ["DAILY_WINDOW_HOURS"] = str(window_hours)


def _resolve_retention_days() -> int:
    raw_value = os.getenv("CRON_LOG_RETENTION_DAYS", "30").strip() or "30"
    retention_days = int(raw_value)
    if retention_days <= 0:
        raise ValueError("CRON_LOG_RETENTION_DAYS must be a positive integer")
    return retention_days


def _attach_cron_file_handler(log_dir: Path, *, retention_days: int) -> Path:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if getattr(handler, "_fleetlytics_cron_handler", False):
            return Path(handler.baseFilename)

    # NOTE: configure_logging() must run first; it short-circuits on repeat calls,
    # which lets this additive handler survive run_daily()'s internal setup path.
    handler = _UtcDailyFileHandler(log_dir, backup_count=retention_days)
    handler._fleetlytics_cron_handler = True  # type: ignore[attr-defined]
    formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    return Path(handler.baseFilename)


@contextmanager
def _acquire_lock(lock_path: Path, *, wait_seconds: int) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    lock_file = lock_path.open("a+", encoding="utf-8")

    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise _LockUnavailable(str(lock_path)) from exc
                time.sleep(1)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    if time.monotonic() >= deadline:
                        raise _LockUnavailable(str(lock_path)) from exc
                    time.sleep(1)
                    continue
                raise

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f"pid={os.getpid()}\nacquired_at={_utc_now_iso()}\n")
        lock_file.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def _build_report_healthcheck(
    report: DailyReport,
    *,
    dry_run: bool,
    started_at: str,
    ended_at: str,
    duration_ms: int,
) -> dict[str, object]:
    totals = dict(report.totals)
    payload: dict[str, object] = {
        "status": _status_from_report(report),
        "exit_code": report.exit_code,
        "run_timestamp": report.run_timestamp,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "window": {
            "start": report.window.start.isoformat(),
            "end": report.window.end.isoformat(),
            "source": report.window.source,
        },
        "totals": totals,
        "fleets_total": totals.get("fleets_total", len(report.fleets)),
        "fleets_ok": totals.get("fleets_ok", 0),
        "fleets_error": totals.get("fleets_error", 0),
        "dry_run": dry_run,
        "report_path": str(_resolve_output_dir() / "_daily" / report.run_timestamp / "daily_report.json"),
        "host": socket.gethostname(),
        "pid": os.getpid(),
    }
    reason = _detect_exit_reason(report)
    if reason is not None:
        payload["reason"] = reason
    return payload


def _status_from_report(report: DailyReport) -> str:
    if report.exit_code == 0:
        return "ok" if report.totals.get("fleets_error", 0) == 0 else "partial"
    if report.exit_code in {1, 2}:
        return "error"
    if report.exit_code == _LOCKED_EXIT_CODE:
        return "locked"
    return "error"


def _detect_exit_reason(report: DailyReport) -> str | None:
    if report.exit_code != 2:
        return None
    discovery_errors = int(report.totals.get("discovery_errors", 0))
    if discovery_errors > 0:
        return "discovery_failed"
    if report.totals.get("fleets_total", 0) == 0:
        return "empty_roster"
    return None


def _write_healthcheck(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_write_healthcheck(path: Path, payload: dict[str, object]) -> None:
    try:
        _write_healthcheck(path, payload)
    except Exception:
        LOGGER.exception("Failed to write cron healthcheck path=%s", path)


def _resolve_output_dir() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output")).expanduser()


def _compute_run_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class _LockUnavailable(RuntimeError):
    """Raised when the cron lock cannot be acquired before the deadline."""


def _print_resolved_paths() -> int:
    log_path = _resolve_log_dir() / f"daily_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
    print(f"lock_path={_resolve_lock_path()}")
    print(f"health_path={_resolve_health_path()}")
    print(f"log_path={log_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI/script entrypoint
    if __package__:
        raise SystemExit(main())
    raise SystemExit(_print_resolved_paths())
