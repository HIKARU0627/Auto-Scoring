"""Unit tests for `auto_scoring.domain.retry_policy` (Issue #18).

Pure and deterministic -- no clock, no asyncio.
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.models import ErrorCategory
from auto_scoring.domain.retry_policy import RetryPolicy, is_retryable


@pytest.mark.parametrize(
    "category",
    [ErrorCategory.TIMEOUT, ErrorCategory.RATE_LIMITED, ErrorCategory.SERVER_ERROR],
)
def test_timeout_429_and_5xx_are_retryable(category: ErrorCategory) -> None:
    assert is_retryable(category) is True


def test_permanent_is_not_retryable() -> None:
    assert is_retryable(ErrorCategory.PERMANENT) is False


def test_should_retry_stops_once_max_attempts_reached() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(category=ErrorCategory.TIMEOUT, attempts=2) is True
    assert policy.should_retry(category=ErrorCategory.TIMEOUT, attempts=3) is False


def test_should_retry_never_retries_a_permanent_failure_regardless_of_attempts() -> None:
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(category=ErrorCategory.PERMANENT, attempts=1) is False


def test_delay_seconds_grows_exponentially() -> None:
    policy = RetryPolicy(
        initial_backoff_seconds=1.0, backoff_multiplier=2.0, max_backoff_seconds=1000.0
    )
    assert policy.delay_seconds(1) == 1.0
    assert policy.delay_seconds(2) == 2.0
    assert policy.delay_seconds(3) == 4.0
    assert policy.delay_seconds(4) == 8.0


def test_delay_seconds_is_capped() -> None:
    policy = RetryPolicy(
        initial_backoff_seconds=1.0, backoff_multiplier=2.0, max_backoff_seconds=5.0
    )
    assert policy.delay_seconds(10) == 5.0


def test_delay_seconds_rejects_non_positive_attempt() -> None:
    policy = RetryPolicy()
    with pytest.raises(ValueError, match="attempt"):
        policy.delay_seconds(0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_attempts": 0},
        {"initial_backoff_seconds": -1.0},
        {"backoff_multiplier": 0.5},
        {"max_backoff_seconds": 0.1, "initial_backoff_seconds": 1.0},
    ],
)
def test_retry_policy_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)  # type: ignore[arg-type]
