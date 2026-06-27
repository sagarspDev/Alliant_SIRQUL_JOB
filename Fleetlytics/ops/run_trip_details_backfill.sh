#!/usr/bin/env bash
# Backfill wrapper for trip locations and trip incidents.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export DATE_RANGE_START="${DATE_RANGE_START:-2026-06-01 00:00:00}"
export DATE_RANGE_END="${DATE_RANGE_END:-$(date -u '+%Y-%m-%d 00:00:00')}"

python -m Fleetlytics.pipeline.cli backfill-trip-details
