"""Validate Fleet and Reporting API connectivity with lightweight requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fleet_api import FleetAPIClient
from reporting_api import ReportingAPIClient, _build_report_form_data
from src.config import ConfigError, load_pull_runtime_config
from src.http_client import FleetlyticsAPIError, build_http_client


def main() -> int:
    try:
        config = load_pull_runtime_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    fleet_client = FleetAPIClient(
        config=config,
        http_client=build_http_client(base_url=config.fleet_api_base_url, config=config),
    )
    reporting_client = ReportingAPIClient(
        config=config,
        http_client=build_http_client(base_url=config.reporting_api_base_url, config=config),
    )

    fleet_payload = fleet_client.http_client.post_json(
        "/fleets/search",
        headers=fleet_client._auth_headers(),
        params={"limit": 1},
        json_body={},
    )
    fleet_rows = _extract_list_size(fleet_payload)

    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(hours=1)
    reporting_payload = reporting_client.http_client.post_multipart(
        "/api/3.18/report/run",
        headers=reporting_client._auth_headers(),
        form_data=_build_report_form_data(
            query="GL_REPORT_DATA",
            app_key=config.reporting_api_app_key,
            parameters={
                "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": end.strftime("%Y-%m-%d %H:%M:%S"),
            },
            account_id=None,
            offset=0,
            limit=1,
        ),
    )

    if not isinstance(reporting_payload, dict):
        raise FleetlyticsAPIError("Unexpected reporting response shape during connectivity check.")
    if reporting_payload.get("valid") is False:
        raise FleetlyticsAPIError(str(reporting_payload.get("message") or "Reporting API marked response invalid"))

    print("API connectivity OK")
    print(
        json.dumps(
            {
                "fleet_search_items_seen": fleet_rows,
                "reporting_valid": reporting_payload.get("valid", True),
                "reporting_rows_returned": len(reporting_payload.get("rows", reporting_payload.get("items", []))),
                "window_start_utc": start.isoformat(),
                "window_end_utc": end.isoformat(),
            },
            indent=2,
        )
    )
    return 0


def _extract_list_size(payload: object) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        item = payload.get("item")
        if isinstance(item, list):
            return len(item)
    raise FleetlyticsAPIError("Unexpected fleet search response shape during connectivity check.")


if __name__ == "__main__":
    raise SystemExit(main())
