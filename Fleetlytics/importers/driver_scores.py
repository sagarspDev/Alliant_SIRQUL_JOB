"""Driver-score SQL importer."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

import psycopg

from src.config import get_db_schema, get_db_url

from .base import ImportResult, _extract_header_metadata, _split_sql_statements


LOGGER = logging.getLogger(__name__)


class DriverScoreImporter:
    """Import the generated driver-score SQL file."""

    def run(self, sql_path: Path, *, dry_run: bool) -> ImportResult:
        """Import one driver-score SQL file and return the execution summary."""

        started = datetime.now(timezone.utc)
        sql_path = Path(sql_path)
        sql_text = sql_path.read_text(encoding="utf-8")
        table_name, declared_rows = _extract_header_metadata(sql_text, sql_path)
        statements = _split_sql_statements(sql_text)
        LOGGER.info(
            "sql_path=%s dry_run=%s statement_count=%s",
            sql_path,
            dry_run,
            len(statements),
        )

        if dry_run:
            rows_inserted = 0
            rows_updated = 0
            rows_skipped = declared_rows
            connection: psycopg.Connection[Any] | None = None
            try:
                connection = psycopg.connect(get_db_url())
                connection.autocommit = False
                with connection.cursor() as cursor:
                    cursor.execute(f"SET search_path TO {get_db_schema()}, public")
                    for statement in statements:
                        if statement.upper() in {"BEGIN", "COMMIT"}:
                            continue
                        cursor.execute(statement)
                        LOGGER.info("Executed statement rows_affected=%s", cursor.rowcount)
                        if cursor.description is not None:
                            # The generated SQL returns (xmax = 0) AS inserted, so row[0]
                            # tells us whether each returned row was inserted or updated.
                            returned_rows = cursor.fetchall()
                            rows_inserted += sum(1 for row in returned_rows if bool(row[0]))
                            rows_updated += sum(1 for row in returned_rows if not bool(row[0]))
                            rows_skipped = max(declared_rows - len(returned_rows), 0)
                connection.rollback()
            except Exception as exc:
                if connection is not None:
                    connection.rollback()
                duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
                LOGGER.exception("Failed to dry-run import %s", sql_path)
                return ImportResult(
                    table_name=table_name,
                    file_path=Path(sql_path),
                    rows_inserted=0,
                    rows_updated=0,
                    rows_skipped=declared_rows,
                    errors=[str(exc)],
                    status="error",
                    duration_ms=duration_seconds * 1000.0,
                    duration_seconds=duration_seconds,
                )
            finally:
                if connection is not None:
                    connection.close()

            duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
            return ImportResult(
                table_name=table_name,
                file_path=Path(sql_path),
                rows_inserted=rows_inserted,
                rows_updated=rows_updated,
                rows_skipped=rows_skipped,
                status="dry_run",
                duration_ms=duration_seconds * 1000.0,
                duration_seconds=duration_seconds,
            )

        rows_inserted = 0
        rows_updated = 0
        rows_skipped = declared_rows
        errors: list[str] = []
        connection: psycopg.Connection[Any] | None = None

        try:
            connection = psycopg.connect(get_db_url())
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute(f"SET search_path TO {get_db_schema()}, public")
                for statement in statements:
                    if statement.upper() in {"BEGIN", "COMMIT"}:
                        continue
                    cursor.execute(statement)
                    LOGGER.info("Executed statement rows_affected=%s", cursor.rowcount)
                    if cursor.description is not None:
                        # The generated SQL returns (xmax = 0) AS inserted, so row[0]
                        # tells us whether each returned row was inserted or updated.
                        returned_rows = cursor.fetchall()
                        rows_inserted += sum(1 for row in returned_rows if bool(row[0]))
                        rows_updated += sum(1 for row in returned_rows if not bool(row[0]))
                        rows_skipped = max(declared_rows - len(returned_rows), 0)
            connection.commit()
        except Exception as exc:
            errors.append(str(exc))
            if connection is not None:
                connection.rollback()
            LOGGER.exception("Failed to import %s", sql_path)
            duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
            return ImportResult(
                table_name=table_name,
                file_path=Path(sql_path),
                rows_inserted=0,
                rows_updated=0,
                rows_skipped=declared_rows,
                errors=errors,
                status="error",
                duration_ms=duration_seconds * 1000.0,
                duration_seconds=duration_seconds,
            )
        finally:
            if connection is not None:
                connection.close()

        duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
        return ImportResult(
            table_name=table_name,
            file_path=Path(sql_path),
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_skipped=rows_skipped,
            errors=errors,
            status="ok",
            duration_ms=duration_seconds * 1000.0,
            duration_seconds=duration_seconds,
        )


def import_driver_scores(sql_path: Path, *, dry_run: bool) -> ImportResult:
    """Import the generated driver-score SQL file."""

    importer = DriverScoreImporter()
    return importer.run(Path(sql_path), dry_run=dry_run)
