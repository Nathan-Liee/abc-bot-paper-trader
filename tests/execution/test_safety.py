"""Static safety audit of the execution package.

The execution layer must stay a paper/validation layer: no MT5 calls, no
network, no secrets travel here. These tests scan source text directly
so the guarantee holds even if a dependency chain changes.
"""

from __future__ import annotations

import re
from pathlib import Path

EXECUTION_ROOT = Path(__file__).resolve().parents[2] / "execution"

# Every forbidden token (case-insensitive) must NEVER appear in execution/.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "MetaTrader5",
    "mt5.",
    "order_send",
    "OrderSend",
    "order_modify",
    "OrderModify",
    "position_modify",
    "PositionModify",
    "tradecopy",
    "TradeCopy",
    "import socket",
    "http://",
    "https://",
    "requests.",
    "import urllib",
    "password",
    "api_key",
    "secret",
)


def _source_files() -> list[Path]:
    return sorted(EXECUTION_ROOT.glob("*.py")) + sorted(EXECUTION_ROOT.glob("**/*.py"))


def test_no_broker_or_network_primitives_in_execution_sources() -> None:
    offenders: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_TOKENS:
            if token.lower() in text:
                offenders.append(f"{path.name}:{token}")
    assert offenders == [], f"forbidden tokens found: {offenders}"


def test_no_credential_like_strings() -> None:
    pattern = re.compile(r"(?:password|token|key|secret)\s*[=:]", re.IGNORECASE)
    offenders: list[str] = []
    for path in _source_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            # journal/test code legitimately says 'key'; exclude dict literals
            if pattern.search(line) and "asdict" not in line:
                offenders.append(f"{path.name}:{lineno}:{line.strip()}")
    assert offenders == [], f"credential-like assignments found: {offenders}"


def test_no_secrets_artifacts_in_package_tree() -> None:
    forbidden_names = {".env", ".env.*", "*.pem", "*.key", "credentials*", "secrets*"}
    found: list[str] = []
    for path in EXECUTION_ROOT.rglob("*"):
        if path.is_file() and any(path.match(pattern) for pattern in forbidden_names):
            found.append(str(path))
    assert found == [], f"secret-bearing files inside execution/: {found}"


def test_command_contract_carries_no_tp_field() -> None:
    text = (EXECUTION_ROOT / "models.py").read_text(encoding="utf-8")
    assert re.search(r"take_profit|tp\s*[:=]", text) is None


def test_simulated_executor_confirmed_offline() -> None:
    text = (EXECUTION_ROOT / "simulated.py").read_text(encoding="utf-8")
    for token in ("import MetaTrader5", "from MetaTrader5", "order_send", "PositionModify("):
        assert token not in text
    assert "socket" not in text
