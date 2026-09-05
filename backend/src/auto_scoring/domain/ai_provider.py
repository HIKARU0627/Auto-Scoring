"""``AIProvider`` port: grade one question and return validated structured output.

Framework-free (see ``AGENTS.md`` "Architecture" -- the domain must not import
FastAPI, SQLAlchemy, HTTP clients, or any external-service SDK). The concrete
provider (Gemini / Claude / GPT) is chosen by PoC 2 (GitHub Issue #14,
business-rules-and-evaluation-data.md section 3 (B)); until then this module
only pins the contract every provider must honour:

* a request never carries student-identifying data, and holds only one
  question's worth of material (business-rules-and-evaluation-data.md
  section 2 (2): クラウド送信ペイロードは設問単位の最小限);
* a response is either a validated :class:`GradingResponse` or a raised
  :class:`SchemaViolation` / :class:`ProviderUnavailable` -- never a
  best-effort free-text parse (Issue #14 acceptance);
* Recognition confidence and Grading confidence travel as two separate
  numbers, end to end (section 10);
* every response carries the :class:`ProviderDescriptor` needed to reproduce
  it later (prompt / model / version / temperature / structured-output mode --
  Issue #14 "再現条件").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from auto_scoring.domain.ai_grading import AIGradingResult
from auto_scoring.domain.models import AnnotationKind, CriterionOutcome


class SchemaViolation(Exception):
    """The provider's raw response failed structured-output validation.

    Raised instead of falling back to free-text parsing (Issue #14
    acceptance: "自由文のparseに依存せず、schema不適合をエラーまたは
    要確認へ送れる"). Callers must route this to the "needs review" path
    (simplified-design-specification.md section 8.2), never to a guessed
    score. Does not retain the raw response body (it may contain OCR'd
    student answer text) -- only a short, student-content-free description.
    """


class ProviderUnavailable(Exception):
    """The provider could not be reached (timeout, rate limit, transport error).

    Distinct from :class:`SchemaViolation`: this is a call failure, not a
    malformed answer. Callers retry per the PoC's backoff policy before
    falling back to "needs review".
    """


@dataclass(frozen=True, kw_only=True)
class ProviderDescriptor:
    """Reproducibility record for one grading call (Issue #14 "再現条件").

    ``prompt_version`` is required, not optional: a prompt template edit with
    the same model/version/temperature/structured_output_mode is still a
    different configuration and must not be pooled with the old one (code
    review finding). It is a short, stable tag or content hash for the exact
    prompt template used -- never the prompt text itself (no student content,
    no risk of drifting into a huge cache key).
    """

    provider: str
    model: str
    version: str | None
    prompt_version: str
    temperature: float
    structured_output_mode: str


def descriptor_key(descriptor: ProviderDescriptor) -> str:
    """Stable identifier for one reproducibility configuration.

    Two recordings under the same ``provider`` name but a different model,
    version, prompt version, temperature, or structured-output mode are two
    different configurations and must never be pooled into the same metrics
    bucket (code review finding: a passing and a failing configuration
    averaged together can look like an overall pass). Callers key
    aggregation on this, not on ``provider`` alone.
    """
    return (
        f"{descriptor.model}|{descriptor.version}|{descriptor.prompt_version}|"
        f"{descriptor.temperature}|{descriptor.structured_output_mode}"
    )


@dataclass(frozen=True, kw_only=True)
class GradingRequest:
    """Everything sent for one question. Holds no student-identifying data
    (business-rules-and-evaluation-data.md section 2 (2)).

    ``answer_image`` is the cropped answer-region image for this question
    only (never a full page, never other questions -- decision record
    section 2 (2)), sent alongside ``ocr_text`` per
    simplified-design-specification.md section 9.1 ("生徒答案画像" and "OCR
    結果" are both listed inputs): a real adapter needs the image itself to
    derive a meaningful Recognition Confidence from handwriting, not just the
    OCR text PoC 1 already extracted.

    ``ocr_text`` is deliberately the only per-call OCR variant: the PoC
    harness issues one request with the human-corrected reading and a second
    with a plausible OCR misreading of the same answer, so Recognition
    Confidence (a PoC 1 / OCRProvider concern) is never computed from, or
    blended into, this request's Grading Confidence output.
    """

    question_id: str
    prompt_text: str
    answer_image: bytes
    ocr_text: str
    model_answer: str
    rubric_text: str
    max_score: int


@dataclass(frozen=True, kw_only=True)
class GradingCriterionOutcome:
    """One rubric criterion's outcome, mapped from the validated AI response."""

    criterion_id: str
    outcome: CriterionOutcome
    confidence: float
    rationale: str


@dataclass(frozen=True, kw_only=True)
class GradingAnnotationCandidate:
    """One AI-proposed annotation, mapped from the validated AI response.

    Carries no coordinates (simplified-design-specification.md section 12.1):
    placement is decided by the app from ``target`` (and, once Issue #19's
    OCR pipeline exists, that text's bounding box), never guessed by the AI.
    """

    target: str
    type: AnnotationKind
    comment: str | None


@dataclass(frozen=True, kw_only=True)
class GradingResponse:
    """Validated grading result for one question, plus the metadata the PoC
    harness needs to compute latency / cost / agreement metrics without
    touching student answer text again.
    """

    question_id: str
    recognition_confidence: float
    score: int
    max_score: int
    grading_confidence: float
    rationale: str
    comment: str
    criteria: tuple[GradingCriterionOutcome, ...]
    annotations: tuple[GradingAnnotationCandidate, ...]
    descriptor: ProviderDescriptor
    latency_seconds: float


def grading_response_from_result(
    result: AIGradingResult,
    *,
    descriptor: ProviderDescriptor,
    latency_seconds: float,
) -> GradingResponse:
    """Map an already-validated :class:`AIGradingResult` onto the domain response.

    Takes a *parsed* result -- callers first run
    ``ai_grading.parse_ai_grading_result`` (or catch the ``ValidationError`` it
    raises and re-raise as :class:`SchemaViolation`) before calling this.
    """
    return GradingResponse(
        question_id=result.question_id,
        recognition_confidence=result.recognition.confidence,
        score=result.grading.score,
        max_score=result.grading.max_score,
        grading_confidence=result.grading.confidence,
        rationale=result.rationale,
        comment=result.comment,
        criteria=tuple(
            GradingCriterionOutcome(
                criterion_id=c.id,
                outcome=c.result,
                confidence=c.confidence,
                rationale=c.rationale,
            )
            for c in result.criteria
        ),
        annotations=tuple(
            GradingAnnotationCandidate(target=a.target, type=a.type, comment=a.comment)
            for a in result.annotations
        ),
        descriptor=descriptor,
        latency_seconds=latency_seconds,
    )


@runtime_checkable
class AIProvider(Protocol):
    """Port every grading provider adapter implements."""

    @property
    def name(self) -> str: ...

    def describe(self) -> ProviderDescriptor:
        """Reproducibility metadata for calls this provider instance makes."""
        ...

    def grade(self, request: GradingRequest) -> GradingResponse:
        """Grade one question.

        Raises :class:`SchemaViolation` if the provider's structured output
        fails validation, or :class:`ProviderUnavailable` if the provider
        could not be reached. Never returns a value derived from free-text
        parsing of a response that failed schema validation.
        """
        ...
