"""HTTP integration tests for `auto_scoring.api.review_router` (Issue #21).

Exercises the review screen's read-only data endpoints end to end through
`TestClient` + real SQLite: the question/rubric list, the original PDF bytes,
and each submission-question's grade/annotation history.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters import review_actions
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
    SubmissionState,
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


def _seed_question_and_submission(
    session_factory: sessionmaker[Session],
    *,
    state: SubmissionState = SubmissionState.UNPROCESSED,
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(
                answer_area=NormalizedRect(x=0.1, y=0.2, width=0.5, height=0.1),
                comment_area=NormalizedRect(x=0.7, y=0.2, width=0.2, height=0.1),
            )
        )
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission(state=state))
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
        comment="全体として要点は押さえられています。",
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
    assert ai["comment"] == "全体として要点は押さえられています。"
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


# --------------------------------------------------------------------------- #
# Issue #22: edit / reject / regrade / approve / undo
# --------------------------------------------------------------------------- #
def test_list_reviews_is_empty_before_any_review(client: TestClient) -> None:
    response = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH)
    assert response.status_code == 200
    assert response.json() == []


def test_approve_requires_an_ai_grade_to_exist(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    assert response.status_code == 409


def test_approve_confirms_the_latest_ai_grade_without_mutating_it(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0, "note": "問題ありません"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "approved"
    assert body["review"]["version"] == 1
    assert body["review"]["ai_grade_result_id"] == "grade-ai"

    # The original AI grade is still retrievable, unmodified (acceptance:
    # "AI値を修正して承認しても元AI値が参照できる").
    grades = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH).json()
    assert len(grades) == 1
    assert grades[0]["id"] == "grade-ai"
    assert grades[0]["source"] == "ai"


def test_edit_creates_a_confirmed_human_grade_and_keeps_the_ai_value(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(
            make_grade(id="grade-ai", source=GradingSource.AI, score=Score(awarded=3, maximum=5))
        )
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={
            "expected_version": 0,
            "score_awarded": 5,
            "score_maximum": 5,
            "comment": "よくできています",
            "recognized_text": "訂正後の答案",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "modified"
    assert body["review"]["ai_grade_result_id"] == "grade-ai"
    assert body["grade"]["source"] == "human"
    assert body["grade"]["score"] == {"awarded": 5, "maximum": 5, "ratio": 1.0}
    assert body["recognition"]["text"] == "訂正後の答案"

    grades = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH).json()
    assert {g["source"] for g in grades} == {"ai", "human"}
    ai_grade = next(g for g in grades if g["source"] == "ai")
    assert ai_grade["score"] == {"awarded": 3, "maximum": 5, "ratio": 0.6}


def test_edit_without_an_ai_grade_yet_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 5, "score_maximum": 5},
    )

    assert response.status_code == 409


def test_edit_carries_forward_the_ais_own_annotations_by_default(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    ai_grade = make_grade(id="grade-ai", source=GradingSource.AI, created_at=at(0))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(ai_grade)
        uow.annotations.add(
            Annotation(
                id="anno-ai-circle",
                submission_id="sub-1",
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.CIRCLE,
                rect=NormalizedRect(x=0.3, y=0.4, width=0.05, height=0.05),
                created_at=at(0),
            )
        )
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 5, "score_maximum": 5},
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["kind"] == "circle"
    assert body["annotations"][0]["id"] != "anno-ai-circle"


def test_reject_does_not_require_an_ai_grade(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/reject",
        headers=_AUTH,
        json={"expected_version": 0, "reason": "手書き文字が判読できない"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "rejected"
    assert body["review"]["note"] == "手書き文字が判読できない"
    assert body["review"]["ai_grade_result_id"] is None


def test_regrade_queues_a_fresh_job_and_records_the_request(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/regrade",
        headers=_AUTH,
        json={"expected_version": 0, "reason": "低confidenceのため再判定"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "regrade_requested"
    assert body["review"]["regrade_job_id"] == body["job_id"]
    assert body["review"]["note"] == "低confidenceのため再判定"

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        job = uow.jobs.get(body["job_id"])
    assert job is not None
    assert job.submission_id == "sub-1"
    assert job.question_id == "q-1"
    assert job.dependency_graph_version is None


def test_undo_reverts_an_approval_back_to_unconfirmed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()
    client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/undo",
        headers=_AUTH,
        json={"expected_version": 1},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "undone"
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert [r["action"] for r in reviews] == ["approved", "undone"]


def test_undo_with_nothing_to_undo_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/undo",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    assert response.status_code == 409


def test_stale_expected_version_is_rejected_with_409(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()
    client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    stale = client.post(
        "/submissions/sub-1/questions/q-1/review/reject",
        headers=_AUTH,
        json={"expected_version": 0, "reason": "やり直し"},
    )

    assert stale.status_code == 409
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert len(reviews) == 1, "the rejected stale request must not have appended a second row"


def test_duplicate_concurrent_approve_requests_do_not_double_create_history(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Two requests racing with the same (stale-by-the-time-it-lands)
    ``expected_version=0`` must not both succeed -- only one Review row may
    ever occupy version 1 for this question (Issue #22 acceptance: "同時/
    重複requestが履歴を二重作成せず、古いversionの更新を拒否する")."""
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    first = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    second = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [201, 409]
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert len(reviews) == 1


