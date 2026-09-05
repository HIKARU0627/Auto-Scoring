"""``JobProcessor`` port: the boundary between the queue and real OCR/AI work.

Framework-free (see `AGENTS.md` "Architecture"). Mirrors `domain.ocr.OCRProvider`
and the planned ``AIProvider``: the queue (`auto_scoring.jobs.queue`) only ever
calls `JobProcessor.process`, and never knows what happens inside it. A real
implementation that calls OCR/AI providers and persists `RecognitionResult`/
`GradeResult` is out of this issue's scope (Issue #18 "対象外") and belongs to a
later issue; tests inject a fake (`tests/fakes.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from auto_scoring.domain.models import ErrorCategory, Job


class ProcessingOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class ProcessingResult:
    """What one `JobProcessor.process` call decided.

    ``usable`` only means something when ``outcome`` is ``SUCCEEDED`` (Issue
    #18 §4.4: a successful-but-low-confidence result must not release a
    dependent question). ``error_category``/``error_message`` only apply to
    ``FAILED`` -- ``error_message`` must never contain answer text or a
    secret (AGENTS.md "Security"; docs/job-queue.md).
    """

    outcome: ProcessingOutcome
    usable: bool = False
    error_category: ErrorCategory | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is ProcessingOutcome.FAILED and self.error_category is None:
            raise ValueError("a FAILED ProcessingResult must carry an error_category")


@runtime_checkable
class JobProcessor(Protocol):
    """Port: do whatever one job's kind requires, and report the outcome.

    Implementations must never log or persist answer text or secrets
    (business-rules-and-evaluation-data.md §2 (2), AGENTS.md "Security").
    """

    async def process(self, job: Job) -> ProcessingResult: ...
