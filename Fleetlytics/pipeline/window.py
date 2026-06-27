"""Daily pull-window resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.config import DATE_FORMAT


LOGGER = logging.getLogger(__name__)
_MAX_SINCE_LAST_SUCCESS_LOOKBACK_DAYS = 30


@dataclass(frozen=True, slots=True)
class DateWindow:
    """Resolved datetime window for a scheduled run."""

    start: datetime
    end: datetime
    source: str


def resolve_daily_window() -> DateWindow:
    """
    Resolve the current daily pull window from environment configuration.

    Supported modes:
      - rolling_24h
      - rolling_7d
      - rolling_hours
      - since_last_success
      - env
    """

    mode = os.getenv("DAILY_WINDOW_MODE", "rolling_24h").strip().lower() or "rolling_24h"
    resolved = _resolve_window_for_mode(mode=mode, now=_utc_now())
    LOGGER.info(
        "resolved_daily_window source=%s start=%s end=%s duration_hours=%s",
        resolved.source,
        resolved.start.isoformat(timespec="seconds"),
        resolved.end.isoformat(timespec="seconds"),
        round((resolved.end - resolved.start).total_seconds() / 3600.0, 3),
    )
    return resolved


def get_watermark_path() -> Path:
    """Return the success watermark path used by daily runs."""

    return Path(__file__).resolve().parent.parent / "state" / "last_success.json"


def read_success_watermark(state_path: Path | None = None) -> dict[str, Any] | None:
    """Read and validate the last-success watermark file."""

    watermark_path = Path(state_path) if state_path is not None else get_watermark_path()
    if not watermark_path.exists():
        return None

    try:
        payload = json.loads(watermark_path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("Failed to read success watermark from %s: %s", watermark_path, exc)
        return None

    if not isinstance(payload, dict):
        LOGGER.warning("Ignoring malformed success watermark at %s: expected object", watermark_path)
        return None

    last_success_end = payload.get("last_success_end")
    last_run_at = payload.get("last_run_at")
    if not isinstance(last_success_end, str) or not last_success_end.strip():
        LOGGER.warning("Ignoring malformed success watermark at %s: missing last_success_end", watermark_path)
        return None
    if not isinstance(last_run_at, str) or not last_run_at.strip():
        LOGGER.warning("Ignoring malformed success watermark at %s: missing last_run_at", watermark_path)
        return None

    try:
        _parse_watermark_datetime(last_success_end)
    except ValueError:
        LOGGER.warning(
            "Ignoring malformed success watermark at %s: invalid last_success_end=%r",
            watermark_path,
            last_success_end,
        )
        return None

    return {
        "last_success_end": last_success_end,
        "last_run_at": last_run_at,
    }


def _resolve_window_for_mode(*, mode: str, now: datetime, state_path: Path | None = None) -> DateWindow:
    if mode == "rolling_hours":
        hours = _resolve_window_hours()
        resolved = DateWindow(
            start=now - timedelta(hours=hours),
            end=now,
            source=f"rolling_{hours}h" if hours != 24 else "rolling_24h",
        )
        return _validate_window(resolved)
    if mode == "rolling_24h":
        resolved = DateWindow(start=now - timedelta(days=1), end=now, source=mode)
        return _validate_window(resolved)
    if mode == "rolling_7d":
        resolved = DateWindow(start=now - timedelta(days=7), end=now, source=mode)
        return _validate_window(resolved)
    if mode == "since_last_success":
        watermark = read_success_watermark(state_path)
        if watermark is None:
            LOGGER.warning(
                "No success watermark found for DAILY_WINDOW_MODE=since_last_success; falling back to rolling_24h"
            )
            resolved = DateWindow(start=now - timedelta(days=1), end=now, source="rolling_24h")
            return _validate_window(resolved)
        floor_dt = now - timedelta(days=_MAX_SINCE_LAST_SUCCESS_LOOKBACK_DAYS)
        last_success_end = _parse_watermark_datetime(str(watermark["last_success_end"]))
        # NOTE: Future-dated watermarks are clamped to `now` so the runner does
        # not emit an invalid start > end window after clock skew or manual edits.
        resolved = DateWindow(start=min(max(last_success_end, floor_dt), now), end=now, source=mode)
        return _validate_window(resolved)
    if mode == "env":
        resolved = DateWindow(
            start=_parse_env_datetime("DATE_RANGE_START"),
            end=_parse_env_datetime("DATE_RANGE_END"),
            source=mode,
        )
        return _validate_window(resolved)
    raise ValueError(f"Unknown DAILY_WINDOW_MODE: {mode!r}")


def _resolve_window_hours() -> int:
    raw_value = os.getenv("DAILY_WINDOW_HOURS", "24").strip() or "24"
    hours = int(raw_value)
    if hours <= 0:
        raise ValueError("DAILY_WINDOW_HOURS must be a positive integer")
    return hours


def _parse_env_datetime(name: str) -> datetime:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        raise ValueError(f"{name} is required when DAILY_WINDOW_MODE=env")

    token = raw_value.split("#", 1)[0].strip()
    try:
        parsed = datetime.strptime(token, DATE_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        try:
            parsed_date = date.fromisoformat(token.split()[0].strip())
        except ValueError as date_exc:
            raise ValueError(
                f"{name} must be a valid datetime in {DATE_FORMAT!r} or YYYY-MM-DD format"
            ) from date_exc
        parsed = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _parse_watermark_datetime(raw_value: str) -> datetime:
    token = raw_value.strip()
    if not token:
        raise ValueError("last_success_end is required")

    normalized = token.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(token.split()[0].strip()), time.min, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _validate_window(window: DateWindow) -> DateWindow:
    if window.end < window.start:
        raise ValueError(
            f"Resolved daily window is invalid: start={window.start.isoformat()} end={window.end.isoformat()}"
        )
    return window


if __name__ == "__main__":  # pragma: no cover - smoke example only
    from unittest.mock import patch

    fake_now = datetime(2026, 6, 15, 12, 30, tzinfo=timezone.utc)
    fake_watermark = {
        "last_success_end": "2026-06-10T08:00:12Z",
        "last_run_at": "2026-06-10T08:00:12Z",
    }
    base_env = {
        "DATE_RANGE_START": "2026-06-01 00:00:00",
        "DATE_RANGE_END": "2026-06-15 00:00:00",
    }

    for mode in ("rolling_24h", "rolling_7d", "rolling_hours", "since_last_success", "env"):
        with patch.dict(os.environ, {**base_env, "DAILY_WINDOW_MODE": mode}, clear=False):
            with patch(__name__ + "._utc_now", return_value=fake_now):
                with patch(__name__ + ".read_success_watermark", return_value=fake_watermark):
                    print(mode, resolve_daily_window())
