"""Filesystem helpers for locating run directories and SQL output folders."""

from __future__ import annotations

from pathlib import Path


def latest_run_dir(retailer_location_id: str | int, output_root: Path) -> Path:
    """Return the latest run directory for a retailer location."""

    retailer_root = Path(output_root) / str(retailer_location_id)
    if not retailer_root.exists():
        raise FileNotFoundError(
            f"No output directory found for retailer_location_id={retailer_location_id!r}."
        )

    candidates = [path for path in retailer_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No run directories found under {retailer_root}.")

    return max(candidates, key=lambda path: path.name)


def sql_dir_for_run(run_dir: Path) -> Path:
    """Return the ``sql`` child directory for a run, creating it if needed."""

    sql_dir = Path(run_dir) / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    return sql_dir

