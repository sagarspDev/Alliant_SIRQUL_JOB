"""Driver score JSON-to-SQL converter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from Fleetlytics.converters.lookups import resolve_fleet_identities_by_internal_id
from Fleetlytics.db.lookups import resolve_driver_ids
from Fleetlytics.converters.snapshot import resolve_snapshot_date
from src.config import get_db_schema

from .base import BaseConverter, SQLExpression, build_upsert_sql
from .coercers import to_float, to_int
from .paths import sql_dir_for_run
from .sql_writer import write_sql_file


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConvertContext:
    """Resolved conversion state shared across driver-score rows."""

    company_id_by_internal_id: dict[str, UUID]
    snapshot_date: date
    retailer_location_ids_by_internal_id: dict[str, int]

    def resolve_retailer_location_id(self, fleet_id: Any) -> int | None:
        """Return the retailer location ID for a fleet internal ID."""

        if fleet_id is None:
            return None
        fleet_key = str(fleet_id).strip()
        if not fleet_key:
            return None
        return self.retailer_location_ids_by_internal_id.get(fleet_key)

    def resolve_company_id(self, fleet_id: Any) -> UUID | None:
        """Return the company ID for a fleet internal ID."""

        if fleet_id is None:
            return None
        fleet_key = str(fleet_id).strip()
        if not fleet_key:
            return None
        return self.company_id_by_internal_id.get(fleet_key)


def _json_text(value: Any) -> str | None:
    """Return a trimmed string value or ``None``."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_snapshot_date(value: Any, fallback: date) -> date:
    """Parse a row-level snapshot date with a fallback."""

    if value is None:
        return fallback
    if isinstance(value, date):
        return value
    text = _json_text(value)
    if not text:
        return fallback
    try:
        return date.fromisoformat(text)
    except ValueError:
        LOGGER.warning("invalid_snapshot_date value=%r fallback=%s", value, fallback.isoformat())
        return fallback


def map_driver_score(
    row: dict[str, Any],
    ctx: ConvertContext,
) -> dict[str, Any] | None:
    """Map one API driver-score row to a database row."""

    driver_id = _json_text(row.get("driverId") or row.get("thirdPartyId"))
    if not driver_id:
        return None

    source_row_index = to_int(row.get("sourceRowIndex"))
    if source_row_index is None:
        return None

    fleet_id = _json_text(row.get("fleetId"))
    if not fleet_id:
        return None
    retailer_location_id = ctx.resolve_retailer_location_id(fleet_id)
    company_id = ctx.resolve_company_id(fleet_id)
    if fleet_id and retailer_location_id is None:
        LOGGER.warning(
            "unresolved_retailer_location_id accountId=%s fleetId=%s",
            row.get("accountId"),
            fleet_id,
        )
    if fleet_id and company_id is None:
        LOGGER.warning(
            "unresolved_company_id accountId=%s fleetId=%s",
            row.get("accountId"),
            fleet_id,
        )

    snapshot_date = _parse_snapshot_date(row.get("snapshotDate"), ctx.snapshot_date)

    return {
        "driver_id": driver_id,
        "account_id": to_int(row.get("accountId")),
        "company_id": company_id,
        "retailer_location_id": retailer_location_id,
        "snapshot_date": snapshot_date,
        "source_group_key": _json_text(row.get("sourceGroupKey")) or "GL_REPORT_DATA",
        "source_row_index": source_row_index,
        "fleet_id": fleet_id,
        "fleet_name": _json_text(row.get("fleetName")),
        "third_party_id": _json_text(row.get("thirdPartyId")),
        "driver_name": _json_text(row.get("driverName")),
        "distance_meters": to_int(row.get("distance")),
        "overall_score": to_float(row.get("overallScore")),
        "accel_score": to_float(row.get("accelScore")),
        "brake_score": to_float(row.get("brakeScore")),
        "collision_score": to_float(row.get("collisionScore")),
        "phone_score": to_float(row.get("phoneScore")),
        "speed_score": to_float(row.get("speedScore")),
        "turn_score": to_float(row.get("turnScore")),
        "accel_incidents": to_float(row.get("accelIncidents")),
        "brake_incidents": to_float(row.get("brakeIncidents")),
        "collision_incidents": to_float(row.get("collisionIncidents")),
        "phone_incidents": to_float(row.get("phoneIncidents")),
        "speed_incidents": to_float(row.get("speedIncidents")),
        "turn_incidents": to_float(row.get("turnIncidents")),
        "last_accel_incident": to_int(row.get("lastAccelIncident")),
        "last_brake_incident": to_int(row.get("lastBrakeIncident")),
        "last_collision_incident": to_int(row.get("lastCollisionIncident")),
        "last_phone_incident": to_int(row.get("lastPhoneIncident")),
        "last_speed_incident": to_int(row.get("lastSpeedIncident")),
        "last_turn_incident": to_int(row.get("lastTurnIncident")),
        "last_synced_at": SQLExpression("now()"),
    }


