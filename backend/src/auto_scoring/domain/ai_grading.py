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
* ``comment`` reuses the same character cap as human-confirmed annotation
  comments (``domain.models.MAX_COMMENT_CHARS``,
  business-rules-and-evaluation-data.md section 2 (6): "全角 120 文字").
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from auto_scoring.domain.models import MAX_COMMENT_CHARS, CriterionOutcome


class RecognitionOutput(BaseModel):
    """What the AI believes the OCR text says, and how sure it is (section 9.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class GradingOutput(BaseModel):
    """The numeric grade and the AI's confidence in *that judgement* (section 10).

    Deliberately a separate model from :class:`RecognitionOutput`: the two
    confidences must never be read from the same field.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

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

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    result: CriterionOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)


class AnnotationCandidate(BaseModel):
    """AI never returns PDF coordinates directly (section 12.1): ``target`` +
    ``type`` (+ optional comment) only -- placement is decided by the app.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str = Field(min_length=1)
    type: str = Field(min_length=1)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_CHARS)


class AIGradingResult(BaseModel):
    """The full structured output for one question (section 9.2 example)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    question_id: str = Field(min_length=1, alias="questionId")
    recognition: RecognitionOutput
    grading: GradingOutput
    criteria: tuple[CriterionResultOutput, ...] = Field(min_length=1)
    comment: str = Field(min_length=1, max_length=MAX_COMMENT_CHARS)
    rationale: str = Field(min_length=1)
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
