"""Retry classification and backoff for background jobs (Issue #18).

Pure and deterministic: no clock, no randomness, no I/O. The queue engine
(`auto_scoring.jobs.queue`) is the only caller that actually waits; this
module just computes "should this be retried" and "how long to wait" so both
can be unit-tested without asyncio.

Design decisions: docs/job-queue.md "retry対象の分類".
"""

from __future__ import annotations

from dataclasses import dataclass

from auto_scoring.domain.models import RETRYABLE_ERROR_CATEGORIES, ErrorCategory


def is_retryable(category: ErrorCategory) -> bool:
    """Whether ``category`` is one of timeout/429/5xx (Issue #18 acceptance:
    "retry対象をtimeout、429、5xxに限定する")."""
    return category in RETRYABLE_ERROR_CATEGORIES


@dataclass(frozen=True, kw_only=True)
class RetryPolicy:
    """Exponential backoff with a cap and a bound on attempts.

    ``max_attempts`` mirrors `auto_scoring.domain.models.Job.max_attempts` --
    the caller is expected to pass the same value used when the job was
    created, not a second, independent limit.
    """

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be >= 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("RetryPolicy.initial_backoff_seconds must be >= 0")
        if self.backoff_multiplier < 1:
            raise ValueError("RetryPolicy.backoff_multiplier must be >= 1")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("RetryPolicy.max_backoff_seconds must be >= initial_backoff_seconds")

    def should_retry(self, *, category: ErrorCategory, attempts: int) -> bool:
        """Whether a job that has made ``attempts`` attempts (including the
        one that just failed with ``category``) should be retried again."""
        return is_retryable(category) and attempts < self.max_attempts

    def delay_seconds(self, attempt: int) -> float:
        """Backoff before the ``attempt``-th retry (1-based: the delay before
        trying again after the 1st failure is ``delay_seconds(1)``).

        Exponential, capped at ``max_backoff_seconds``. No jitter -- the
        queue's tests rely on this being exactly reproducible.
        """
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)
