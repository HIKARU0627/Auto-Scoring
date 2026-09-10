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

    ``skipped_reason`` is the third case, and Issue #164 is why it exists.
    A processor that decides there is nothing to do -- no answer area was
    ever defined for this question, so there is no crop to grade -- used to
    return ``SUCCEEDED`` with ``usable=False`` and nothing else, and the job
    row then said ``succeeded``, ``last_error`` NULL, 0.013 seconds. Measured
    on one real run: **23 of 37 grading jobs** looked exactly like that, and
    a person reading the queue could not tell them from work that was done.
    Saying so is not the same as failing: nothing is wrong, nothing can be
    retried, and the question is already in front of a human on the review
    screen. It carries a fixed vocabulary word, never free text and never
    anything read off the paper.
    """

    outcome: ProcessingOutcome
    usable: bool = False
    error_category: ErrorCategory | None = None
    error_message: str | None = None
    skipped_reason: str | None = None

    def __post_init__(self) -> None:
        if self.outcome is ProcessingOutcome.FAILED and self.error_category is None:
            raise ValueError("a FAILED ProcessingResult must carry an error_category")
        if self.skipped_reason is not None:
            if self.outcome is not ProcessingOutcome.SUCCEEDED:
                raise ValueError("skipped_reason only applies to a SUCCEEDED ProcessingResult")
            if self.usable:
                # "Nothing was done" and "the result may release a dependent
                # question" cannot both be true, and letting them be would
                # release a dependent onto a prerequisite that has no grade.
                raise ValueError("a skipped ProcessingResult cannot be usable")


@runtime_checkable
class JobProcessor(Protocol):
    """Port: do whatever one job's kind requires, and report the outcome.

    Implementations must never log or persist answer text or secrets
    (business-rules-and-evaluation-data.md §2 (2), AGENTS.md "Security").
    """

    async def process(self, job: Job) -> ProcessingResult: ...
