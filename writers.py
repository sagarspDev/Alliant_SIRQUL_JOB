"""Output writers for Fleetlytics JSON and CSV exports.

This module owns the output-layer contract documented in
``FLEETLYTICS_CONTEXT.md``:

- one timestamped run directory per retailer location
- paired JSON and CSV outputs for fleet, drivers, driver scores, and trip scores
- safe handling of nested payloads and non-serializable values

The JSON exports remain raw API payloads. The CSV exports are projection files
aligned with the canonical DDL in
``Fleetlytics/Docs/045_create_sirqul_fleet_driver_tables.sql`` so the future
Supabase mapper can reuse the same column semantics with minimal translation.
The score CSVs also include human-readable datetime companions for every
epoch-based field.

Fleet CSV columns:
``retailer_location_id, internal_id, name, location_type, public_location,
qr_code_url, location_token, active, latitude, longitude, manager, categories,
filters, billable_entity, retailer, offers, meta_data, contact, stats``

Driver CSV columns:
``account_id, driver_id, retailer_location_id, display, username, account_type,
contact_email, location_display, active, latitude, longitude, location_count,
manager, contact, employer, app_info, locations, app_blob_driver_id,
app_blob_work_shift_audience_id, app_blob_additional_services``

The CSV projections intentionally exclude internal/audit/FK-only columns such as
``company_id``, ``user_id``, ``created_at``, ``updated_at``, and
``last_synced_at``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timezone
import argparse
import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import path depends on execution context
    from .src.logger import get_logger
    from .pipeline.paths import build_run_dir
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    from src.logger import get_logger
    from Fleetlytics.pipeline.paths import build_run_dir

_LOGGER = get_logger(__name__)

CSV_ENCODING = "utf-8"
DEFAULT_JSON_INDENT = 2
DEFAULT_JSON_SORT_KEYS = False

FLEET_CSV_FIELDS: list[str] = [
    "retailer_location_id",
    "internal_id",
    "name",
    "location_type",
    "public_location",
    "qr_code_url",
    "location_token",
    "active",
    "latitude",
    "longitude",
    "manager",
    "categories",
    "filters",
    "billable_entity",
    "retailer",
    "offers",
    "meta_data",
    "contact",
    "stats",
]

DRIVER_CSV_FIELDS: list[str] = [
    "account_id",
    "driver_id",
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
    "app_blob_driver_id",
    "app_blob_work_shift_audience_id",
    "app_blob_additional_services",
]


@dataclass(slots=True)
class RunPaths:
    """Resolve and create the timestamped directory for a Fleetlytics run."""

    output_dir: Path
    retailer_location_id: int | str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S_UTC"))
    run_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir).expanduser()
        self.run_dir = build_run_dir(self.output_dir, str(self.retailer_location_id), self.timestamp)

    def path_for(self, entity_name: str, ext: str) -> Path:
        """Return the output path for ``entity_name`` and file extension ``ext``."""

        normalized_entity = entity_name.strip()
        normalized_ext = ext.strip().lstrip(".")
        if not normalized_entity:
            raise ValueError("entity_name must not be blank")
        if not normalized_ext:
            raise ValueError("ext must not be blank")
        return self.run_dir / f"{normalized_entity}.{normalized_ext}"


@dataclass(slots=True)
class EntityWriteResult:
    """Summary of one entity write operation."""

    entity: str
    row_count: int
    json_path: Path
    csv_path: Path
    json_bytes: int
    csv_bytes: int


class JSONWriter:
    """Write Fleetlytics payloads to pretty-printed JSON files."""

    def __init__(self, *, indent: int = DEFAULT_JSON_INDENT, sort_keys: bool = DEFAULT_JSON_SORT_KEYS) -> None:
        self.indent = indent
        self.sort_keys = sort_keys

    def write(self, entity_name: str, payload: Any, run_paths: RunPaths) -> Path:
        """Write ``payload`` to the JSON file for ``entity_name`` and return the path."""

        output_path = run_paths.path_for(entity_name, "json")
        with output_path.open("w", encoding=CSV_ENCODING) as handle:
            json.dump(
                payload,
                handle,
                indent=self.indent,
                sort_keys=self.sort_keys,
                ensure_ascii=False,
                default=_json_default,
            )
            handle.write("\n")
        return output_path


class CSVWriter:
    """Write flattened Fleetlytics exports to CSV using the stdlib ``csv`` module.

    List handling policy:
    - scalar lists are joined with ``;`` to preserve a readable analytical
      export
    - nested dicts and complex list items are serialized as compact JSON text
    - ``additionalServices`` always uses the ``;`` join policy requested by the
      output contract
    """

    def write_fleet(self, fleet_dict: Mapping[str, Any], run_paths: RunPaths) -> tuple[Path, int]:
        """Write the DDL-aligned fleet CSV and return ``(path, rows_written)``.

        Columns follow ``public.sirqul_fleet`` in
        ``Fleetlytics/Docs/045_create_sirqul_fleet_driver_tables.sql`` and omit
        internal columns such as ``company_id``, ``created_at``, ``updated_at``,
        and ``last_synced_at``.
        """

        row = _build_fleet_csv_row(fleet_dict)
        output_path = run_paths.path_for("fleet", "csv")
        self._write_csv_rows([row], FLEET_CSV_FIELDS, output_path)
        return output_path, 1

    def write_drivers(self, drivers_list: Sequence[Mapping[str, Any]], run_paths: RunPaths) -> tuple[Path, int]:
        """Write the DDL-aligned driver CSV and return ``(path, rows_written)``.

        Columns follow ``public.sirqul_driver`` in
        ``Fleetlytics/Docs/045_create_sirqul_fleet_driver_tables.sql`` and omit
        internal columns such as ``user_id``, ``created_at``, ``updated_at``,
        and ``last_synced_at``. Appended convenience columns expose parsed
        ``appInfo.appBlob`` values for human inspection and future ingestion.
        """

        rows = [_build_driver_csv_row(driver) for driver in drivers_list]
        output_path = run_paths.path_for("drivers", "csv")
        self._write_csv_rows(rows, DRIVER_CSV_FIELDS, output_path)
        return output_path, len(rows)

    def write_driver_scores(
        self,
        scores: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> tuple[Path, int]:
        """Write driver score rows as a flat JSON and CSV export."""

        rows = [dict(row) for row in scores]
        output_path = run_paths.path_for("driver_scores", "csv")
        columns = _records_to_columns(
            rows,
            preferred_columns=["driverId", "driverName", "fleetId", "fleetName", "thirdPartyId", "accountId"],
        )
        self._write_csv_rows(rows, columns, output_path)
        return output_path, len(rows)

    def write_trip_scores(
        self,
        trips: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> tuple[Path, int]:
        """Write trip score rows as a flat JSON and CSV export."""

        rows = [dict(row) for row in trips]
        output_path = run_paths.path_for("trip_scores", "csv")
        columns = _records_to_columns(
            rows,
            preferred_columns=["driverId", "driverName", "fleetId", "fleetName", "thirdPartyId", "accountId"],
        )
        self._write_csv_rows(rows, columns, output_path)
        return output_path, len(rows)

    def write_trip_locations(
        self,
        rows: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> tuple[Path, int]:
        """Write trip location rows as a flat JSON and CSV export."""

        materialized_rows = [dict(row) for row in rows]
        output_path = run_paths.path_for("trip_locations", "csv")
        columns = _records_to_columns(
            materialized_rows,
            preferred_columns=["tripId", "accountId", "timestamp", "latitude", "longitude"],
        )
        self._write_csv_rows(materialized_rows, columns, output_path)
        return output_path, len(materialized_rows)

    def write_trip_incidents(
        self,
        rows: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> tuple[Path, int]:
        """Write trip incident rows as a flat JSON and CSV export."""

        materialized_rows = [dict(row) for row in rows]
        output_path = run_paths.path_for("trip_incidents", "csv")
        columns = _records_to_columns(
            materialized_rows,
            preferred_columns=["tripId", "accountId", "timestamp", "type", "latitude", "longitude"],
        )
        self._write_csv_rows(materialized_rows, columns, output_path)
        return output_path, len(materialized_rows)

    def _write_csv_rows(self, rows: Sequence[Mapping[str, Any]], columns: Sequence[str], output_path: Path) -> None:
        """Persist flat row mappings to ``output_path`` using UTF-8 CSV encoding."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
            if columns:
                writer.writeheader()
            for row in rows:
                writer.writerow({column: _normalize_csv_value(row.get(column)) for column in columns})


