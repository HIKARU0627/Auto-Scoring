"""Dispatch a `Job` to the `JobProcessor` registered for its `kind` (Issue #23).

`jobs.queue.JobQueueService` only ever holds one `JobProcessor` (Issue #18's
design, ``docs/job-queue.md``) -- fine while every job in the system was
`JobKind.GRADING`. Issue #23 adds a second kind (``EXPORT``) with an
unrelated implementation (`jobs.export_processor.ExportJobProcessor`); this
composes both behind that same one-processor seam so `JobQueueService`
itself needs no change.
"""

from __future__ import annotations

from collections.abc import Mapping

from auto_scoring.domain.job_execution import JobProcessor, ProcessingResult
from auto_scoring.domain.models import Job, JobKind


class ByKindJobProcessor:
    """Routes to ``overrides[job.kind]``, or ``default`` if ``job.kind`` has
    no entry."""

    def __init__(self, *, default: JobProcessor, overrides: Mapping[JobKind, JobProcessor]) -> None:
        self._default = default
        self._overrides = dict(overrides)

    async def process(self, job: Job) -> ProcessingResult:
        processor = self._overrides.get(job.kind, self._default)
        return await processor.process(job)
