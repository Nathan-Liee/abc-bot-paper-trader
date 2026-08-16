"""Configuration for the AI Decision Engine.

Exact approved model IDs (selection gate 2026-08-17) — shorthand labels are
NOT accepted by the endpoint; these full route IDs are implementation values.
All credentials come from the environment; never store secrets in code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://10.197.141.202:20128/v1"

# Exact approved model configuration (benchmark-report.md §20, verified via
# GET /v1/models on 2026-08-17). Do not use shorthand like
# `cf/llama-3.1-8b-fp8-fast` — the endpoint only resolves full route IDs.
PRIMARY_MODEL = "cf/@cf/meta/llama-3.1-8b-instruct-fp8-fast"
SECONDARY_MODEL = "groq/llama-3.3-70b-versatile"
FALLBACK_MODEL = "cf/@cf/qwen/qwen2.5-coder-32b-instruct"

# Benchmark spec v1.0.0 §5: request timeout 60 s. The <2 s figure is a
# latency evaluation criterion, NOT the request timeout — do not change
# timeout policy without a separate design task.
DEFAULT_TIMEOUT_S = 60.0

# Per-level bounded retry budget. One retry per level keeps failure handling
# deterministic and prevents retry storms. HTTP 429 sleeps before retrying
# (mirrors benchmark runner behavior: spec §5 sleep 10 s, but engine keeps
# max_attempts=2 — bounded).
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_429_SLEEP_S = 10.0

DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.0


@dataclass(frozen=True)
class ModelConfig:
    """One model level in the deterministic fallback chain."""

    model_id: str
    provider: str

    @classmethod
    def of(cls, model_id: str) -> ModelConfig:
        provider = model_id.split("/", 1)[0] if "/" in model_id else "unknown"
        return cls(model_id=model_id, provider=provider)


@dataclass(frozen=True)
class EngineConfig:
    """Engine-wide configuration. No secrets here."""

    primary: ModelConfig
    secondary: ModelConfig
    fallback: ModelConfig
    base_url: str
    timeout_s: float
    max_attempts: int
    retry_429_sleep_s: float
    max_tokens: int
    temperature: float

    @property
    def chain(self) -> tuple[ModelConfig, ...]:
        return (self.primary, self.secondary, self.fallback)


@dataclass(frozen=True)
class Secrets:
    """Credential container — never logged, never stored, never committed."""

    api_key: str


def default_config() -> EngineConfig:
    return EngineConfig(
        primary=ModelConfig.of(PRIMARY_MODEL),
        secondary=ModelConfig.of(SECONDARY_MODEL),
        fallback=ModelConfig.of(FALLBACK_MODEL),
        base_url=os.environ.get("ABC_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        timeout_s=float(os.environ.get("ABC_AI_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))),
        max_attempts=int(os.environ.get("ABC_AI_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS))),
        retry_429_sleep_s=float(
            os.environ.get("ABC_AI_RETRY_429_SLEEP_S", str(DEFAULT_RETRY_429_SLEEP_S))
        ),
        max_tokens=int(os.environ.get("ABC_AI_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))),
        temperature=float(os.environ.get("ABC_AI_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
    )


def load_secrets() -> Secrets:
    """Load the Bearer API key from the environment. Never accepted from args."""
    key = os.environ.get("ABC_AI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ABC_AI_API_KEY must be set (use .env / environment, never code)")
    return Secrets(api_key=key)


def load_config() -> tuple[EngineConfig, Secrets]:
    """Convenience: build config + secrets from the environment."""
    return default_config(), load_secrets()
