"""Queue configuration (Issue #18).

A plain dataclass, not `pydantic-settings` -- matching the existing
``create_app(..., max_concurrent_uploads: int = 2, ...)`` convention
(`auto_scoring.api.app`) rather than adding a new settings framework for one
more numeric knob. See docs/job-queue.md "並列度・retry設定".
"""

from __future__ import annotations

from dataclasses import dataclass

from auto_scoring.domain.retry_policy import RetryPolicy


@dataclass(frozen=True, kw_only=True)
class QueueSettings:
    #: Upper bound on concurrently-RUNNING jobs, shared across every
    #: submission and every question (Issue #18 acceptance: "設定した並列数
    #: を超えず"). technology-stack.md §3.4 / business-rules-and-evaluation-
    #: data.md §3 (E): the project owner decided 4 (Issue #81), raising the
    #: provisional 2 this shipped with. It stays a *setting*, not a constant
    #: -- the adopted providers' own rate limits are still unmeasured
    #: (§3.1 E), so 4 is a default to operate from, not a proven ceiling;
    #: backoff and requeue remain required regardless.
    max_concurrency: int = 4
    #: Default `auto_scoring.domain.models.Job.max_attempts` for jobs this
    #: package creates. Governs TIMEOUT/SERVER_ERROR retries only --
    #: RATE_LIMITED is bounded by ``rate_limited_budget_seconds`` instead
    #: (Issue #153; see `auto_scoring.domain.retry_policy.RetryPolicy`).
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0
    #: Separate, slower schedule for `ErrorCategory.RATE_LIMITED` (Issue
    #: #153 decision: a provider rejecting a call for being over quota is not
    #: the same kind of failure as a timeout or a 5xx, and retrying it on the
    #: same 1s/2s schedule just re-hits the same congestion window).
    rate_limited_initial_backoff_seconds: float = 5.0
    rate_limited_backoff_multiplier: float = 2.0
    rate_limited_max_backoff_seconds: float = 60.0
    #: Total nominal wait-time budget for RATE_LIMITED retries (Issue #153
    #: decision: "回数ではなく経過時間で決める…既定120秒"). Replaces
    #: ``max_attempts`` as the stopping condition for that one category.
    rate_limited_budget_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("QueueSettings.max_concurrency must be >= 1")
        # Reuses RetryPolicy's own validation instead of duplicating it here,
        # and fails at construction time instead of at the first job's
        # failure inside `JobQueueService._retry_policy_for` -- a bad value
        # (negative backoff, multiplier < 1, max below initial) used to pass
        # QueueSettings() silently and only raise later, after a RUNNING row
        # was already committed, leaving that job stuck until a restart
        # (Issue #18 review round 2, P2).
        _ = self.retry_policy

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.max_attempts,
            initial_backoff_seconds=self.initial_backoff_seconds,
            backoff_multiplier=self.backoff_multiplier,
            max_backoff_seconds=self.max_backoff_seconds,
            rate_limited_initial_backoff_seconds=self.rate_limited_initial_backoff_seconds,
            rate_limited_backoff_multiplier=self.rate_limited_backoff_multiplier,
            rate_limited_max_backoff_seconds=self.rate_limited_max_backoff_seconds,
            rate_limited_budget_seconds=self.rate_limited_budget_seconds,
        )
