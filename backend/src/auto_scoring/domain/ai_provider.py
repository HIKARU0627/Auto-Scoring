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

import json
import math
from dataclasses import dataclass
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from auto_scoring.domain.ai_grading import AIGradingResult
from auto_scoring.domain.dependency_graph import DependencyProvision
from auto_scoring.domain.models import AnnotationKind, CriterionOutcome, CriterionResult

#: A required string that must contain more than just whitespace (mirrors
#: ``ai_grading._NonBlankStr``): plain ``min_length=1`` accepts ``" "``.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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

    Raised bare only for a transport failure that does not fit one of the
    subclasses below; a real adapter should prefer the specific subclass so
    callers (`auto_scoring.jobs.grading_processor.GradingJobProcessor`) can
    classify it into `auto_scoring.domain.models.ErrorCategory` for the
    queue's retry policy (Issue #20: "timeout、429/5xxを分類しqueueのretry
    規則へ接続する"), mirroring `domain.ocr.OCRProviderError`'s own
    subclasses for the same purpose.
    """


class ProviderTimeoutError(ProviderUnavailable):
    """The provider did not respond within its configured timeout."""


class ProviderRateLimitedError(ProviderUnavailable):
    """The provider rejected the call for exceeding a rate limit/quota (429)."""


class ProviderServerError(ProviderUnavailable):
    """The provider reported a transient server-side failure (5xx or similar)."""


@dataclass(frozen=True, kw_only=True)
class ProviderDescriptor:
    """Reproducibility record for one grading call (Issue #14 "再現条件").

    ``prompt_version`` is required, not optional: a prompt template edit with
    the same model/version/temperature/structured_output_mode is still a
    different configuration and must not be pooled with the old one (code
    review finding). It is a short, stable tag or content hash for the exact
    prompt template used -- never the prompt text itself (no student content,
    no risk of drifting into a huge cache key).

    Invariants are enforced here, at construction, not only by the
    ``--dataset`` JSON boundary (:class:`_DescriptorInput`): a real
    ``AIProvider`` adapter builds this directly from its own ``describe()``,
    bypassing that boundary entirely, so a blank ``provider``/``model``/
    ``prompt_version``/``structured_output_mode`` or a non-finite
    ``temperature`` must be impossible to construct at all -- not merely
    rejected when it happens to arrive as recorded JSON (code review finding:
    a supposedly-reproducible descriptor that is actually blank or infinite
    cannot really reproduce anything).
    """

    provider: str
    model: str
    version: str | None
    prompt_version: str
    temperature: float
    structured_output_mode: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("provider", self.provider),
            ("model", self.model),
            ("prompt_version", self.prompt_version),
            ("structured_output_mode", self.structured_output_mode),
        ):
            if not value.strip():
                raise ValueError(f"ProviderDescriptor.{field_name} must be a non-blank string")
        if self.version is not None and not self.version.strip():
            raise ValueError("ProviderDescriptor.version must not be a whitespace-only string")
        # ``bool`` is a subclass of Python's ``int`` (and so of ``float`` for
        # arithmetic purposes), so ``math.isfinite(True)`` and ``True >= 0``
        # both pass silently -- checked explicitly, before the numeric check,
        # so a directly-constructed descriptor cannot record a bare ``True``/
        # ``False`` as its temperature when the ``--dataset`` JSON boundary
        # (``_DescriptorInput``, strict-mode) would already reject the same
        # value (code review finding).
        if isinstance(self.temperature, bool):
            raise ValueError(
                f"ProviderDescriptor.temperature must be a number, not a bool, "
                f"got {self.temperature!r}"
            )
        if not math.isfinite(self.temperature) or self.temperature < 0:
            raise ValueError(
                f"ProviderDescriptor.temperature must be finite and >= 0, got {self.temperature!r}"
            )


def _normalized_temperature(temperature: float) -> float:
    """Normalize a temperature value so ``descriptor_key`` is stable
    regardless of how the ``ProviderDescriptor`` was constructed.

    ``ProviderDescriptor`` is a plain ``dataclass``, not a pydantic model, so
    a directly-constructed instance is never coerced: an adapter passing the
    Python int literal ``0`` for ``temperature`` keeps it as an ``int`` at
    runtime, while the same value loaded through ``_DescriptorInput``
    (pydantic, a ``float`` field) becomes ``0.0``. ``json.dumps`` renders
    these two differently (``0`` vs ``0.0``), splitting what should be one
    configuration into two separate metric buckets. Converting to ``float``
    here -- and folding negative zero to positive zero, since ``-0.0 ==
    0.0`` but the two serialize to different JSON text -- keeps the key
    stable across both construction paths (code review finding).
    """
    value = float(temperature)
    return 0.0 if value == 0.0 else value


def _normalized_str(value: str) -> str:
    """Normalize a descriptor string field so ``descriptor_key`` is stable
    regardless of how the ``ProviderDescriptor`` was constructed.

    ``_DescriptorInput`` parses these fields through ``_NonBlankStr``
    (``StringConstraints(strip_whitespace=True, ...)``), which strips
    surrounding whitespace -- but ``ProviderDescriptor`` is a plain
    ``dataclass``, so a directly-constructed instance (e.g.
    ``model=" model-a "``) keeps it. Without normalizing here too, the same
    adapter configuration would serialize to two different keys depending on
    which path constructed the descriptor, splitting one configuration into
    two metric buckets (code review finding; mirrors
    ``_normalized_temperature``).
    """
    return value.strip()


def descriptor_key(descriptor: ProviderDescriptor) -> str:
    """Stable, collision-free identifier for one reproducibility configuration.

    Two recordings under the same ``provider`` name but a different model,
    version, prompt version, temperature, or structured-output mode are two
    different configurations and must never be pooled into the same metrics
    bucket (code review finding: a passing and a failing configuration
    averaged together can look like an overall pass). Callers key
    aggregation on this, not on ``provider`` alone.

    Encoded as a JSON array rather than a ``"|"``-joined string: a naive
    join is ambiguous whenever a field value itself contains the delimiter
    (code review finding: ``model="a|b", version="c"`` and ``model="a",
    version="b|c"`` would join to the identical string). JSON array
    serialization escapes/quotes each element, so the two cases are never
    equal.
    """
    return json.dumps(
        [
            _normalized_str(descriptor.model),
            _normalized_str(descriptor.version) if descriptor.version is not None else None,
            _normalized_str(descriptor.prompt_version),
            _normalized_temperature(descriptor.temperature),
            _normalized_str(descriptor.structured_output_mode),
        ],
        ensure_ascii=False,
    )


class _DescriptorInput(BaseModel):
    """Untrusted-input boundary for one recorded cell's ``descriptor``.

    Strictly validated, never coerced (code review finding: a naive
    ``str(raw["model"])`` / ``float(raw["temperature"])`` cast would turn
    ``model: null`` into the literal string ``"None"``, or
    ``temperature: true`` into ``1.0``, silently accepting reproducibility
    metadata that cannot actually reproduce the call). This is the same
    trust boundary as an ``AIGradingResult`` response
    (``ai_grading.parse_ai_grading_result``) -- a real ``--dataset`` file is
    untrusted input (AGENTS.md "Verification").
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: _NonBlankStr
    version: _NonBlankStr | None = None
    prompt_version: _NonBlankStr
    temperature: float = Field(ge=0.0)
    structured_output_mode: _NonBlankStr

    @model_validator(mode="after")
    def _temperature_is_finite(self) -> _DescriptorInput:
        if not math.isfinite(self.temperature):
            raise ValueError(f"temperature must be finite, got {self.temperature!r}")
        return self


def parse_provider_descriptor(raw: str | bytes, *, provider: str) -> ProviderDescriptor:
    """Parse and validate one recorded cell's ``descriptor`` JSON.

    Raises ``pydantic.ValidationError`` on any malformed value (missing
    field, wrong type, blank string, non-finite temperature, unknown extra
    field, ...) -- there is no fallback that coerces a bad value into
    something plausible-looking.
    """
    parsed = _DescriptorInput.model_validate_json(raw)
    return ProviderDescriptor(
        provider=provider,
        model=parsed.model,
        version=parsed.version,
        prompt_version=parsed.prompt_version,
        temperature=parsed.temperature,
        structured_output_mode=parsed.structured_output_mode,
    )


@dataclass(frozen=True, kw_only=True)
class PrerequisiteAnswer:
    """What one prerequisite question hands to a dependent question's grading
    call (Issue #20; business-rules-and-evaluation-data.md section 4.3).

    Only the fields section 4.3 allows are representable here: the
    prerequisite's recognized text and its criterion/score outcome. There is
    no field for the prerequisite's answer image, its AI comment, or any
    student-identifying data -- section 4.3's "渡してはならないもの" list --
    so a caller cannot accidentally attach them even by mistake.
    `provides` names which of `recognized_text`/`score`+`max_score`/
    `criteria` this instance actually carries, mirroring
    `domain.dependency_graph.DependencyEdge.provides` (Issue #26): a caller
    builds one `PrerequisiteAnswer` per prerequisite edge, filling in only
    the fields that edge's own `provides` calls for.

    ``criteria`` reuses `domain.models.CriterionResult` (id + outcome +
    confidence), the same shape a persisted `GradeResult` already carries --
    not `GradingCriterionOutcome` (which adds a ``rationale``): section 4.3's
    "criterion 結果と最終得点" allows the outcome itself to cross into a
    dependent question's context, not the prerequisite's free-text judgement
    rationale (section 4.3's own "AIコメント文・自由文の判定根拠" exclusion).
    """

    question_id: str
    provides: tuple[DependencyProvision, ...]
    recognized_text: str | None = None
    score: int | None = None
    max_score: int | None = None
    criteria: tuple[CriterionResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.question_id.strip():
            raise ValueError("PrerequisiteAnswer.question_id must be a non-blank string")
        if not self.provides:
            raise ValueError("PrerequisiteAnswer.provides must include at least one item")
        if DependencyProvision.RECOGNIZED_TEXT in self.provides and self.recognized_text is None:
            raise ValueError(
                "PrerequisiteAnswer.recognized_text is required when provides includes "
                "RECOGNIZED_TEXT"
            )
        if DependencyProvision.SCORE in self.provides:
            if self.score is None or self.max_score is None:
                raise ValueError(
                    "PrerequisiteAnswer.score/max_score are required when provides includes SCORE"
                )
            if not 0 <= self.score <= self.max_score:
                raise ValueError(
                    f"PrerequisiteAnswer.score {self.score} outside range 0..{self.max_score}"
                )
        if DependencyProvision.CRITERION_RESULT in self.provides and not self.criteria:
            raise ValueError(
                "PrerequisiteAnswer.criteria must be non-empty when provides includes "
                "CRITERION_RESULT"
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

    Invariants are enforced at construction (mirrors
    ``ProviderDescriptor.__post_init__``): a real adapter builds this
    directly, bypassing any pydantic boundary, so a blank ``question_id``/
    ``prompt_text``/``model_answer``/``rubric_text``, an empty
    ``answer_image``, or a negative ``max_score`` must be impossible to
    construct at all, not merely caught later by whatever happens to read
    the request (code review finding: the plain type annotations alone did
    not stop a caller from building one of these and sending it to a real
    provider adapter as if it were valid). ``ocr_text`` is deliberately
    exempt: an empty string is the legitimate reading of a question the
    student left blank (mirrors
    ``ai_grading_metrics.GradingInputRecord.ocr_clean``).

    ``prerequisite_context`` (Issue #20) carries only the prerequisite
    question data business-rules-and-evaluation-data.md section 4.3
    allows to cross into a dependent question's grading call -- built by
    ``auto_scoring.domain.grading_context.build_prerequisite_context`` from
    the confirmed `DependencyGraph` (Issue #26), never assembled ad hoc by a
    caller. Empty for a question with no prerequisite edge into it.
    """

    question_id: str
    prompt_text: str
    answer_image: bytes
    ocr_text: str
    model_answer: str
    rubric_text: str
    max_score: int
    prerequisite_context: tuple[PrerequisiteAnswer, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("question_id", self.question_id),
            ("prompt_text", self.prompt_text),
            ("model_answer", self.model_answer),
            ("rubric_text", self.rubric_text),
        ):
            if not value.strip():
                raise ValueError(f"GradingRequest.{field_name} must be a non-blank string")
        if not self.answer_image:
            raise ValueError("GradingRequest.answer_image must not be empty")
        if self.max_score < 0:
            raise ValueError(f"GradingRequest.max_score must be >= 0, got {self.max_score!r}")


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

    ``recognition_text`` carries the AI's recognized-text reading alongside
    its confidence: simplified-design-specification.md section 16.5 lists
    "AI認識文字" (AI-recognized text) as its own field in the review UI,
    distinct from the score/rationale/comment -- a caller cannot display or
    persist it if only the confidence number survives the mapping from the
    validated wire response (code review finding).
    """

    question_id: str
    recognition_text: str
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
        recognition_text=result.recognition.text,
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
