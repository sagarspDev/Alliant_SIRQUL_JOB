"""Filesystem helpers for the Fleetlytics pipeline package."""

from __future__ import annotations

from pathlib import Path


def build_run_dir(output_root: Path, fleet_internal_id: str, run_timestamp: str) -> Path:
    """Return ``<output_root>/<fleet_internal_id>/<run_timestamp>/`` and create it."""

    run_dir = Path(output_root).expanduser() / str(fleet_internal_id) / str(run_timestamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

