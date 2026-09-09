"""OCR domain types and the ``OCRProvider`` port.

Framework-free (see ``AGENTS.md`` "Architecture" -- ``api -> domain <- adapters``).
The concrete provider is Google Document AI (business-rules-and-evaluation-
data.md section 3 (A), Issue #81; adapter in
``auto_scoring.adapters.ocr.document_ai_provider``, Issue #114). This module
pins only the contract every provider must honour:

* text, per-token bounding boxes, and a confidence value plus a coarse band come
  back together (simplified-design-specification.md section 8.1);
* an unreadable span is still returned and flagged ``ConfidenceBand.LOW``;
  adapters preserve the provider's raw text (or an empty sentinel) instead of
  filling the span with a post-processing guess
  (Issue #13 acceptance: do not fill unrecognisable spans with a guess);
* bounding boxes are in normalised page coordinates (0.0 to 1.0) so the value
  survives the pdfium <-> Python round trip (design section 12.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

_UNIT_EPS = 1e-9


class ConfidenceBand(StrEnum):
    """Coarse recognition confidence (design section 8.2)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Where :func:`band_for` cuts. **Presentation only** -- never a gate.
#:
#: The decision that actually matters (needs_review, and whether a dependent
#: question is released) is made once, elsewhere, against
#: `auto_scoring.jobs.recognition_settings.RecognitionSettings.
#: confidence_threshold` -- business-rules-and-evaluation-data.md section
#: 3.1 (C): "閾値ハードコードで判定を分岐させない、閾値は設定の単一箇所から
#: 読む". These two numbers are deliberately *not* that threshold and must
#: never be compared against a score to decide anything; they only choose
#: which of design section 8.2's three words to show next to a number the
#: reviewer can already see. Cutting HIGH at the same 0.80 the default
#: threshold happens to use would invite exactly the drift that rule exists
#: to prevent, by making the band look like the gate.
_HIGH_BAND_MINIMUM = 0.90
_MEDIUM_BAND_MINIMUM = 0.70


def band_for(confidence: float) -> ConfidenceBand:
    """The coarse band to show alongside ``confidence`` (design section 8.2).

    Lives here, in the domain, rather than in each adapter: it is the one
    place every `OCRProvider` implementation maps a provider's own score onto
    this project's three words, so two adapters cannot silently disagree
    about what "medium" means in the same review screen.
    """
    if confidence >= _HIGH_BAND_MINIMUM:
        return ConfidenceBand.HIGH
    if confidence >= _MEDIUM_BAND_MINIMUM:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned box in normalised page coordinates (0.0 to 1.0).

    ``x`` / ``y`` are the top-left corner; ``width`` / ``height`` extend right
    and down.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
        ):
            if not -_UNIT_EPS <= value <= 1.0 + _UNIT_EPS:
                raise ValueError(f"{name} must be within [0.0, 1.0], got {value!r}")
        if self.x + self.width > 1.0 + _UNIT_EPS:
            raise ValueError("x + width must not exceed 1.0")
        if self.y + self.height > 1.0 + _UNIT_EPS:
            raise ValueError("y + height must not exceed 1.0")

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def iou(self, other: BoundingBox) -> float:
        """Intersection-over-union with ``other`` (0.0 when the boxes are disjoint)."""
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        if right <= left or bottom <= top:
            return 0.0
        intersection = (right - left) * (bottom - top)
        union = self.area + other.area - intersection
        return intersection / union if union > 0.0 else 0.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> BoundingBox:
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )


@dataclass(frozen=True)
class OcrToken:
    """One recognised text span with its box and confidence.

    An unreadable span is still emitted with ``band == ConfidenceBand.LOW``.
    ``text`` preserves the provider's raw output, or is empty when no text was
    returned; adapters must not fill it with a post-processing guess.
    """

    text: str
    bounding_box: BoundingBox
    confidence: float
    band: ConfidenceBand

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0.0, 1.0], got {self.confidence!r}")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> OcrToken:
        return cls(
            text=str(data["text"]),
            bounding_box=BoundingBox.from_mapping(data["bounding_box"]),
            confidence=float(data["confidence"]),
            band=ConfidenceBand(str(data["band"])),
        )


