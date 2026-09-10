"""Retry classification and backoff for background jobs (Issue #18, #153).

Pure and deterministic: no clock, no randomness, no I/O. The queue engine
(`auto_scoring.jobs.queue`) is the only caller that actually waits; this
module just computes "should this be retried" and "how long to wait" so both
can be unit-tested without asyncio. Anything that needs a random jitter value
or the current wall-clock time (parsing an HTTP-date ``Retry-After``, drawing
a jitter fraction) is computed outside this module and passed in as a plain
number -- see ``rate_limited_delay_seconds``'s ``jitter`` parameter and
`auto_scoring.jobs.queue.JobQueueService`'s injected random source.

Design decisions: docs/job-queue.md "retry対象の分類", Issue #153 "決めること".
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
    """Exponential backoff with a cap and a bound on attempts -- except for
    `ErrorCategory.RATE_LIMITED`, which Issue #153 deliberately bounds by
    elapsed wait time instead (see ``should_retry``/``rate_limited_delay_seconds``
    below). ``max_attempts`` mirrors
    `auto_scoring.domain.models.Job.max_attempts` -- the caller is expected to
    pass the same value used when the job was created, not a second,
    independent limit -- and only governs TIMEOUT/SERVER_ERROR now.

    A real run hit 429 twice and exhausted all 3 attempts within 5 seconds
    (the old 1s/2s schedule below), handing the question to a human even
    though a later manual retry succeeded immediately: the provider's
    congestion had nothing to do with how many times this process asked, and
    three quick attempts at the same congestion window just re-hit it three
    times (docs/job-queue.md; Issue #153). ``rate_limited_*`` fields are a
    separate, slower schedule (default: 5s initial, ×2, capped at 60s) used
    only for `ErrorCategory.RATE_LIMITED`, and ``rate_limited_budget_seconds``
    (default 120s) replaces ``max_attempts`` as the stopping condition for
    that category: keep retrying until the *nominal* (unjittered) cumulative
    wait would exceed the budget, not until a fixed attempt count is reached.
    """

    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0
    #: Separate exponential schedule for `ErrorCategory.RATE_LIMITED` only
    #: (Issue #153 decision: "待ち方…無ければ指数バックオフ（初期5秒・×2・
    #: 上限60秒・jitterあり）").
    rate_limited_initial_backoff_seconds: float = 5.0
    rate_limited_backoff_multiplier: float = 2.0
    rate_limited_max_backoff_seconds: float = 60.0
    #: Total nominal wait-time budget for `ErrorCategory.RATE_LIMITED` retries
    #: (Issue #153 decision: "回数ではなく経過時間で決める…既定120秒"). Once the
    #: cumulative *nominal* (unjittered) backoff already spent reaches this,
    #: no further retry is scheduled regardless of ``max_attempts``/``attempts``.
    rate_limited_budget_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be >= 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("RetryPolicy.initial_backoff_seconds must be >= 0")
        if self.backoff_multiplier < 1:
            raise ValueError("RetryPolicy.backoff_multiplier must be >= 1")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("RetryPolicy.max_backoff_seconds must be >= initial_backoff_seconds")
        if self.rate_limited_initial_backoff_seconds < 0:
            raise ValueError("RetryPolicy.rate_limited_initial_backoff_seconds must be >= 0")
        if self.rate_limited_backoff_multiplier < 1:
            raise ValueError("RetryPolicy.rate_limited_backoff_multiplier must be >= 1")
        if self.rate_limited_max_backoff_seconds < self.rate_limited_initial_backoff_seconds:
            raise ValueError(
                "RetryPolicy.rate_limited_max_backoff_seconds must be >= "
                "rate_limited_initial_backoff_seconds"
            )
        if self.rate_limited_budget_seconds <= 0:
            raise ValueError("RetryPolicy.rate_limited_budget_seconds must be > 0")

    def should_retry(
        self,
        *,
        category: ErrorCategory,
        attempts: int,
        retry_after_seconds: float | None = None,
    ) -> bool:
        """Whether a job that has made ``attempts`` attempts (including the
        one that just failed with ``category``) should be retried again.

        ``retry_after_seconds`` is only consulted for `ErrorCategory.
        RATE_LIMITED` (ignored otherwise): a provider-supplied ``Retry-After``
        that alone exceeds the whole wait-time budget is not worth waiting
        out -- give up now rather than sleeping past the budget in one shot
        (Issue #153 decision: "待ち時間の予算を超えるRetry-Afterが来たら、
        待たずに諦めて…人に回す").
        """
        if not is_retryable(category):
            return False
        if category is ErrorCategory.RATE_LIMITED:
            if (
                retry_after_seconds is not None
                and retry_after_seconds > self.rate_limited_budget_seconds
            ):
                return False
            return self._rate_limited_elapsed_before(attempts) < self.rate_limited_budget_seconds
        return attempts < self.max_attempts

    def delay_seconds(self, attempt: int) -> float:
        """Backoff before the ``attempt``-th retry (1-based: the delay before
        trying again after the 1st failure is ``delay_seconds(1)``).

        Exponential, capped at ``max_backoff_seconds``. No jitter -- the
        queue's tests rely on this being exactly reproducible. Used for
        TIMEOUT/SERVER_ERROR only; `ErrorCategory.RATE_LIMITED` uses
        ``rate_limited_delay_seconds`` instead (see ``delay_for``).
        """
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)

    def rate_limited_delay_seconds(
        self,
        attempt: int,
        *,
        retry_after_seconds: float | None = None,
        jitter: float = 0.0,
    ) -> float:
        """Backoff before the ``attempt``-th retry of a RATE_LIMITED failure.

        A non-``None`` ``retry_after_seconds`` (already parsed and sanity-
        checked outside this module -- see the module docstring) is always
        honoured exactly, with no jitter added: it is a provider-specified
        wait, not this process's own guess (Issue #153 decision: "Retry-After
        があれば必ず尊重する"). Otherwise this uses the exponential
        ``rate_limited_*`` schedule with "equal jitter"
        (https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/):
        half the nominal capped delay is fixed, and ``jitter`` (injected from
        outside, expected to be a fraction in ``[0.0, 1.0)`` drawn by the
        caller) scales the other half -- guaranteeing some real backoff even
        at ``jitter == 0.0`` while still decorrelating concurrent jobs hitting
        the same provider congestion.
        """
        if retry_after_seconds is not None:
            return retry_after_seconds
        if not 0.0 <= jitter < 1.0:
            raise ValueError("jitter must be within [0.0, 1.0)")
        base = self._rate_limited_backoff_base(attempt)
        half = base / 2.0
        return half + jitter * half

    def delay_for(
        self,
        *,
        category: ErrorCategory,
        attempt: int,
        retry_after_seconds: float | None = None,
        jitter: float = 0.0,
    ) -> float:
        """Dispatch to ``rate_limited_delay_seconds`` for RATE_LIMITED, or
        ``delay_seconds`` for everything else -- the single entry point
        `auto_scoring.jobs.queue.JobQueueService` uses so it never has to
        duplicate the category check itself.
        """
        if category is ErrorCategory.RATE_LIMITED:
            return self.rate_limited_delay_seconds(
                attempt, retry_after_seconds=retry_after_seconds, jitter=jitter
            )
        return self.delay_seconds(attempt)

    def _rate_limited_backoff_base(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        delay = self.rate_limited_initial_backoff_seconds * (
            self.rate_limited_backoff_multiplier ** (attempt - 1)
        )
        return min(delay, self.rate_limited_max_backoff_seconds)

    def _rate_limited_elapsed_before(self, attempts: int) -> float:
        """Nominal (unjittered) cumulative RATE_LIMITED backoff already spent
        before the ``attempts``-th attempt -- i.e. the sum of the delays
        before retries ``1``..``attempts - 1``. Deliberately ignores jitter
        and any actually-honoured ``Retry-After`` value: the budget is an
        upper bound on how long this process is willing to keep a job's
        worth of retries queued, computed the same way regardless of how
        lucky or unlucky the actual jittered waits turned out to be (and
        strictly less than or equal to what real waits could have been,
        since jitter only ever adds to, never subtracts from, half the
        nominal delay) -- see ``rate_limited_delay_seconds``.
        """
        return sum(self._rate_limited_backoff_base(k) for k in range(1, attempts))
