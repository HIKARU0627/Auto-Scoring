"""Pydantic schema for AI structured grading output (simplified-design-specification.md
section 9.2, section 10, section 12.1; business-rules-and-evaluation-data.md section 3 (B)).

This is the untrusted-input boundary: an ``AIProvider`` returns raw JSON over the
wire, and this module is the single place that turns it into validated data or
raises. It never falls back to free-text parsing (GitHub Issue #14 acceptance:
"自由文のparseに依存せず、schema不適合をエラーまたは要確認へ送れる") -- a
malformed response is a :class:`SchemaViolation` (see ``ai_provider.py``), not a
best-effort guess.

``pydantic`` is a validation library, not a web framework, an HTTP client, or an
external-service SDK, so using it here does not cross the boundary
``AGENTS.md`` "Architecture" draws for the domain layer (``api -> domain <-
adapters``); ``backend/tests/test_architecture.py`` enforces the actual
forbidden-import list.

Design decisions this schema encodes:

* Recognition confidence and Grading confidence are separate required fields
  (section 10: "文字認識 98% / 採点判断 63%" must be representable
  simultaneously) -- never collapsed into one number.
* ``rationale`` (採点根拠, section 16.5 "採点根拠") is required, not optional:
  Issue #14 asks for score / criterion result / comment / 根拠 / Grading
  Confidence to all be schema-validated.
* ``annotations`` never carry coordinates (section 12.1): the AI returns a
  ``target`` word/phrase and a ``type``; placement is the app's job.
  ``type`` is restricted to :class:`~auto_scoring.domain.models.AnnotationKind`,
  the fixed MVP set (business-rules-and-evaluation-data.md section 2 (5)):
  section 12.1's own illustrative JSON (``"type": "correction"``) predates
  that fixed set and is not itself a valid value -- a provider must return
  one of the enum's members (e.g. ``"underline"``) or the response is a
  schema violation, never silently accepted as an unsupported type that
  would fail later at persistence or rendering time.
* ``comment`` reuses the same character cap as human-confirmed annotation
  comments (``domain.models.MAX_COMMENT_CHARS``,
  business-rules-and-evaluation-data.md section 2 (6): "全角 120 文字").
* Every model is ``strict=True``: a provider sending ``"score": "4"`` or
  ``"confidence": "0.8"`` (a string standing in for a number) is a schema
  violation, not a value to coerce. Required text fields
  (``question_id`` / ``comment`` / ``rationale`` / criterion ``id`` /
  ``rationale`` / annotation ``target`` / ``type``) also reject a
  whitespace-only string, since ``min_length`` alone would let one through.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from auto_scoring.domain.models import MAX_COMMENT_CHARS, AnnotationKind, CriterionOutcome

#: A required string that must contain more than just whitespace. Plain
#: ``min_length=1`` accepts ``" "``; this also strips before checking length.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RecognitionOutput(BaseModel):
    """What the AI believes the OCR text says, and how sure it is (section 9.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    #: Not a ``_NonBlankStr``: an unreadable region is a legitimate empty
    #: string, matching ``domain.ocr.OcrResult`` (never a guessed value).
    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class GradingOutput(BaseModel):
    """The numeric grade and the AI's confidence in *that judgement* (section 10).

    Deliberately a separate model from :class:`RecognitionOutput`: the two
    confidences must never be read from the same field.
    """

    #: ``populate_by_name`` is deliberately *not* set: this is an untrusted
    #: wire boundary (AGENTS.md "Verification"), and the documented contract
    #: (simplified-design-specification.md section 9.2) is the camelCase
    #: alias only. Accepting the Python-style name too would let a provider
    #: that returns ``max_score`` instead of the documented ``maxScore`` pass
    #: as schema-valid, silently understating the real schema violation rate
    #: (code review finding).
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    score: int = Field(ge=0)
    max_score: int = Field(ge=0, alias="maxScore")
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _score_within_max(self) -> GradingOutput:
        if self.score > self.max_score:
            raise ValueError(f"score {self.score} exceeds maxScore {self.max_score}")
        return self


class CriterionResultOutput(BaseModel):
    """One rubric criterion's outcome, confidence, and required rationale."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: _NonBlankStr
    result: CriterionOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: _NonBlankStr


class AnnotationCandidate(BaseModel):
    """AI never returns PDF coordinates directly (section 12.1): ``target`` +
    ``type`` (+ optional comment) only -- placement is decided by the app.

    ``comment`` is required (and so cannot be blank -- ``_NonBlankStr``) when
    ``type`` is :attr:`~auto_scoring.domain.models.AnnotationKind.COMMENT`:
    a comment-kind annotation with no comment text has nothing to display,
    and ``domain.models.Annotation`` requires non-blank text to construct
    one later. Rejecting it here, at the untrusted response boundary, keeps
    that failure a schema violation instead of a crash at persistence or
    rendering time (code review finding).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target: _NonBlankStr
    type: AnnotationKind
    comment: Annotated[_NonBlankStr, Field(max_length=MAX_COMMENT_CHARS)] | None = None

    @model_validator(mode="after")
    def _comment_type_requires_comment_text(self) -> AnnotationCandidate:
        if self.type == AnnotationKind.COMMENT and self.comment is None:
            raise ValueError("annotation type 'comment' requires a non-blank 'comment' field")
        return self


class AIGradingResult(BaseModel):
    """The full structured output for one question (section 9.2 example)."""

    #: See :class:`GradingOutput` -- ``populate_by_name`` is deliberately
    #: off at this untrusted wire boundary: only the documented ``questionId``
    #: alias is accepted, not the Python-style ``question_id`` (code review
    #: finding).
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    question_id: Annotated[_NonBlankStr, Field(alias="questionId")]
    recognition: RecognitionOutput
    grading: GradingOutput
    criteria: tuple[CriterionResultOutput, ...] = Field(min_length=1)
    comment: Annotated[_NonBlankStr, Field(max_length=MAX_COMMENT_CHARS)]
    rationale: _NonBlankStr
    annotations: tuple[AnnotationCandidate, ...] = ()

    @model_validator(mode="after")
    def _criteria_ids_unique(self) -> AIGradingResult:
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("criteria contains duplicate ids")
        return self


def parse_ai_grading_result(raw: str | bytes) -> AIGradingResult:
    """Parse and validate one provider's raw JSON response.

    Raises ``pydantic.ValidationError`` on any schema violation (missing
    field, wrong type, score > maxScore, empty ``rationale``/``comment``,
    unknown extra field, ...). Callers (``ai_provider`` adapters and the PoC
    harness) wrap this in :class:`auto_scoring.domain.ai_provider.SchemaViolation`
    -- there is no fallback that extracts a partial answer from invalid JSON
    or free text.
    """
    return AIGradingResult.model_validate_json(raw)
