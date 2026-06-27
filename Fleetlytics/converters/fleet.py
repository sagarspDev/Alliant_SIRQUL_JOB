"""Fleet JSON-to-SQL converter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .base import BaseConverter
from .mappers import map_fleet
from .paths import sql_dir_for_run


class FleetConverter(BaseConverter):
    """Convert the latest fleet JSON payload into an UPSERT SQL file."""

    entity_name = "fleet"
    source_filename = "fleet.json"
    target_table = "sirqul_fleet"
    conflict_columns = ["retailer_location_id"]
    updatable_columns = [
        "company_id",
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
        "last_synced_at",
    ]
    generated_columns = {"created_at", "updated_at"}
    sql_filename = "001_fleet.sql"

    def load_source(self, run_dir: Path) -> dict[str, Any]:
        """Load and unwrap the latest fleet JSON payload."""

        source_path = Path(run_dir) / self.source_filename
        if not source_path.exists():
            raise FileNotFoundError(f"Missing fleet source file: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            raise ValueError(f"Fleet source file is empty: {source_path}")

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Fleet source file is not valid JSON: {source_path}") from exc

        if isinstance(payload, dict) and isinstance(payload.get("item"), dict):
            item = payload["item"]
        elif isinstance(payload, dict):
            item = payload
        else:
            raise ValueError(f"Fleet source must be a JSON object: {source_path}")

        if not item:
            raise ValueError(f"Fleet source file contains no fleet item: {source_path}")

        return item

    def map_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        """Map one fleet record to a database row dict."""

        return map_fleet(record)

    def write_run_sql(self, run_dir: Path) -> Path:
        """Convert the latest fleet record and write the SQL output."""

        records = self.load_source(run_dir)
        rows = self.convert(records)
        sql_dir = sql_dir_for_run(run_dir)
        output_path = self.write_sql(rows, sql_dir)
        return output_path


def convert_fleet(run_dir: Path) -> Path:
    """Convert the latest fleet JSON payload into ``001_fleet.sql``."""

    converter = FleetConverter()
    return converter.write_run_sql(run_dir)
