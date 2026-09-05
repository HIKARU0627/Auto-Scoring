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
    #: data.md §3 (E): default 2, final value pending PoC 2's load test.
    max_concurrency: int = 2
    #: Default `auto_scoring.domain.models.Job.max_attempts` for jobs this
    #: package creates.
    max_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("QueueSettings.max_concurrency must be >= 1")

    @property
    def retry_policy(self) -> RetryPolicy:
        return RetryPolicy(
            max_attempts=self.max_attempts,
            initial_backoff_seconds=self.initial_backoff_seconds,
            backoff_multiplier=self.backoff_multiplier,
            max_backoff_seconds=self.max_backoff_seconds,
        )
