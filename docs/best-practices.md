# Best Practices

- Keep all real credentials in non-versioned env files with restricted permissions.
- Use UTC for all schedules and explicit windows.
- Use the env-file launcher in production instead of relying on inherited shell state.
- Keep production, UAT, and test fully isolated at the path and credential level.
- Validate API and DB connectivity before enabling cron or systemd.
- Monitor the health file and daily logs after every scheduler change.
- Keep lock protection enabled to prevent overlapping runs.
- Prefer dry-run validation before changing schedules or environment files.
