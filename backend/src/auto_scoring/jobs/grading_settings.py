"""Confidence gate for `auto_scoring.jobs.grading_processor.GradingJobProcessor`.

A plain dataclass, matching `auto_scoring.jobs.recognition_settings.
RecognitionSettings`'s own reasoning for not adopting a settings framework
for one more numeric knob. Kept as its own type -- not a second field on
`RecognitionSettings` -- because Recognition Confidence and Grading
Confidence are separate, never-conflated measurements throughout this
codebase (simplified-design-specification.md section 10) and each gets its
own threshold for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class GradingSettings:
    """``confidence_threshold`` gates `Job.usable`, never whether a human
    review step happens at all: a `GradeResult` is always persisted and
    always ``source=ai`` (a proposal, simplified-design-specification.md
    section 19), regardless of this value.

    The project owner decided (Issue #81, business-rules-and-evaluation-data.md
    section 3 (C)) *not* to fix a single value: the threshold stays a setting,
    ``0.80`` stays its default, and the number is adjusted while operating.
    Same reasoning as `auto_scoring.jobs.recognition_settings.
    RecognitionSettings` -- a default to run with, never a licence to skip
    human review.
    """

    confidence_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                "GradingSettings.confidence_threshold must be within 0..1, "
                f"got {self.confidence_threshold!r}"
            )
