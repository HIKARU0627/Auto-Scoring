"""Placeholder `JobProcessor` used until a real OCR/AI implementation exists.

Issue #18 explicitly excludes "OCR/AIのprovider固有処理" -- this processor
lets the queue (and the real sidecar) run without one, but is honest about
it: every job it touches fails permanently with a message saying so, rather
than silently reporting success. A later issue replaces this default with a
real implementation via ``create_app(job_processor=...)``.
"""

from __future__ import annotations

from auto_scoring.domain.job_execution import ProcessingOutcome, ProcessingResult
from auto_scoring.domain.models import ErrorCategory, Job


class NullJobProcessor:
    """Fails every job permanently; never calls an external provider."""

    async def process(self, job: Job) -> ProcessingResult:
        return ProcessingResult(
            outcome=ProcessingOutcome.FAILED,
            error_category=ErrorCategory.PERMANENT,
            error_message=(
                "no JobProcessor configured -- OCR/AI processing is implemented by a "
                "later issue; pass job_processor= to create_app to supply one"
            ),
        )
