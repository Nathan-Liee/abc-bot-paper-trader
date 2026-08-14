"""Application settings and hard-coded safety defaults.

This module belongs to the configuration foundation. It deliberately
contains NO trading logic, AI, risk, or execution behaviour.

Safety model
------------
The safety flags below are hard-coded constants. They are read from the
environment only to *detect and refuse* unsafe configuration; they can
never be enabled:

* ``LIVE_TRADING_ENABLED``   -> always ``False`` (live trading is forbidden)
* ``READ_ONLY_MODE``         -> always ``True``  (cannot be disabled)
* ``DEMO_EXECUTION_ALLOWED`` -> always ``False`` (no order submission)
* ``COLLECTOR_MODE``         -> always ``"PAPER_DATA_ONLY"``

Only non-execution values (environment name, storage paths, log level)
may be overridden through ``ABC_BOT_*`` environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_NAME = "abc-bot-paper-trader"

SUPPORTED_ENVS = ("development", "test", "production")
SUPPORTED_MODES = ("PAPER_DATA_ONLY",)
SUPPORTED_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# ---------------------------------------------------------------------------
# Hard-coded safety defaults (not configurable, by design).
# ---------------------------------------------------------------------------

LIVE_TRADING_ENABLED = False
READ_ONLY_MODE = True
DEMO_EXECUTION_ALLOWED = False
COLLECTOR_MODE = "PAPER_DATA_ONLY"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Safety fields can never be enabled."""

    env: str = "development"
    mode: str = COLLECTOR_MODE
    read_only_mode: bool = READ_ONLY_MODE
    live_trading_enabled: bool = LIVE_TRADING_ENABLED
    demo_execution_allowed: bool = DEMO_EXECUTION_ALLOWED
    data_dir: Path = PROJECT_ROOT / "data"
    sqlite_dir: Path = PROJECT_ROOT / "data" / "sqlite"
    events_dir: Path = PROJECT_ROOT / "data" / "events"
    analytics_dir: Path = PROJECT_ROOT / "data" / "analytics"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.env not in SUPPORTED_ENVS:
            raise ValueError(
                f"unsupported environment {self.env!r}; must be one of {SUPPORTED_ENVS}"
            )
        if self.mode not in SUPPORTED_MODES:
            raise ValueError(
                f"unsupported collector mode {self.mode!r}; only {SUPPORTED_MODES} is supported"
            )
        if self.live_trading_enabled:
            raise ValueError("live trading is forbidden in abc-bot-paper-trader")
        if not self.read_only_mode:
            raise ValueError("read-only mode cannot be disabled")
        if self.demo_execution_allowed:
            raise ValueError("demo execution is forbidden in abc-bot-paper-trader")
        if self.log_level not in SUPPORTED_LOG_LEVELS:
            raise ValueError(
                f"unsupported log level {self.log_level!r}; must be one of {SUPPORTED_LOG_LEVELS}"
            )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_settings() -> Settings:
    """Load settings from ``ABC_BOT_*`` environment variables.

    Safety fields are read only to verify they are not requested; any
    request to enable live trading or execution is refused by
    :meth:`Settings.__post_init__`.
    """

    return Settings(
        env=os.getenv("ABC_BOT_ENV", "development"),
        mode=os.getenv("ABC_BOT_MODE", COLLECTOR_MODE),
        read_only_mode=_as_bool(os.getenv("ABC_BOT_READ_ONLY_MODE", "true")),
        live_trading_enabled=_as_bool(os.getenv("ABC_BOT_LIVE_TRADING_ENABLED", "false")),
        demo_execution_allowed=_as_bool(os.getenv("ABC_BOT_DEMO_EXECUTION_ALLOWED", "false")),
        data_dir=_as_path(os.getenv("ABC_BOT_DATA_DIR", "data")),
        sqlite_dir=_as_path(os.getenv("ABC_BOT_SQLITE_DIR", "data/sqlite")),
        events_dir=_as_path(os.getenv("ABC_BOT_EVENTS_DIR", "data/events")),
        analytics_dir=_as_path(os.getenv("ABC_BOT_ANALYTICS_DIR", "data/analytics")),
        log_level=os.getenv("ABC_BOT_LOG_LEVEL", "INFO").upper(),
    )
