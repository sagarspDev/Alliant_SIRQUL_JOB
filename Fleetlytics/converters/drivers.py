"""Driver JSON-to-SQL converter."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from Fleetlytics.db.lookups import (
    resolve_user_ids_by_email,
    resolve_user_ids_by_focus_driver_id,
)

from .base import BaseConverter, build_upsert_sql
from .mappers import map_driver
from .paths import sql_dir_for_run
from .sql_writer import write_sql_file
from src.config import get_db_schema


LOGGER = logging.getLogger(__name__)


class DriverConverter(BaseConverter):
    """Convert driver JSON payloads into an UPSERT SQL file."""

    entity_name = "drivers"
    source_filename = "drivers.json"
    target_table = "sirqul_driver"
    conflict_columns = ["driver_id"]
    updatable_columns = [
        "account_id",
        "user_id",
        "retailer_location_id",
        "display",
        "username",
        "account_type",
        "contact_email",
        "location_display",
        "active",
        "latitude",
        "longitude",
        "location_count",
        "manager",
        "contact",
        "employer",
        "app_info",
        "locations",
        "last_synced_at",
    ]
    generated_columns = {"created_at", "updated_at"}
    sql_filename = "002_drivers.sql"

    def load_source(self, run_dir: Path) -> list[dict[str, Any]]:
        """Load the driver source payload."""

        source_path = Path(run_dir) / self.source_filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing driver source file: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            raise ValueError(f"Driver source file is empty: {source_path}")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Driver source file is not valid JSON: {source_path}") from exc

        if not isinstance(payload, list):
            raise ValueError(f"Driver source must be a JSON list: {source_path}")

        return payload

    def map_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Map one driver record to a database row dict."""

        raise NotImplementedError("Driver mapping requires a resolved user_id.")

    @staticmethod
    def _extract_contact_email(driver: Mapping[str, Any]) -> str | None:
        """Return the best available driver contact email."""

        top_level = driver.get("contactEmail")
        if isinstance(top_level, str) and top_level.strip():
            return top_level.strip()

        contact = driver.get("contact")
        if isinstance(contact, Mapping):
            contact_info = contact.get("contactInfo")
            if isinstance(contact_info, Mapping):
                nested_email = contact_info.get("emailAddress")
                if isinstance(nested_email, str) and nested_email.strip():
                    return nested_email.strip()
        return None

    @staticmethod
    def _extract_focus_driver_id(driver: Mapping[str, Any]) -> str | None:
        """Return the driver identity from ``focus_data.DriverId`` when present."""

        focus_data = driver.get("focus_data")
        if not isinstance(focus_data, Mapping):
            return None
        driver_id = focus_data.get("DriverId")
        if driver_id is None:
            return None
        driver_id_text = str(driver_id).strip()
        return driver_id_text or None

    @staticmethod
    def _extract_default_retailer_location_id() -> int:
        """Resolve the fallback retailer location ID from the environment."""

        raw_value = os.getenv("TARGET_RETAILER_LOCATION_ID", "").strip()
        if not raw_value:
            raise ValueError("TARGET_RETAILER_LOCATION_ID is required for driver conversion.")
        return int(raw_value)

    @staticmethod
    def _resolve_default_retailer_location_id(run_dir: Path) -> int:
        """Resolve the default retailer location ID from the run artifacts first."""

        source_path = Path(run_dir) / "fleet.json"
        if source_path.exists():
            try:
                payload = json.loads(source_path.read_text(encoding="utf-8").strip())
                if isinstance(payload, dict) and isinstance(payload.get("item"), dict):
                    item = payload["item"]
                elif isinstance(payload, dict):
                    item = payload
                else:
                    item = None
                if isinstance(item, dict):
                    retailer_location_id = item.get("retailerLocationId")
                    if retailer_location_id is not None:
                        return int(str(retailer_location_id).strip())
            except Exception as exc:
                LOGGER.warning("Failed to resolve retailer location from fleet.json: %s", exc)

        raw_value = os.getenv("TARGET_RETAILER_LOCATION_ID", "").strip()
        if raw_value:
            return int(raw_value)
        raise ValueError(
            "Unable to resolve default retailer location ID from fleet.json; "
            "set TARGET_RETAILER_LOCATION_ID for legacy one-shot runs."
        )

    @staticmethod
    def _extract_primary_retailer_location_id(driver: Mapping[str, Any]) -> int | None:
        """Return the first retailer location ID from the driver payload."""

        locations = driver.get("locations")
        if not isinstance(locations, list) or not locations:
            return None
        first_location = locations[0]
        if not isinstance(first_location, Mapping):
            return None
        retailer_location_id = first_location.get("retailerLocationId")
        if retailer_location_id is None:
            return None
        try:
            return int(retailer_location_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _noop_sql(source_filename: str, run_dir: Path, table_name: str) -> str:
        """Build a valid transaction shell for empty driver runs."""

        header_lines = [
            "-- Generated by Fleetlytics converters",
            f"-- Source: {source_filename}",
            f"-- Run: {run_dir}",
            f"-- Table: {table_name}",
            "-- Rows: 0",
            f"-- Generated at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
        ]
        return "\n".join(header_lines + ["BEGIN;", "COMMIT;"]) + "\n"

    def _resolve_rows(
        self,
        records: list[dict[str, Any]],
        *,
        default_retailer_location_id: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split source records into resolved rows and skipped diagnostics."""

        focus_driver_ids: list[str] = []
        emails: list[str] = []
        for driver in records:
            focus_driver_id = self._extract_focus_driver_id(driver)
            if focus_driver_id:
                focus_driver_ids.append(focus_driver_id)
            email = self._extract_contact_email(driver)
            if email:
                emails.append(email)

        user_ids_by_focus_driver_id = resolve_user_ids_by_focus_driver_id(focus_driver_ids)
        user_ids_by_email = resolve_user_ids_by_email(emails)
        rows: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for driver in records:
            account_id = driver.get("accountId")
            display = driver.get("display")
            focus_driver_id = self._extract_focus_driver_id(driver)
            contact_email = self._extract_contact_email(driver)
            normalized_email = contact_email.lower() if contact_email else None

            user_id = None
            if focus_driver_id:
                user_id = user_ids_by_focus_driver_id.get(focus_driver_id)
            if user_id is None and normalized_email:
                user_id = user_ids_by_email.get(normalized_email)

            if user_id is None:
                if not focus_driver_id and not normalized_email:
                    reason = "no_driver_identity"
                else:
                    reason = "user_not_found"
                skipped.append(
                    {
                        "account_id": account_id,
                        "display": display,
                        "driver_id": focus_driver_id,
                        "contact_email": contact_email,
                        "reason": reason,
                    }
                )
                LOGGER.error(
                    "driver_account_id=%s display=%r driver_id=%r contact_email=%r reason=%s",
                    account_id,
                    display,
                    focus_driver_id,
                    contact_email,
                    reason,
                )
                continue

            primary_retailer_location_id = self._extract_primary_retailer_location_id(driver)
            row = map_driver(
                driver,
                user_id=user_id,
                default_retailer_location_id=(
                    primary_retailer_location_id
                    if primary_retailer_location_id is not None
                    else default_retailer_location_id
                ),
            )
            driver_id = row.get("driver_id")
            if driver_id is None or str(driver_id).strip() == "":
                skipped.append(
                    {
                        "account_id": account_id,
                        "display": display,
                        "contact_email": contact_email,
                        "reason": "missing_driver_id",
                    }
                )
                LOGGER.error(
                    "driver_account_id=%s display=%r contact_email=%r reason=%s",
                    account_id,
                    display,
                    contact_email,
                    "missing_driver_id",
                )
                continue
            rows.append(row)

        return rows, skipped

    def write_run_sql(self, run_dir: Path) -> Path:
        """Convert the latest driver records and write the SQL output."""

        records = self.load_source(run_dir)
        default_retailer_location_id = self._resolve_default_retailer_location_id(run_dir)
        rows, skipped = self._resolve_rows(
            records,
            default_retailer_location_id=default_retailer_location_id,
        )

        LOGGER.info(
            "drivers_total=%s drivers_resolved=%s drivers_skipped=%s",
            len(records),
            len(rows),
            len(skipped),
        )

        sql_dir = sql_dir_for_run(run_dir)
        skipped_path = sql_dir / "002_drivers.skipped.json"
        skipped_path.write_text(
            json.dumps(skipped, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if not rows:
            output_path = write_sql_file(
                sql_dir / self.sql_filename,
                self._noop_sql(self.source_filename, run_dir, self.target_table),
            )
            LOGGER.warning("No resolvable drivers were found; wrote no-op SQL.")
            return output_path

        schema = get_db_schema()
        output_path = write_sql_file(
            sql_dir / self.sql_filename,
            build_upsert_sql(
                schema=schema,
                table=self.target_table,
                rows=rows,
                conflict_columns=self.conflict_columns,
                updatable_columns=self.updatable_columns,
                generated_columns=self.generated_columns,
                source_filename=self.source_filename,
                run_dir=Path(run_dir),
            ),
        )
        return output_path


def convert_drivers(run_dir: Path) -> Path:
    """Convert the latest driver JSON payload into ``002_drivers.sql``."""

    converter = DriverConverter()
    return converter.write_run_sql(run_dir)
