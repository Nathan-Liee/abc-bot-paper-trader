"""Unit tests: deterministic validators for the AI Decision Engine."""

from __future__ import annotations

from ai_decision.validation import (
    FORBIDDEN_OUTPUT_KEYS,
    validate_authority_boundary,
    validate_confidence,
    validate_direction,
    validate_reason,
    validate_schema,
)

# direction ----------------------------------------------------------------


def test_validate_direction_valid() -> None:
    for token in ("BUY", "SELL", "NO-TRADE"):
        direction, err = validate_direction(token)
        assert direction == token
        assert err is None


def test_validate_direction_invalid() -> None:
    for token in ("HOLD", "BUY NOW", "LONG", "", None, 5):
        direction, err = validate_direction(token)
        assert direction is None
        assert err == "direction_invalid" or err == "direction_not_string"


def test_validate_direction_upper() -> None:
    direction, _err = validate_direction("buy")
    assert direction == "BUY"


# confidence ----------------------------------------------------------------


def test_validate_confidence_bounds() -> None:
    assert validate_confidence(0.0)[0] == 0.0
    assert validate_confidence(1.0)[0] == 1.0
    assert validate_confidence(0.5)[0] == 0.5
    assert validate_confidence(1)[0] == 1.0  # int accepted


def test_validate_confidence_rejects_invalid() -> None:
    for bad in (-0.1, 1.1, 2, float("nan"), float("inf"), True, "0.5", None):
        conf, err = validate_confidence(bad)
        assert conf is None
        assert err is not None


# reason -------------------------------------------------------------------


def test_validate_reason_string() -> None:
    assert validate_reason("momentum") == ("momentum", None)
    assert validate_reason("") == ("", None)


def test_validate_reason_rejects_non_string() -> None:
    for bad in (None, 5, ["list"], {"d": 1}):
        reason, err = validate_reason(bad)
        assert reason is None
        assert err == "reason_not_string"


def test_validate_reason_too_long() -> None:
    reason, err = validate_reason("x" * 2001)
    assert reason is None
    assert err == "reason_too_long"


# authority boundary ---------------------------------------------------------


def test_validate_authority_boundary_clean() -> None:
    assert validate_authority_boundary({"direction", "confidence", "reason"}) == []


def test_validate_authority_boundary_forbidden_keys() -> None:
    violations = validate_authority_boundary({"direction", "lot", "SL", "Take_Profit"})
    assert len(violations) == 1
    assert "lot" in violations[0]
    assert "sl" in violations[0]  # lowercased
    assert "take_profit" in violations[0]


def test_forbidden_keys_cover_authority_domain() -> None:
    assert {
        "lot",
        "risk",
        "sl",
        "tp",
        "exposure",
        "margin",
        "execution",
        "exit",
    } <= FORBIDDEN_OUTPUT_KEYS


# schema ---------------------------------------------------------------------


def test_validate_schema_valid() -> None:
    ok, errors, triple = validate_schema(
        {"direction": "BUY", "confidence": 0.8, "reason": "trend"},
        {"direction", "confidence", "reason"},
    )
    assert ok
    assert errors == []
    assert triple == ("BUY", 0.8, "trend")


def test_validate_schema_missing_confidence() -> None:
    ok, errors, _triple = validate_schema(
        {"direction": "BUY", "confidence": None, "reason": "trend"},
        {"direction", "confidence", "reason"},
    )
    assert not ok
    assert "confidence_not_number" in errors


def test_validate_schema_out_of_range_confidence() -> None:
    ok, _errors, _triple = validate_schema(
        {"direction": "BUY", "confidence": 1.2, "reason": "trend"},
        {"direction", "confidence", "reason"},
    )
    assert not ok


def test_validate_schema_missing_reason() -> None:
    ok, errors, _triple = validate_schema(
        {"direction": "BUY", "confidence": 0.8, "reason": None},
        {"direction", "confidence", "reason"},
    )
    assert not ok
    assert "reason_not_string" in errors


def test_validate_schema_invalid_direction() -> None:
    ok, errors, _triple = validate_schema(
        {"direction": "HOLD", "confidence": 0.8, "reason": "r"},
        {"direction", "confidence", "reason"},
    )
    assert not ok
    assert "direction_invalid" in errors


def test_validate_schema_forbidden_key() -> None:
    ok, errors, _triple = validate_schema(
        {"direction": "BUY", "confidence": 0.8, "reason": "r"},
        {"direction", "confidence", "reason", "lot", "position_size"},
    )
    assert not ok
    assert any("AUTHORITY_VIOLATION" in e for e in errors)
    assert "lot" in errors[0]
    assert "position_size" in errors[0]


def test_validate_schema_forbidden_reason_phrase() -> None:
    ok, errors, _triple = validate_schema(
        {"direction": "BUY", "confidence": 0.8, "reason": "buy stop loss near"},
        {"direction", "confidence", "reason"},
    )
    assert not ok
    assert any("forbidden_reason_phrase:stop loss" in e for e in errors)
