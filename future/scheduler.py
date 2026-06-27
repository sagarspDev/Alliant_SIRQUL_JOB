"""DEFERRED - not part of the active daily pipeline. See FLEETLYTICS_CONTEXT.md Phase E."""

# Future daily scheduler sketch
#
# A scheduled job (cron, Windows Task Scheduler, or equivalent) would invoke
# ``main.py`` once per day after the one-time pull flow is expanded into a
# recurring run mode.
#
# Proposed invocation pattern:
# - load environment from ``.env``
# - execute ``python -m Fleetlytics.main`` or ``python main.py`` from the
#   Fleetlytics project root
# - capture stdout/stderr in the same log directory used by the pipeline
#
# No executable scheduling logic is defined here yet.
