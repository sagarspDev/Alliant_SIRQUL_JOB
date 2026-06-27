"""Configuration loading and validation for Fleetlytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Final, Optional
from uuid import UUID

from dotenv import load_dotenv

DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class DateRange:
    """Inclusive UTC date range used for pulls."""

    start: datetime
    end: datetime

    def to_formatted_strings(self) -> tuple[str, str]:
        """Return the range in the canonical API/log format."""

        return format_datetime(self.start), format_datetime(self.end)


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated Fleetlytics application settings."""

    fleet_api_base_url: str
    fleet_api_app_key: str
    fleet_api_auth_token: str
    fleet_network_uid: str
    reporting_api_base_url: str
    reporting_api_app_key: str
    reporting_api_rest_key: str
    target_retailer_location_id: str
    date_range: DateRange
    output_dir: Path
    log_level: str
    log_dir: Path
    http_timeout_seconds: float
    http_retry_count: int
    http_backoff_factor: float
    run_log_max_bytes: int
    run_log_backup_count: int
    reporting_account_id: str = ""


def load_config(env_path: str | Path | None = None) -> AppConfig:
    """Load, validate, and normalize Fleetlytics settings.

    Args:
        env_path: Optional path to a `.env` file. When omitted, the current
            working directory is used.

    Returns:
        A validated configuration object.

    Raises:
        ConfigError: If required variables are missing or malformed.
    """

    _load_env_file(env_path)

    fleet_api_base_url = _required("FLEET_API_BASE_URL")
    fleet_api_app_key = _required("FLEET_API_APP_KEY")
    fleet_api_auth_token = _required("FLEET_API_AUTH_TOKEN")
    fleet_network_uid = _required("FLEET_NETWORK_UID")

    reporting_api_base_url = _required("REPORTING_API_BASE_URL")
    reporting_api_app_key = _required("REPORTING_API_APP_KEY")
    reporting_api_rest_key = _required("REPORTING_API_REST_KEY")
    reporting_account_id = _optional("REPORTING_ACCOUNT_ID")

    target_retailer_location_id = _required("TARGET_RETAILER_LOCATION_ID")

    date_range = _resolve_date_range(
        os.getenv("DATE_RANGE_START"),
        os.getenv("DATE_RANGE_END"),
    )

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    _validate_log_level(log_level)
    http_timeout_seconds = _resolve_float_env("HTTP_TIMEOUT_SECONDS", default=30.0, minimum=0.001)
    http_retry_count = _resolve_int_env("HTTP_RETRY_COUNT", default=3, minimum=0)
    http_backoff_factor = _resolve_float_env("HTTP_BACKOFF_FACTOR", default=0.5, minimum=0.0)
    run_log_max_bytes = _resolve_int_env("RUN_LOG_MAX_BYTES", default=5 * 1024 * 1024, minimum=1024)
    run_log_backup_count = _resolve_int_env("RUN_LOG_BACKUP_COUNT", default=3, minimum=1)

    return AppConfig(
        fleet_api_base_url=fleet_api_base_url,
        fleet_api_app_key=fleet_api_app_key,
        fleet_api_auth_token=fleet_api_auth_token,
        fleet_network_uid=fleet_network_uid,
        reporting_api_base_url=reporting_api_base_url,
        reporting_api_app_key=reporting_api_app_key,
        reporting_api_rest_key=reporting_api_rest_key,
        reporting_account_id=reporting_account_id,
        target_retailer_location_id=target_retailer_location_id,
        date_range=date_range,
        output_dir=output_dir,
        log_level=log_level,
        log_dir=log_dir,
        http_timeout_seconds=http_timeout_seconds,
        http_retry_count=http_retry_count,
        http_backoff_factor=http_backoff_factor,
        run_log_max_bytes=run_log_max_bytes,
        run_log_backup_count=run_log_backup_count,
    )


