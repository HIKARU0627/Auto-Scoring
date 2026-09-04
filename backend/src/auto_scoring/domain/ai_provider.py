"""The ``AIProvider`` port and its request/response contract (簡易設計書 §20).

The app only ever sees "grade this question" — never a vendor SDK. Concrete
providers (Gemini / Claude / GPT / local) are chosen after PoC 2 (GitHub Issue
#14) and live in ``adapters/``; the domain sees only this Protocol.

A provider MUST return a schema-valid :class:`~auto_scoring.domain.ai_grading.AIGradingResult`
or raise :class:`SchemaViolation`. Callers must not fall back to parsing free
text (受入条件, Issue #14).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from auto_scoring.domain.ai_grading import AIGradingResult


class SchemaViolation(Exception):
    """Raised when a provider's raw response cannot be coerced into
    :class:`AIGradingResult`. The caller routes the question to "要確認" /
    error rather than guessing (簡易設計書 §24 "AI 低 Confidence" と同様)."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider}: schema violation: {reason}")
        self.provider = provider
        self.reason = reason


class ProviderUnavailable(Exception):
    """Raised when the provider cannot be called at all (missing credentials,
    network failure, rate limit exhausted). Distinct from :class:`SchemaViolation`,
    which means the call succeeded but the payload was malformed."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RubricCriterion(_Model):
    """One scored criterion extracted from the grading manual (業務ルール §0.1)."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    points: float = Field(ge=0.0)


class GradingRequest(_Model):
    """The per-question payload sent for grading.

    Mirrors 業務ルール §2(2): question-scoped, minimal, and free of any student
    identifier. ``answer_image_ref`` is an opaque local handle to the cropped
    answer-area image, never a filename or the full page.
    """

    question_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    max_score: float = Field(gt=0.0)
    rubric: list[RubricCriterion] = Field(min_length=1)
    reference_answer: str
    ocr_text: str
    answer_image_ref: str | None = None


class TokenUsage(_Model):
    """Token counts for cost estimation."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ProviderDescriptor(_Model):
    """Reproducibility conditions recorded for every run (技術プローブ, Issue #14)."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str
    temperature: float = Field(ge=0.0)
    structured_output_mode: str
    """e.g. ``"json_schema"``, ``"tool_call"``, ``"response_format"``."""

    prompt_id: str
    """Stable identifier / hash of the prompt template used."""


class GradingResponse(_Model):
    """A successful grading call: the validated result plus run metadata."""

    result: AIGradingResult
    descriptor: ProviderDescriptor
    usage: TokenUsage | None = None
    latency_s: float | None = Field(default=None, ge=0.0)


@runtime_checkable
class AIProvider(Protocol):
    """Port for AI grading. Implementations live in ``adapters/``."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        """Static reproducibility metadata for this configured provider."""
        ...

    def grade(self, request: GradingRequest) -> GradingResponse:
        """Grade one question.

        Raises:
            SchemaViolation: the model replied but the payload was malformed.
            ProviderUnavailable: the provider could not be reached.
        """
        ...
