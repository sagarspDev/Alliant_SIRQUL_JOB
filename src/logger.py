"""Logging setup for Fleetlytics."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
import os

_LOGGING_INITIALIZED = False
_RUN_LOG_FILE: Path | None = None


def configure_logging(log_dir: str | Path, level: str = "INFO") -> Path:
    """Configure stdout and rotating file logging.

    Returns the path to the run-specific log file.
    """

    global _LOGGING_INITIALIZED, _RUN_LOG_FILE

    resolved_log_dir = Path(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    if _LOGGING_INITIALIZED and _RUN_LOG_FILE is not None:
        return _RUN_LOG_FILE

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = resolved_log_dir / f"fleetlytics_{run_timestamp}.log"

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    max_bytes = _resolve_int_env("RUN_LOG_MAX_BYTES", default=5 * 1024 * 1024, minimum=1024)
    backup_count = _resolve_int_env("RUN_LOG_BACKUP_COUNT", default=3, minimum=1)
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    _LOGGING_INITIALIZED = True
    _RUN_LOG_FILE = log_file
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return a module-specific logger."""

    return logging.getLogger(name)


def _resolve_int_env(name: str, *, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    if value < minimum:
        return default
    return value