class DriverScoreConverter(BaseConverter):
    """Convert driver-score JSON payloads into an UPSERT SQL file."""

    entity_name = "driver_scores"
    source_filename = "driver_scores.json"
    target_table = "sirqul_driver_scores"
    conflict_columns = ["snapshot_date", "fleet_id", "driver_id"]
    updatable_columns = [
        "driver_id",
        "account_id",
        "company_id",
        "retailer_location_id",
        "snapshot_date",
        "fleet_id",
        "fleet_name",
        "third_party_id",
        "driver_name",
        "distance_meters",
        "overall_score",
        "accel_score",
        "brake_score",
        "collision_score",
        "phone_score",
        "speed_score",
        "turn_score",
        "accel_incidents",
        "brake_incidents",
        "collision_incidents",
        "phone_incidents",
        "speed_incidents",
        "turn_incidents",
        "last_accel_incident",
        "last_brake_incident",
        "last_collision_incident",
        "last_phone_incident",
        "last_speed_incident",
        "last_turn_incident",
        "last_synced_at",
    ]
    generated_columns = {
        "id",
        "created_at",
        "updated_at",
        "last_accel_incident_datetime",
        "last_brake_incident_datetime",
        "last_collision_incident_datetime",
        "last_phone_incident_datetime",
        "last_speed_incident_datetime",
        "last_turn_incident_datetime",
    }
    sql_filename = "003_driver_scores.sql"

    def __init__(self) -> None:
        self._context: ConvertContext | None = None

    def load_source(self, run_dir: Path) -> list[dict[str, Any]]:
        """Load and validate the driver-score JSON payload."""

        source_path = Path(run_dir) / self.source_filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing driver score source file: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            raise ValueError(f"Driver score source file is empty: {source_path}")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Driver score source file is not valid JSON: {source_path}") from exc

        if isinstance(payload, list):
            rows: list[dict[str, Any]] = []
            for row in payload:
                if not isinstance(row, dict):
                    raise ValueError(f"Driver score rows must be JSON objects: {source_path}")
                rows.append(row)
            return rows

        if not isinstance(payload, dict):
            raise ValueError(f"Driver score source must be a JSON object or list: {source_path}")

        rows: list[dict[str, Any]] = []
        for group_key, group_rows in payload.items():
            if not isinstance(group_rows, list):
                raise ValueError(
                    f"Driver score group {group_key!r} must contain a JSON list: {source_path}"
                )
            for row in group_rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Driver score rows must be JSON objects: {source_path}")
                enriched_row = dict(row)
                enriched_row.setdefault("sourceGroupKey", str(group_key).strip() or "GL_REPORT_DATA")
                rows.append(enriched_row)

        return rows

    def map_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Map one driver-score record using the active conversion context."""

        raise NotImplementedError(
            "DriverScoreConverter requires source group context; use write_run_sql()."
        )

    @staticmethod
    def _noop_sql(source_filename: str, run_dir: Path, table_name: str) -> str:
        """Build a valid transaction shell for empty driver-score runs."""

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

    def write_run_sql(self, run_dir: Path) -> Path:
        """Convert the latest driver-score payload and write the SQL output."""

        records = self.load_source(run_dir)
        snapshot_date = resolve_snapshot_date()
        source_driver_ids = sorted(
            {
                driver_id
                for driver_id in (
                    _json_text(record.get("driverId") or record.get("thirdPartyId"))
                    for record in records
                )
                if driver_id
            }
        )
        fleet_ids = sorted(
            {
                str(record.get("fleetId")).strip()
                for record in records
                if record.get("fleetId") is not None and str(record.get("fleetId")).strip()
            }
        )
        fleet_identities_by_internal_id = resolve_fleet_identities_by_internal_id(fleet_ids)
        self._context = ConvertContext(
            company_id_by_internal_id={
                fleet_id: identity.company_id for fleet_id, identity in fleet_identities_by_internal_id.items()
            },
            snapshot_date=snapshot_date,
            retailer_location_ids_by_internal_id={
                fleet_id: identity.retailer_location_id
                for fleet_id, identity in fleet_identities_by_internal_id.items()
            },
        )

        mapped_rows: list[dict[str, Any]] = []
        skipped_rows = 0
        filtered_rows = 0
        raw_rows = 0
        imported_driver_ids = resolve_driver_ids(source_driver_ids)
        filtered_driver_ids: set[str] = set()
        for row_index, record in enumerate(records, start=1):
            raw_rows += 1
            driver_id = _json_text(record.get("driverId") or record.get("thirdPartyId"))
            if not driver_id:
                skipped_rows += 1
                LOGGER.error(
                    "driver_score_row_index=%s driverId=%r thirdPartyId=%r reason=%s",
                    row_index,
                    record.get("driverId"),
                    record.get("thirdPartyId"),
                    "missing_driver_id",
                )
                continue
            if driver_id not in imported_driver_ids:
                filtered_rows += 1
                filtered_driver_ids.add(driver_id)
                continue
            record = dict(record)
            record["driverId"] = driver_id
            record.setdefault("sourceGroupKey", "GL_REPORT_DATA")
            record.setdefault("sourceRowIndex", row_index)
            mapped_row = map_driver_score(record, self._context)
            if mapped_row is None:
                skipped_rows += 1
                LOGGER.error(
                    "driver_score_row_index=%s driverId=%r reason=%s",
                    row_index,
                    driver_id,
                    "mapping_failed",
                )
                continue
            mapped_rows.append(mapped_row)

        if filtered_driver_ids:
            LOGGER.warning(
                "driver_score_filtered_missing_driver_ids=%s filtered_rows=%s",
                sorted(filtered_driver_ids),
                filtered_rows,
            )

        LOGGER.info(
            "driver_scores_total=%s driver_scores_resolved=%s driver_scores_skipped=%s driver_scores_filtered=%s driver_scores_lookups=%s snapshot_date=%s",
            raw_rows,
            len(mapped_rows),
            skipped_rows,
            filtered_rows,
            len(imported_driver_ids),
            snapshot_date.isoformat(),
        )

        sql_dir = sql_dir_for_run(run_dir)
        if not mapped_rows:
            output_path = write_sql_file(
                sql_dir / self.sql_filename,
                self._noop_sql(self.source_filename, run_dir, self.target_table),
            )
            LOGGER.warning("No resolvable driver-score rows were found; wrote no-op SQL.")
            return output_path

        sql_text = build_upsert_sql(
            schema=get_db_schema(),
            table=self.target_table,
            rows=mapped_rows,
            conflict_columns=self.conflict_columns,
            updatable_columns=self.updatable_columns,
            generated_columns=self.generated_columns,
            source_filename=self.source_filename,
            run_dir=Path(run_dir),
        )
        sql_text = (
            "-- NOTE: last_synced_at is only bumped when the ON CONFLICT WHERE clause finds a real diff.\n"
            + sql_text
        )
        output_path = write_sql_file(sql_dir / self.sql_filename, sql_text)
        return output_path


def convert_driver_scores(run_dir: Path) -> Path:
    """Convert the latest driver-score payload into ``003_driver_scores.sql``."""

    converter = DriverScoreConverter()
    return converter.write_run_sql(run_dir)


if __name__ == "__main__":  # pragma: no cover - smoke example only
    example_row = {
        "accountId": 3634735,
        "fleetId": "hub_fleet_id_1",
        "thirdPartyId": "00uujq2ggsUWtrHCF1d7",
        "distance": 271673,
        "overallScore": 25.27075,
        "accelScore": 47.472,
        "brakeScore": 61.12075,
        "collisionScore": 100,
        "phoneScore": 43.59275,
        "speedScore": 87.12225,
        "turnScore": 55.18275,
        "accelIncidents": 27,
        "brakeIncidents": 26,
        "collisionIncidents": 0,
        "phoneIncidents": 27,
        "speedIncidents": 9,
        "turnIncidents": 31,
        "lastAccelIncident": 1780334653000,
        "lastBrakeIncident": 1780338313000,
        "lastCollisionIncident": None,
        "lastPhoneIncident": 1780338193000,
        "lastSpeedIncident": 1780291393000,
        "lastTurnIncident": 1780338193000,
    }
    example_ctx = ConvertContext(
        company_id_by_internal_id={"hub_fleet_id_1": UUID("00000000-0000-0000-0000-000000000000")},
        snapshot_date=date(2026, 6, 8),
        retailer_location_ids_by_internal_id={"hub_fleet_id_1": 353799},
    )
    print(map_driver_score(example_row, example_ctx))