class OutputWriter:
    """Facade that writes both JSON and CSV variants for every entity."""

    def __init__(
        self,
        *,
        json_writer: JSONWriter | None = None,
        csv_writer: CSVWriter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.json_writer = json_writer or JSONWriter()
        self.csv_writer = csv_writer or CSVWriter()
        self.logger = logger or _LOGGER

    def write_fleet(self, fleet_dict: Mapping[str, Any], run_paths: RunPaths) -> EntityWriteResult:
        """Write the fleet payload to JSON and CSV."""

        json_path = self.json_writer.write("fleet", fleet_dict, run_paths)
        csv_path, row_count = self.csv_writer.write_fleet(fleet_dict, run_paths)
        return self._log_result("fleet", row_count, json_path, csv_path)

    def write_drivers(self, drivers_list: Sequence[Mapping[str, Any]], run_paths: RunPaths) -> EntityWriteResult:
        """Write the driver list to JSON and CSV."""

        json_path = self.json_writer.write("drivers", list(drivers_list), run_paths)
        csv_path, row_count = self.csv_writer.write_drivers(drivers_list, run_paths)
        return self._log_result("drivers", row_count, json_path, csv_path)

    def write_driver_scores(
        self,
        scores: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        """Write the driver score list to JSON and CSV."""

        json_path = self.json_writer.write("driver_scores", list(scores), run_paths)
        csv_path, row_count = self.csv_writer.write_driver_scores(scores, run_paths)
        return self._log_result("driver_scores", row_count, json_path, csv_path)

    def write_trip_scores(
        self,
        trips: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        """Write the trip score list to JSON and CSV."""

        json_path = self.json_writer.write("trip_scores", list(trips), run_paths)
        csv_path, row_count = self.csv_writer.write_trip_scores(trips, run_paths)
        return self._log_result("trip_scores", row_count, json_path, csv_path)

    def write_trip_locations(
        self,
        rows: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        """Write the trip location list to JSON and CSV."""

        json_path = self.json_writer.write("trip_locations", list(rows), run_paths)
        csv_path, row_count = self.csv_writer.write_trip_locations(rows, run_paths)
        return self._log_result("trip_locations", row_count, json_path, csv_path)

    def write_trip_incidents(
        self,
        rows: Sequence[Mapping[str, Any]],
        run_paths: RunPaths,
    ) -> EntityWriteResult:
        """Write the trip incident list to JSON and CSV."""

        json_path = self.json_writer.write("trip_incidents", list(rows), run_paths)
        csv_path, row_count = self.csv_writer.write_trip_incidents(rows, run_paths)
        return self._log_result("trip_incidents", row_count, json_path, csv_path)

    def _log_result(self, entity: str, row_count: int, json_path: Path, csv_path: Path) -> EntityWriteResult:
        """Log the file paths, row counts, and sizes for a completed write."""

        json_bytes = json_path.stat().st_size
        csv_bytes = csv_path.stat().st_size
        self.logger.info(
            "Wrote %s JSON path=%s size_bytes=%s",
            entity,
            json_path,
            json_bytes,
        )
        self.logger.info(
            "Wrote %s CSV path=%s rows=%s size_bytes=%s",
            entity,
            csv_path,
            row_count,
            csv_bytes,
        )
        self.logger.info(
            "Completed %s write rows=%s json_size_bytes=%s csv_size_bytes=%s",
            entity,
            row_count,
            json_bytes,
            csv_bytes,
        )
        return EntityWriteResult(
            entity=entity,
            row_count=row_count,
            json_path=json_path,
            csv_path=csv_path,
            json_bytes=json_bytes,
            csv_bytes=csv_bytes,
        )


def _build_fleet_csv_row(fleet_dict: Mapping[str, Any]) -> dict[str, Any]:
    """Project a fleet payload into the DDL-aligned CSV columns."""

    stats = {
        "favorite": _get(fleet_dict, "favorite"),
        "favoriteCount": _get(fleet_dict, "favoriteCount"),
        "noteCount": _get(fleet_dict, "noteCount"),
        "sharedCount": _get(fleet_dict, "sharedCount"),
        "likeCount": _get(fleet_dict, "likeCount"),
        "dislikeCount": _get(fleet_dict, "dislikeCount"),
        "hasRatings": _get(fleet_dict, "hasRatings"),
    }

    meta_data = _get(fleet_dict, "metaData")
    if meta_data is not None and not isinstance(meta_data, str):
        meta_data = _to_json_str(meta_data)

    return {
        "retailer_location_id": _get(fleet_dict, "retailerLocationId"),
        "internal_id": _get(fleet_dict, "internalId"),
        "name": _get(fleet_dict, "name"),
        "location_type": _get(fleet_dict, "locationType"),
        "public_location": _get(fleet_dict, "publicLocation"),
        "qr_code_url": _get(fleet_dict, "qrCodeUrl"),
        "location_token": _get(fleet_dict, "locationToken"),
        "active": _get(fleet_dict, "active"),
        "latitude": _get(fleet_dict, "latitude"),
        "longitude": _get(fleet_dict, "longitude"),
        "manager": _to_json_str(_get(fleet_dict, "manager")),
        "categories": _to_json_str(_get(fleet_dict, "categories")),
        "filters": _to_json_str(_get(fleet_dict, "filters")),
        "billable_entity": _to_json_str(_get(fleet_dict, "billableEntity")),
        "retailer": _to_json_str(_get(fleet_dict, "retailer")),
        "offers": _to_json_str(_get(fleet_dict, "offers")),
        "meta_data": meta_data,
        "contact": _to_json_str(_get(fleet_dict, "contact")),
        "stats": _to_json_str(stats),
    }


def _build_driver_csv_row(driver: Mapping[str, Any]) -> dict[str, Any]:
    """Project a driver payload into the DDL-aligned CSV columns.

    The first 16 columns align with ``public.sirqul_driver`` in
    ``Fleetlytics/Docs/045_create_sirqul_fleet_driver_tables.sql``. The final
    three columns are convenience fields derived from ``appInfo.appBlob`` for
    downstream visibility.
    """

    app_info = _get(driver, "appInfo")
    parsed_app_blob = _parse_app_blob(app_info)
    additional_services = _get(parsed_app_blob, "additionalServices")

    return {
        "account_id": _get(driver, "accountId"),
        "retailer_location_id": _get(driver, "locations[0].retailerLocationId"),
        "display": _get(driver, "display"),
        "username": _get(driver, "username"),
        "account_type": _get(driver, "accountType"),
        "contact_email": _first_present_value(
            driver,
            ("contactEmail", "contact.contactInfo.emailAddress"),
        ),
        "location_display": _get(driver, "locationDisplay"),
        "active": _get(driver, "active"),
        "latitude": _get(driver, "latitude"),
        "longitude": _get(driver, "longitude"),
        "location_count": _get(driver, "locationCount"),
        "manager": _to_json_str(_get(driver, "manager")),
        "contact": _to_json_str(_get(driver, "contact")),
        "employer": _to_json_str(_get(driver, "employer")),
        "app_info": _to_json_str(app_info),
        "locations": _to_json_str(_get(driver, "locations")),
        "app_blob_driver_id": _get(parsed_app_blob, "driverId"),
        "app_blob_work_shift_audience_id": _get(parsed_app_blob, "workShiftAudienceId"),
        "app_blob_additional_services": _render_additional_services(additional_services),
    }


def _expand_account_grouped_rows(
    grouped_rows: Mapping[int | str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Flatten driver-keyed score or trip rows into a single table."""

    rows: list[dict[str, Any]] = []
    for account_id, records in grouped_rows.items():
        for record in records:
            flat_record = _flatten_record(record)
            flat_record["accountId"] = _coerce_scalar(account_id)
            rows.append(_add_readable_epoch_columns(flat_record))
    return rows


def _add_readable_epoch_columns(row: Mapping[str, Any]) -> dict[str, Any]:
    """Add human-readable UTC datetime columns next to epoch-based fields."""

    augmented_row: dict[str, Any] = {}
    for key, value in row.items():
        augmented_row[key] = value
        if _looks_like_epoch_field(key):
            readable_value = _format_epoch_ms_utc(value)
            if readable_value is not None:
                augmented_row[f"{key}Datetime"] = readable_value
    return augmented_row


def _looks_like_epoch_field(column_name: str) -> bool:
    """Return ``True`` for score columns that store Unix epoch milliseconds."""

    return column_name in {
        "startDate",
        "endDate",
        "lastAccelIncident",
        "lastBrakeIncident",
        "lastCollisionIncident",
        "lastPhoneIncident",
        "lastSpeedIncident",
        "lastTurnIncident",
    }


def _format_epoch_ms_utc(value: Any) -> str | None:
    """Render epoch milliseconds as ``YYYY-MM-DD HH:MM:SS`` in UTC."""

    if value in (None, ""):
        return None

    try:
        epoch_ms = float(value)
    except (TypeError, ValueError):
        return None

    if epoch_ms != epoch_ms:  # NaN check without importing math
        return None

    try:
        return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def _records_to_columns(
    rows: Sequence[Mapping[str, Any]],
    *,
    preferred_columns: Sequence[str] | None = None,
) -> list[str]:
    """Create a stable CSV column order from flat row mappings."""

    if not rows:
        return list(preferred_columns or [])

    seen: list[str] = []
    for row in rows:
        for column in row.keys():
            if column not in seen:
                seen.append(column)

    ordered_columns: list[str] = []
    if preferred_columns:
        for column in preferred_columns:
            if column in seen and column not in ordered_columns:
                ordered_columns.append(column)

    for column in seen:
        if column not in ordered_columns:
            ordered_columns.append(column)

    return ordered_columns


def _flatten_record(record: Mapping[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Recursively flatten nested mappings while preserving readable values."""

    flattened: dict[str, Any] = {}
    for key, value in record.items():
        composed_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, Mapping):
            flattened.update(_flatten_record(value, composed_key, sep=sep))
        elif isinstance(value, (list, tuple, set)):
            flattened[composed_key] = _serialize_list(value)
        else:
            flattened[composed_key] = value
    return flattened


def _serialize_list(values: Iterable[Any]) -> str:
    """Serialize list-like values for CSV output.

    Scalar sequences are joined with ``;``. Nested structures are emitted as
    compact JSON so the data stays round-trippable and visually inspectable.
    """

    materialized = list(values)
    if not materialized:
        return ""

    if all(_is_scalar(value) for value in materialized):
        return ";".join("" if value is None else str(value) for value in materialized)

    return json.dumps(materialized, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _render_additional_services(value: Any) -> str:
    """Render ``additionalServices`` as a semicolon-joined string."""

    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, Iterable):
        return _serialize_list(value)

    return str(value)


def _first_present_value(record: Mapping[str, Any], candidates: Sequence[str]) -> Any:
    """Return the first non-empty value found at one of the candidate paths."""

    for candidate in candidates:
        value = _get(record, candidate)
        if value is not None and value != "":
            return value
    return None


def _get(obj: Any, path: str, default: Any = None) -> Any:
    """Safely follow dotted paths and list indices.

    Examples:
    - ``locations[0].retailerLocationId``
    - ``contact.contactInfo.emailAddress``
    """

    if obj is None:
        return default

    current: Any = obj
    for token in _path_tokens(path):
        if isinstance(token, str):
            if not isinstance(current, Mapping) or token not in current:
                return default
            current = current[token]
            continue

        if isinstance(current, (str, bytes, bytearray)) or not isinstance(current, Sequence):
            return default
        if token < 0 or token >= len(current):
            return default
        current = current[token]

    return current


def _path_tokens(path: str) -> list[int | str]:
    """Tokenize a dotted path with optional list indices."""

    tokens: list[int | str] = []
    for match in re.finditer(r"([^.\[\]]+)|\[(\d+)\]", path):
        name, index = match.groups()
        if name is not None:
            tokens.append(name)
        elif index is not None:
            tokens.append(int(index))
    return tokens


def _to_json_str(value: Any) -> str | None:
    """Return a compact JSON string for ``value`` or ``None`` when absent."""

    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))


def _parse_app_blob(app_info: Any) -> dict[str, Any]:
    """Extract and parse ``appInfo.appBlob`` into a dict for derived columns."""

    app_blob = _get(app_info, "appBlob")
    if app_blob is None:
        return {}

    if isinstance(app_blob, Mapping):
        return dict(app_blob)

    if isinstance(app_blob, str):
        raw = app_blob.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            _LOGGER.debug("Failed to parse appInfo.appBlob JSON: %s", raw)
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
        _LOGGER.debug("appInfo.appBlob JSON did not decode to an object: %r", parsed)
        return {}

    return {}


def _is_scalar(value: Any) -> bool:
    """Return ``True`` for values that can be represented directly in CSV."""

    return value is None or isinstance(value, (str, int, float, bool))


def _coerce_scalar(value: Any) -> Any:
    """Normalize simple scalar identifiers without changing their type unnecessarily."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_csv_value(value: Any) -> Any:
    """Convert values into CSV-friendly scalars or compact strings."""

    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)

    if isinstance(value, (list, tuple, set)):
        return _serialize_list(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass

    return str(value)


def _json_default(value: Any) -> Any:
    """Fallback serializer for non-JSON-native types."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if isinstance(value, set):
        return list(value)
    return str(value)


def _replay_run(existing_run_dir: Path) -> Path:
    """Rebuild CSV exports from existing JSON artifacts into a new run folder."""

    resolved_run_dir = existing_run_dir.expanduser().resolve()
    if not resolved_run_dir.is_dir():
        raise FileNotFoundError(f"Replay directory does not exist: {resolved_run_dir}")

    fleet_json_path = resolved_run_dir / "fleet.json"
    drivers_json_path = resolved_run_dir / "drivers.json"
    if not fleet_json_path.is_file():
        raise FileNotFoundError(f"Missing fleet.json in replay directory: {fleet_json_path}")
    if not drivers_json_path.is_file():
        raise FileNotFoundError(f"Missing drivers.json in replay directory: {drivers_json_path}")

    fleet_output_dir = resolved_run_dir.parent
    output_dir = fleet_output_dir.parent
    retailer_location_id = fleet_output_dir.name
    run_paths = RunPaths(output_dir=output_dir, retailer_location_id=retailer_location_id)

    fleet_payload = json.loads(fleet_json_path.read_text(encoding=CSV_ENCODING))
    drivers_payload = json.loads(drivers_json_path.read_text(encoding=CSV_ENCODING))
    if not isinstance(drivers_payload, list):
        raise ValueError(f"Expected drivers.json to contain a list: {drivers_json_path}")

    csv_writer = CSVWriter()
    fleet_csv_path, fleet_rows = csv_writer.write_fleet(fleet_payload, run_paths)
    drivers_csv_path, driver_rows = csv_writer.write_drivers(drivers_payload, run_paths)

    print(f"Replayed run directory: {run_paths.run_dir}")
    print(f"fleet.csv -> {fleet_csv_path} ({fleet_rows} row)")
    print(f"drivers.csv -> {drivers_csv_path} ({driver_rows} rows)")

    return run_paths.run_dir


def _print_first_data_row(path: Path) -> str:
    """Return the first non-header row from a CSV file."""

    with path.open("r", encoding=CSV_ENCODING, newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        row = next(reader, [])
    return ",".join(row)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for replaying writer output from existing JSON files."""

    parser = argparse.ArgumentParser(description="Replay Fleetlytics CSV writing from existing JSON outputs")
    parser.add_argument(
        "--replay",
        type=Path,
        help="Existing run directory containing fleet.json and drivers.json",
    )
    args = parser.parse_args(argv)

    if args.replay is None:
        parser.error("the --replay argument is required")

    new_run_dir = _replay_run(args.replay)
    print(f"first_row_fleet={_print_first_data_row(new_run_dir / 'fleet.csv')}")
    print(f"first_row_drivers={_print_first_data_row(new_run_dir / 'drivers.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
