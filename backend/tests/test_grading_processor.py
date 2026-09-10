"""Tests for `auto_scoring.jobs.grading_processor.GradingJobProcessor`
(Issue #20), against a real on-disk SQLite database and `LocalFileStore`,
with scriptable fake `OCRProvider`/`AIProvider` -- no real provider is
called (the services decisions A/B name in business-rules-and-evaluation-
data.md sections 3 (A)/(B) have no adapters wired up yet).
"""

from __future__ import annotations

import logging

import openpyxl
import pytest
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.ai.unconfigured_provider import UnconfiguredAIProvider
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.ocr.unconfigured_provider import UnconfiguredOCRProvider
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.ai_provider import (
    GradingAnnotationCandidate,
    GradingCriterionOutcome,
    GradingRequest,
    GradingResponse,
    ProviderAttempt,
    ProviderDescriptor,
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.job_execution import ProcessingOutcome
from auto_scoring.domain.job_scheduling import plan_submission_jobs
from auto_scoring.domain.models import (
    AnnotationKind,
    AnswerImageFinding,
    AnswerImageStatus,
    CriterionOutcome,
    ErrorCategory,
    GradingSource,
    JobKind,
    ReviewAction,
    RubricCriterion,
    Score,
    find_answer_image,
)
from auto_scoring.domain.ocr import BoundingBox, ConfidenceBand, OcrResult, OcrToken
from auto_scoring.domain.submission_intake import NOT_THE_ANSWER_CROP_REASON
from auto_scoring.domain.test_material import TestMaterial
from auto_scoring.jobs.grading_processor import (
    GradingJobProcessor,
    grade_result_id,
    grading_recognition_id,
)
from auto_scoring.jobs.grading_settings import GradingSettings
from auto_scoring.jobs.recognition_processor import RecognitionJobProcessor
from auto_scoring.jobs.recognition_settings import RecognitionSettings
from tests.support import (
    at,
    make_answer_image,
    make_grade,
    make_job,
    make_question,
    make_recognition,
    make_review,
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


#: Matches `tests.support.make_rubric()`'s default criteria ids -- the
#: mismatch check (Issue #20 review, P1) requires a response's criteria to
#: correspond exactly to the registered rubric, so every test that grades
#: against the default rubric needs a response carrying these same ids.
_DEFAULT_RUBRIC_CRITERIA = (
    GradingCriterionOutcome(
        criterion_id="c-1", outcome=CriterionOutcome.PASS, confidence=0.9, rationale="根拠1"
    ),
    GradingCriterionOutcome(
        criterion_id="c-2", outcome=CriterionOutcome.PASS, confidence=0.9, rationale="根拠2"
    ),
)


def _response(
    *,
    question_id: str = "q-1",
    max_score: int = 5,
    score: int = 4,
    grading_confidence: float = 0.9,
    recognition_confidence: float = 0.95,
    criteria: tuple[GradingCriterionOutcome, ...] = _DEFAULT_RUBRIC_CRITERIA,
    annotations: tuple[GradingAnnotationCandidate, ...] = (),
    answer_image_finding: AnswerImageFinding | None = None,
) -> GradingResponse:
    return GradingResponse(
        question_id=question_id,
        answer_image_finding=answer_image_finding,
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


def _register_annotation_resource(
    session_factory: sessionmaker[Session], store: LocalFileStore, rows: list[list[str]]
) -> None:
    """Attach a 添削資料 Excel to the seeded test, the way Issue #101's intake
    does. The workbook is written here from invented strings -- the real
    material may not enter this repository (``AGENTS.md`` "Security")."""
    stored_path = "tests/test-1/03_annotation.xlsx"
    path = store.resolve_stored_path(stored_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.test_materials.add(
            TestMaterial(
                id="material-1",
                test_id="test-1",
                role=MaterialRole.ANNOTATION_RESOURCE,
                stored_path=stored_path,
                sha256="0" * 64,
                size_bytes=path.stat().st_size,
                original_filename=None,
                created_at=at(),
            )
        )
        uow.commit()


_CATALOG_ROWS = [
    ["架空の講座名"],
    ["回数", "問題番号", "生徒の誤り方・現状", "採点基準", "赤入れ案"],
    ["第1回", "問1", "架空の誤答A", "3点減", "架空の赤入れA"],
]


async def test_a_registered_excel_annotation_resource_reaches_the_grading_call(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #106 end to end: the 添削資料 catalogue is on the request the
    provider is called with, so the grading prompt can carry it."""
    _seed(session_factory, store)
    _register_annotation_resource(session_factory, store, _CATALOG_ROWS)
    ai_provider.script(_response())

    await processor.process(make_job(kind=JobKind.GRADING, question_id="q-1"))

    (entry,) = ai_provider.calls[0].error_catalog
    assert entry.mistake == "架空の誤答A"
    assert entry.deduction == "3点減"
    assert entry.red_ink == "架空の赤入れA"


async def test_grading_proceeds_without_a_catalogue_and_says_why(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """添削資料 is optional but recommended (Issue #95 decision 3), so a file
    whose columns are not recognized must not fail the job -- and must not be
    indistinguishable from having registered nothing either."""
    _seed(session_factory, store)
    _register_annotation_resource(
        session_factory, store, [["日付", "担当"], ["2026-09-10", "架空の氏名"]]
    )
    ai_provider.script(_response())

    with caplog.at_level(logging.WARNING):
        result = await processor.process(make_job(kind=JobKind.GRADING, question_id="q-1"))

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert ai_provider.calls[0].error_catalog == ()
    assert any(
        "no catalogue could be read" in record.getMessage()
        and "no_header_row" in record.getMessage()
        for record in caplog.records
    )


async def test_a_test_with_no_annotation_resource_sends_an_empty_catalogue(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """The ordinary case, pinned so Issue #106 cannot start requiring a
    材料 that the required-input list (business-rules section 2 (18)) does not
    require."""
    _seed(session_factory, store)
    ai_provider.script(_response())

    result = await processor.process(make_job(kind=JobKind.GRADING, question_id="q-1"))

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert ai_provider.calls[0].error_catalog == ()


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


async def test_a_host_with_no_ocr_still_grades_and_still_releases_dependents(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Issue #114, the shipped composition before this change.

    `api.sidecar` never injected an `ocr_provider`, so every install ran the
    placeholder: text always empty, Recognition Confidence always 0.0, and
    therefore ``usable=False`` on every question and every dependent
    `BLOCKED` until a human pressed /resume on it. Grading itself worked --
    the provider is multimodal and reads the crop -- which is why the gap
    survived: scores came out, only the chain stopped.

    What must hold now: grading still runs (with an empty ``ocr_text``, the
    OCR reading being merely "得られていれば" per design section 8.1.1), and
    the question comes out usable on the strength of the two confidences
    that do exist.
    """
    recognition = RecognitionJobProcessor(
        session_factory,
        store,
        UnconfiguredOCRProvider("AUTO_SCORING_DOCUMENT_AI_PROCESSOR is not set"),
    )
    processor = GradingJobProcessor(session_factory, store, recognition, ai_provider)
    _seed(session_factory, store)
    ai_provider.script(_response())
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is True
    assert ai_provider.calls[0].ocr_text == ""
    assert ai_provider.calls[0].answer_image == _IMAGE_BYTES
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.grades.history("sub-1", "q-1")) == 1
        # No OCR row -- only the grader's own reading. That absence is how
        # "no OCR here" stays distinguishable from "the OCR read it and got
        # nothing" (Issue #114 acceptance 8).
        readings = uow.recognitions.history("sub-1", "q-1")
    assert [reading.id for reading in readings] == [grading_recognition_id(job)]


async def test_a_host_with_no_ocr_is_still_gated_by_the_grader_s_own_confidence(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Dropping the OCR term is not the same as dropping the gate.

    With no OCR reading to compare against, the two remaining checks of
    design section 8.1.3 -- the grading AI's own reading, and its grading
    confidence -- are what stands between an unread answer and an
    auto-released dependent. Both still block.
    """
    recognition = RecognitionJobProcessor(
        session_factory, store, UnconfiguredOCRProvider("not configured")
    )
    processor = GradingJobProcessor(session_factory, store, recognition, ai_provider)
    _seed(session_factory, store)
    ai_provider.script(_response(recognition_confidence=0.2))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False


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


async def test_a_skipped_grading_says_on_its_own_row_why_it_did_nothing(
    session_factory: sessionmaker[Session],
    processor: GradingJobProcessor,
) -> None:
    """Issue #164's acceptance criterion 2: stop finishing in 0.013 seconds
    with nothing to show for it.

    Measured on one real run, **23 of 37 grading jobs** were
    ``succeeded`` / ``usable=0`` / ``last_error`` NULL, every one of them
    because the question had no answer area, and none of them
    distinguishable on the queue from work that was actually done. The value
    is `AnswerImage.reason`'s fixed vocabulary -- the same strings
    `app/lib/core/grading_failure_reason.dart` already reads off
    ``last_error`` -- so nothing from the paper reaches it.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(model_answer="模範解答"))
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission())
        uow.answer_images.add(
            make_answer_image(
                status=AnswerImageStatus.NEEDS_REVIEW, reason="no_answer_area_defined"
            )
        )
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1"])

    result = await processor.process(make_job(kind=JobKind.GRADING, question_id="q-1"))

    assert result.skipped_reason == "no_answer_area_defined"


async def test_a_crop_the_grader_says_is_not_the_answer_produces_no_grade(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #136, the whole point of it.

    On a real 8-subject run, 7 of the 14 grades produced were 0 点 at
    confidence 1.00 against a crop that was not that question's answer, and
    the review screen showed them exactly like a correct 0. The grade row is
    what makes the two look alike, so when the grader itself reports the
    image is not this question's answer, no grade row is written.
    """
    _seed(session_factory, store)
    ai_provider.script(
        _response(
            score=0,
            grading_confidence=1.0,
            answer_image_finding=AnswerImageFinding.NOT_THE_ANSWER,
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    # Retrying re-sends identical bytes to an identical model: there is
    # nothing a second attempt could learn.
    assert result.error_category is ErrorCategory.PERMANENT
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_a_crop_the_grader_says_is_not_the_answer_is_flagged_for_a_human(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """The verdict lands on the crop's own row, in intake's vocabulary.

    Two things follow from that, and both are asserted here: the reason
    reaches the review screen through the job's ``last_error`` (which is how
    the app knows to send the reviewer to the 回答欄, not to the score box),
    and a second attempt spends no provider call, because the crop is now
    `AnswerImageStatus.NEEDS_REVIEW` like any other untrusted one.
    """
    _seed(session_factory, store)
    ai_provider.script(_response(answer_image_finding=AnswerImageFinding.NOT_THE_ANSWER))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_message is not None
    assert NOT_THE_ANSWER_CROP_REASON in result.error_message
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        images = uow.answer_images.list_for_submission("sub-1")
    image = find_answer_image(images, "q-1")
    assert image is not None
    assert image.status is AnswerImageStatus.NEEDS_REVIEW
    assert image.reason == NOT_THE_ANSWER_CROP_REASON

    # The re-run: same job, and the provider is not called a second time.
    assert len(ai_provider.calls) == 1
    second = await processor.process(job)
    assert second.outcome is ProcessingOutcome.SUCCEEDED
    assert second.usable is False
    assert len(ai_provider.calls) == 1
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_not_the_answer_wins_over_a_score_the_same_response_awarded(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """A response that says both things is contradictory, and the score is
    not the half to believe.

    Nothing observed on real material has produced this combination -- every
    such response scored 0 -- but leaving it undecided would mean the answer
    comes from whichever branch happened to run first. A score derived from
    an image the grader says is not this question's answer is worth no more
    at 5/5 than at 0/5.
    """
    _seed(session_factory, store)
    ai_provider.script(_response(score=5, answer_image_finding=AnswerImageFinding.NOT_THE_ANSWER))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_a_blank_answer_area_is_still_graded_and_the_finding_is_recorded(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """ "The answer is blank" is not "this is not the answer" (Issue #136).

    A student who leaves a question empty is an ordinary answer sheet, and
    its 0 may well be correct -- so ``blank`` changes nothing about how the
    grade is produced today. It is *stored*, though: whether ``blank``
    should also stop a grade depends on how often questions are genuinely
    unanswered, and that number has to be countable from data already on
    disk rather than costing another full run on real material.
    """
    _seed(session_factory, store)
    ai_provider.script(
        _response(score=0, grading_confidence=1.0, answer_image_finding=AnswerImageFinding.BLANK)
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.grades.history("sub-1", "q-1")
        images = uow.answer_images.list_for_submission("sub-1")
    assert len(history) == 1
    assert history[0].answer_image_finding is AnswerImageFinding.BLANK
    # And the crop is left alone: nothing about it was found wanting.
    image = find_answer_image(images, "q-1")
    assert image is not None
    assert image.status is AnswerImageStatus.OK


async def test_a_provider_that_reports_no_finding_grades_exactly_as_before(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Absence is not a claim (Issue #136).

    A provider that ignores ``answerImage`` -- and every response recorded
    before the field existed -- must keep behaving the way it does today,
    not be credited with having vouched for the crop.
    """
    _seed(session_factory, store)
    ai_provider.script(_response(answer_image_finding=None))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is True
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        history = uow.grades.history("sub-1", "q-1")
    assert len(history) == 1
    assert history[0].answer_image_finding is None


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


async def test_schema_violation_records_which_field_failed_and_why(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Issue #121: `Job.last_error` stopped at "[gemini SchemaViolation]",
    and the sidecar log said nothing at all -- so a question that failed
    permanently on every retry could only be explained by capturing the
    provider's response by hand.

    The field path and pydantic's error code are literals of this project's
    own schema, so both belong in the diagnosis `ProviderAttempt` assembles
    (Issue #97 round 4's rule, not an exception to it).
    """
    _seed(session_factory, store)
    ai_provider.name = "gemini"
    ai_provider.script(
        SchemaViolation(
            "provider returned invalid structured output",
            detail="annotations.0.comment: string_too_long",
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    with caplog.at_level(logging.WARNING):
        result = await processor.process(job)

    assert result.error_message is not None
    assert "annotations.0.comment: string_too_long" in result.error_message
    # A permanent failure that leaves no `GradeResult` behind must also
    # leave a line in the sidecar log -- the live run found none, because a
    # single-provider setup never goes through `FallbackAIProvider`, which
    # until now was the only thing that logged one.
    assert any(
        record.levelno == logging.WARNING and result.error_message in record.getMessage()
        for record in caplog.records
    )


async def test_a_response_scored_out_of_the_wrong_total_is_rejected_before_persisting(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """A response whose ``maxScore`` is not this question's registered points
    is grading a different scale, and "4" out of the wrong total is not a
    grade -- never persisted.

    There is no companion "wrong question id" case any more: since Issue
    #117 the response carries no question identifier at all, so
    `GradingResponse.question_id` is filled in from the request that was
    sent rather than copied out of the answer. What that check used to
    catch is now impossible to express."""
    _seed(session_factory, store)
    ai_provider.script(_response(max_score=99))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "gemini ProviderUnavailable status=401"),
        (403, "gemini ProviderUnavailable status=403"),
        (404, "gemini ProviderUnavailable status=404"),
    ],
)
async def test_a_failed_call_records_which_provider_failed_and_how(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
    status: int,
    expected: str,
) -> None:
    """Issue #97 review round 4: a revoked ADC login (401), a project without
    aiplatform enabled (403) and a misspelled ``AUTO_SCORING_GEMINI_MODEL``
    (404) must not all read as "call failed" -- they are the three things a
    first launch on a new machine actually hits, and they need different
    answers from the operator.

    `Job.last_error` is where this has to live: on a total failure there is
    no `GradeResult` to carry the provider triple, and this string is what
    the jobs API returns.
    """
    _seed(session_factory, store)
    ai_provider.name = "gemini"
    ai_provider.script(ProviderUnavailable("request failed", status_code=status))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_message is not None
    assert expected in result.error_message


async def test_an_exhausted_chain_records_every_link_in_last_error(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """ "Vertex was 403 so it fell through to OpenRouter, which was 401" --
    the intermediate links, which the last exception on its own cannot
    describe (`FallbackAIProvider` fills them in)."""
    _seed(session_factory, store)
    failure = ProviderUnavailable("request failed", status_code=401)
    failure.attempts = (
        ProviderAttempt(provider="gemini", error="ProviderUnavailable", status_code=403),
        ProviderAttempt(provider="openrouter", error="ProviderUnavailable", status_code=401),
    )
    ai_provider.script(failure)
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_message is not None
    assert "gemini ProviderUnavailable status=403" in result.error_message
    assert "openrouter ProviderUnavailable status=401" in result.error_message


async def test_the_recorded_diagnosis_is_assembled_not_filtered(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """The rule rounds 1-3 arrived at, applied to the diagnosis round 4 asked
    for: `Job.last_error` is built from a literal provider id, an exception
    class name and a number. Even an adapter whose *message* quotes
    configuration cannot put it there, because the message is not used at
    all.
    """
    _seed(session_factory, store)
    ai_provider.script(
        ProviderUnavailable(
            "gemini request failed for project sk-secret-pasted-DO-NOT-USE", status_code=403
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_message is not None
    assert "status=403" in result.error_message
    assert "sk-secret-pasted-DO-NOT-USE" not in result.error_message


async def test_an_unconfigured_host_fails_the_job_and_writes_no_grade(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
) -> None:
    """Issue #97: on a host where no AI provider could be built, a grading
    Job must end FAILED/`PERMANENT` -- not SUCCEEDED with a 0-point,
    confidence-0.0 `GradeResult` that reads, in the review UI, exactly like a
    real provider that graded the answer and awarded nothing.

    `PERMANENT` because no number of retries installs credentials on this
    machine; the reason belongs to the whole app (``GET
    /grading/availability``), not to each question's `last_error`.
    """
    _seed(session_factory, store)
    recognition = RecognitionJobProcessor(session_factory, store, ocr_provider)
    processor = GradingJobProcessor(
        session_factory,
        store,
        recognition,
        UnconfiguredAIProvider("AUTO_SCORING_AI_GRADING_TRANSPORT is required"),
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    # The reason names a variable, but `last_error` is built from the
    # provider's `name` alone (`GradingJobProcessor._failed`) -- assert the
    # configuration text does not travel into per-question storage.
    assert result.error_message is not None
    assert "AUTO_SCORING_AI_GRADING_TRANSPORT" not in result.error_message
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


async def test_rate_limited_retry_after_reaches_the_processing_result(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #153: a 429's parsed ``Retry-After`` (already resolved to
    seconds by the adapter -- `ProviderRateLimitedError.retry_after_seconds`)
    must survive the trip through `GradingJobProcessor._failed` into
    `ProcessingResult`, so `auto_scoring.jobs.queue.JobQueueService` can
    honour it instead of guessing a delay."""
    _seed(session_factory, store)
    ai_provider.script(ProviderRateLimitedError("boom", retry_after_seconds=30.0))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_category is ErrorCategory.RATE_LIMITED
    assert result.retry_after_seconds == 30.0


async def test_timeout_never_carries_a_retry_after(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """A TIMEOUT/SERVER_ERROR failure has no `Retry-After` concept -- must
    not carry one through even if some future adapter mistakenly set it."""
    _seed(session_factory, store)
    ai_provider.script(ProviderTimeoutError("boom"))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.error_category is ErrorCategory.TIMEOUT
    assert result.retry_after_seconds is None


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


async def test_grading_processor_missing_answer_image_carries_submission_review_reason(
    session_factory: sessionmaker[Session],
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #215: Missing answer image in grading carries submission review_reason
    to last_error."""
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(model_answer="模範解答"))
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission(review_reason="extra_pages:3>2"))
        uow.commit()
    _confirm_graph(session_factory, question_ids=["q-1"])
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    assert result.error_message == "no answer image recorded for this question (extra_pages:3>2)"
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


async def test_recognition_confidence_is_gated_by_the_recognition_threshold_not_grading(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Issue #20 review, P1: recognition confidence must never be compared
    against `GradingSettings`'s threshold. A recognition confidence that
    clears a lenient grading threshold but not the (separately configured,
    stricter) recognition threshold must still be unusable.
    """
    _seed(session_factory, store)
    ocr_provider.script(text="やや不鮮明な答案", confidence=0.7)
    recognition = RecognitionJobProcessor(
        session_factory, store, ocr_provider, settings=RecognitionSettings(confidence_threshold=0.9)
    )
    processor = GradingJobProcessor(
        session_factory,
        store,
        recognition,
        ai_provider,
        grading_settings=GradingSettings(confidence_threshold=0.5),
    )
    ai_provider.script(_response(grading_confidence=0.95, recognition_confidence=0.95))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    # 0.7 clears the 0.5 grading threshold but not the 0.9 recognition
    # threshold -- the old bug compared 0.7 against 0.5 and returned usable.
    assert result.usable is False


async def test_reprocessing_after_a_crash_reuses_the_persisted_recognition_threshold_check(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """The idempotent-replay branch (an existing `GradeResult` already
    persisted) must apply the same recognition-vs-grading threshold
    separation as the first-attempt branch (Issue #20 review, P1)."""
    _seed(session_factory, store)
    ocr_provider.script(text="やや不鮮明な答案", confidence=0.7)
    recognition = RecognitionJobProcessor(
        session_factory, store, ocr_provider, settings=RecognitionSettings(confidence_threshold=0.9)
    )
    processor = GradingJobProcessor(
        session_factory,
        store,
        recognition,
        ai_provider,
        grading_settings=GradingSettings(confidence_threshold=0.5),
    )
    ai_provider.script(_response(grading_confidence=0.95, recognition_confidence=0.95))
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.usable is False
    assert second.outcome is ProcessingOutcome.SUCCEEDED
    assert second.usable is False
    assert len(ai_provider.calls) == 1  # replay must not call the provider again


async def test_the_graders_own_corrected_recognition_is_persisted_and_gates_usable(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #20 review, P1: a multimodal provider may correct the OCR
    reading it was given (`AIProviderContract` explicitly allows this). That
    corrected text/confidence must be persisted (not discarded) and must
    gate `usable` -- a low grader-reported recognition confidence must not
    be masked by a high original OCR confidence.
    """
    _seed(session_factory, store)  # OCR confidence is 0.96 (high)
    ai_provider.script(
        _response(recognition_confidence=0.2)  # the grader itself is unsure
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    assert result.usable is False  # grader's own low recognition confidence gates it
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        grading_recognition = uow.recognitions.get(grading_recognition_id(job))
    assert grading_recognition is not None
    assert grading_recognition.text == "模範的な解答"  # the grader's corrected reading
    assert grading_recognition.confidence == pytest.approx(0.2)
    assert grading_recognition.source is GradingSource.AI


async def test_the_rubric_is_numbered_for_the_provider_and_ids_travel_beside_it(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """The provider receives the criteria as a numbered list plus the
    question's scoring method (additive vs. subtractive, Issue #20 review
    P1), and the registered ids ride along in ``criterion_ids`` -- out of
    the prompt entirely (Issue #117), in the same order the numbering
    implies, so a response naming a position can still be mapped back."""
    _seed(session_factory, store)
    ai_provider.script(_response())
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    await processor.process(job)

    request = ai_provider.calls[0]
    assert "1. " in request.rubric_text
    assert "2. " in request.rubric_text
    assert "c-1" not in request.rubric_text
    assert "c-2" not in request.rubric_text
    assert request.criterion_ids == ("c-1", "c-2")
    assert "加算方式" in request.rubric_text  # tests.support.make_question() defaults to ADDITIVE


async def test_response_with_an_unknown_criterion_id_is_rejected_before_persisting(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #20 review, P1: a schema-valid response whose criteria do not
    correspond to the registered rubric (an unknown id here) must be
    rejected before persisting, not saved as a usable candidate."""
    _seed(session_factory, store)
    ai_provider.script(
        _response(
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="not-a-registered-criterion",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠",
                ),
            )
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


async def test_response_omitting_a_registered_criterion_is_rejected_before_persisting(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ai_provider: _ScriptedAIProvider,
    processor: GradingJobProcessor,
) -> None:
    """Issue #20 review, P1: a response that silently omits one of the
    rubric's registered criteria (here: only c-1, never addressing c-2) is
    rejected the same way as an unknown id -- an incomplete rubric mapping
    must not be saved as a usable candidate."""
    _seed(session_factory, store)
    ai_provider.script(
        _response(
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="c-1",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠1",
                ),
            )
        )
    )
    job = make_job(kind=JobKind.GRADING, question_id="q-1")

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_category is ErrorCategory.PERMANENT
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.grades.history("sub-1", "q-1") == []


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
    # rubric-2 registers c-3/c-4 (not the default c-1/c-2), so the response
    # must address those exact criterion ids.
    ai_provider.script(
        _response(
            question_id="q-2",
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="c-3",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠3",
                ),
                GradingCriterionOutcome(
                    criterion_id="c-4",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠4",
                ),
            ),
        )
    )
    dependent_job = make_job(id="job-q2", kind=JobKind.GRADING, question_id="q-2")
    dependent_result = await processor.process(dependent_job)

    assert dependent_result.usable is True
    dependent_request = ai_provider.calls[-1]
    assert len(dependent_request.prerequisite_context) == 1
    prerequisite_answer = dependent_request.prerequisite_context[0]
    assert prerequisite_answer.question_id == "q-1"
    # The grader's own (possibly corrected) reading of q-1 -- persisted as a
    # second, more recent AI RecognitionResult (Issue #20 review, P1) -- is
    # what q-1 was actually graded against, so it is what a dependent's
    # context carries forward, not the original (pre-grading) OCR text.
    assert prerequisite_answer.recognized_text == "模範的な解答"
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


async def test_prerequisite_context_ignores_an_undone_human_correction(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Issue #22 P1 review: a dependent question's grading context must be
    resolved through the prerequisite's own review history, not simply "the
    latest human row wins" -- once a reviewer's correction to the
    prerequisite (q-1) is reverted with Undo, its `GradeResult`/
    `RecognitionResult` rows are still there (append-only) but must stop
    feeding q-2's context, the same way the review screen's own
    `QuestionReviewState.displayGrade` stops showing them.
    """
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
    ai_grade_id = grade_result_id(prerequisite_job)

    # A reviewer corrects q-1 (a `modified` Review) -- a much lower score and
    # a different recognized text -- then immediately reverts it with Undo.
    # Both actions are legitimate review-screen calls
    # (`adapters.review_actions.edit_question`/`undo_last_review`); this
    # reproduces their net effect directly against the repositories to keep
    # this test scoped to `GradingJobProcessor` alone.
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(
            make_grade(
                id="grade-human-q1",
                question_id="q-1",
                source=GradingSource.HUMAN,
                score=Score(awarded=1, maximum=5),
                confidence=1.0,
                created_at=at(100),
            )
        )
        uow.recognitions.add(
            make_recognition(
                id="rec-human-q1",
                question_id="q-1",
                source=GradingSource.HUMAN,
                text="人による誤った修正",
                confidence=1.0,
                created_at=at(100),
            )
        )
        modified_review = make_review(
            id="review-modified-q1",
            question_id="q-1",
            action=ReviewAction.MODIFIED,
            version=1,
            ai_grade_result_id=ai_grade_id,
            human_grade_result_id="grade-human-q1",
            created_at=at(100),
        )
        uow.reviews.add(modified_review)
        uow.reviews.add(
            make_review(
                id="review-undone-q1",
                question_id="q-1",
                action=ReviewAction.UNDONE,
                version=2,
                ai_grade_result_id=None,
                undone_review_id=modified_review.id,
                created_at=at(200),
            )
        )
        uow.commit()

    # Now grade the dependent (q-2); its request must carry q-1's *AI*
    # context, exactly as if the human correction above had never happened.
    ai_provider.script(
        _response(
            question_id="q-2",
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="c-3",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠3",
                ),
                GradingCriterionOutcome(
                    criterion_id="c-4",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠4",
                ),
            ),
        )
    )
    dependent_job = make_job(id="job-q2", kind=JobKind.GRADING, question_id="q-2")
    dependent_result = await processor.process(dependent_job)

    assert dependent_result.usable is True
    dependent_request = ai_provider.calls[-1]
    assert len(dependent_request.prerequisite_context) == 1
    prerequisite_answer = dependent_request.prerequisite_context[0]
    assert prerequisite_answer.question_id == "q-1"
    assert prerequisite_answer.recognized_text == "模範的な解答"
    assert prerequisite_answer.score == 4


async def test_prerequisite_context_uses_a_standalone_manual_recognition_correction(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    ocr_provider: _ScriptedOCRProvider,
    ai_provider: _ScriptedAIProvider,
) -> None:
    """Issue #22 P2 review, round 3: a human `RecognitionResult` created
    through the older, review-workflow-independent ``POST .../recognitions``
    endpoint (Issue #19) is never tied to any `Review` row at all. A
    dependent question's grading context must still pick it up over the
    prerequisite's own (possibly misread) AI text -- treating "no `modified`
    Review for this question" the same as "no human correction exists at
    all" would silently hand the dependent question the wrong text even
    though a reviewer already fixed it.
    """
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

    # A reviewer manually corrects q-1's recognized text through the
    # standalone `POST .../recognitions` endpoint (Issue #19) -- no `Review`
    # row of any kind is ever created for this, unlike an `edit_question`
    # correction (`adapters.recognitions_router.create_manual_recognition`
    # reproduced here directly, keeping this test scoped to
    # `GradingJobProcessor`).
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.recognitions.add(
            make_recognition(
                id="rec-manual-q1",
                question_id="q-1",
                source=GradingSource.HUMAN,
                text="手動で訂正した文字",
                confidence=1.0,
                created_at=at(100),
            )
        )
        uow.commit()

    # Now grade the dependent (q-2); its request must carry the manually
    # corrected text, not q-1's own (uncorrected) AI reading.
    ai_provider.script(
        _response(
            question_id="q-2",
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="c-3",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠3",
                ),
                GradingCriterionOutcome(
                    criterion_id="c-4",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠4",
                ),
            ),
        )
    )
    dependent_job = make_job(id="job-q2", kind=JobKind.GRADING, question_id="q-2")
    dependent_result = await processor.process(dependent_job)

    assert dependent_result.usable is True
    dependent_request = ai_provider.calls[-1]
    assert len(dependent_request.prerequisite_context) == 1
    prerequisite_answer = dependent_request.prerequisite_context[0]
    assert prerequisite_answer.question_id == "q-1"
    assert prerequisite_answer.recognized_text == "手動で訂正した文字"
    assert prerequisite_answer.score == 4


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
