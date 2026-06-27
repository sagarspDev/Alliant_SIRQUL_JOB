"""Helpers for resolving the driver-score snapshot date."""

from __future__ import annotations

from datetime import date
import logging
import os


LOGGER = logging.getLogger(__name__)

_SNAPSHOT_DATE_CACHE: date | None = None


def _parse_date_env(name: str) -> date:
    """Parse a ``YYYY-MM-DD`` environment value into a date."""

    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        raise ValueError(f"{name} is required")

    token = raw_value.split()[0].strip()
    try:
        return date.fromisoformat(token)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid YYYY-MM-DD date") from exc


def resolve_snapshot_date() -> date:
    """Resolve and memoize the driver-score snapshot date for this process."""

    global _SNAPSHOT_DATE_CACHE

    if _SNAPSHOT_DATE_CACHE is not None:
        return _SNAPSHOT_DATE_CACHE

    mode = os.getenv("SCORE_SNAPSHOT_DATE_MODE", "end_date").strip().lower() or "end_date"
    if mode == "end_date":
        resolved = _parse_date_env("DATE_RANGE_END")
    elif mode == "run_date":
        resolved = date.today()
    elif mode == "custom":
        resolved = _parse_date_env("SCORE_SNAPSHOT_DATE_CUSTOM")
    else:
        raise ValueError(f"Unknown SCORE_SNAPSHOT_DATE_MODE: {mode!r}")

    LOGGER.info("resolved_snapshot_date=%s mode=%s", resolved.isoformat(), mode)
    _SNAPSHOT_DATE_CACHE = resolved
    return resolved
