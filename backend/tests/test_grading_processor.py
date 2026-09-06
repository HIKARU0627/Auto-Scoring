"""Tests for `auto_scoring.jobs.grading_processor.GradingJobProcessor`
(Issue #20), against a real on-disk SQLite database and `LocalFileStore`,
with scriptable fake `OCRProvider`/`AIProvider` -- no real provider is
called (decisions A/B, business-rules-and-evaluation-data.md sections 3
(A)/(B), are still pending).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.ai_provider import (
    GradingAnnotationCandidate,
    GradingCriterionOutcome,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    SchemaViolation,
)
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.job_execution import ProcessingOutcome
from auto_scoring.domain.job_scheduling import plan_submission_jobs
from auto_scoring.domain.models import (
    AnnotationKind,
    AnswerImageStatus,
    ErrorCategory,
    GradingSource,
    JobKind,
    RubricCriterion,
)
from auto_scoring.domain.ocr import BoundingBox, ConfidenceBand, OcrResult, OcrToken
from auto_scoring.jobs.grading_processor import GradingJobProcessor, grade_result_id
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor
from tests.support import (
    at,
    make_answer_image,
    make_job,
    make_question,
    make_rubric,
    make_submission,
    make_test,
)

_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n-fake-question-crop-"

_DESCRIPTOR = ProviderDescriptor(
    provider="scripted-ai",
    model="scripted-model",
    version="test",
    prompt_version="v1",
    temperature=0.0,
    structured_output_mode="json_schema",
)


class _ScriptedOCRProvider:
    """Returns whatever text/confidence ``script`` was told to, once per call."""

    name = "scripted-ocr"

    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self._next: OcrResult | None = None

    def script(self, *, text: str, confidence: float) -> None:
        self._next = OcrResult(
            text=text,
            tokens=(
                OcrToken(
                    text=text,
                    bounding_box=BoundingBox(0.1, 0.1, 0.2, 0.05),
                    confidence=confidence,
                    band=ConfidenceBand.HIGH if confidence >= 0.8 else ConfidenceBand.LOW,
                ),
            ),
            provider=self.name,
        )

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        self.calls.append(image)
        assert self._next is not None, "no outcome scripted"
        return self._next


class _ScriptedAIProvider:
    """Returns/raises whatever ``script`` was told to, once per call."""

    name = "scripted-ai"

    def __init__(self) -> None:
        self.calls: list[GradingRequest] = []
        self._next: GradingResponse | Exception | None = None

    def script(self, outcome: GradingResponse | Exception) -> None:
        self._next = outcome

    def describe(self) -> ProviderDescriptor:
        return _DESCRIPTOR

    def grade(self, request: GradingRequest) -> GradingResponse:
        self.calls.append(request)
        assert self._next is not None, "no outcome scripted"
        if isinstance(self._next, Exception):
            raise self._next
        return self._next


def _response(
    *,
    question_id: str = "q-1",
    max_score: int = 5,
    score: int = 4,
    grading_confidence: float = 0.9,
    recognition_confidence: float = 0.95,
    criteria: tuple[GradingCriterionOutcome, ...] = (),
    annotations: tuple[GradingAnnotationCandidate, ...] = (),
) -> GradingResponse:
    return GradingResponse(
        question_id=question_id,
        recognition_text="模範的な解答",
        recognition_confidence=recognition_confidence,
        score=score,
        max_score=max_score,
        grading_confidence=grading_confidence,
        rationale="採点根拠",
        comment="総評コメント",
        criteria=criteria,
        annotations=annotations,
        descriptor=_DESCRIPTOR,
        latency_seconds=0.01,
    )


def _confirm_graph(
    session_factory: sessionmaker[Session],
    *,
    test_id: str = "test-1",
    question_ids: list[str],
    edges: list[DependencyEdge] | None = None,
) -> int:
    """Confirm a `DependencyGraph` over already-registered questions.

    Unlike `tests.support.seed_confirmed_dependency_graph`, this does not
    also insert a `Test`/`Question`/`Submission` -- these tests need to
    control `Question.model_answer` and add a `Rubric`, so the entities are
    seeded by each test itself and only the graph is built here.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        draft = DependencyGraph.from_candidates(
            id=f"{test_id}:v1",
            test_id=test_id,
            version=1,
            question_ids=question_ids,
            edges=edges or [],
            created_at=at(),
        )
        uow.dependency_graphs.save(draft)
        confirmed = draft.confirm(edges=edges or [], confirmed_at=at())
        assert uow.dependency_graphs.try_confirm(confirmed) is True
        uow.commit()
    return confirmed.version


@pytest.fixture
def ocr_provider() -> _ScriptedOCRProvider:
    provider = _ScriptedOCRProvider()
    provider.script(text="光合成について説明する。", confidence=0.96)
    return provider


@pytest.fixture
def ai_provider() -> _ScriptedAIProvider:
    return _ScriptedAIProvider()


