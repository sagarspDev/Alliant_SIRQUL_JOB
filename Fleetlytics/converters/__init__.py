"""Conversion scaffolding for Fleetlytics JSON-to-SQL output."""

from __future__ import annotations

from .base import BaseConverter, build_upsert_sql
from .coercers import (
    ms_to_int,
    ms_to_int_safe,
    to_bool,
    to_date_str,
    to_float,
    to_int,
    to_iso_date,
    to_json_str,
)
from .paths import latest_run_dir, sql_dir_for_run

__all__ = [
    "BaseConverter",
    "build_upsert_sql",
    "latest_run_dir",
    "ms_to_int",
    "ms_to_int_safe",
    "sql_dir_for_run",
    "to_bool",
    "to_date_str",
    "to_float",
    "to_int",
    "to_iso_date",
    "to_json_str",
]
