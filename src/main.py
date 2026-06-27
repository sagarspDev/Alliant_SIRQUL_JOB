"""DEFERRED - not part of the active daily pipeline. See FLEETLYTICS_CONTEXT.md Phase E."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from .config import load_config
from .logger import configure_logging, get_logger


def main() -> int:
    """Initialize config and logging.

    TODO (future): plug in the daily-run scheduler here once the one-time pull
    flow is complete and the scheduling requirement is approved.
    """

    load_dotenv(
        dotenv_path=Path(__file__).resolve().parent.parent / ".env",
        override=False,
    )
    configure_logging(
        os.getenv("LOG_DIR", "logs"),
        os.getenv("LOG_LEVEL", "INFO"),
    )
    config = load_config()
    logger = get_logger(__name__)
    logger.info("Fleetlytics foundation initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
