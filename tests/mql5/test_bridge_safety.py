"""Static read-only safety verification for the MQL5 bridge.

Fails if any execution-capable token appears in the bridge source tree,
or if the platform-mandated OnTradeTransaction parameter types are used
anywhere other than the handler declaration itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from collector.settings import PROJECT_ROOT

BRIDGE_SRC = PROJECT_ROOT / "mql5-bridge" / "src"
SRC_PATTERNS = ("*.mq5", "*.mqh")

# Execution-capable APIs / structs. Presence anywhere = build failure.
# EXCEPTION: MqlTradeRequest / MqlTradeResult are the platform-mandated
# parameter types of the OnTradeTransaction *observer* signature; they
# are checked separately and allowed only on that declaration line.
FORBIDDEN_TOKENS = (
    "OrderSend",
    "OrderSendAsync",
    "OrderModify",
    "OrderDelete",
    "OrderClose",
    "OrderCloseAll",
    "PositionClose",
    "PositionModify",
    "OrderCalcProfit",
    "OrderCalcMargin",
    "OrderCheck",
    "TradeAction",
    "TradeDeal",
    "TradePosition",
    "TradeOrder",
    "CTrade",
    "CAccountStopout",
)

# Allowed only on the OnTradeTransaction declaration line.
HANDLER_ONLY_TOKENS = ("MqlTradeRequest", "MqlTradeResult")

# Read-only APIs that must be present (observability, not execution).
REQUIRED_TOKENS = (
    "SymbolInfoTick",
    "OnTradeTransaction",
    "OnTick",
    "OnTimer",
    "OnDeinit",
    "FileWriteString",
    "FileFlush",
    "SymbolInfoDouble",
    "HistoryDealSelect",
    "HistoryOrderSelect",
    "PositionSelectByTicket",
    "OrderGetTicket",
    "TerminalInfoInteger",
)

# OnTradeTransaction is the platform-mandated trade *transaction*
# observer: its signature references the read-only transaction/request/
# result structs, but the handler must never dereference request/result.
HANDLER_DECLARATION = re.compile(r"OnTradeTransaction\s*\(")


def _source_files() -> list[Path]:
    return sorted(path for pattern in SRC_PATTERNS for path in BRIDGE_SRC.rglob(pattern))


def _all_source_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _source_files())


def test_bridge_source_files_exist() -> None:
    names = {path.name for path in _source_files()}
    required = {
        "Bridge.mq5",
        "Config.mqh",
        "JsonExporter.mqh",
        "EventBuilder.mqh",
        "HealthMonitor.mqh",
    }
    assert required <= names


def test_no_execution_capable_token_in_source() -> None:
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            assert re.search(rf"\b{re.escape(token)}\b", text) is None, (
                f"execution token {token!r} found in {path}"
            )


def test_handler_params_never_dereferenced() -> None:
    text = Path(BRIDGE_SRC / "Bridge.mq5").read_text(encoding="utf-8")
    assert "request." not in text, "OnTradeTransaction request param must never be dereferenced"
    assert "result." not in text, "OnTradeTransaction result param must never be dereferenced"


def test_handler_structs_confined_to_declaration() -> None:
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for token in HANDLER_ONLY_TOKENS:
            occurrences = [m.start() for m in re.finditer(re.escape(token), text)]
            for position in occurrences:
                inside_declaration = _inside_handler_declaration(text, position)
                assert inside_declaration, (
                    f"{token} outside the OnTradeTransaction declaration in {path}"
                )


def _inside_handler_declaration(text: str, position: int) -> bool:
    """True if *position* lies between the handler signature start and its
    closing parenthesis (the signature spans several lines)."""
    before = text[:position]
    match = HANDLER_DECLARATION.search(before)
    if match is None:
        return False
    depth = 0
    for index in range(match.end(), len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index > position
    return False


def test_required_read_only_tokens_present() -> None:
    text = _all_source_text()
    for token in REQUIRED_TOKENS:
        assert token in text, f"required read-only token {token!r} missing from bridge source"


def test_symbol_configured_once() -> None:
    config = Path(BRIDGE_SRC / "Config.mqh").read_text(encoding="utf-8")
    assert "InpSymbol" in config
    assert '"XAUUSDc"' in config
    for path in _source_files():
        if path.name != "Config.mqh":
            assert "XAUUSDc" not in path.read_text(encoding="utf-8"), (
                f"symbol hard-coded outside Config.mqh in {path}"
            )


def test_output_path_is_configurable() -> None:
    config = Path(BRIDGE_SRC / "Config.mqh").read_text(encoding="utf-8")
    assert "InpEventFile" in config
    assert "mql5_bridge_events.jsonl" in config
