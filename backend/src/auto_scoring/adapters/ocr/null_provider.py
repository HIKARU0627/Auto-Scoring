"""Placeholder `OCRProvider` used until a real cloud/local adapter is chosen.

business-rules-and-evaluation-data.md section 3 (A): the OCR service to use is
**not yet decided** by the project owner -- PoC 1 (Issue #13) built the
`OCRProvider` contract and the metrics/aggregation pipeline, but never adopted
a specific SDK (no candidate's credentials/eval dataset were available; see
docs/poc-1-japanese-handwriting-ocr.md section 0.1/section 6). Section 3.1's
block condition for A is explicit: until it is decided, ship "the
`OCRProvider` interface and a dummy implementation only" -- no SDK-specific
request/response handling.

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