@pytest.fixture
def processor(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> GradingJobProcessor:
    recognition = RecognitionJobProcessor(session_factory, store, ocr_provider)
    return GradingJobProcessor(session_factory, store, recognition, ai_provider)


def _seed(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    *,
    model_answer: str | None = "光合成は光エネルギーを使い二酸化炭素と水から有機物を作る反応である",
    with_rubric: bool = True,
) -> None:
    image = make_answer_image()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(model_answer=model_answer))
        if with_rubric:
            uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission())
        uow.answer_images.add(image)
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1"])
    if image.status is AnswerImageStatus.OK:
        store.write_atomic(store.root / image.image_path, _IMAGE_BYTES)


async def test_a_normal_grading_call_persists_a_usable_grade_result(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(_response())
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is True
    assert len(ai_provider.calls) == 1
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.grades.history("sub-1", "q-1")
    assert len(history) == 1
    grade = history[0]
    assert grade.source is GradingSource.AI
    assert grade.score.awarded == 4
    assert grade.score.maximum == 5
    assert grade.confidence == pytest.approx(0.9)
    assert grade.comment == "総評コメント"
    assert grade.rationale == "採点根拠"
    assert grade.provider == "scripted-ai"
    assert grade.model == "scripted-model"
    assert grade.prompt_version == "v1"
    assert grade.dependency_graph_version == 1


async def test_grading_request_includes_the_ocr_text_and_answer_image(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(_response())
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    await processor.process(job)

    request = ai_provider.calls[0]
    assert request.ocr_text == "光合成について説明する。"
    assert request.answer_image == _IMAGE_BYTES
    assert request.question_id == "q-1"
    assert request.max_score == 5


async def test_low_grading_confidence_is_not_usable_but_still_persisted(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(_response(grading_confidence=0.4))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.grades.history("sub-1", "q-1")) == 1


async def test_low_recognition_confidence_still_grades_but_is_not_usable(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #20 acceptance: either confidence below threshold -> needs
    review -- but a low-confidence (not unreadable) recognition still lets
    grading run, so both confidences actually exist to compare."""
    _seed(session_factory, store)
    ocr_provider.script(text="こうごうせい(推測)", confidence=0.3)
    ai_provider.script(_response(grading_confidence=0.95))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    assert len(ai_provider.calls) == 1  # grading was still attempted


async def test_needs_review_answer_image_skips_grading_entirely(
    session_factory: sessionmaker[Session],
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(model_answer="模範解答"))
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission())
        uow.answer_images.add(
            make_answer_image(status=AnswerImageStatus.NEEDS_REVIEW, reason="page_count_mismatch")
        )
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1"])
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False
    assert ai_provider.calls == []
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_schema_violation_fails_permanently_without_persisting_a_grade(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(SchemaViolation("provider returned invalid structured output"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    assert result.error_message is not None
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_mismatched_response_fails_permanently_without_persisting_a_grade(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(_response(question_id="some-other-question"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


@pytest.mark.parametrize(
    ("raised", "expected_category"),
    [
        (ProviderTimeoutError("boom"), ErrorCategory.TIMEOUT),
        (ProviderRateLimitedError("boom"), ErrorCategory.RATE_LIMITED),
        (ProviderServerError("boom"), ErrorCategory.SERVER_ERROR),
    ],
)
async def test_provider_errors_are_classified_and_never_leak_the_raw_message(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
    raised: Exception,
    expected_category: ErrorCategory,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(raised)
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is expected_category
    assert result.error_message is not None
    assert "boom" not in result.error_message
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_missing_model_answer_fails_permanently_without_calling_the_provider(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store, model_answer=None)
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    assert ai_provider.calls == []


async def test_missing_rubric_fails_permanently_without_calling_the_provider(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store, with_rubric=False)
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    assert ai_provider.calls == []


async def test_recognition_failure_short_circuits_grading(
    session_factory: sessionmaker[Session],
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #20's job never calls `AIProvider` at all when the OCR half
    (Issue #19) fails outright -- there is no text to grade."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(model_answer="模範解答"))
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission())
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1"])
    job = make_job(kind=JobKind.GRADING, question_id="q-1")  # no answer image recorded

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert ai_provider.calls == []


async def test_reprocessing_the_same_job_after_a_crash_does_not_call_the_provider_twice(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Mirrors `RecognitionJobProcessor`'s own crash-recovery idempotency
    (Issue #19 review round 1) for the grading half: the same `Job` row is
    handed to `process` again after an earlier call already committed a
    `GradeResult` but the queue never recorded SUCCEEDED."""
    _seed(session_factory, store)
    ai_provider.script(_response())
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.usable is True
    assert second.outcome is ProcessingOutcome.SUCCEEDED
    assert second.usable is True
    assert len(ai_provider.calls) == 1  # only the first call reached the provider
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.grades.history("sub-1", "q-1")) == 1
        grade = uow.grades.get(grade_result_id(job))
    assert grade is not None


async def test_annotation_candidates_are_persisted_as_ai_annotations(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    _seed(session_factory, store)
    ai_provider.script(
        _response(
            annotations=(
                GradingAnnotationCandidate(
                    target="こうごうせい", type=AnnotationKind.UNDERLINE, comment="誤字"
                ),
            )
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    await processor.process(job)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        annotations = uow.annotations.list_for("sub-1", "q-1")
    assert len(annotations) == 1
    assert annotations[0].source is GradingSource.AI
    assert annotations[0].kind is AnnotationKind.UNDERLINE
    assert annotations[0].anchor_text == "こうごうせい"
    assert annotations[0].comment == "誤字"


async def test_confidence_threshold_is_configurable(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    _seed(session_factory, store)
    recognition = RecognitionJobProcessor(session_factory, store, ocr_provider)
    strict_processor = GradingJobProcessor(
        session_factory,
        store,
        recognition,
        ai_provider,
        grading_settings=GradingSettings(confidence_threshold=0.99),
    )
    ai_provider.script(_response(grading_confidence=0.9))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await strict_processor.process(job)

    assert result.usable is False  # 0.9 < the configured 0.99 threshold


async def test_prerequisite_context_is_built_from_the_completed_prerequisite(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Issue #20 additional acceptance: a dependent question's grading call
    only sees the prerequisite's recognized text/score/criteria -- graph
    edges and DAG scheduling (Issue #26/#18) are what let this call happen
    at all, since the dependent's own Job stays BLOCKED until then."""
    image_q1 = make_answer_image(id="ai-q1", question_id="q-1")
    image_q2 = make_answer_image(
        id="ai-q2", question_id="q-2", image_path="submissions/sub-1/q2.png"
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="問1", model_answer="模範解答1"))
        uow.questions.add(make_question(id="q-2", number="問2", model_answer="問1の答えを2倍する"))
        uow.rubrics.add(make_rubric(id="rubric-1", question_id="q-1"))
        uow.rubrics.add(
            make_rubric(
                id="rubric-2",
                question_id="q-2",
                criteria=(
                    RubricCriterion(id="c-3", description="正確性", max_points=3, position=0),
                    RubricCriterion(id="c-4", description="表現", max_points=2, position=1),
                ),
            )
        )
        uow.submissions.add(make_submission())
        uow.answer_images.add(image_q1)
        uow.answer_images.add(image_q2)
        uow.commit()
    store.write_atomic(store.root / image_q1.image_path, _IMAGE_BYTES)
    store.write_atomic(store.root / image_q2.image_path, _IMAGE_BYTES)
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT, DependencyProvision.SCORE),
        rationale="問2は問1の答えに依存する",
    )
    _confirm_graph(session_factory, question_ids=["q-1", "q-2"], edges=[edge])

    recognition = RecognitionJobProcessor(session_factory, store, ocr_provider)
    processor = GradingJobProcessor(session_factory, store, recognition, ai_provider)

    # Grade the prerequisite (q-1) first, as the DAG requires.
    ai_provider.script(_response(question_id="q-1"))
    prerequisite_job = make_job(id="job-q1", kind=JobKind.GRADING, question_id="q-1")
    prerequisite_result = await processor.process(prerequisite_job)
    assert prerequisite_result.usable is True

    # Now grade the dependent (q-2); its request must carry q-1's context.
    ai_provider.script(_response(question_id="q-2"))
    dependent_job = make_job(id="job-q2", kind=JobKind.GRADING, question_id="q-2")
    dependent_result = await processor.process(dependent_job)

    assert dependent_result.usable is True
    dependent_request = ai_provider.calls[-1]
    assert len(dependent_request.prerequisite_context) == 1
    prerequisite_answer = dependent_request.prerequisite_context[0]
    assert prerequisite_answer.question_id == "q-1"
    assert prerequisite_answer.recognized_text == "光合成について説明する。"
    assert prerequisite_answer.score == 4
    assert prerequisite_answer.max_score == 5

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        dependent_grade = uow.grades.get(grade_result_id(dependent_job))
    assert dependent_grade is not None
    assert dependent_grade.dependency_graph_version == 1
    assert len(dependent_grade.context) == 1
    assert dependent_grade.context[0].question_id == "q-1"
    assert dependent_grade.context[0].recognition_result_id is not None
    assert dependent_grade.context[0].grade_result_id is not None


async def test_dependent_question_job_is_blocked_until_prerequisite_is_usable(
    session_factory: sessionmaker[Session],
) -> None:
    """Issue #20 additional acceptance: "前提未完了では依存Questionの
    AIProviderが呼ばれない" -- enforced structurally by the DAG scheduler
    (Issue #18/#26), verified here at the level `plan_submission_jobs`
    itself decides: a dependent question's `Job` is planned `BLOCKED`, never
    ready, when its prerequisite has not completed.
    """
    edge = DependencyEdge(
        from_question_id="q-1",
        to_question_id="q-2",
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale="問2は問1に依存する",
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="問1"))
        uow.questions.add(make_question(id="q-2", number="問2"))
        uow.submissions.add(make_submission())
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1", "q-2"], edges=[edge])

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        graph = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert graph is not None
    plans = {p.question_id: p for p in plan_submission_jobs(graph)}
    assert plans["q-1"].ready is True
    assert plans["q-2"].ready is False
    assert plans["q-2"].blocking_question_id == "q-1"
