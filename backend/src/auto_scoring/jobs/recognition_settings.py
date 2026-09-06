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
    section 3 (C) / section 3.1 "C確定まで"): a `RecognitionResult` is always
    persisted and always ``source=ai`` (a proposal, simplified-design-
    specification.md section 19), regardless of this value.

    The value is **not yet decided** by the project owner -- pending PoC 1 and
    PoC 2's confidence distributions (business-rules-and-evaluation-data.md
    section 3 (C)). ``0.80`` is only the placeholder that document itself
    names as its own provisional default; it is not a product decision, and
    callers must not treat it as final (section 3.1: "既定値は「未確定」と明記
    したプレースホルダにする").
    """

    confidence_threshold: float = 0.80

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                "RecognitionSettings.confidence_threshold must be within 0..1, "
                f"got {self.confidence_threshold!r}"
            )
