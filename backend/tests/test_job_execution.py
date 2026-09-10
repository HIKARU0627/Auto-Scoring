"""Unit tests for `auto_scoring.domain.job_execution.ProcessingResult`'s
``retry_after_seconds`` invariant (Issue #153).
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory


def test_retry_after_seconds_defaults_to_none() -> None:
    result = ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True)
    assert result.retry_after_seconds is None


def test_retry_after_seconds_is_allowed_on_a_rate_limited_failure() -> None:
    result = ProcessingResult(
        outcome=ProcessingOutcome.FAILED,
        error_category=ErrorCategory.RATE_LIMITED,
        retry_after_seconds=30.0,
    )
    assert result.retry_after_seconds == 30.0


def test_retry_after_seconds_rejected_on_a_succeeded_result() -> None:
    with pytest.raises(ValueError, match="retry_after_seconds"):
        ProcessingResult(outcome=ProcessingOutcome.SUCCEEDED, usable=True, retry_after_seconds=30.0)


@pytest.mark.parametrize(
    "category", [ErrorCategory.TIMEOUT, ErrorCategory.SERVER_ERROR, ErrorCategory.PERMANENT]
)
def test_retry_after_seconds_rejected_on_a_non_rate_limited_failure(
    category: ErrorCategory,
) -> None:
    with pytest.raises(ValueError, match="retry_after_seconds"):
        ProcessingResult(
            outcome=ProcessingOutcome.FAILED, error_category=category, retry_after_seconds=30.0
        )
