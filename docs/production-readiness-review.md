# Production Readiness Review

## Must Have

- Pin and review dependencies before the first production tag.
- Store real secrets outside version control and restrict file permissions on env files.
- Use isolated output, log, lock, and health paths per environment.
- Validate API and database connectivity before enabling the scheduler.
- Monitor exit codes and `CRON_HEALTH_PATH`.
- Keep scheduler overlap protection enabled with `CRON_LOCK_PATH`.

## Should Have

- Move secrets to a vault or platform secret manager.
- Add alerting on failed cron runs, lock contention, and stale health files.
- Add structured log shipping into the platform logging stack.
- Add backup and retention policies for output artifacts and database targets.
- Add CI to run import smoke tests and CLI help checks on every change.

## Nice to Have

- Add packaged release artifacts or container images.
- Add metrics export and external health endpoints.
- Add automated dependency update monitoring.
- Add a dedicated runbook for incident response and historical backfills.

## Risks

- Real API rate limits and payload size behavior are still environment-dependent.
- DB write performance depends on target PostgreSQL sizing and indexing.
- The repo still contains historical local artifacts that should not be copied into a clean production checkout.
