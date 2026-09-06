"""Fakes for the parallel job queue's async tests (Issue #18).

Both make the queue's behaviour deterministic: `FakeClock.sleep` advances a
virtual clock instead of really waiting, and `FakeJobProcessor` returns
scripted results instead of calling a real OCR/AI provider.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
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


class FakeJobProcessor:
    """Scriptable `auto_scoring.domain.job_execution.JobProcessor`.

    ``script`` queues a sequence of results for one ``(submission_id,
    question_id)`` pair; each call to `process` for that pair pops the next
    scripted result, falling back to ``default`` once the script is
    exhausted. Tracks concurrency (``max_concurrency_seen``) and every job it
    was asked to process, for assertions.
    """

    def __init__(
        self,
        *,
        default: ProcessingResult | None = None,
        hold_seconds: float = 0.0,
        hold_event: asyncio.Event | None = None,
    ) -> None:
        self._default = default or ProcessingResult(
            outcome=ProcessingOutcome.SUCCEEDED, usable=True
        )
        self._hold_seconds = hold_seconds
        self._hold_event = hold_event
        self._scripts: dict[tuple[str, str | None], list[ProcessingResult]] = defaultdict(list)
        self.calls: list[Job] = []
        self.current_concurrency = 0
        self.max_concurrency_seen = 0

    def script(
        self, submission_id: str, question_id: str | None, results: list[ProcessingResult]
    ) -> None:
        self._scripts[(submission_id, question_id)].extend(results)

    def set_default(self, result: ProcessingResult) -> None:
        self._default = result

    async def process(self, job: Job) -> ProcessingResult:
        self.current_concurrency += 1
        self.max_concurrency_seen = max(self.max_concurrency_seen, self.current_concurrency)
        try:
            self.calls.append(job)
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
            self.current_concurrency -= 1