def test_concurrent_approve_requests_racing_past_the_precheck_resolve_with_one_conflict(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unlike the sequential test above (the first request's commit always
    lands before the second's pre-check even runs, since `TestClient.post`
    blocks until each request finishes), this forces both requests to pass
    `next_review_version`'s cheap pre-check at the same ``expected_version``
    *before* either writes anything -- exactly the race
    ``uq_reviews_submission_question_version`` exists to guard.

    `SqlAlchemyReviewRepository.add` flushes immediately, so the loser's
    `IntegrityError` can surface there, before `_finalize_review`'s
    conflict-handling `try` used to start (P2 review, when it only wrapped
    `uow.commit()`) -- resolving with a bare 500 instead of the promised 409.
    """
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    barrier = threading.Barrier(2)
    original_next_version = review_actions._next_version

    def _next_version_after_barrier(*args: object, **kwargs: object) -> object:
        result = original_next_version(*args, **kwargs)  # type: ignore[arg-type]
        # Both requests must have already computed the same next version
        # (both saw an empty history) before either is allowed to proceed to
        # its own `uow.reviews.add`/`uow.commit()` below.
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(review_actions, "_next_version", _next_version_after_barrier)

    statuses: list[int | None] = [None, None]

    def _approve(index: int) -> None:
        response = client.post(
            "/submissions/sub-1/questions/q-1/review/approve",
            headers=_AUTH,
            json={"expected_version": 0},
        )
        statuses[index] = response.status_code

    threads = [threading.Thread(target=_approve, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(statuses) == [201, 409]
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert len(reviews) == 1


def test_approve_with_the_currently_displayed_ai_grade_id_succeeds(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0, "expected_ai_grade_id": "grade-ai"},
    )

    assert response.status_code == 201


def test_approve_rejects_a_stale_expected_ai_grade_id(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """A regrade landing after the reviewer's screen loaded but before this
    approve reached the server must not let the approve silently confirm the
    fresh, unreviewed attempt (Issue #22 P1 review)."""
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai-old", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-ai-new", source=GradingSource.AI, created_at=at(1)))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0, "expected_ai_grade_id": "grade-ai-old"},
    )

    assert response.status_code == 409
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []


def test_approve_without_an_expected_ai_grade_id_skips_the_check(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Backward-compatible default: omitting ``expected_ai_grade_id``
    entirely (an older client) behaves exactly as before this check existed."""
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai-old", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-ai-new", source=GradingSource.AI, created_at=at(1)))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )

    assert response.status_code == 201
    assert response.json()["review"]["ai_grade_result_id"] == "grade-ai-new"


def test_edit_rejects_a_stale_expected_ai_grade_id(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai-old", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-ai-new", source=GradingSource.AI, created_at=at(1)))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={
            "expected_version": 0,
            "expected_ai_grade_id": "grade-ai-old",
            "score_awarded": 5,
            "score_maximum": 5,
        },
    )

    assert response.status_code == 409
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []


def test_edit_with_score_awarded_above_maximum_is_rejected_with_422(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """A request that passes pydantic's own field validation (both are
    non-negative ints) but fails once `edit_question` builds the domain
    `Score` must surface as a 422 client error, not an unhandled 500 (P2
    review)."""
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 2, "score_maximum": 1},
    )

    assert response.status_code == 422
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []


def test_edit_with_an_unknown_criterion_outcome_is_rejected_with_422(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={
            "expected_version": 0,
            "score_awarded": 5,
            "score_maximum": 5,
            "criteria": [{"criterion_id": "c-1", "outcome": "not-a-real-outcome"}],
        },
    )

    assert response.status_code == 422
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []


def test_edit_with_an_out_of_page_annotation_rect_is_rejected_with_422(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={
            "expected_version": 0,
            "score_awarded": 5,
            "score_maximum": 5,
            "annotations": [{"kind": "circle", "x": 0.9, "y": 0.9, "width": 0.5, "height": 0.5}],
        },
    )

    assert response.status_code == 422
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []


def test_submission_becomes_reviewed_only_once_every_question_is_confirmed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.questions.add(make_question(id="q-2", number="2"))
        uow.submissions.add(make_submission(state=SubmissionState.NEEDS_REVIEW))
        uow.grades.add(make_grade(id="grade-q1", question_id="q-1", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-q2", question_id="q-2", source=GradingSource.AI))
        uow.commit()

    first = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert first.status_code == 201
    assert first.json()["submission_state"] == "needs_review"

    second = client.post(
        "/submissions/sub-1/questions/q-2/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert second.status_code == 201
    assert second.json()["submission_state"] == "reviewed"

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.REVIEWED


def test_submission_returns_to_needs_review_once_an_undo_unconfirms_a_question(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.submissions.add(make_submission(state=SubmissionState.NEEDS_REVIEW))
        uow.grades.add(make_grade(id="grade-q1", question_id="q-1", source=GradingSource.AI))
        uow.commit()
    approved = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert approved.json()["submission_state"] == "reviewed"

    undone = client.post(
        "/submissions/sub-1/questions/q-1/review/undo",
        headers=_AUTH,
        json={"expected_version": 1},
    )

    assert undone.status_code == 201
    assert undone.json()["submission_state"] == "needs_review"
