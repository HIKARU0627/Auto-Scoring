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

from auto_scoring.adapters.ai.null_provider import NullAIProvider
from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    PrerequisiteAnswer,
    ProviderDescriptor,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
    grading_response_from_result,
)
from auto_scoring.domain.dependency_graph import DependencyProvision
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

    def test_grade_preserves_the_recognized_text(self, provider: AIProvider) -> None:
        """simplified-design-specification.md section 16.5 lists "AI認識文字"
        as its own review-UI field, distinct from the confidence number
        (Issue #14 review: "GradingResponseにrecognized textを保持する").

        Not required to equal the request's ``ocr_text``: a real multimodal
        provider is given ``answer_image`` too (docs/poc-2-ai-grading.md
        section 2.1 -- exactly so it can derive Recognition Confidence from
        the handwriting itself, not just trust the given OCR text) and may
        legitimately correct an OCR misreading, so its own recognized
        reading can differ from what it was given (code review finding: this
        provider-agnostic contract test used to reject any conforming
        adapter that corrects OCR errors, since it required byte-for-byte
        equality with the input). See
        ``test_grading_response_from_result_preserves_a_corrected_recognition_text``
        below for the mapping-fidelity check this leaves in place.
        """
        response = provider.grade(_VALID_REQUEST)
        assert isinstance(response.recognition_text, str)

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


def test_null_ai_provider_declares_a_name_and_reproducibility_metadata() -> None:
    """`NullAIProvider` (Issue #20) is the real, shipped placeholder adapter
    until the provider chain decided in business-rules-and-evaluation-data.md
    section 3 (B) (Issue #81) is implemented.

    Not tested via the full `AIProviderContract` mixin: that mixin's
    ``test_schema_violation_never_falls_back_to_free_text_parsing`` relies on
    `_ReplayAIProvider`'s own ``question_id == "malformed"`` convention for
    simulating a bad response -- `NullAIProvider` never parses anything at
    all (it never calls a network), so there is no malformed response for it
    to raise on; forcing it to special-case that sentinel just to satisfy the
    test would be fabricated behaviour, not a real contract check.
    """
    provider = NullAIProvider()
    assert isinstance(provider, AIProvider)
    assert provider.name
    descriptor = provider.describe()
    assert isinstance(descriptor, ProviderDescriptor)
    assert descriptor.provider
    assert descriptor.model


def test_null_ai_provider_is_always_unusable_and_never_fabricates() -> None:
    """Issue #20: honest about not being configured, mirroring
    `NullOCRProvider` -- confidence 0.0, never a guessed score/reading."""
    provider = NullAIProvider()

    response = provider.grade(_VALID_REQUEST)

    assert response.grading_confidence == 0.0
    assert response.recognition_confidence == 0.0
    assert response.score == 0
    assert response.recognition_text == ""
    assert response.annotations == ()


def test_replay_provider_preserves_annotation_candidates() -> None:
    """simplified-design-specification.md section 12.1: the app places
    annotation candidates on the PDF, so the ``AIProvider`` port must not
    drop them (Issue #14 review: "provider応答内のannotation候補を保持
    する").

    Deliberately *not* part of ``AIProviderContract`` (code review finding):
    that mixin runs against every future real adapter too, and a generic
    request gives no guarantee a conforming model will propose any
    annotation for it -- ``AIGradingResult.annotations`` explicitly defaults
    to an empty tuple. Requiring a non-empty, specific annotation there
    would make a spec-compliant adapter fail non-deterministically. This
    replays ``_ReplayAIProvider``'s own known canned payload instead, to
    check the plumbing preserves annotations when a provider *does* return
    them.
    """
    provider = _ReplayAIProvider()
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


