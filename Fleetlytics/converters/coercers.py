"""Type coercion helpers used by the conversion layer."""

from __future__ import annotations

from datetime import date, datetime
import json
from typing import Any


def to_int(value: Any) -> int | None:
    """Coerce a value to ``int`` when possible."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            try:
                return int(float(value.strip()))
            except ValueError:
                return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    """Coerce a value to ``float`` when possible."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    """Coerce common truthy/falsey values to ``bool``."""

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off"}:
            return False
    return None


def to_json_str(value: Any) -> str | None:
    """Serialize a value to compact JSON using UTF-8 friendly output."""

    if value is None or value == "":
        return None
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def ms_to_int(value: Any) -> int | None:
    """Defensively coerce a millisecond timestamp to ``int``."""

    return to_int(value)


def to_date_str(value: Any) -> str | None:
    """Coerce a date-like value to ``YYYY-MM-DD``."""

    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw_value)
            except ValueError:
                return None
            return parsed_date.isoformat()
        return parsed.date().isoformat()
    return None


def to_iso_date(value: Any) -> str | None:
    """Alias for :func:`to_date_str` kept for compatibility with the scaffold."""

    return to_date_str(value)


def ms_to_int_safe(value: Any) -> int | None:
    """Alias for :func:`ms_to_int` kept for compatibility with the scaffold."""

    return ms_to_int(value)

