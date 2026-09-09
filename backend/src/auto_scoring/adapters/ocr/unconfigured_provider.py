"""``OCRProvider`` for a host where no OCR provider could be built.

Replaces ``NullOCRProvider`` (Issue #19), which answered every image with a
single empty token at ``confidence=0.0``. That was an honest *placeholder*
while no real adapter existed at all -- but once
`auto_scoring.adapters.ocr.factory.create_ocr_provider` is wired into the
sidecar (Issue #114), the only way to still land here is a host with no
Document AI processor configured or no Application Default Credentials to
reach it with, and there that placeholder was actively wrong in two ways:

* It **wrote a confidence number for something nothing had read**, which
  simplified-design-specification.md section 8.1.4 forbids outright
  ("読めていないものに数値を与えない"). A persisted `RecognitionResult` at
  confidence 0.0 is indistinguishable, in the review UI, from an OCR that
  looked at the crop and found nothing there.
* Because that 0.0 then failed
  `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`'s
  threshold, **every** question on such a host came out ``usable=False`` and
  every dependent question stayed `BLOCKED` until a human pressed
  ``/resume`` on each one -- while section 24 says the opposite in as many
  words: "OCR失敗: **採点は止めない。**" (see also section 8.1.5: OCR is off
  the grading critical path since Issue #95 decision 10).

So this one raises `domain.ocr.OCRUnavailable` instead of answering, and
that processor treats it as a completed recognition step with *no reading*:
no `RecognitionResult` row at all, and no OCR term in the job's ``usable``.
The remaining two terms -- the grading AI's own reading of the answer and its
grading confidence -- still gate, which is exactly what
business-rules-and-evaluation-data.md section 4.3 calls for once OCR text is
no longer guaranteed to exist ("**OCR テキストとは限らない。**... 採点 AI
自身の読み取りが引き継ぐ対象になる場合がある").

Mirrors `auto_scoring.adapters.ai.unconfigured_provider.UnconfiguredAIProvider`
(Issue #97) deliberately, down to :attr:`reason`: the same discipline, stated
once for the whole app by ``GET /ocr/availability`` (`auto_scoring.api.app`)
rather than repeated into every question's `Job.last_error`.
"""

from __future__ import annotations

from typing import NoReturn

from auto_scoring.domain.ocr import OCRUnavailable


class UnconfiguredOCRProvider:
    """Always raises `OCRUnavailable`; never calls a network."""

    name = "unconfigured"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    @property
    def reason(self) -> str:
        """Why no provider could be built, in terms an operator can act on.

        Names configuration *variables* and host prerequisites, never their
        values (`auto_scoring.adapters.ocr.factory`'s own rule for
        `OCRProviderConfigError`). Published by ``GET /ocr/availability``.
        """
        return self._reason

    def recognize(self, image: bytes, *, language: str = "ja") -> NoReturn:
        raise OCRUnavailable(f"no OCR provider is configured: {self._reason}")
