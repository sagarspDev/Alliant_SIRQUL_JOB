"""Trip score JSON-to-SQL converter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from Fleetlytics.converters.lookups import resolve_fleet_identities_by_internal_id
from Fleetlytics.db.lookups import resolve_driver_ids
from src.config import get_db_schema

from .base import BaseConverter, SQLExpression, build_upsert_sql
from .coercers import to_float, to_int
from .paths import sql_dir_for_run
from .sql_writer import write_sql_file


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConvertContext:
    """Resolved conversion state shared across trip-score rows."""

    company_id_by_internal_id: dict[str, UUID]
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


def _build_geo(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the geo JSONB payload or return ``None`` when empty."""

    # The shared SQL writer renders dict values as ``::jsonb`` literals.
    geo = {
        "startLatitude": to_float(row.get("startLatitude")),
        "startLongitude": to_float(row.get("startLongitude")),
        "startDescription": row.get("startDescription"),
        "endLatitude": to_float(row.get("endLatitude")),
        "endLongitude": to_float(row.get("endLongitude")),
        "endDescription": row.get("endDescription"),
    }
    if all(value is None for value in geo.values()):
        return None
    return geo


def _build_weather(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the weather JSONB payload or return ``None`` when empty."""

    # The shared SQL writer renders dict values as ``::jsonb`` literals.
    weather = {
        "weatherCode": row.get("weatherCode"),
        "weatherTempLow": to_float(row.get("weatherTempLow")),
        "weatherTempHigh": to_float(row.get("weatherTempHigh")),
        "weatherWind": to_float(row.get("weatherWind")),
    }
    if all(value is None for value in weather.values()):
        return None
    return weather


def map_trip_score(row: dict[str, Any], ctx: ConvertContext) -> dict[str, Any] | None:
    """Map one API trip-score row to a database row."""

    trip_id = _json_text(row.get("tripId"))
    driver_id = _json_text(row.get("driverId") or row.get("thirdPartyId"))
    if not trip_id or not driver_id:
        return None

    start_date = to_int(row.get("startDate"))
    end_date = to_int(row.get("endDate"))
    if start_date is None or end_date is None:
        LOGGER.error(
            "trip_id=%s reason=%s startDate=%r endDate=%r",
            trip_id,
            "missing_trip_window",
            row.get("startDate"),
            row.get("endDate"),
        )
        return None
    if end_date < start_date:
        LOGGER.error(
            "trip_id=%s reason=%s startDate=%r endDate=%r",
            trip_id,
            "invalid_trip_window",
            row.get("startDate"),
            row.get("endDate"),
        )
        return None

    fleet_id = _json_text(row.get("fleetId"))
    retailer_location_id = ctx.resolve_retailer_location_id(fleet_id)
    company_id = ctx.resolve_company_id(fleet_id)
    if fleet_id and retailer_location_id is None:
        LOGGER.warning(
            "unresolved_retailer_location_id tripId=%s fleetId=%s",
            trip_id,
            fleet_id,
        )
    if fleet_id and company_id is None:
        LOGGER.warning("unresolved_company_id tripId=%s fleetId=%s", trip_id, fleet_id)

    return {
        "trip_id": trip_id,
        "account_id": to_int(row.get("accountId")),
        "driver_id": driver_id,
        "company_id": company_id,
        "retailer_location_id": retailer_location_id,
        "fleet_id": fleet_id,
        "fleet_name": _json_text(row.get("fleetName")),
        "third_party_id": _json_text(row.get("thirdPartyId")),
        "driver_name": _json_text(row.get("driverName")),
        "trip_type": _json_text(row.get("tripType")),
        "distance_meters": to_int(row.get("distance")),
        "start_date": start_date,
        "end_date": end_date,
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
        "geo": _build_geo(row),
        "weather": _build_weather(row),
        "last_synced_at": SQLExpression("now()"),
    }


class TripScoreConverter(BaseConverter):
    """Convert trip-score JSON payloads into an UPSERT SQL file."""

    entity_name = "trip_scores"
    source_filename = "trip_scores.json"
    target_table = "sirqul_trip_scores"
    conflict_columns = ["trip_id"]
    updatable_columns = [
        "driver_id",
        "account_id",
        "company_id",
        "retailer_location_id",
        "fleet_id",
        "fleet_name",
        "third_party_id",
        "driver_name",
        "trip_type",
        "distance_meters",
        "start_date",
        "end_date",
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
        "geo",
        "weather",
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
        "start_date_datetime",
        "end_date_datetime",
        "duration_seconds",
    }
    sql_filename = "004_trip_scores.sql"

    def __init__(self) -> None:
        self._context: ConvertContext | None = None

    def load_source(self, run_dir: Path) -> list[dict[str, Any]]:
        """Load and flatten the nested trip-score JSON payload."""

        source_path = Path(run_dir) / self.source_filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing trip score source file: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            raise ValueError(f"Trip score source file is empty: {source_path}")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Trip score source file is not valid JSON: {source_path}") from exc

        if isinstance(payload, list):
            rows: list[dict[str, Any]] = []
            for row in payload:
                if not isinstance(row, dict):
                    raise ValueError(f"Trip score rows must be JSON objects: {source_path}")
                rows.append(row)
            return rows

        if not isinstance(payload, dict):
            raise ValueError(f"Trip score source must be a JSON object or list: {source_path}")

        rows: list[dict[str, Any]] = []
        for group_key, group_rows in payload.items():
            if not isinstance(group_rows, list):
                raise ValueError(
                    f"Trip score group {group_key!r} must contain a JSON list: {source_path}"
                )
            for row in group_rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Trip score rows must be JSON objects: {source_path}")
                enriched_row = dict(row)
                enriched_row.setdefault("sourceGroupKey", str(group_key).strip() or "GL_TRIP_DATA")
                rows.append(enriched_row)

        return rows

    def map_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Map one trip-score record using the active conversion context."""

        if self._context is None:
            raise RuntimeError("TripScoreConverter context has not been initialised.")
        mapped = map_trip_score(dict(record), self._context)
        if mapped is None:
            raise ValueError("Trip score record is missing a valid tripId/accountId or window.")
        return mapped

    @staticmethod
    def _noop_sql(source_filename: str, run_dir: Path, table_name: str) -> str:
        """Build a valid transaction shell for empty trip-score runs."""

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
        """Convert the latest trip-score payload and write the SQL output."""

        records = self.load_source(run_dir)
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
        imported_driver_ids = resolve_driver_ids(source_driver_ids)
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
            retailer_location_ids_by_internal_id={
                fleet_id: identity.retailer_location_id
                for fleet_id, identity in fleet_identities_by_internal_id.items()
            },
        )

        mapped_rows: list[dict[str, Any]] = []
        skipped_rows = 0
        filtered_rows = 0
        filtered_driver_ids: set[str] = set()
        for index, record in enumerate(records, start=1):
            trip_id = _json_text(record.get("tripId"))
            driver_id = _json_text(record.get("driverId") or record.get("thirdPartyId"))
            if not trip_id or not driver_id:
                skipped_rows += 1
                LOGGER.error(
                    "trip_score_index=%s tripId=%r driverId=%r reason=%s",
                    index,
                    record.get("tripId"),
                    record.get("driverId") or record.get("thirdPartyId"),
                    "missing_trip_id_or_driver_id",
                )
                continue
            if driver_id not in imported_driver_ids:
                filtered_rows += 1
                filtered_driver_ids.add(driver_id)
                continue
            enriched_record = dict(record)
            enriched_record["driverId"] = driver_id
            enriched_record["sourceGroupKey"] = _json_text(enriched_record.get("sourceGroupKey")) or "GL_TRIP_DATA"
            enriched_record["sourceRowIndex"] = index
            mapped_row = map_trip_score(enriched_record, self._context)
            if mapped_row is None:
                skipped_rows += 1
                continue
            mapped_rows.append(mapped_row)

        if filtered_driver_ids:
            LOGGER.warning(
                "trip_score_filtered_missing_driver_ids=%s filtered_rows=%s",
                sorted(filtered_driver_ids),
                filtered_rows,
            )

        deduped_rows: list[dict[str, Any]] = []
        seen_trip_ids: set[str] = set()
        duplicate_count = 0
        for row in mapped_rows:
            trip_id = str(row.get("trip_id")).strip()
            if not trip_id:
                continue
            if trip_id in seen_trip_ids:
                duplicate_count += 1
                continue
            seen_trip_ids.add(trip_id)
            deduped_rows.append(row)

        if duplicate_count:
            LOGGER.warning("trip_score_duplicate_rows_suppressed=%s", duplicate_count)

        LOGGER.info(
            "trip_scores_total=%s trip_scores_resolved=%s trip_scores_skipped=%s trip_scores_filtered=%s trip_scores_deduped=%s trip_scores_lookups=%s",
            len(records),
            len(deduped_rows),
            skipped_rows,
            filtered_rows,
            duplicate_count,
            len(imported_driver_ids),
        )

        sql_dir = sql_dir_for_run(run_dir)
        if not deduped_rows:
            output_path = write_sql_file(
                sql_dir / self.sql_filename,
                self._noop_sql(self.source_filename, run_dir, self.target_table),
            )
            LOGGER.warning("No resolvable trip scores were found; wrote no-op SQL.")
            return output_path

        output_path = write_sql_file(
            sql_dir / self.sql_filename,
            build_upsert_sql(
                schema=get_db_schema(),
                table=self.target_table,
                rows=deduped_rows,
                conflict_columns=self.conflict_columns,
                updatable_columns=self.updatable_columns,
                generated_columns=self.generated_columns,
                source_filename=self.source_filename,
                run_dir=Path(run_dir),
            ),
        )
        return output_path


