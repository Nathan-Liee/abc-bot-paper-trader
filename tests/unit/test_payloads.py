"""Payload validation tests: presence, types, enums, conditionals, ranges."""

from __future__ import annotations

import pytest

from collector.event_model import ContractValidationError, validate_payload
from shared.contracts.types import EventType
from tests.unit.event_factories import (
    ai_response_payload,
    net_profit_positive_payload,
    reconciliation_payload,
    risk_gate_payload,
    tick_payload,
)


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        (EventType.TICK_RECEIVED, tick_payload()),
        (EventType.AI_RESPONSE, ai_response_payload()),
        (EventType.RISK_GATE, risk_gate_payload()),
        (EventType.RECONCILIATION, reconciliation_payload()),
        (EventType.NET_PROFIT_POSITIVE, net_profit_positive_payload()),
    ],
)
def test_valid_payloads_are_accepted(event_type: EventType, payload: dict[str, object]) -> None:
    validate_payload(event_type, payload)


def test_missing_required_field_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="missing required field"):
        validate_payload(EventType.TICK_RECEIVED, {"symbol": "XAUUSD"})


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="unknown field"):
        validate_payload(EventType.TICK_RECEIVED, tick_payload(bogus=1))


def test_unknown_extension_dict_is_accepted() -> None:
    validate_payload(EventType.TICK_RECEIVED, tick_payload(_unknown={"vendor": "x"}))


def test_unknown_extension_must_be_a_dict() -> None:
    with pytest.raises(ContractValidationError, match="_unknown must be a dict"):
        validate_payload(EventType.TICK_RECEIVED, tick_payload(_unknown="nope"))


def test_invalid_type_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="bid must be of type number"):
        validate_payload(EventType.TICK_RECEIVED, tick_payload(bid="2000"))


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ContractValidationError, match="decision must be one of"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(decision="HOLD"))


def test_float_is_a_valid_number() -> None:
    validate_payload(EventType.TICK_RECEIVED, tick_payload(bid=2000.0))


def test_bool_is_not_a_number() -> None:
    with pytest.raises(ContractValidationError, match="bid must be of type number"):
        validate_payload(EventType.TICK_RECEIVED, tick_payload(bid=True))


def test_const_value_is_enforced() -> None:
    from tests.unit.event_factories import position_opened_payload

    validate_payload(EventType.POSITION_OPENED, position_opened_payload())
    with pytest.raises(ContractValidationError, match="state must be 'OPEN'"):
        validate_payload(EventType.POSITION_OPENED, position_opened_payload(state="CLOSED"))


def test_ai_response_error_required_when_invalid() -> None:
    with pytest.raises(ContractValidationError, match="error is required when valid == False"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(valid=False))


def test_ai_response_error_forbidden_when_valid() -> None:
    with pytest.raises(ContractValidationError, match="error must not be present"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(error="boom"))


def test_ai_response_error_accepted_when_invalid() -> None:
    validate_payload(
        EventType.AI_RESPONSE,
        ai_response_payload(valid=False, decision="NO-TRADE", confidence=0.1, error="model down"),
    )


def test_risk_gate_rejection_reason_required_on_reject() -> None:
    with pytest.raises(ContractValidationError, match="rejection_reason is required"):
        validate_payload(EventType.RISK_GATE, risk_gate_payload(gate_result="REJECT"))


def test_risk_gate_rejection_reason_forbidden_on_allow() -> None:
    with pytest.raises(ContractValidationError, match="rejection_reason must not be present"):
        validate_payload(EventType.RISK_GATE, risk_gate_payload(rejection_reason="too risky"))


def test_risk_gate_reject_with_reason_is_valid() -> None:
    validate_payload(
        EventType.RISK_GATE,
        risk_gate_payload(gate_result="REJECT", final_lot=0.0, rejection_reason="budget exhausted"),
    )


def test_reconciliation_details_forbidden_when_synced() -> None:
    with pytest.raises(ContractValidationError, match="mismatch_details must not be present"):
        validate_payload(
            EventType.RECONCILIATION, reconciliation_payload(mismatch_details={"a": 1})
        )


def test_reconciliation_details_allowed_on_mismatch() -> None:
    validate_payload(
        EventType.RECONCILIATION,
        reconciliation_payload(
            mismatch=True,
            result="ESCALATED",
            action="ESCALATE",
            mismatch_details={"positions": "unresolvable"},
        ),
    )


def test_net_profit_positive_must_be_strictly_positive() -> None:
    with pytest.raises(ContractValidationError, match="must be greater than 0"):
        validate_payload(
            EventType.NET_PROFIT_POSITIVE, net_profit_positive_payload(running_net_pnl_usd=0.0)
        )
    with pytest.raises(ContractValidationError, match="must be greater than 0"):
        validate_payload(
            EventType.NET_PROFIT_POSITIVE, net_profit_positive_payload(running_net_pnl_usd=-5.0)
        )


def test_ai_response_confidence_range() -> None:
    with pytest.raises(ContractValidationError, match="confidence must be at least 0"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(confidence=-0.1))
    with pytest.raises(ContractValidationError, match="confidence must be at most 1"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(confidence=1.5))


def test_ai_response_latency_non_negative() -> None:
    with pytest.raises(ContractValidationError, match="latency_ms must be at least 0"):
        validate_payload(EventType.AI_RESPONSE, ai_response_payload(latency_ms=-1.0))


def test_tick_optional_fields_accepted() -> None:
    validate_payload(
        EventType.TICK_RECEIVED,
        tick_payload(tick_volume=5, tick_id="tick-abc"),
    )
