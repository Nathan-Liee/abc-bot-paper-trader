"""Execution contract models: TradePlan and ExecutionCommand invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from execution.models import (
    Direction,
    EntryType,
    ExecutionCommand,
    TradePlan,
)
from tests.execution.factories import make_command, make_plan


class TestTradePlan:
    def test_plan_is_immutable(self) -> None:
        plan = make_plan()
        with pytest.raises(FrozenInstanceError):
            plan.lot = 99.0  # type: ignore[misc]

    def test_valid_plan_has_no_failures(self) -> None:
        assert make_plan().validate() == []

    def test_lineage_ids_must_be_uuids(self) -> None:
        plan = make_plan(trade_id="not-a-uuid")  # type: ignore[arg-type]
        assert "plan.trade_id:invalid_uuid" in plan.validate()

    def test_risk_evaluation_id_is_required(self) -> None:
        plan = make_plan()
        assert plan.risk_evaluation_id
        assert plan.inference_id is not None  # lineage chain is wired

    def test_direction_must_be_buy_or_sell(self) -> None:
        plan = make_plan(direction="HOLD")
        assert "plan.direction:invalid:HOLD" in plan.validate()

    def test_non_positive_lot_rejected(self) -> None:
        assert "plan.lot:non_positive" in make_plan(lot=0.0).validate()
        assert "plan.lot:non_positive" in make_plan(lot=-0.01).validate()

    def test_sl_must_be_positive(self) -> None:
        assert "plan.sl:non_positive" in make_plan(sl=-1.0).validate()

    def test_expiry_must_follow_generation(self) -> None:
        plan = make_plan()
        plan = TradePlan(
            trade_id=plan.trade_id,
            correlation_id=plan.correlation_id,
            inference_id=plan.inference_id,
            risk_evaluation_id=plan.risk_evaluation_id,
            direction=plan.direction,
            lot=plan.lot,
            entry_reference=plan.entry_reference,
            sl=plan.sl,
            risk_amount=plan.risk_amount,
            risk_percent=plan.risk_percent,
            exposure=plan.exposure,
            symbol=plan.symbol,
            generated_at=plan.generated_at,
            expires_at=plan.generated_at,  # not strictly after
            policy_profile=plan.policy_profile,
        )
        assert "plan.expiry_not_after_generated" in plan.validate()

    def test_round_trip_via_dict(self) -> None:
        plan = make_plan()
        assert TradePlan.from_dict(plan.to_dict()) == plan


class TestExecutionCommand:
    def test_valid_command_has_no_failures(self) -> None:
        assert make_command().validate() == []

    def test_idempotency_key_is_command_id(self) -> None:
        command = make_command()
        assert command.idempotency_key == command.command_id

    def test_market_is_the_only_entry_type(self) -> None:
        assert [member.value for member in EntryType] == ["MARKET"]
        assert make_command().entry_type is EntryType.MARKET

    def test_invalid_command_id_rejected(self) -> None:
        command = make_command()
        command = ExecutionCommand(
            command_id="ORD-123",
            trade_id=command.trade_id,
            symbol=command.symbol,
            direction=command.direction,
            volume=command.volume,
            entry_type=command.entry_type,
            sl=command.sl,
            created_at=command.created_at,
            expires_at=command.expires_at,
        )
        assert "command.command_id:invalid_uuid" in command.validate()

    def test_invalid_direction_rejected(self) -> None:
        assert "command.direction:invalid:NO-TRADE" in make_command(direction="NO-TRADE").validate()

    def test_non_positive_volume_rejected(self) -> None:
        assert "command.volume:non_positive" in make_command(volume=0.0).validate()

    def test_expiry_must_follow_creation(self) -> None:
        command = make_command()
        command = ExecutionCommand(
            command_id=command.command_id,
            trade_id=command.trade_id,
            symbol=command.symbol,
            direction=command.direction,
            volume=command.volume,
            entry_type=command.entry_type,
            sl=command.sl,
            created_at=command.created_at,
            expires_at=command.created_at,
        )
        assert "command.expiry_not_after_created" in command.validate()

    def test_round_trip_via_dict(self) -> None:
        command = make_command()
        assert ExecutionCommand.from_dict(command.to_dict()) == command

    def test_no_risk_or_tp_fields_on_command(self) -> None:
        """Authority guard: execution commands carry no risk/TP/confidence."""
        field_names = {field.name for field in fields(ExecutionCommand)}
        for forbidden in ("tp", "take_profit", "confidence", "reason", "lot", "margin"):
            assert forbidden not in field_names


class TestDirectionContract:
    def test_buy_sell_only(self) -> None:
        assert {member.value for member in Direction} == {"BUY", "SELL"}
