"""Typed request/result objects for Fleetlytics per-fleet pulls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PullRequest:
    """Inputs required to run one Fleetlytics pull for a single fleet."""

    fleet_internal_id: str
    retailer_location_id: int | None
    date_range_start: date | datetime
    date_range_end: date | datetime
    output_root: Path
    run_timestamp: str


@dataclass(slots=True)
class PullResult:
    """Mutable per-fleet pull outcome."""

    fleet_internal_id: str
    run_dir: Path
    status: str = "error"
    fleet_ok: bool = False
    drivers_ok: bool = False
    driver_scores_ok: bool = False
    trip_scores_ok: bool = False
    trip_locations_ok: bool = False
    trip_incidents_ok: bool = False
    driver_count: int = 0
    driver_score_count: int = 0
    trip_score_count: int = 0
    trip_location_count: int = 0
    trip_incident_count: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)


if __name__ == "__main__":  # pragma: no cover - smoke example only
    sample_request = PullRequest(
        fleet_internal_id="demo-fleet",
        retailer_location_id=None,
        date_range_start=date(2026, 6, 1),
        date_range_end=date(2026, 6, 2),
        output_root=Path("/tmp/fleetlytics-output"),
        run_timestamp="2026-06-15_120000_UTC",
    )
    sample_result = PullResult(
        fleet_internal_id="demo-fleet",
        run_dir=Path("/tmp/fleetlytics-output/demo-fleet/2026-06-15_120000_UTC"),
    )
    print(sample_request)
    print(sample_result)
