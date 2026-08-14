"""Safety-default validation for the bootstrap configuration foundation.

These are the only tests that exist at bootstrap time: they validate
configuration foundation and import structure, not business logic (none
exists yet).
"""

from __future__ import annotations

import pytest

from collector.settings import (
    COLLECTOR_MODE,
    DEMO_EXECUTION_ALLOWED,
    LIVE_TRADING_ENABLED,
    PROJECT_ROOT,
    READ_ONLY_MODE,
    SUPPORTED_MODES,
    Settings,
    load_settings,
)

_ENV_VARS = (
    "ABC_BOT_ENV",
    "ABC_BOT_MODE",
    "ABC_BOT_READ_ONLY_MODE",
    "ABC_BOT_LIVE_TRADING_ENABLED",
    "ABC_BOT_DEMO_EXECUTION_ALLOWED",
    "ABC_BOT_DATA_DIR",
    "ABC_BOT_SQLITE_DIR",
    "ABC_BOT_EVENTS_DIR",
    "ABC_BOT_ANALYTICS_DIR",
    "ABC_BOT_JSONL_SOURCE",
    "ABC_BOT_INGESTION_POLL_SECONDS",
    "ABC_BOT_LOG_LEVEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_live_trading_is_forbidden() -> None:
    assert LIVE_TRADING_ENABLED is False


def test_read_only_mode_is_mandatory() -> None:
    assert READ_ONLY_MODE is True


def test_demo_execution_is_forbidden() -> None:
    assert DEMO_EXECUTION_ALLOWED is False


def test_default_mode_is_paper_data_only() -> None:
    assert COLLECTOR_MODE == "PAPER_DATA_ONLY"
    assert SUPPORTED_MODES == ("PAPER_DATA_ONLY",)


def test_default_settings_are_safe() -> None:
    settings = load_settings()
    assert settings.mode == "PAPER_DATA_ONLY"
    assert settings.read_only_mode is True
    assert settings.live_trading_enabled is False
    assert settings.demo_execution_allowed is False
    assert settings.env == "development"


def test_settings_reject_unsafe_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABC_BOT_LIVE_TRADING_ENABLED", "true")
    with pytest.raises(ValueError, match="live trading is forbidden"):
        load_settings()
    monkeypatch.delenv("ABC_BOT_LIVE_TRADING_ENABLED")

    monkeypatch.setenv("ABC_BOT_DEMO_EXECUTION_ALLOWED", "true")
    with pytest.raises(ValueError, match="demo execution is forbidden"):
        load_settings()
    monkeypatch.delenv("ABC_BOT_DEMO_EXECUTION_ALLOWED")

    monkeypatch.setenv("ABC_BOT_READ_ONLY_MODE", "false")
    with pytest.raises(ValueError, match="read-only mode cannot be disabled"):
        load_settings()


def test_settings_reject_unsupported_env_and_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABC_BOT_ENV", "staging")
    with pytest.raises(ValueError, match="unsupported environment"):
        load_settings()

    monkeypatch.setenv("ABC_BOT_ENV", "development")
    monkeypatch.setenv("ABC_BOT_MODE", "PAPER_EXECUTION")
    with pytest.raises(ValueError, match="unsupported collector mode"):
        load_settings()


def test_default_paths_are_project_relative() -> None:
    settings = load_settings()
    assert settings.data_dir == PROJECT_ROOT / "data"
    assert settings.sqlite_dir == PROJECT_ROOT / "data" / "sqlite"
    assert settings.events_dir == PROJECT_ROOT / "data" / "events"
    assert settings.analytics_dir == PROJECT_ROOT / "data" / "analytics"


def test_non_execution_env_overrides_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ABC_BOT_ENV", "test")
    monkeypatch.setenv("ABC_BOT_DATA_DIR", "data")
    monkeypatch.setenv("ABC_BOT_SQLITE_DIR", "data/sqlite-custom")
    monkeypatch.setenv("ABC_BOT_LOG_LEVEL", "debug")

    settings = load_settings()
    assert settings.env == "test"
    assert settings.sqlite_dir == PROJECT_ROOT / "data" / "sqlite-custom"
    assert settings.log_level == "DEBUG"


def test_safety_policy_rejects_unsafe_construction() -> None:
    with pytest.raises(ValueError, match="live trading is forbidden"):
        Settings(live_trading_enabled=True)  # type: ignore[arg-type]


def test_safety_policy_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    settings = load_settings()
    with pytest.raises(FrozenInstanceError):
        settings.live_trading_enabled = True  # type: ignore[misc]
