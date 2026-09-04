"""Reusable ``AIProvider`` contract test (promoted artifact, Issue #14).

Any concrete provider added later (Gemini / Claude / GPT / local) subclasses
:class:`AIProviderContract`, supplies a provider plus a matching request, and
inherits the behavioural checks. ``ReplayAIProvider`` is the reference
implementation exercised here.
"""

from __future__ import annotations

import abc
from pathlib import Path

import pytest

from auto_scoring.domain.ai_grading import AIGradingResult
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
)
from poc.replay_provider import load_replay_provider

_FIXTURES = Path(__file__).resolve().parents[1] / "poc" / "fixtures"

_REQUEST = GradingRequest(
    question_id="q-symbol-select",
    question_text="次のうち正しいものを記号で答えなさい。",
    max_score=2,
    rubric=[{"id": "c1", "description": "正解記号「イ」と一致", "points": 2}],  # type: ignore[list-item]
    reference_answer="イ",
    ocr_text="イ",
)


class AIProviderContract(abc.ABC):
    """Behavioural contract every :class:`AIProvider` implementation must satisfy."""

    @abc.abstractmethod
    def make_provider(self) -> AIProvider: ...

    @abc.abstractmethod
    def make_request(self) -> GradingRequest: ...

    def test_is_an_ai_provider(self) -> None:
        assert isinstance(self.make_provider(), AIProvider)

    def test_descriptor_records_reproducibility_conditions(self) -> None:
        descriptor = self.make_provider().descriptor
        assert isinstance(descriptor, ProviderDescriptor)
        assert descriptor.provider and descriptor.model
        assert descriptor.temperature >= 0.0
        assert descriptor.structured_output_mode

    def test_grade_returns_schema_valid_result(self) -> None:
        response = self.make_provider().grade(self.make_request())
        assert isinstance(response, GradingResponse)
        assert isinstance(response.result, AIGradingResult)
        assert response.result.question_id == self.make_request().question_id
        # Recognition and grading confidence are both present and independent.
        assert 0.0 <= response.result.recognition.confidence <= 1.0
        assert 0.0 <= response.result.grading.confidence <= 1.0

    def test_unknown_question_raises_provider_unavailable(self) -> None:
        bad = self.make_request().model_copy(update={"question_id": "does-not-exist"})
        with pytest.raises(ProviderUnavailable):
            self.make_provider().grade(bad)


class TestReplayAIProviderContract(AIProviderContract):
    def make_provider(self) -> AIProvider:
        return load_replay_provider(_FIXTURES, "synthetic-a", "ocr_clean")

    def make_request(self) -> GradingRequest:
        return _REQUEST


def test_malformed_recording_raises_schema_violation() -> None:
    # synthetic-b / ocr_noisy / q-photosynthesis has grading.rationale removed.
    provider = load_replay_provider(_FIXTURES, "synthetic-b", "ocr_noisy")
    request = _REQUEST.model_copy(update={"question_id": "q-photosynthesis"})
    with pytest.raises(SchemaViolation) as excinfo:
        provider.grade(request)
    assert excinfo.value.provider == "synthetic-b"
    assert "rationale" in excinfo.value.reason