def test_grading_response_from_result_preserves_a_corrected_recognition_text() -> None:
    """Mapping-fidelity check, distinct from the provider-agnostic contract
    above (which no longer requires equality with the request's ``ocr_text``,
    since a real provider may legitimately correct it): builds an
    ``AIGradingResult`` whose ``recognition.text`` deliberately differs from
    any request's OCR text -- as a real multimodal provider's corrected
    reading would -- and confirms ``grading_response_from_result`` carries
    that exact value through, rather than silently dropping it or defaulting
    to something else."""
    raw = json.dumps(
        {
            "questionId": "q1",
            "recognition": {"text": "訂正後の認識結果", "confidence": 0.95},
            "grading": {"score": 4, "maxScore": 5, "confidence": 0.8},
            "criteria": [
                {"id": "c1", "result": "pass", "confidence": 0.9, "rationale": "根拠1"},
            ],
            "comment": "コメント",
            "rationale": "全体根拠",
            "annotations": [],
        }
    )
    parsed = parse_ai_grading_result(raw)
    descriptor = ProviderDescriptor(
        provider="test",
        model="test",
        version=None,
        prompt_version="v1",
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    response = grading_response_from_result(parsed, descriptor=descriptor, latency_seconds=0.0)
    assert response.recognition_text == "訂正後の認識結果"


def test_provider_unavailable_is_distinct_from_schema_violation() -> None:
    """A transport/rate-limit failure must not be reported as a bad grade."""
    assert issubclass(ProviderUnavailable, Exception)
    assert not issubclass(ProviderUnavailable, SchemaViolation)
    assert not issubclass(SchemaViolation, ProviderUnavailable)


@pytest.mark.parametrize(
    "exc_type", [ProviderTimeoutError, ProviderRateLimitedError, ProviderServerError]
)
def test_provider_unavailable_subclasses_are_classifiable(exc_type: type[Exception]) -> None:
    """Issue #20: timeout/429/5xx must be distinguishable so
    `auto_scoring.jobs.grading_processor.GradingJobProcessor` can route each
    to the matching `ErrorCategory` for the queue's retry policy."""
    assert issubclass(exc_type, ProviderUnavailable)
    assert not issubclass(exc_type, SchemaViolation)


def test_prerequisite_answer_requires_recognized_text_when_declared() -> None:
    with pytest.raises(ValueError, match="recognized_text"):
        PrerequisiteAnswer(
            question_id="q-1", provides=(DependencyProvision.RECOGNIZED_TEXT,), recognized_text=None
        )


def test_prerequisite_answer_accepts_a_blank_recognized_text() -> None:
    """An empty recognized text is the legitimate prerequisite reading of a
    question the student left blank -- must not be rejected."""
    PrerequisiteAnswer(
        question_id="q-1", provides=(DependencyProvision.RECOGNIZED_TEXT,), recognized_text=""
    )


def test_prerequisite_answer_requires_score_when_declared() -> None:
    with pytest.raises(ValueError, match="score"):
        PrerequisiteAnswer(question_id="q-1", provides=(DependencyProvision.SCORE,))


def test_prerequisite_answer_rejects_score_above_max() -> None:
    with pytest.raises(ValueError, match="outside range"):
        PrerequisiteAnswer(
            question_id="q-1", provides=(DependencyProvision.SCORE,), score=6, max_score=5
        )


def test_prerequisite_answer_requires_criteria_when_declared() -> None:
    with pytest.raises(ValueError, match="criteria"):
        PrerequisiteAnswer(question_id="q-1", provides=(DependencyProvision.CRITERION_RESULT,))


def test_prerequisite_answer_rejects_a_blank_question_id() -> None:
    with pytest.raises(ValueError, match="question_id"):
        PrerequisiteAnswer(
            question_id="  ",
            provides=(DependencyProvision.RECOGNIZED_TEXT,),
            recognized_text="answer",
        )


def test_prerequisite_answer_requires_at_least_one_provision() -> None:
    with pytest.raises(ValueError, match="provides"):
        PrerequisiteAnswer(question_id="q-1", provides=())


def test_grading_request_defaults_to_no_prerequisite_context() -> None:
    request = GradingRequest(**_VALID_REQUEST_KWARGS)  # type: ignore[arg-type]
    assert request.prerequisite_context == ()


def test_grading_request_carries_prerequisite_context() -> None:
    prerequisite = PrerequisiteAnswer(
        question_id="q-0",
        provides=(DependencyProvision.RECOGNIZED_TEXT, DependencyProvision.SCORE),
        recognized_text="前提の答案",
        score=3,
        max_score=5,
    )
    kwargs = dict(_VALID_REQUEST_KWARGS)
    kwargs["prerequisite_context"] = (prerequisite,)
    request = GradingRequest(**kwargs)  # type: ignore[arg-type]
    assert request.prerequisite_context == (prerequisite,)


_VALID_DESCRIPTOR_KWARGS: dict[str, object] = {
    "provider": "p",
    "model": "m",
    "version": None,
    "prompt_version": "v1",
    "temperature": 0.0,
    "structured_output_mode": "json_schema",
}


@pytest.mark.parametrize("field", ["provider", "model", "prompt_version", "structured_output_mode"])
def test_descriptor_rejects_a_blank_required_field_at_construction(field: str) -> None:
    """Code review finding: a real ``AIProvider`` adapter builds
    ``ProviderDescriptor`` directly from its own ``describe()``, bypassing
    the ``--dataset`` JSON boundary (``_DescriptorInput``) entirely -- a
    blank value must be impossible to construct, not merely rejected when it
    happens to arrive as recorded JSON."""
    kwargs = dict(_VALID_DESCRIPTOR_KWARGS)
    kwargs[field] = "   "
    with pytest.raises(ValueError):
        ProviderDescriptor(**kwargs)  # type: ignore[arg-type]


def test_descriptor_rejects_a_whitespace_only_version() -> None:
    kwargs = dict(_VALID_DESCRIPTOR_KWARGS)
    kwargs["version"] = "  "
    with pytest.raises(ValueError):
        ProviderDescriptor(**kwargs)  # type: ignore[arg-type]


def test_descriptor_accepts_a_none_version() -> None:
    ProviderDescriptor(**_VALID_DESCRIPTOR_KWARGS)  # type: ignore[arg-type]


@pytest.mark.parametrize("temperature", [float("inf"), float("-inf"), float("nan"), -0.1])
def test_descriptor_rejects_a_non_finite_or_negative_temperature(temperature: float) -> None:
    kwargs = dict(_VALID_DESCRIPTOR_KWARGS)
    kwargs["temperature"] = temperature
    with pytest.raises(ValueError):
        ProviderDescriptor(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("temperature", [True, False])
def test_descriptor_rejects_a_bool_temperature(temperature: bool) -> None:
    """Code review finding: ``bool`` is a subclass of Python's ``int``, so
    ``math.isfinite(True)`` and ``True >= 0`` both pass silently -- a real
    adapter constructing ``ProviderDescriptor`` directly (bypassing the
    ``--dataset`` JSON boundary, where strict-mode already rejects a JSON
    ``true``/``false`` here) must not be able to record a bare bool as its
    temperature either."""
    kwargs = dict(_VALID_DESCRIPTOR_KWARGS)
    kwargs["temperature"] = temperature
    with pytest.raises(ValueError):
        ProviderDescriptor(**kwargs)  # type: ignore[arg-type]


_VALID_REQUEST_KWARGS: dict[str, object] = {
    "question_id": "q1",
    "prompt_text": "設問文",
    "answer_image": b"\x89PNG\r\n\x1a\n",
    "ocr_text": "答案テキスト",
    "model_answer": "模範解答",
    "rubric_text": "採点基準",
    "max_score": 5,
}


@pytest.mark.parametrize("field", ["question_id", "prompt_text", "model_answer", "rubric_text"])
def test_grading_request_rejects_a_blank_required_field_at_construction(field: str) -> None:
    """Code review finding: a real adapter builds ``GradingRequest`` directly,
    bypassing any pydantic boundary -- a blank field must be impossible to
    construct, not merely rejected when it happens to arrive some other way."""
    kwargs = dict(_VALID_REQUEST_KWARGS)
    kwargs[field] = "   "
    with pytest.raises(ValueError):
        GradingRequest(**kwargs)  # type: ignore[arg-type]


def test_grading_request_accepts_a_blank_ocr_text() -> None:
    """An empty ``ocr_text`` is the legitimate reading of a question the
    student left blank -- unlike the other text fields, it must not be
    rejected (mirrors ``GradingInputRecord.ocr_clean``)."""
    kwargs = dict(_VALID_REQUEST_KWARGS)
    kwargs["ocr_text"] = ""
    GradingRequest(**kwargs)  # type: ignore[arg-type]


def test_grading_request_rejects_an_empty_answer_image() -> None:
    kwargs = dict(_VALID_REQUEST_KWARGS)
    kwargs["answer_image"] = b""
    with pytest.raises(ValueError):
        GradingRequest(**kwargs)  # type: ignore[arg-type]


def test_grading_request_rejects_a_negative_max_score() -> None:
    kwargs = dict(_VALID_REQUEST_KWARGS)
    kwargs["max_score"] = -1
    with pytest.raises(ValueError):
        GradingRequest(**kwargs)  # type: ignore[arg-type]