if __name__ == "__main__":  # pragma: no cover - smoke block only
    sample_row = {
        "tripId": "trip-1",
        "accountId": 123,
        "fleetId": "fleet-1",
        "thirdPartyId": "tp-1",
        "tripType": "driver",
        "distance": 42,
        "startDate": 1000,
        "endDate": 2000,
        "startLatitude": 1.5,
        "startLongitude": 2.5,
        "startDescription": "Start",
        "endLatitude": 3.5,
        "endLongitude": 4.5,
        "endDescription": "End",
        "weatherCode": 113,
        "weatherTempLow": 10,
        "weatherTempHigh": 20,
        "weatherWind": 5,
    }
    ctx = ConvertContext(
        company_id_by_internal_id={"fleet-1": UUID("00000000-0000-0000-0000-000000000000")},
        retailer_location_ids_by_internal_id={"fleet-1": 101},
    )
    mapped = map_trip_score(sample_row, ctx)
    assert mapped is not None
    assert mapped["geo"] == {
        "startLatitude": 1.5,
        "startLongitude": 2.5,
        "startDescription": "Start",
        "endLatitude": 3.5,
        "endLongitude": 4.5,
        "endDescription": "End",
    }
    assert mapped["weather"] == {
        "weatherCode": 113,
        "weatherTempLow": 10.0,
        "weatherTempHigh": 20.0,
        "weatherWind": 5.0,
    }

    empty_geo_row = dict(sample_row)
    for key in ("startLatitude", "startLongitude", "startDescription", "endLatitude", "endLongitude", "endDescription"):
        empty_geo_row[key] = None
    mapped_empty_geo = map_trip_score(empty_geo_row, ctx)
    assert mapped_empty_geo is not None
    assert mapped_empty_geo["geo"] is None

    invalid_window_row = dict(sample_row)
    invalid_window_row["endDate"] = 999
    assert map_trip_score(invalid_window_row, ctx) is None
