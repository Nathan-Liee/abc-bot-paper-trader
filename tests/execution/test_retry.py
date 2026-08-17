"""Error classification matrix and retry policy budgets."""

from __future__ import annotations

import pytest

from execution.retry import (
    RETRY_MATRIX,
    ErrorCode,
    RetryClass,
    RetryPolicy,
    classify_error,
)


class TestClassificationMatrix:
    def test_every_error_code_classified_exactly_once(self) -> None:
        codes = {member for member in ErrorCode}
        assert set(RETRY_MATRIX) == codes
        assert len(RETRY_MATRIX) == len(codes)
        classes = list(RETRY_MATRIX.values())
        for cls in classes:
            assert cls in RetryClass

    def test_network_timeout_is_safe(self) -> None:
        assert classify_error(ErrorCode.NETWORK_TIMEOUT.value) is RetryClass.SAFE

    def test_close_failed_is_safe(self) -> None:
        assert classify_error(ErrorCode.CLOSE_FAILED.value) is RetryClass.SAFE

    def test_ambiguous_response_requires_reconciliation(self) -> None:
        assert classify_error(ErrorCode.AMBIGUOUS_RESPONSE.value) is RetryClass.RECONCILE
        assert classify_error(ErrorCode.RECONCILIATION_PENDING.value) is RetryClass.RECONCILE

    def test_requote_and_broker_reject_are_permanent_no_blind_retry(self) -> None:
        assert classify_error(ErrorCode.REQUOTE_SLIPPAGE.value) is RetryClass.PERMANENT
        assert classify_error(ErrorCode.BROKER_REJECT.value) is RetryClass.PERMANENT
        assert classify_error(ErrorCode.STALE_FEED.value) is RetryClass.PERMANENT
        assert classify_error(ErrorCode.INSUFFICIENT_MARGIN.value) is RetryClass.PERMANENT

    def test_duplicate_is_idempotent_replay(self) -> None:
        assert classify_error(ErrorCode.DUPLICATE_COMMAND.value) is RetryClass.IDEMPOTENT

    def test_sl_attach_failure_is_emergency(self) -> None:
        assert classify_error(ErrorCode.SL_ATTACH_FAILED.value) is RetryClass.EMERGENCY

    def test_failed_is_unsafe(self) -> None:
        assert classify_error(ErrorCode.FAILED.value) is RetryClass.UNSAFE

    def test_unknown_code_fails_closed_to_reconcile(self) -> None:
        assert classify_error("SOME_FUTURE_CODE") is RetryClass.RECONCILE
        assert classify_error(None) is RetryClass.RECONCILE
        assert classify_error("") is RetryClass.RECONCILE


class TestRetryPolicy:
    def test_defaults_match_owner_budgets(self) -> None:
        policy = RetryPolicy()
        assert policy.close_retries == 2
        assert policy.sl_attach_retries == 2
        assert policy.submit_retries == 2

    def test_valid_policy_passes(self) -> None:
        assert RetryPolicy().validate() == []

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"close_retries": -1},
            {"sl_attach_retries": -1},
            {"submit_retries": -1},
            {"close_retries": True},  # bool is not an int budget
            {"submit_retries": 2.5},  # non-integer
        ],
    )
    def test_invalid_budgets_rejected(self, kwargs: dict[str, object]) -> None:
        policy = RetryPolicy(**kwargs)  # type: ignore[arg-type]
        assert policy.validate() != []
