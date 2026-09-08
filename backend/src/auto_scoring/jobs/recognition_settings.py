"""Confidence gate for `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`.

A plain dataclass, matching `auto_scoring.jobs.settings.QueueSettings`'s own
reasoning for not adopting `pydantic-settings` for one more numeric knob.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class RecognitionSettings:
    """``confidence_threshold`` gates `Job.usable`, never whether a human
    review step happens at all (business-rules-and-evaluation-data.md
    section 3 (C) / section 3.1 (C)): a `RecognitionResult` is always
    persisted and always ``source=ai`` (a proposal, simplified-design-
    specification.md section 19), regardless of this value.

    The project owner decided (Issue #81, business-rules-and-evaluation-data.md
    section 3 (C)) *not* to fix a single value: the threshold stays a setting,
    ``0.80`` stays its default, and the number is adjusted while operating.
    So this is a real default to run with -- not the "未確定" placeholder it
    used to be -- but it is equally not a final number, and section 3.1's
    remaining constraint is unchanged: no caller may skip human review on the
    strength of it.
    """

    confidence_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                "RecognitionSettings.confidence_threshold must be within 0..1, "
                f"got {self.confidence_threshold!r}"
            )
