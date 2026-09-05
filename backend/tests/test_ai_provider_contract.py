"""Contract every :class:`AIProvider` implementation must satisfy.

``AIProviderContract`` is the reusable part: when PoC 2 (Issue #14) promotes a
real adapter (Gemini / Claude / GPT), add a test class that subclasses it and
overrides the ``provider`` fixture. ``_ReplayAIProvider`` is test-only
scaffolding that keeps the contract exercised until then -- it replays a
canned response instead of calling a real API, is not a grading candidate,
and must never move into ``src/`` (Issue #14 promotion condition: "採用
provider/model、fallback、再試行条件、cost上限が決定される" and
"不採用adapterを削除し、AIProvider contract testを残す").
"""

import json

import pytest
from pydantic import ValidationError

from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
    grading_response_from_result,
)
from auto_scoring.domain.models import AnnotationKind

_VALID_REQUEST = GradingRequest(
    question_id="q1",
    prompt_text="設問文",
    answer_image=b"\x89PNG\r\n\x1a\n",
    ocr_text="答案テキスト",
    model_answer="模範解答",
    rubric_text="採点基準",
    max_score=5,
)


class AIProviderContract:
    """Mix-in of provider-agnostic checks. Not collected on its own."""

    @pytest.fixture
    def provider(self) -> AIProvider:
        raise NotImplementedError

    def test_declares_a_name(self, provider: AIProvider) -> None:
        assert isinstance(provider, AIProvider)
        assert provider.name

    def test_describes_reproducibility_metadata(self, provider: AIProvider) -> None:
        """Issue #14 "再現条件": prompt/model/version/temperature must be recorded."""
        descriptor = provider.describe()
        assert isinstance(descriptor, ProviderDescriptor)
        assert descriptor.provider
        assert descriptor.model
        assert descriptor.temperature >= 0.0

    def test_grade_returns_response_with_separate_confidences(self, provider: AIProvider) -> None:
        response = provider.grade(_VALID_REQUEST)
        assert isinstance(response, GradingResponse)
        assert 0.0 <= response.recognition_confidence <= 1.0
        assert 0.0 <= response.grading_confidence <= 1.0
        assert 0 <= response.score <= response.max_score

    def test_grade_preserves_annotation_candidates(self, provider: AIProvider) -> None:
        """simplified-design-specification.md section 12.1: the app places
        annotation candidates on the PDF, so the AIProvider port must not
        drop them (Issue #14 review: "provider応答内のannotation候補を保持
        する")."""
        response = provider.grade(
            GradingRequest(
                question_id="with-annotations",
                prompt_text="設問文",
                answer_image=b"\x89PNG\r\n\x1a\n",
                ocr_text="行く",
                model_answer="模範解答",
                rubric_text="採点基準",
                max_score=5,
            )
        )
        assert response.annotations
        assert response.annotations[0].target == "行く"
        assert response.annotations[0].type == AnnotationKind.UNDERLINE

    def test_grade_receives_the_answer_image(self, provider: AIProvider) -> None:
        """simplified-design-specification.md section 9.1 lists both the
        answer image and the OCR text as inputs; a real adapter needs the
        image to derive a meaningful Recognition Confidence from handwriting
        (Issue #14 review: "採点リクエストに解答画像自体を含める")."""
        request = GradingRequest(
            question_id="q1",
            prompt_text="設問文",
            answer_image=b"\x89PNG\r\n\x1a\nnot-really-a-png",
            ocr_text="答案テキスト",
            model_answer="模範解答",
            rubric_text="採点基準",
            max_score=5,
        )
        assert isinstance(request.answer_image, bytes)
        assert request.answer_image
        # The port must accept a request carrying a real image without
        # requiring special-casing by callers.
        provider.grade(request)

    def test_schema_violation_never_falls_back_to_free_text_parsing(
        self, provider: AIProvider
    ) -> None:
        """A provider that returns invalid structured output must raise
        SchemaViolation, not synthesize a best-effort grade from the raw text
        (Issue #14 acceptance)."""
        with pytest.raises(SchemaViolation):
            provider.grade(
                GradingRequest(
                    question_id="malformed",
                    prompt_text="設問文",
                    answer_image=b"\x89PNG\r\n\x1a\n",
                    ocr_text="答案テキスト",
                    model_answer="模範解答",
                    rubric_text="採点基準",
                    max_score=5,
                )
            )


class _ReplayAIProvider:
    """Replays a canned response for every request except ``question_id ==
    "malformed"``, which simulates a provider returning invalid structured
    output. Test-only: never call a real API, never promote to ``src/``.
    """

    name = "replay-stub"

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model="replay-fixture",
            version="test",
            prompt_version="replay-prompt-v1",
            temperature=0.0,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        if request.question_id == "malformed":
            raw = json.dumps({"questionId": request.question_id, "grading": {"score": 1}})
        else:
            raw = json.dumps(
                {
                    "questionId": request.question_id,
                    "recognition": {"text": request.ocr_text, "confidence": 0.9},
                    "grading": {"score": 4, "maxScore": request.max_score, "confidence": 0.8},
                    "criteria": [
                        {
                            "id": "c1",
                            "result": "pass",
                            "confidence": 0.9,
                            "rationale": "模範解答と一致する要素を含む。",
                        }
                    ],
                    "comment": "概ね良好です。",
                    "rationale": "criterion c1を充足するため4点とした。",
                    "annotations": [
                        {"target": request.ocr_text, "type": "underline", "comment": "過去形"}
                    ],
                }
            )

        try:
            parsed_result = parse_ai_grading_result(raw)
        except ValidationError as exc:
            raise SchemaViolation("provider returned invalid structured output") from exc

        return grading_response_from_result(
            parsed_result, descriptor=self.describe(), latency_seconds=0.01
        )


class TestReplayAIProviderContract(AIProviderContract):
    @pytest.fixture
    def provider(self) -> _ReplayAIProvider:
        return _ReplayAIProvider()


def test_provider_unavailable_is_distinct_from_schema_violation() -> None:
    """A transport/rate-limit failure must not be reported as a bad grade."""
    assert issubclass(ProviderUnavailable, Exception)
    assert not issubclass(ProviderUnavailable, SchemaViolation)
    assert not issubclass(SchemaViolation, ProviderUnavailable)
