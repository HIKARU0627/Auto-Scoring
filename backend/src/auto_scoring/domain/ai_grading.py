"""Structured AI grading output schema (簡易設計書 §9.2 / §10).

The AI never returns free text alone. Every grading response is validated against
these Pydantic models so that a downstream consumer never has to parse prose.

Two confidences are kept deliberately separate and must not be conflated
(簡易設計書 §10):

* **Recognition Confidence** — how likely the handwriting was read correctly
  (:class:`RecognitionOutcome.confidence`).
* **Grading Confidence** — how likely the score is correct *given* the read text
  (:class:`GradingOutcome.confidence`).

This module is part of the framework-free domain core. It depends only on
Pydantic (the project's validation/DTO library, ``technology-stack.md`` §3), not
on FastAPI, HTTP clients, or any AI-vendor SDK.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

CriterionResult = Literal["pass", "partial", "fail"]
"""Three-valued per-criterion outcome (業務ルール §0.1 / 簡易設計書 §9.2)."""

AnnotationKind = Literal["circle", "cross", "triangle", "underline", "box", "comment"]
"""Annotation kinds the AI may propose. Coordinates are never returned by the AI
(業務ルール §2(5)); only the target text, the kind, and an optional comment."""

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
"""A probability in the closed interval ``[0.0, 1.0]``."""


class _Model(BaseModel):
    """Shared config: reject unknown keys (so a malformed model response is a
    validation error, not a silently dropped field) and accept camelCase input
    (providers emit ``questionId`` / ``maxScore`` per 簡易設計書 §9.2)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )


class RecognitionOutcome(_Model):
    """What the AI believes the student wrote, and how sure it is of the reading."""

    text: str
    confidence: Confidence


class GradingOutcome(_Model):
    """The proposed score for the question and how sure the AI is of that score."""

    score: float = Field(ge=0.0)
    max_score: float = Field(gt=0.0)
    confidence: Confidence
    rationale: str = Field(min_length=1)
    """根拠: why this score was given. Required — never an empty string."""

    @model_validator(mode="after")
    def _score_within_bounds(self) -> GradingOutcome:
        if self.score > self.max_score:
            raise ValueError("score must not exceed max_score")
        return self


class CriterionEvaluation(_Model):
    """Result for a single rubric criterion, with its own confidence and 根拠."""

    id: str = Field(min_length=1)
    result: CriterionResult
    confidence: Confidence
    rationale: str = Field(min_length=1)
    """根拠 for this criterion's result. Required."""


class AnnotationSuggestion(_Model):
    """A markup suggestion. Position is resolved later from the OCR bounding box
    or falls back to the question comment area (簡易設計書 §12.4); the AI supplies
    only the semantic content."""

    target_text: str = Field(min_length=1)
    kind: AnnotationKind
    comment: str | None = Field(default=None, max_length=120)


class AIGradingResult(_Model):
    """Full structured output for grading one question (簡易設計書 §9.2).

    ``comment`` is capped at 120 full-width characters (業務ルール §2(6)); the AI
    output is a *candidate* only and is confirmed by a human (§2(17))."""

    question_id: str = Field(min_length=1)
    recognition: RecognitionOutcome
    grading: GradingOutcome
    criteria: list[CriterionEvaluation] = Field(min_length=1)
    comment: str = Field(max_length=120)
    annotations: list[AnnotationSuggestion] = Field(default_factory=list)


if __name__ == "__main__":  # pragma: no cover
    # Regenerate the data-less label schema (業務ルール §6.3):
    #   uv run python -m auto_scoring.domain.ai_grading
    import json
    import pathlib

    target = (
        pathlib.Path(__file__).resolve().parents[3]
        / "docs"
        / "schema"
        / "ai-grading-result.schema.json"
    )
    target.write_text(
        json.dumps(AIGradingResult.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target}")
