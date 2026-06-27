"""Fleet discovery and reconciliation against ``sirqul_fleet``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

try:  # pragma: no cover - execution context dependent
    from .. import fleet_api
    from ..db.lookups import resolve_company_ids_by_retailer_location_id
    from ..src.config import get_db_schema, get_db_url
    from ..src.logger import get_logger
except ImportError:  # pragma: no cover - fallback for direct execution from Fleetlytics/
    import fleet_api
    from Fleetlytics.db.lookups import resolve_company_ids_by_retailer_location_id
    from src.config import get_db_schema, get_db_url
    from src.logger import get_logger


LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class DiscoveredFleet:
    internal_id: str
    name: str
    raw: dict


@dataclass
class ReconciliationResult:
    known: list[DiscoveredFleet] = field(default_factory=list)
    inserted: list[DiscoveredFleet] = field(default_factory=list)
    pending: list[DiscoveredFleet] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def total_seen(self) -> int:
        return len(self.known) + len(self.inserted) + len(self.pending)


def discover_and_reconcile_fleets(
    *,
    output_root: Path,
    run_timestamp: str,
    dry_run: bool = False,
) -> ReconciliationResult:
    """
    1. Call fleet_api.search_fleets().
    2. Load existing rows from sirqul_fleet via a single DB query.
    3. Classify each /fleets/search row as known | new-resolvable | new-unresolvable.
    4. For new-resolvable rows, UPSERT into sirqul_fleet (unless dry_run).
    5. Write diagnostic files to <output_root>/_discovery/<run_timestamp>/.
    6. Return ReconciliationResult.
    """

    global _TARGET_COMPANY_EXISTS_CACHE, _TARGET_COMPANY_CACHE_KEY

    result = ReconciliationResult()
    output_root = Path(output_root).expanduser()
    raw_fleets: list[dict[str, Any]] = []
    diagnostic_dir = output_root / "_discovery" / run_timestamp
    _TARGET_COMPANY_EXISTS_CACHE = None
    _TARGET_COMPANY_CACHE_KEY = None

    try:
        raw_fleets = fleet_api.search_fleets()
    except Exception as exc:
        result.errors.append(f"/fleets/search failed: {exc}")
        _write_diagnostics(
            diagnostic_dir=diagnostic_dir,
            raw_fleets=raw_fleets,
            result=result,
            dry_run=dry_run,
        )
        _log_summary(result, dry_run)
        return result

    discovered_fleets = [_to_discovered_fleet(row) for row in raw_fleets]

    try:
        schema = get_db_schema()
        existing_by_internal_id = _load_existing_fleets(schema=schema)
    except Exception as exc:
        result.errors.append(f"sirqul_fleet read failed: {exc}")
        _write_diagnostics(
            diagnostic_dir=diagnostic_dir,
            raw_fleets=raw_fleets,
            result=result,
            dry_run=dry_run,
        )
        _log_summary(result, dry_run)
        return result

    retailer_location_ids = [
        retailer_location_id
        for retailer_location_id in (
            _extract_retailer_location_id(discovered.raw) for discovered in discovered_fleets
        )
        if retailer_location_id is not None
    ]
    company_ids_by_retailer_location_id = resolve_company_ids_by_retailer_location_id(
        retailer_location_ids
    )

    upsert_candidates: list[tuple[DiscoveredFleet, int, Any]] = []
    for discovered in discovered_fleets:
        if discovered.internal_id in existing_by_internal_id:
            result.known.append(discovered)
            continue

        retailer_location_id = _extract_retailer_location_id(discovered.raw)
        if retailer_location_id is None:
            result.pending.append(discovered)
            continue

        resolved_company_id = company_ids_by_retailer_location_id.get(retailer_location_id)
        if resolved_company_id is None:
            result.pending.append(discovered)
            continue

        upsert_candidates.append((discovered, retailer_location_id, resolved_company_id))

    insertable_rows: list[tuple[int, Any, str, str, bool, Jsonb, None]] = []
    would_insert: list[DiscoveredFleet] = []
    for discovered, retailer_location_id, company_id in upsert_candidates:
        name = discovered.name.strip() or discovered.internal_id
        if not discovered.name.strip():
            LOGGER.warning(
                "Blank fleet name in /fleets/search payload; using internal_id as fallback internal_id=%s",
                discovered.internal_id,
            )

        insertable_rows.append(
            (
                retailer_location_id,
                company_id,
                discovered.internal_id,
                name,
                True,
                Jsonb(discovered.raw),
                None,
            )
        )
        would_insert.append(
            DiscoveredFleet(
                internal_id=discovered.internal_id,
                name=name,
                raw=discovered.raw,
            )
        )

    if insertable_rows:
        upsert_error = _upsert_discovered_fleets(
            schema=schema,
            rows=insertable_rows,
            dry_run=dry_run,
        )
        if upsert_error is None:
            result.inserted.extend(would_insert)
        else:
            result.errors.append(upsert_error)
            result.pending.extend(would_insert)
    _write_diagnostics(
        diagnostic_dir=diagnostic_dir,
        raw_fleets=raw_fleets,
        result=result,
        dry_run=dry_run,
    )
    _log_summary(result, dry_run)
    return result


def _to_discovered_fleet(row: dict[str, Any]) -> DiscoveredFleet:
    """Normalize one raw /fleets/search row into the local discovery shape."""

    internal_id = _first_non_blank(
        row.get("internal_id"),
        row.get("internalId"),
        row.get("id"),
        row.get("fleetId"),
    )
    if not internal_id:
        internal_id = json.dumps(row, sort_keys=True)
        LOGGER.warning("Missing recognizable fleet identifier in /fleets/search row; using row JSON as fallback")

    # NOTE: No saved /fleets/search sample exists under output/ or Docs/, so this field
    # mapping is defensive until the real payload keys are confirmed.
    name = _first_non_blank(
        row.get("name"),
        row.get("fleetName"),
        row.get("display"),
        row.get("title"),
    ) or str(internal_id)

    return DiscoveredFleet(
        internal_id=str(internal_id),
        name=str(name),
        raw=row,
    )


def _first_non_blank(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _load_existing_fleets(*, schema: str) -> dict[str, dict[str, Any]]:
    """Load current sirqul_fleet rows keyed by internal_id."""

    query = sql.SQL(
        """
        SELECT retailer_location_id, internal_id, company_id, name, active
        FROM {}.sirqul_fleet
        """
    ).format(sql.Identifier(schema))

    existing: dict[str, dict[str, Any]] = {}
    with psycopg.connect(get_db_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            for retailer_location_id, internal_id, company_id, name, active in cursor.fetchall():
                if internal_id is None:
                    continue
                existing[str(internal_id)] = {
                    "retailer_location_id": retailer_location_id,
                    "company_id": company_id,
                    "name": name,
                    "active": active,
                }
    return existing


def _extract_retailer_location_id(row: dict[str, Any]) -> int | None:
    """Resolve the retailer location ID from a discovered fleet payload."""

    for key in ("retailerLocationId", "retailer_location_id", "locationId", "id"):
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            continue
    internal_id = row.get("internalId") or row.get("internal_id") or row.get("fleetId")
    if internal_id is None:
        return None
    try:
        return int(str(internal_id).strip())
    except (TypeError, ValueError):
        return None


def _upsert_discovered_fleets(
    *,
    schema: str,
    rows: list[tuple[int, Any, str, str, bool, Jsonb, None]],
    dry_run: bool,
) -> str | None:
    """Insert or update resolved discovered fleets in one transaction."""

    values_sql = sql.SQL(", ").join(
        [sql.SQL("(%s, %s, %s, %s, %s, %s, %s, now())")] * len(rows)
    )
    # NOTE: The prompt text called this column `metadata`, but the checked-in DDL at
    # Docs/045_create_sirqul_fleet_driver_tables.sql currently names it `meta_data`.
    # Use the repo's declared schema here until the live table contract is reconfirmed.
    query = sql.SQL(
        """
        INSERT INTO {}.sirqul_fleet (
            retailer_location_id,
            company_id,
            internal_id,
            name,
            active,
            meta_data,
            stats,
            last_synced_at
        )
        VALUES {}
        ON CONFLICT (retailer_location_id) DO UPDATE SET
            company_id     = EXCLUDED.company_id,
            internal_id    = EXCLUDED.internal_id,
            name           = EXCLUDED.name,
            active         = EXCLUDED.active,
            meta_data      = EXCLUDED.meta_data,
            last_synced_at = now()
        WHERE
            sirqul_fleet.company_id  IS DISTINCT FROM EXCLUDED.company_id
         OR sirqul_fleet.internal_id IS DISTINCT FROM EXCLUDED.internal_id
         OR sirqul_fleet.name        IS DISTINCT FROM EXCLUDED.name
         OR sirqul_fleet.active      IS DISTINCT FROM EXCLUDED.active
         OR sirqul_fleet.meta_data   IS DISTINCT FROM EXCLUDED.meta_data
        """
    ).format(sql.Identifier(schema), values_sql)

    flattened_params = [value for row in rows for value in row]

    connection: psycopg.Connection[Any] | None = None
    try:
        connection = psycopg.connect(get_db_url())
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute(query, flattened_params)
        if dry_run:
            connection.rollback()
        else:
            connection.commit()
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        LOGGER.exception("Discovered fleet UPSERT failed")
        return f"fleet UPSERT failed: {exc}"
    finally:
        if connection is not None:
            connection.close()
    return None


def _write_diagnostics(
    *,
    diagnostic_dir: Path,
    raw_fleets: list[dict[str, Any]],
    result: ReconciliationResult,
    dry_run: bool,
) -> None:
    """Persist raw discovery output and reconciliation diagnostics."""

    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    (diagnostic_dir / "fleets_search_raw.json").write_text(
        json.dumps(raw_fleets, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (diagnostic_dir / "reconciliation_summary.json").write_text(
        json.dumps(
            {
                "fetched_at": result.fetched_at.isoformat(),
                "dry_run": dry_run,
                "counts": {
                    "seen": result.total_seen(),
                    "known": len(result.known),
                    "inserted": len(result.inserted),
                    "pending": len(result.pending),
                    "errors": len(result.errors),
                },
                "known": [_serialize_discovered_fleet(fleet) for fleet in result.known],
                "inserted": [_serialize_discovered_fleet(fleet) for fleet in result.inserted],
                "pending": [_serialize_discovered_fleet(fleet) for fleet in result.pending],
                "errors": result.errors,
            },
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostic_dir / "pending_fleets.json").write_text(
        json.dumps([fleet.raw for fleet in result.pending], indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _serialize_discovered_fleet(fleet: DiscoveredFleet) -> dict[str, Any]:
    return asdict(fleet)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _log_summary(result: ReconciliationResult, dry_run: bool) -> None:
    LOGGER.info(
        "[discovery] seen=%s known=%s inserted=%s pending=%s errors=%s dry_run=%s",
        result.total_seen(),
        len(result.known),
        len(result.inserted),
        len(result.pending),
        len(result.errors),
        dry_run,
    )


if __name__ == "__main__":  # pragma: no cover - smoke example only
    empty = ReconciliationResult()
    print(empty.total_seen())
