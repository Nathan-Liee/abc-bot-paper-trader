"""Structural validation of plan/command dictionaries (fail-closed tags)."""

from __future__ import annotations

import pytest

from execution.models import ExecutionCommand, TradePlan
from execution.validation import (
    is_expired,
    remaining_seconds,
    validate_command_dict,
    validate_plan_dict,
)
from tests.execution.factories import make_command, make_plan, ts_in


def _plan_dict(**overrides: object) -> dict[str, object]:
    data = make_plan().to_dict()
    data.update(overrides)
    return data


def _command_dict(**overrides: object) -> dict[str, object]:
    data = make_command().to_dict()
    data.update(overrides)
    return data


class TestPlanDict:
    def test_valid_plan_dict_passes(self) -> None:
        assert validate_plan_dict(_plan_dict()) == []

    def test_missing_required_field_tagged(self) -> None:
        data = _plan_dict()
        del data["risk_evaluation_id"]
        errors = validate_plan_dict(data)
        assert "plan.missing_field:risk_evaluation_id" in errors

    def test_all_missing_fields_tagged(self) -> None:
        errors = validate_plan_dict({"direction": "BUY"})
        assert "plan.missing_field:risk_evaluation_id" in errors
        assert "plan.missing_field:generated_at" in errors
        assert "plan.missing_field:expires_at" in errors

    def test_unknown_field_tagged(self) -> None:
        errors = validate_plan_dict(_plan_dict(take_profit=4600.0))
        assert "plan.unknown_field:take_profit" in errors

    def test_forbidden_execution_field_tagged(self) -> None:
        errors = validate_plan_dict(_plan_dict(confidence=0.9, reason="x", take_profit=4600.0))
        assert "plan.unknown_field:confidence" in errors
        assert "plan.unknown_field:reason" in errors
        assert "plan.unknown_field:take_profit" in errors

    def test_from_dict_round_trip_still_valid(self) -> None:
        plan = TradePlan.from_dict(_plan_dict())
        assert plan.validate() == []


class TestCommandDict:
    def test_valid_command_dict_passes(self) -> None:
        assert validate_command_dict(_command_dict()) == []

    def test_missing_required_field_tagged(self) -> None:
        data = _command_dict()
        del data["command_id"]
        errors = validate_command_dict(data)
        assert "command.missing_field:command_id" in errors

    def test_unknown_field_tagged(self) -> None:
        errors = validate_command_dict(_command_dict(order_type="LIMIT"))
        assert "command.unknown_field:order_type" in errors

    def test_forbidden_fields_never_accepted(self) -> None:
        data = _command_dict(tp=4600.0, confidence=0.9, lot=0.5, margin=10.0)
        errors = validate_command_dict(data)
        assert "command.forbidden_field:tp" in errors
        assert "command.forbidden_field:confidence" in errors
        assert "command.forbidden_field:lot" in errors
        assert "command.forbidden_field:margin" in errors

    def test_invalid_command_id_uuid_tagged(self) -> None:
        errors = validate_command_dict(_command_dict(command_id="not-uuid"))
        assert "command.command_id:invalid_uuid" in errors

    def test_non_market_entry_type_rejected_before_construction(self) -> None:
        errors = validate_command_dict(_command_dict(entry_type="LIMIT"))
        assert "command.unknown_field:entry_type" not in errors  # valid key...
        # ...but the enum conversion would raise; constructors are MARKET-only
        with pytest.raises(ValueError):
            ExecutionCommand.from_dict(_command_dict(entry_type="LIMIT"))


class TestExpiry:
    def test_unparseable_timestamp_is_expired(self) -> None:
        assert is_expired("garbage") is True
        assert remaining_seconds("garbage") == float("-inf")

    def test_future_timestamp_not_expired(self) -> None:
        assert is_expired(ts_in(60.0)) is False
        assert remaining_seconds(ts_in(60.0)) > 0

    def test_past_timestamp_expired(self) -> None:
        assert is_expired(ts_in(-60.0)) is True
        assert remaining_seconds(ts_in(-60.0)) < 0

    def test_plan_and_command_share_expiry_semantics(self) -> None:
        from execution.validation import is_expired_command, is_expired_plan

        assert is_expired_plan(make_plan(ttl_seconds=-60.0)) is True
        assert is_expired_plan(make_plan(ttl_seconds=60.0)) is False
        assert is_expired_command(make_command(expires_at=ts_in(-1.0))) is True
        assert is_expired_command(make_command(expires_at=ts_in(60.0))) is False
