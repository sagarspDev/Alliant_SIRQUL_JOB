#!/usr/bin/env bash
# Cron-safe wrapper. Loads an env file, activates the venv, and runs the cron entrypoint.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

ENV_FILE="${1:-.env}"

exec "${PROJECT_ROOT}/scripts/run_fleetlytics.sh" \
  --env-file "${ENV_FILE}" \
  -- python -m Fleetlytics.pipeline.cron --lock-wait-seconds 0
