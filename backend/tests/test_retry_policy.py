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
        {"rate_limited_initial_backoff_seconds": -1.0},
        {"rate_limited_backoff_multiplier": 0.5},
        {"rate_limited_max_backoff_seconds": 0.1, "rate_limited_initial_backoff_seconds": 1.0},
        {"rate_limited_budget_seconds": 0.0},
        {"rate_limited_budget_seconds": -1.0},
    ],
)
def test_retry_policy_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Issue #153: RATE_LIMITED gets its own schedule and a time budget, not
# max_attempts -- a real run exhausted all 3 attempts (1s + 2s legacy
# backoff) within 5 seconds while the provider was still congested, then a
# later manual retry succeeded immediately. Waiting longer would have
# worked; retrying faster does not help against congestion.
# --------------------------------------------------------------------------- #
def test_rate_limited_ignores_max_attempts() -> None:
    """A RATE_LIMITED failure keeps retrying well past ``max_attempts`` as
    long as the (nominal, unjittered) cumulative wait budget is not yet
    spent -- this is the whole point of decoupling it from attempt count."""
    policy = RetryPolicy(max_attempts=1, rate_limited_budget_seconds=1000.0)
    assert policy.should_retry(category=ErrorCategory.RATE_LIMITED, attempts=5) is True


def test_rate_limited_stops_once_the_nominal_wait_budget_is_spent() -> None:
    # rate_limited_delay bases: 5, 10, 20, 40, 60(capped from 80), 60, ...
    # cumulative before attempts=5 is 5+10+20+40=75 (< 120): still retry.
    # cumulative before attempts=6 is 75+60=135 (>= 120): give up.
    policy = RetryPolicy(
        rate_limited_initial_backoff_seconds=5.0,
        rate_limited_backoff_multiplier=2.0,
        rate_limited_max_backoff_seconds=60.0,
        rate_limited_budget_seconds=120.0,
    )
    assert policy.should_retry(category=ErrorCategory.RATE_LIMITED, attempts=5) is True
    assert policy.should_retry(category=ErrorCategory.RATE_LIMITED, attempts=6) is False


def test_rate_limited_still_stops_being_retryable_when_permanent() -> None:
    policy = RetryPolicy(rate_limited_budget_seconds=1000.0)
    assert policy.should_retry(category=ErrorCategory.PERMANENT, attempts=1) is False


def test_rate_limited_delay_uses_its_own_schedule_not_the_default_one() -> None:
    policy = RetryPolicy(
        initial_backoff_seconds=1.0,
        backoff_multiplier=2.0,
        max_backoff_seconds=1000.0,
        rate_limited_initial_backoff_seconds=5.0,
        rate_limited_backoff_multiplier=2.0,
        rate_limited_max_backoff_seconds=1000.0,
    )
    # jitter=0.0 (the minimum of the "equal jitter" range) still yields half
    # of the nominal capped delay -- never the TIMEOUT/SERVER_ERROR schedule.
    assert policy.rate_limited_delay_seconds(1, jitter=0.0) == 2.5
    assert policy.rate_limited_delay_seconds(2, jitter=0.0) == 5.0
    # jitter=0.999... approaches (but never reaches) the full nominal delay.
    assert 4.99 < policy.rate_limited_delay_seconds(1, jitter=0.999) < 5.0


def test_rate_limited_delay_is_capped_before_jitter() -> None:
    policy = RetryPolicy(
        rate_limited_initial_backoff_seconds=10.0,
        rate_limited_backoff_multiplier=10.0,
        rate_limited_max_backoff_seconds=60.0,
    )
    # Nominal nth delay would be huge; capped at 60 first, so jitter only
    # ever spans [30, 60), never past the configured ceiling.
    assert policy.rate_limited_delay_seconds(5, jitter=0.0) == 30.0
    assert policy.rate_limited_delay_seconds(5, jitter=0.999) < 60.0


def test_rate_limited_delay_rejects_jitter_outside_unit_interval() -> None:
    policy = RetryPolicy()
    with pytest.raises(ValueError, match="jitter"):
        policy.rate_limited_delay_seconds(1, jitter=1.0)
    with pytest.raises(ValueError, match="jitter"):
        policy.rate_limited_delay_seconds(1, jitter=-0.01)


def test_rate_limited_delay_honours_retry_after_exactly_no_jitter() -> None:
    """Issue #153 decision: "Retry-After があれば必ず尊重する" -- honoured
    exactly, not scaled by jitter, since it is the provider's own number."""
    policy = RetryPolicy(rate_limited_initial_backoff_seconds=5.0)
    assert policy.rate_limited_delay_seconds(1, retry_after_seconds=30.0, jitter=0.999) == 30.0
    assert policy.rate_limited_delay_seconds(3, retry_after_seconds=0.5) == 0.5


def test_should_retry_gives_up_immediately_when_retry_after_exceeds_the_budget() -> None:
    """Issue #153 decision: a Retry-After bigger than the whole wait-time
    budget is not worth waiting out -- give up now instead of sleeping past
    the budget in a single wait."""
    policy = RetryPolicy(rate_limited_budget_seconds=120.0)
    assert (
        policy.should_retry(
            category=ErrorCategory.RATE_LIMITED, attempts=1, retry_after_seconds=121.0
        )
        is False
    )
    assert (
        policy.should_retry(
            category=ErrorCategory.RATE_LIMITED, attempts=1, retry_after_seconds=120.0
        )
        is True
    )


def test_delay_for_dispatches_on_category() -> None:
    policy = RetryPolicy(
        initial_backoff_seconds=1.0,
        backoff_multiplier=2.0,
        max_backoff_seconds=1000.0,
        rate_limited_initial_backoff_seconds=5.0,
        rate_limited_max_backoff_seconds=1000.0,
    )
    assert policy.delay_for(category=ErrorCategory.TIMEOUT, attempt=2) == 2.0
    assert policy.delay_for(category=ErrorCategory.SERVER_ERROR, attempt=2) == 2.0
    assert (
        policy.delay_for(
            category=ErrorCategory.RATE_LIMITED, attempt=2, retry_after_seconds=None, jitter=0.0
        )
        == 5.0
    )
    assert (
        policy.delay_for(
            category=ErrorCategory.RATE_LIMITED,
            attempt=2,
            retry_after_seconds=12.0,
            jitter=0.5,
        )
        == 12.0
    )
