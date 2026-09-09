"""Builders for domain entities used across the persistence tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.dependency_graph import DependencyEdge, DependencyGraph
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    AnswerImage,
    AnswerImageStatus,
    GradeResult,
    GradingSource,
    Job,
    JobKind,
    Question,
    RecognitionResult,
    Review,
    ReviewAction,
    Rubric,
    RubricCriterion,
    Score,
    Submission,
    Test,
)

# Naive UTC: matches how SQLite's DateTime column stores and returns values.
EPOCH = datetime(2026, 1, 1)


def at(seconds: int = 0) -> datetime:
    """A deterministic timestamp ``seconds`` after :data:`EPOCH`."""
    return EPOCH + timedelta(seconds=seconds)


def make_test(**overrides: Any) -> Test:
    values: dict[str, Any] = {
        "id": "test-1",
        "name": "国語 第1回",
        "subject": "国語",
        "created_at": at(),
    }
    values.update(overrides)
    return Test(**values)


def make_question(**overrides: Any) -> Question:
    values: dict[str, Any] = {
        "id": "q-1",
        "test_id": "test-1",
        "number": "問1",
        "page": 1,
        "points": 5,
    }
    values.update(overrides)
    return Question(**values)


def make_rubric(**overrides: Any) -> Rubric:
    values: dict[str, Any] = {
        "id": "rubric-1",
        "question_id": "q-1",
        "criteria": (
            RubricCriterion(id="c-1", description="主旨", max_points=3, position=0),
            RubricCriterion(id="c-2", description="表現", max_points=2, position=1),
        ),
    }
    values.update(overrides)
    return Rubric(**values)


def make_submission(**overrides: Any) -> Submission:
    values: dict[str, Any] = {
        "id": "sub-1",
        "test_id": "test-1",
        "source_pdf_path": "submissions/sub-1/source.pdf",
        "source_pdf_sha256": "0" * 64,
        "page_count": 1,
        "created_at": at(),
    }
    values.update(overrides)
    return Submission(**values)


def make_answer_image(**overrides: Any) -> AnswerImage:
    values: dict[str, Any] = {
        "id": "answer-image-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "page": 1,
        "image_path": "submissions/sub-1/questions/q-1.png",
        "status": AnswerImageStatus.OK,
        "created_at": at(),
    }
    values.update(overrides)
    return AnswerImage(**values)


def make_recognition(**overrides: Any) -> RecognitionResult:
    values: dict[str, Any] = {
        "id": "rec-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "text": "光合成",
        "confidence": 0.91,
        "created_at": at(),
    }
    values.update(overrides)
    return RecognitionResult(**values)


def make_grade(**overrides: Any) -> GradeResult:
    values: dict[str, Any] = {
        "id": "grade-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "score": Score(awarded=4, maximum=5),
        "confidence": 0.88,
        "created_at": at(),
    }
    values.update(overrides)
    return GradeResult(**values)


def make_annotation_comment(**overrides: Any) -> Annotation:
    values: dict[str, Any] = {
        "id": "anno-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "kind": AnnotationKind.COMMENT,
        "comment": "理由の説明が不足しています。",
        "created_at": at(),
    }
    values.update(overrides)
    return Annotation(**values)


def make_review(**overrides: Any) -> Review:
    values: dict[str, Any] = {
        "id": "review-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "action": ReviewAction.APPROVED,
        "version": 1,
        "ai_grade_result_id": "grade-1",
        "created_at": at(),
    }
    values.update(overrides)
    return Review(**values)


def make_job(**overrides: Any) -> Job:
    values: dict[str, Any] = {
        "id": "job-1",
        "kind": JobKind.GRADING,
        "submission_id": "sub-1",
        "created_at": at(),
        "updated_at": at(),
    }
    values.update(overrides)
    return Job(**values)


def seed_confirmed_dependency_graph(
    session_factory: sessionmaker[Session],
    *,
    test_id: str = "test-1",
    submission_id: str = "sub-1",
    question_ids: list[str],
    edges: list[DependencyEdge] | None = None,
    question_pages: Mapping[str, int] | None = None,
    page_count: int = 1,
) -> int:
    """Register a test with ``question_ids``, one submission, and a
    CONFIRMED dependency graph over those questions (Issue #18's queue tests
    need this fixture shape repeatedly). Returns the graph version.

    ``question_pages`` / ``page_count`` spread the questions over a
    multi-page answer instead of the default single page. The queue itself
    is indifferent to `Question.page`, but Issue #25's additional acceptance
    is stated for "1答案3ページ以上", so the fixture has to be able to
    actually be that answer rather than only claim to be.
    """
    pages = question_pages or {}
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test(id=test_id))
        for qid in question_ids:
            uow.questions.add(
                make_question(id=qid, test_id=test_id, number=qid, page=pages.get(qid, 1))
            )
        uow.submissions.add(
            make_submission(id=submission_id, test_id=test_id, page_count=page_count)
        )
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


def written_on_pdf_bytes(
    *,
    pages: int = 1,
    width: float = 300.0,
    height: float = 400.0,
    metadata: Mapping[str, str] | None = None,
) -> bytes:
    """A PDF whose every page carries pen-like ink spread over the sheet.

    Since Issue #122, intake refuses to send a crop that is as good as blank
    to be graded (`domain.submission_intake.is_nearly_blank_crop`) -- so a
    fixture built from `PdfWriter.add_blank_page` no longer stands in for "a
    student's answer sheet". It stands in for an *unanswered* one, which is
    what the tripwire exists to catch, and every intake test that used one
    was asserting the happy path against material the product would now
    correctly stop.

    The strokes are a grid of short segments rather than one filled block:
    dense enough that any answer area a test defines contains ink well above
    the tripwire's threshold, sparse enough to stay handwriting-shaped, so
    that neither `adapters.image.ink.measure_page_ruling` (which requires a
    long unbroken run) nor the preview deskew reads them as page structure.
    """
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))
    for _ in range(pages):
        pdf_canvas.setStrokeColorRGB(0.1, 0.1, 0.1)
        pdf_canvas.setLineWidth(max(1.0, min(width, height) / 100.0))
        step_x, step_y = width / 24.0, height / 32.0
        for column in range(1, 24):
            for row in range(1, 32):
                x, y = column * step_x, row * step_y
                pdf_canvas.line(x, y, x + step_x * 0.6, y + step_y * 0.35)
        pdf_canvas.showPage()
    pdf_canvas.save()

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(buffer.getvalue())))
    if metadata:
        writer.add_metadata(dict(metadata))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
