"""Database session and SQL file importer scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

import psycopg

from src.config import get_db_schema, get_db_url

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ImportResult:
    """Result summary for a single SQL file import."""

    table_name: str
    file_path: Path
    rows_inserted: int
    rows_updated: int
    rows_skipped: int
    errors: list[str] = field(default_factory=list)
    status: str = "ok"
    duration_ms: float = 0.0
    duration_seconds: float = 0.0


class DBSession:
    """Context manager for a psycopg connection scoped to one transaction."""

    def __init__(self) -> None:
        self._connection: psycopg.Connection[Any] | None = None

    def __enter__(self) -> psycopg.Connection[Any]:
        connection = psycopg.connect(get_db_url())
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {get_db_schema()}, public")
        self._connection = connection
        return connection

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._connection is None:
            return False
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        self._connection.close()
        self._connection = None
        return False


def _split_sql_statements(sql_text: str) -> list[str]:
    """Split a generated SQL file into executable statements."""

    non_comment_lines = [
        line for line in sql_text.splitlines() if not line.lstrip().startswith("--")
    ]
    cleaned_sql = "\n".join(non_comment_lines)
    statements: list[str] = []
    for chunk in cleaned_sql.split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


def _extract_header_metadata(sql_text: str, file_path: Path) -> tuple[str, int]:
    """Extract the table name and declared row count from the SQL header."""

    table_name = file_path.stem
    row_count = 0
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-- Table:"):
            table_name = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("-- Rows:"):
            try:
                row_count = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                row_count = 0
    return table_name, row_count


class SQLFileImporter:
    """Executor for generated SQL files."""

    def run(self, sql_path: Path, *, dry_run: bool) -> ImportResult:
        """Import one SQL file and return the execution summary."""

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
            for index, statement in enumerate(statements, start=1):
                preview = statement[:80]
                tail = statement[-80:] if len(statement) > 80 else statement
                LOGGER.info("Statement %s preview=%r tail=%r", index, preview, tail)
            duration_seconds = (datetime.now(timezone.utc) - started).total_seconds()
            return ImportResult(
                table_name=table_name,
                file_path=Path(sql_path),
                rows_inserted=0,
                rows_updated=0,
                rows_skipped=declared_rows,
                status="dry_run",
                duration_ms=duration_seconds * 1000.0,
                duration_seconds=duration_seconds,
            )

        rows_inserted = 0
        rows_updated = 0
        rows_skipped = declared_rows
        errors: list[str] = []

        try:
            with DBSession() as connection:
                with connection.cursor() as cursor:
                    for statement in statements:
                        if statement.upper() in {"BEGIN", "COMMIT"}:
                            continue
                        cursor.execute(statement)
                        LOGGER.info("Executed statement rows_affected=%s", cursor.rowcount)
                        if cursor.description is not None:
                            returned_rows = cursor.fetchall()
                            rows_inserted += sum(1 for row in returned_rows if bool(row[0]))
                            rows_updated += sum(1 for row in returned_rows if not bool(row[0]))
                            rows_skipped = max(declared_rows - len(returned_rows), 0)
        except Exception as exc:
            errors.append(str(exc))
            LOGGER.exception("Failed to import %s", sql_path)
            raise

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
