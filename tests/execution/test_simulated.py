"""Deterministic simulated broker: every required scenario (task §10)."""

from __future__ import annotations

import pytest

from execution.models import CommandState, ResultStatus
from execution.retry import ErrorCode
from execution.simulated import SimulatedExecutor, SimulatorScenario, SubmitMode
from tests.execution.factories import make_command


@pytest.fixture
def executor() -> SimulatedExecutor:
    return SimulatedExecutor()


class TestSubmitScenarios:
    def test_full_fill(self, executor: SimulatedExecutor) -> None:
        command = make_command(volume=0.10)
        result = executor.submit(command)
        assert result.status is ResultStatus.FILLED
        assert result.filled_volume == 0.10
        assert result.fill_price == 4400.0
        assert result.sl_applied is True
        assert result.broker_request_id is not None
        position = executor.get_position(command)
        assert position is not None
        assert position.volume == 0.10
        assert position.sl == command.sl

    def test_partial_fill_cancels_remainder_at_broker(self, executor: SimulatedExecutor) -> None:
        command = make_command(volume=0.10)
        executor.set_scenario(
            command.command_id, SimulatorScenario(mode=SubmitMode.PARTIAL_FILL, fill_ratio=0.6)
        )
        result = executor.submit(command)
        assert result.status is ResultStatus.PARTIALLY_FILLED
        assert result.filled_volume == 0.06
        position = executor.get_position(command)
        assert position is not None
        assert position.volume == 0.06

    def test_full_fill_with_slippage(self, executor: SimulatedExecutor) -> None:
        command = make_command(direction="BUY")
        executor.set_scenario(
            command.command_id,
            SimulatorScenario(mode=SubmitMode.FULL_FILL, slippage_points=12.0),
        )
        result = executor.submit(command)
        assert result.fill_price == 4400.0 + 0.12  # 12 points * 0.01

    def test_sell_fill_prices_off_bid(self, executor: SimulatedExecutor) -> None:
        command = make_command(direction="SELL")
        executor.set_scenario(
            command.command_id,
            SimulatorScenario(mode=SubmitMode.FULL_FILL, slippage_points=5.0),
        )
        result = executor.submit(command)
        assert result.fill_price == 4400.0 - 0.05

    def test_reject(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(
            command.command_id,
            SimulatorScenario(mode=SubmitMode.REJECT, retcode=10016),
        )
        result = executor.submit(command)
        assert result.status is ResultStatus.REJECTED
        assert result.error_code == ErrorCode.BROKER_REJECT.value
        assert result.broker_retcode == 10016

    def test_requote(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.REQUOTE))
        result = executor.submit(command)
        assert result.status is ResultStatus.REJECTED
        assert result.error_code == ErrorCode.REQUOTE_SLIPPAGE.value

    def test_timeout_not_landed_leaves_no_evidence(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.TIMEOUT))
        result = executor.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert result.error_code == ErrorCode.NETWORK_TIMEOUT.value
        outcome = executor.query(command)
        assert outcome.discovered_state is None  # nothing at the broker
        assert outcome.ambiguous is False

    def test_timeout_landed_is_recoverable(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(
            command.command_id,
            SimulatorScenario(mode=SubmitMode.TIMEOUT, timeout_landed=True),
        )
        result = executor.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        outcome = executor.query(command)
        assert outcome.discovered_state is CommandState.FILLED
        assert outcome.evidence["position_sl"] == command.sl

    def test_ambiguous_stays_inconclusive(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.AMBIGUOUS))
        result = executor.submit(command)
        assert result.status is ResultStatus.UNKNOWN
        assert result.error_code == ErrorCode.AMBIGUOUS_RESPONSE.value
        outcome = executor.query(command)
        assert outcome.ambiguous is True

    def test_expired_refused_by_broker(self, executor: SimulatedExecutor) -> None:
        command = make_command(expires_at="2020-01-01T00:00:00+00:00")
        result = executor.submit(command)
        assert result.status is ResultStatus.EXPIRED

    def test_stale_feed_and_position_exists_codes(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.set_scenario(command.command_id, SimulatorScenario(mode=SubmitMode.STALE_FEED))
        assert executor.submit(command).error_code == ErrorCode.STALE_FEED.value
        second = make_command()
        executor.set_scenario(second.command_id, SimulatorScenario(mode=SubmitMode.POSITION_EXISTS))
        assert executor.submit(second).error_code == ErrorCode.POSITION_EXISTS.value

    def test_broker_side_duplicate_rejection(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        first = executor.submit(command)
        assert first.status is ResultStatus.FILLED
        duplicate = executor.submit(command)
        assert duplicate.status is ResultStatus.REJECTED
        assert duplicate.error_code == ErrorCode.DUPLICATE_COMMAND.value

    def test_query_unknown_command_finds_nothing(self, executor: SimulatedExecutor) -> None:
        outcome = executor.query(make_command())
        assert outcome.discovered_state is None
        assert outcome.evidence["found"] is False


class TestProtectiveActions:
    def test_attach_sl_success(self, executor: SimulatedExecutor) -> None:
        command = make_command(sl=4399.25)
        executor.submit(command)
        result = executor.attach_sl(command, executor.get_position(command).position_id, 4399.25)
        assert result.sl_applied is True
        assert executor.get_position(command).sl == 4399.25

    def test_attach_sl_failure_mode(self, executor: SimulatedExecutor) -> None:
        executor.set_sl_attach_fail(True)
        command = make_command()
        executor.submit(command)
        result = executor.attach_sl(command, executor.get_position(command).position_id, command.sl)
        assert result.status is ResultStatus.FAILED
        assert result.error_code == ErrorCode.SL_ATTACH_FAILED.value

    def test_sl_is_not_attached_when_attach_fails_at_fill(
        self, executor: SimulatedExecutor
    ) -> None:
        executor.set_sl_attach_fail(True)
        command = make_command()
        result = executor.submit(command)
        assert result.status is ResultStatus.FILLED
        assert result.sl_applied is False
        assert executor.get_position(command).sl is None

    def test_close_success(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.submit(command)
        position_id = executor.get_position(command).position_id
        result = executor.close_position(command, position_id)
        assert result.status is ResultStatus.CLOSED
        outcome = executor.query(command)
        assert outcome.discovered_state is CommandState.CLOSED

    def test_close_failure_mode(self, executor: SimulatedExecutor) -> None:
        executor.set_close_fail(True)
        command = make_command()
        executor.submit(command)
        result = executor.close_position(command, executor.get_position(command).position_id)
        assert result.status is ResultStatus.FAILED
        assert result.error_code == ErrorCode.CLOSE_FAILED.value

    def test_close_after_close_is_failure(self, executor: SimulatedExecutor) -> None:
        command = make_command()
        executor.submit(command)
        position_id = executor.get_position(command).position_id
        assert executor.close_position(command, position_id).status is ResultStatus.CLOSED
        assert executor.close_position(command, position_id).status is ResultStatus.FAILED


class TestScenarioGranularity:
    def test_scenario_is_per_command(self, executor: SimulatedExecutor) -> None:
        happy = make_command()
        reject = make_command()
        other = make_command()
        executor.set_scenario(reject.command_id, SimulatorScenario(mode=SubmitMode.REJECT))
        assert executor.submit(happy).status is ResultStatus.FILLED
        assert executor.submit(reject).status is ResultStatus.REJECTED
        assert executor.submit(other).status is ResultStatus.FILLED  # default unaffected
