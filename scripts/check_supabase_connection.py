"""Check the Supabase/Postgres connection and sample a few Sirqul tables."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import psycopg

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import ConfigError, get_db_schema, get_db_url


TABLES = (
    "sirqul_fleet",
    "sirqul_driver",
    "sirqul_driver_scores",
    "sirqul_trip_scores",
    "sirqul_trip_locations",
    "sirqul_trip_incidents",
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a psycopg row to a plain dictionary for readable output."""

    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    if isinstance(row, tuple):
        return {"values": list(row)}
    return {"value": row}


def main() -> int:
    """Open the database connection and print a short verification summary."""

    try:
        db_url = get_db_url()
        schema = get_db_schema()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    with psycopg.connect(db_url, autocommit=True) as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    current_database() AS database_name,
                    current_user AS user_name,
                    current_schema AS schema_name,
                    version() AS server_version
                """
            )
            identity = cursor.fetchone()
            print("Connection OK")
            print(json.dumps(identity, indent=2, default=str))

            for table_name in TABLES:
                qualified_table = f"{schema}.{table_name}"
                print(f"\nTable: {qualified_table}")
                try:
                    cursor.execute(f"SELECT COUNT(*) AS row_count FROM {qualified_table}")
                    row_count = cursor.fetchone()
                    print(f"Row count: {row_count['row_count']}")

                    cursor.execute(f"SELECT * FROM {qualified_table} LIMIT 3")
                    sample_rows = cursor.fetchall()
                    print("Sample rows:")
                    print(json.dumps([_row_to_dict(row) for row in sample_rows], indent=2, default=str))
                except Exception as exc:  # pragma: no cover - manual smoke test path
                    print(f"Failed to query {qualified_table}: {exc}")

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