@dataclass(frozen=True)
class OcrResult:
    """Recognition output for one question-region image."""

    text: str
    tokens: tuple[OcrToken, ...] = ()
    provider: str = ""

    @property
    def has_low_confidence(self) -> bool:
        return any(token.band is ConfidenceBand.LOW for token in self.tokens)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> OcrResult:
        return cls(
            text=str(data["text"]),
            tokens=tuple(OcrToken.from_mapping(token) for token in data.get("tokens", ())),
            provider=str(data.get("provider", "")),
        )


@runtime_checkable
class OCRProvider(Protocol):
    """Port: turn one question-region image into text + boxes + confidence.

    Implementations must never receive student-identifying data, and must not log
    request or response bodies (Issue #13; business-rules-and-evaluation-data.md
    section 2 (2)).

    ``recognize`` returns an :class:`OcrResult` for anything the provider was
    able to answer at all, including a low-confidence/unreadable one (see
    :class:`OcrToken`'s docstring) -- that is not a failure. Raise one of the
    exceptions below only when the provider could not produce a result at all
    (Issue #19: timeout / rate limit / malformed response / any other
    provider-side error), so callers such as
    ``auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`` can
    classify the failure for retry purposes
    (``auto_scoring.domain.models.ErrorCategory``).

    :class:`OCRUnavailable` is the one exception that does not mean a failed
    call: it means this host has no OCR at all, which the same caller treats
    as "no reading" rather than as an error (Issue #114). See its docstring.
    """

    @property
    def name(self) -> str: ...

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult: ...


class OCRProviderError(Exception):
    """Base class for a provider call that produced no :class:`OcrResult` at all.

    Distinct from a low-confidence/unreadable *result* (still a successful
    call, see :class:`OcrToken`) -- these mean the call itself did not
    complete. Adapters must not include request/response bodies or answer
    text in the message (AGENTS.md "Security"); callers must not either when
    turning this into a persisted `Job.last_error` (Issue #19).
    """


class OCRTimeoutError(OCRProviderError):
    """The provider did not respond within its configured timeout."""


class OCRRateLimitedError(OCRProviderError):
    """The provider rejected the call for exceeding a rate limit/quota."""


class OCRServerError(OCRProviderError):
    """The provider reported a transient server-side failure (5xx or similar)."""


class OCRResponseSchemaError(OCRProviderError):
    """The provider's response could not be parsed into an :class:`OcrResult`."""


class OCRUnavailable(OCRProviderError):
    """This host cannot do OCR at all -- not "this call failed" (Issue #114).

    Distinct from every other member of this hierarchy, which all mean a
    provider that *exists here* did not answer this one call. This one means
    there is no provider on this machine: no Document AI processor
    configured, or no Application Default Credentials to reach it with
    (`auto_scoring.adapters.ocr.unconfigured_provider.UnconfiguredOCRProvider`).
    Retrying cannot change that, and neither can a human pressing "resume" on
    a question.

    It exists because those two are not the same fact and the app must not
    conflate them (Issue #114 acceptance 8): "the OCR read this answer and
    was not confident" is a reason to send the question to a human, while
    "this machine has no OCR" is a reason to carry on without one --
    simplified-design-specification.md section 24 ("OCR失敗: **採点は止め
    ない。**... 読み取り結果は「なし」として提示する") and section 8.1.5
    ("OCRは採点の critical path から外れる").

    `auto_scoring.jobs.recognition_processor.RecognitionJobProcessor` is
    therefore the one caller that treats this as a *completed* recognition
    step with no reading, rather than as a failure: it persists no
    `RecognitionResult` at all, because section 8.1.4 forbids attaching a
    confidence number to something nothing read ("**読めていないものに数値を
    与えない**"). A row saying ``confidence=0.0`` -- what the deleted
    ``NullOCRProvider`` used to write -- is indistinguishable in the review UI
    from an OCR that looked and found nothing.
    """


def overall_confidence(result: OcrResult) -> float:
    """One scalar confidence for ``result``, for `RecognitionResult.confidence`
    and the needs-review threshold check (business-rules-and-evaluation-
    data.md section 3 (C)).

    The minimum of every token's confidence, not an average: one unreadable
    span must be enough to flag the whole question for review even if every
    other span was read cleanly (Issue #19 acceptance: "決定済みConfidence
    閾値未満はneeds_reviewとし自動確定しない" -- an average could hide exactly
    the low-confidence span this rule exists to catch). ``0.0`` when nothing
    was recognized at all (no tokens), matching
    ``auto_scoring.domain.ocr_metrics.evaluate_sample``'s own "failed" case.
    """
    if not result.tokens:
        return 0.0
    return min(token.confidence for token in result.tokens)
