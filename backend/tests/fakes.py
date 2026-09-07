"""Fakes for the parallel job queue's async tests (Issue #18).

Both make the queue's behaviour deterministic: `FakeClock.sleep` advances a
virtual clock instead of really waiting, and `FakeJobProcessor` returns
scripted results instead of calling a real OCR/AI provider.
"""

from __future__ import annotations

import asyncio
import itertools
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import Job


class FakeClock:
    """Deterministic clock: ``sleep`` advances virtual time instantly."""

    def __init__(self, start: datetime) -> None:
        self._now = start
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._now += timedelta(seconds=seconds)
        # Yield control once so other ready tasks in the event loop get a
        # turn, matching real asyncio.sleep's cooperative-scheduling effect
        # without actually waiting.
        await asyncio.sleep(0)

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


@dataclass(frozen=True, kw_only=True)
class ProcessingSpan:
    """When one job actually ran, as `FakeJobProcessor` observed it.

    ``started`` / ``finished`` are values of a single monotonically
    increasing event counter shared by every span the same processor
    records -- deliberately *not* wall-clock or `FakeClock` readings.
    Issue #50 (docs/job-queue.md "Linux環境で…決定的に失敗していた原因") is
    the record of what happens to a queue assertion that depends on real
    elapsed time: it becomes a race whose outcome is decided by how fast the
    event loop happens to run, and no timeout value fixes it. `FakeClock` is
    no help either -- its virtual time only moves when something sleeps, so
    two genuinely concurrent jobs would read the identical timestamp and
    could not be ordered at all. A counter ticked once per start and once per
    finish, from the single-threaded event loop, records exactly the ordering
    an assertion about dependency order and overlap needs, and records it
    deterministically.

    Every counter value is distinct, so two spans overlap (ran concurrently)
    exactly when `overlaps` says so.
    """

    job_id: str
    submission_id: str
    question_id: str | None
    started: int
    finished: int

    def overlaps(self, other: ProcessingSpan) -> bool:
        return self.started < other.finished and other.started < self.finished


def peak_overlap(spans: Sequence[ProcessingSpan]) -> int:
    """The largest number of ``spans`` that were ever in flight at once.

    Derived from the recorded spans themselves rather than read off
    `FakeJobProcessor.max_concurrency_seen`, so a test can check the
    concurrency cap without trusting the same counter the processor
    maintains for its own bookkeeping.
    """
    events = sorted([(span.started, 1) for span in spans] + [(span.finished, -1) for span in spans])
    peak = 0
    live = 0
    for _, delta in events:
        live += delta
        peak = max(peak, live)
    return peak


class FakeJobProcessor:
    """Scriptable `auto_scoring.domain.job_execution.JobProcessor`.

    ``script`` queues a sequence of results for one ``(submission_id,
    question_id)`` pair; each call to `process` for that pair pops the next
    scripted result, falling back to ``default`` once the script is
    exhausted. Tracks concurrency (``max_concurrency_seen``) and every job it
    was asked to process, for assertions.

    ``release_at_concurrency`` turns each call into a latch: a job entering
    `process` blocks until that many jobs are in flight at once, after which
    every job (then and later) runs straight through. It is how a test proves
    the queue really *did* run independent work in parallel rather than
    merely never exceeding the cap -- an assertion that concurrency stayed
    within the limit is equally true of a queue that ran everything one at a
    time, but such a queue can never open this latch. Must be at most
    `QueueSettings.max_concurrency`, and at least that many jobs must be
    simultaneously runnable, or it is never opened by the jobs themselves.

    A latch that is never opened gives up after ``latch_timeout_seconds``
    and lets every waiter through, recording the fact in ``latch_timed_out``.
    Waiting forever instead would turn a queue regression into a hung test
    (the workers block inside `process`, so `JobQueueService.shutdown` never
    returns either) rather than a failed one -- and a test suite that hangs
    is worse than one that fails. This timeout only bounds how long a
    *failing* run takes to say so; no passing assertion depends on it.
    """

    def __init__(
        self,
        *,
        default: ProcessingResult | None = None,
        hold_seconds: float = 0.0,
        hold_event: asyncio.Event | None = None,
        release_at_concurrency: int | None = None,
        latch_timeout_seconds: float = 5.0,
    ) -> None:
        self._default = default or ProcessingResult(
            outcome=ProcessingOutcome.SUCCEEDED, usable=True
        )
        self._hold_seconds = hold_seconds
        self._hold_event = hold_event
        self._release_at = release_at_concurrency
        self._released = asyncio.Event() if release_at_concurrency is not None else None
        self._latch_timeout_seconds = latch_timeout_seconds
        self.latch_timed_out = False
        self._scripts: dict[tuple[str, str | None], list[ProcessingResult]] = defaultdict(list)
        self._event_counter = itertools.count()
        self.calls: list[Job] = []
        self.spans: list[ProcessingSpan] = []
        self.current_concurrency = 0
        self.max_concurrency_seen = 0

    def span_for(self, submission_id: str, question_id: str) -> ProcessingSpan:
        """The single span recorded for one submission-question pair."""
        matches = [
            span
            for span in self.spans
            if span.submission_id == submission_id and span.question_id == question_id
        ]
        assert len(matches) == 1, (
            f"expected exactly one span for {submission_id!r}/{question_id!r}, got {matches}"
        )
        return matches[0]

    def script(
        self, submission_id: str, question_id: str | None, results: list[ProcessingResult]
    ) -> None:
        self._scripts[(submission_id, question_id)].extend(results)

    def set_default(self, result: ProcessingResult) -> None:
        self._default = result

    async def process(self, job: Job) -> ProcessingResult:
        self.current_concurrency += 1
        self.max_concurrency_seen = max(self.max_concurrency_seen, self.current_concurrency)
        started = next(self._event_counter)
        try:
            self.calls.append(job)
            if self._released is not None:
                if self.current_concurrency >= (self._release_at or 0):
                    self._released.set()
                try:
                    await asyncio.wait_for(
                        self._released.wait(), timeout=self._latch_timeout_seconds
                    )
                except TimeoutError:
                    self.latch_timed_out = True
                    self._released.set()
            if self._hold_event is not None:
                await self._hold_event.wait()
            else:
                # Always yield at least once, even with hold_seconds=0, so
                # real concurrency can interleave.
                await asyncio.sleep(self._hold_seconds)
            queued = self._scripts.get((job.submission_id, job.question_id))
            if queued:
                return queued.pop(0)
            return self._default
        finally:
            # Recorded before the permit is released (the queue holds its
            # semaphore until `process` returns), so a job that really did
            # wait for a prerequisite always finishes at a lower counter
            # value than the dependent's start (Issue #25).
            self.spans.append(
                ProcessingSpan(
                    job_id=job.id,
                    submission_id=job.submission_id,
                    question_id=job.question_id,
                    started=started,
                    finished=next(self._event_counter),
                )
            )
            self.current_concurrency -= 1
