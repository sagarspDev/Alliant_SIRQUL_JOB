# Risk Assessment

## Operational risks

- Invalid or incomplete env files will stop the pipeline before execution.
- Shared log, output, lock, or health paths between environments can cause collisions.
- Cron overlap or long-running jobs can delay later schedules if lock contention is ignored.

## External dependency risks

- Sirqul API availability, latency, and rate limiting are outside local control.
- PostgreSQL availability and privileges directly affect conversion/import phases.
- DNS, firewall, proxy, or TLS issues can break production runs even when code is unchanged.

## Data risks

- Large date windows can create heavy API payloads and longer import times.
- Historical backfills can reprocess significant data volume if windows are not chosen carefully.
- Discovery depends on `companies.focus_data->'eventInfo'->>'flAccountId'` mappings being present; fleets without a matching company are skipped.

## Mitigations in this repository

- Env-based configuration with templates
- Cron lock file to prevent overlap
- Health summary JSON for monitoring
- API and DB connectivity validation scripts
- Separate production, UAT, and test env-file templates