def load_pull_runtime_config(env_path: str | Path | None = None) -> AppConfig:
    """Load shared pull runtime config without requiring one-shot fleet selection."""

    _load_env_file(env_path)

    fleet_api_base_url = _required("FLEET_API_BASE_URL")
    fleet_api_app_key = _required("FLEET_API_APP_KEY")
    fleet_api_auth_token = _required("FLEET_API_AUTH_TOKEN")
    fleet_network_uid = _required("FLEET_NETWORK_UID")

    reporting_api_base_url = _required("REPORTING_API_BASE_URL")
    reporting_api_app_key = _required("REPORTING_API_APP_KEY")
    reporting_api_rest_key = _required("REPORTING_API_REST_KEY")
    reporting_account_id = _optional("REPORTING_ACCOUNT_ID")

    target_retailer_location_id = os.getenv("TARGET_RETAILER_LOCATION_ID", "").strip() or "daily-run"
    date_range = _resolve_date_range(
        os.getenv("DATE_RANGE_START"),
        os.getenv("DATE_RANGE_END"),
    )

    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    _validate_log_level(log_level)
    http_timeout_seconds = _resolve_float_env("HTTP_TIMEOUT_SECONDS", default=30.0, minimum=0.001)
    http_retry_count = _resolve_int_env("HTTP_RETRY_COUNT", default=3, minimum=0)
    http_backoff_factor = _resolve_float_env("HTTP_BACKOFF_FACTOR", default=0.5, minimum=0.0)
    run_log_max_bytes = _resolve_int_env("RUN_LOG_MAX_BYTES", default=5 * 1024 * 1024, minimum=1024)
    run_log_backup_count = _resolve_int_env("RUN_LOG_BACKUP_COUNT", default=3, minimum=1)

    return AppConfig(
        fleet_api_base_url=fleet_api_base_url,
        fleet_api_app_key=fleet_api_app_key,
        fleet_api_auth_token=fleet_api_auth_token,
        fleet_network_uid=fleet_network_uid,
        reporting_api_base_url=reporting_api_base_url,
        reporting_api_app_key=reporting_api_app_key,
        reporting_api_rest_key=reporting_api_rest_key,
        reporting_account_id=reporting_account_id,
        target_retailer_location_id=target_retailer_location_id,
        date_range=date_range,
        output_dir=output_dir,
        log_level=log_level,
        log_dir=log_dir,
        http_timeout_seconds=http_timeout_seconds,
        http_retry_count=http_retry_count,
        http_backoff_factor=http_backoff_factor,
        run_log_max_bytes=run_log_max_bytes,
        run_log_backup_count=run_log_backup_count,
    )


def format_datetime(value: datetime) -> str:
    """Format a UTC datetime for API usage and file naming."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime(DATE_FORMAT)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str:
    return os.getenv(name, "").strip()


def _load_env_file(env_path: str | Path | None = None) -> None:
    """Load the project ``.env`` file without overriding existing values."""

    resolved_env_path = (
        Path(env_path)
        if env_path is not None
        else Path(__file__).resolve().parent.parent / ".env"
    )
    load_dotenv(dotenv_path=resolved_env_path, override=False)


def _resolve_date_range(start_raw: Optional[str], end_raw: Optional[str]) -> DateRange:
    start = _parse_optional_datetime(start_raw)
    end = _parse_optional_datetime(end_raw)

    if start and end:
        resolved = DateRange(start=_ensure_utc(start), end=_ensure_utc(end))
    elif start or end:
        raise ConfigError(
            "DATE_RANGE_START and DATE_RANGE_END must either both be set or both be blank."
        )
    else:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        resolved = DateRange(start=start, end=end)

    if resolved.end < resolved.start:
        raise ConfigError("DATE_RANGE_END must be greater than or equal to DATE_RANGE_START.")

    if resolved.end - resolved.start > timedelta(days=45):
        from .logger import get_logger

        get_logger(__name__).warning(
            "Configured date range exceeds 45 days: %s -> %s",
            format_datetime(resolved.start),
            format_datetime(resolved.end),
        )

    return resolved


def _parse_optional_datetime(raw_value: Optional[str]) -> Optional[datetime]:
    if raw_value is None:
        return None

    value = raw_value.split("#", 1)[0].strip()
    if not value:
        return None

    try:
        parsed = datetime.strptime(value, DATE_FORMAT)
    except ValueError as exc:
        raise ConfigError(
            f"Invalid datetime value '{raw_value}'. Expected format: {DATE_FORMAT}"
        ) from exc
    return parsed.replace(tzinfo=timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _validate_log_level(level: str) -> None:
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ConfigError(
            "LOG_LEVEL must be one of DEBUG, INFO, WARNING, or ERROR."
        )


def _resolve_int_env(name: str, *, default: int, minimum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def _resolve_float_env(name: str, *, default: float, minimum: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}.")
    return value


def get_latest_run_dir(retailer_location_id: str | int) -> Path:
    """Return the latest run directory for a retailer location."""

    _load_env_file()
    output_root = Path(os.getenv("OUTPUT_DIR", "output"))
    from Fleetlytics.converters.paths import latest_run_dir

    try:
        return latest_run_dir(str(retailer_location_id), output_root)
    except FileNotFoundError as exc:
        raise ConfigError(str(exc)) from exc


def get_company_id() -> UUID:
    """Return the configured company UUID."""

    _load_env_file()
    raw_value = _required("TARGET_COMPANY_ID")
    try:
        return UUID(raw_value)
    except ValueError as exc:
        raise ConfigError("TARGET_COMPANY_ID must be a valid UUID.") from exc


def get_db_url() -> str:
    """Return the configured Supabase Postgres connection URL."""

    _load_env_file()
    return _required("SUPABASE_DB_URL")


def get_db_schema() -> str:
    """Return the configured Supabase schema name."""

    _load_env_file()
    schema = os.getenv("SUPABASE_SCHEMA", "public").strip() or "public"
    if not schema.replace("_", "").isalnum():
        raise ConfigError("SUPABASE_SCHEMA must be a valid SQL identifier.")
    return schema
