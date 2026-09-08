"""Placeholder `OCRProvider` used until the chosen service has a real adapter.

business-rules-and-evaluation-data.md section 3 (A): the project owner chose
**Google Document AI** (Issue #81), but no adapter for it exists yet -- PoC 1
(Issue #13) built only the `OCRProvider` contract and the metrics/aggregation
pipeline, and never called a real service (no credentials/eval dataset were
available; see docs/poc-1-japanese-handwriting-ocr.md section 0.1/section 6,
live probe in Issue #54). Section 3.1 (A) still requires SDK-specific
request/response handling to stay inside the `OCRProvider` implementation.

Mirrors `auto_scoring.jobs.null_processor.NullJobProcessor`: rather than
raising (which `RecognitionJobProcessor` would have to guess a retry category
for) or fabricating a plausible-looking read, this always reports the image as
completely unrecognized. That is honest about not being configured yet, and
it composes correctly with the "needs_review, never auto-confirm" rule
(Issue #19 acceptance) by construction -- every question routes to manual
review until a real adapter is injected via ``create_app(ocr_provider=...)``.
"""

from __future__ import annotations

from auto_scoring.domain.ocr import BoundingBox, ConfidenceBand, OcrResult, OcrToken

#: Covers the whole image -- there is no real detection to report a smaller
#: region for.
_WHOLE_IMAGE = BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)


class NullOCRProvider:
    """Always reports "nothing recognized"; never calls a network."""

    name = "null"

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        return OcrResult(
            text="",
            tokens=(
                OcrToken(
                    text="",
                    bounding_box=_WHOLE_IMAGE,
                    confidence=0.0,
                    band=ConfidenceBand.LOW,
                ),
            ),
            provider=self.name,
        )
