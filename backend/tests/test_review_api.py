"""HTTP integration tests for `auto_scoring.api.review_router` (Issue #21).

Exercises the review screen's read-only data endpoints end to end through
`TestClient` + real SQLite: the question/rubric list, the original PDF bytes,
and each submission-question's grade/annotation history.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    CriterionOutcome,
    CriterionResult,
    GradingSource,
    NormalizedRect,
    Score,
)
from tests.support import (
    at,
    make_annotation_comment,
    make_grade,
    make_question,
    make_rubric,
    make_submission,
    make_test,
)

_TOKEN = "review-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    data_root: Path,
) -> Iterator[TestClient]:
    app = create_app(api_token=_TOKEN, session_factory=session_factory, data_root=data_root)
    with TestClient(app) as test_client:
        yield test_client


def _seed_question_and_submission(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(
                answer_area=NormalizedRect(x=0.1, y=0.2, width=0.5, height=0.1),
                comment_area=NormalizedRect(x=0.7, y=0.2, width=0.2, height=0.1),
            )
        )
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission())
        uow.commit()


def test_list_questions_returns_404_for_unknown_test(client: TestClient) -> None:
    response = client.get("/tests/no-such-test/questions", headers=_AUTH)
    assert response.status_code == 404


def test_list_questions_includes_areas_and_rubric(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.get("/tests/test-1/questions", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    question = body[0]
    assert question["id"] == "q-1"
    assert question["answer_area"] == {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1}
    assert question["comment_area"] == {"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.1}
    assert question["score_area"] is None
    assert [c["id"] for c in question["rubric"]] == ["c-1", "c-2"]


def test_get_source_pdf_returns_404_for_unknown_submission(client: TestClient) -> None:
    response = client.get("/submissions/no-such-submission/source-pdf", headers=_AUTH)
    assert response.status_code == 404


def test_get_source_pdf_returns_404_when_file_missing_on_disk(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.get("/submissions/sub-1/source-pdf", headers=_AUTH)

    assert response.status_code == 404


def test_get_source_pdf_round_trips_the_stored_bytes(
    client: TestClient, session_factory: sessionmaker[Session], data_root: Path
) -> None:
    _seed_question_and_submission(session_factory)
    store = LocalFileStore(data_root)
    store.write_atomic(store.submission_source_pdf_path("sub-1"), b"%PDF-1.7-fake-pdf-bytes")

    response = client.get("/submissions/sub-1/source-pdf", headers=_AUTH)

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7-fake-pdf-bytes"
    assert response.headers["content-type"] == "application/pdf"


def test_list_grades_is_empty_before_any_grade(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH)
    assert response.status_code == 200
    assert response.json() == []


def test_list_grades_returns_ai_and_human_grades_with_dual_confidence(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    ai_grade = make_grade(
        id="grade-ai",
        source=GradingSource.AI,
        score=Score(awarded=4, maximum=5),
        confidence=0.88,
        rationale="理由の説明が不足しています。",
        criteria=(
            CriterionResult(criterion_id="c-1", outcome=CriterionOutcome.PASS, confidence=0.97),
            CriterionResult(criterion_id="c-2", outcome=CriterionOutcome.PARTIAL, confidence=0.76),
        ),
        created_at=at(0),
    )
    human_grade = make_grade(
        id="grade-human",
        source=GradingSource.HUMAN,
        score=Score(awarded=5, maximum=5),
        confidence=1.0,
        created_at=at(60),
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(ai_grade)
        uow.grades.add(human_grade)
        uow.commit()

    response = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert [g["id"] for g in body] == ["grade-ai", "grade-human"]
    ai = body[0]
    assert ai["source"] == "ai"
    assert ai["score"] == {"awarded": 4, "maximum": 5, "ratio": 0.8}
    assert ai["confidence"] == 0.88
    assert ai["rationale"] == "理由の説明が不足しています。"
    assert [c["criterion_id"] for c in ai["criteria"]] == ["c-1", "c-2"]
    assert body[1]["source"] == "human"
    assert body[1]["score"]["awarded"] == 5


def test_list_annotations_is_empty_before_any_annotation(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/questions/q-1/annotations", headers=_AUTH)
    assert response.status_code == 200
    assert response.json() == []


def test_list_annotations_returns_recorded_marks(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    circle = Annotation(
        id="anno-circle",
        submission_id="sub-1",
        question_id="q-1",
        source=GradingSource.AI,
        kind=AnnotationKind.CIRCLE,
        rect=NormalizedRect(x=0.3, y=0.4, width=0.05, height=0.05),
        created_at=at(0),
    )
    comment = make_annotation_comment(id="anno-comment", created_at=at(1))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.annotations.add(circle)
        uow.annotations.add(comment)
        uow.commit()

    response = client.get("/submissions/sub-1/questions/q-1/annotations", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["kind"] == "circle"
    assert body[0]["rect"] == {"x": 0.3, "y": 0.4, "width": 0.05, "height": 0.05}
    assert body[1]["kind"] == "comment"
    assert body[1]["comment"] == "理由の説明が不足しています。"
