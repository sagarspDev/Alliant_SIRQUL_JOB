"""Import run aggregation and report writing helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .base import ImportResult


@dataclass(slots=True)
class ImportReport:
    """Aggregate import results and persist a run-level report."""

    run_dir: Path
    results: list[ImportResult] = field(default_factory=list)
    skipped_records: list[dict[str, Any]] = field(default_factory=list)

    def add_result(self, result: ImportResult) -> None:
        """Append one import result to the report."""

        self.results.append(result)

    def add_skipped_records(self, records: list[dict[str, Any]]) -> None:
        """Append skipped conversion records to the report."""

        self.skipped_records.extend(records)

    def summary(self) -> dict[str, Any]:
        """Return a serialisable summary of all tracked imports."""

        totals = {
            "rows_inserted": sum(result.rows_inserted for result in self.results),
            "rows_updated": sum(result.rows_updated for result in self.results),
            "rows_skipped": sum(result.rows_skipped for result in self.results),
            "tables": len(self.results),
            "skipped_records": len(self.skipped_records),
        }
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "totals": totals,
            "results": [
                {
                    **asdict(result),
                    "file_path": str(result.file_path),
                }
                for result in self.results
            ],
            "skipped_records": self.skipped_records,
        }

    def write(self) -> Path:
        """Write ``import_report.json`` into the run directory."""

        report_path = Path(self.run_dir) / "import_report.json"
        report_path.write_text(
            json.dumps(self.summary(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return report_path
