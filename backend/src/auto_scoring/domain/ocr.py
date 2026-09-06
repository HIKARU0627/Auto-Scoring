"""OCR domain types and the ``OCRProvider`` port.

Framework-free (see ``AGENTS.md`` "Architecture" -- ``api -> domain <- adapters``).
The concrete provider is chosen by PoC 1 (GitHub Issue #13); until then this
module only pins the contract every provider must honour:

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
