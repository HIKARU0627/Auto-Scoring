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

    # 0 is not a real HTTP status -- placeholder for "this thread hasn't
    # written its result yet" that both slots are always overwritten past
    # before the assertion below reads them (each thread is joined first).
    statuses: list[int] = [0, 0]

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


def test_edit_with_a_score_maximum_not_matching_the_questions_registered_points_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """`Score.__post_init__` alone only checks ``0 <= awarded <= maximum`` --
    a client-invented ``score_maximum`` that is internally consistent (e.g.
    ``score_awarded=100, score_maximum=100`` against a 5-point question)
    passes that check but must still be rejected: it does not match the
    question's own registered ``points``, and accepting it would flow a
    bogus score downstream as if it were legitimate (Issue #22 P2 review,
    round 2)."""
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/edit",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 100, "score_maximum": 100},
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
        # With the `review_reason` intake always writes alongside NEEDS_REVIEW
        # (`adapters.submission_intake`: every branch that picks that state
        # picks a reason with it, pinned by `test_submission_intake_service.py`
        # 193/220/245). Issue #112 made that pairing load-bearing -- it is how
        # an un-confirm tells "intake flagged this" from "intake was fine" --
        # so a fixture without it is a submission intake could never produce.
        uow.submissions.add(
            make_submission(
                state=SubmissionState.NEEDS_REVIEW,
                review_reason="answer_area_undefined:q-1",
            )
        )
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


def test_a_cleanly_intaken_submission_becomes_reviewed_when_every_question_is_confirmed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Issue #112 受入1: 全問承認すると完了として記録される。

    ``AI_PROCESSED`` -- no ``review_reason`` -- is what intake leaves an
    ordinary submission in: `adapters.submission_intake` only routes on to
    ``NEEDS_REVIEW`` when it could not pin the answer areas. Before this Issue
    `_sync_submission_review_state` skipped that state outright, so approving
    every question of a perfectly normal answer recorded nothing: ホーム画面's
    「確認済み N / M」 never moved and the same answer kept being offered as the
    one to resume.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.questions.add(make_question(id="q-2", number="2"))
        uow.submissions.add(make_submission(state=SubmissionState.AI_PROCESSED))
        uow.grades.add(make_grade(id="grade-q1", question_id="q-1", source=GradingSource.AI))
        uow.grades.add(make_grade(id="grade-q2", question_id="q-2", source=GradingSource.AI))
        uow.commit()

    first = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert first.status_code == 201
    # 受入4: 1問でも未確定なら完了にならない。And it stays where intake left it --
    # a half-reviewed ordinary answer is not an intake problem, so it must not
    # start claiming to be one.
    assert first.json()["submission_state"] == "ai_processed"

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
    # Never acquired a reason it was never flagged for.
    assert submission.review_reason is None


def test_undo_returns_a_cleanly_intaken_submission_to_ai_processed_not_needs_review(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Issue #112 受入5: Undoで完了が外れる。**ただし要確認にはしない。**

    ``NEEDS_REVIEW`` is the one state this app colours as needing a person
    (`docs/design-tokens.md` §3.1) and the one ホーム画面 opens first. Sending a
    submission whose intake was fine there -- because a reviewer took one
    approval back -- would raise that flag over an answer with nothing wrong
    with it, and nothing would ever lower it again.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.submissions.add(make_submission(state=SubmissionState.AI_PROCESSED))
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
    assert undone.json()["submission_state"] == "ai_processed"

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.AI_PROCESSED
    assert submission.review_reason is None


def test_confidence_alone_never_makes_a_submission_reviewed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """簡易設計書 §25.2 / Issue #112 オーナー条件1: 完了はAI由来にならない。

    Every question carries an AI grade at the maximum Confidence there is, and
    the submission is still not complete, because **no person has confirmed
    anything**. 「確認済み」 is the record of a human having looked; the moment it
    can be derived from what the AI thought, it stops being evidence of that.

    This is a regression test against a *future* change, not a past bug: it
    fails the day someone adds a threshold, an auto-confirm, or a "skip the
    high-confidence ones" shortcut to the completion rule.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.questions.add(make_question(id="q-2", number="2"))
        uow.submissions.add(make_submission(state=SubmissionState.AI_PROCESSED))
        uow.grades.add(
            make_grade(id="grade-q1", question_id="q-1", source=GradingSource.AI, confidence=1.0)
        )
        uow.grades.add(
            make_grade(id="grade-q2", question_id="q-2", source=GradingSource.AI, confidence=1.0)
        )
        uow.commit()

    # A review action on one question is what re-evaluates the submission, so
    # this drives the recheck without confirming q-2. Rejecting is a human
    # action that is deliberately *not* a confirmation.
    rejected = client.post(
        "/submissions/sub-1/questions/q-1/review/reject",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert rejected.status_code == 201
    assert rejected.json()["submission_state"] == "ai_processed"

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is not SubmissionState.REVIEWED


def test_the_lowest_confidence_still_completes_once_a_person_confirms(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The other half of `test_confidence_alone_never_makes_a_submission_reviewed`:
    Confidence does not hold completion back either. What decides is the human
    confirmation and nothing else (簡易設計書 §25.2).
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.submissions.add(make_submission(state=SubmissionState.AI_PROCESSED))
        uow.grades.add(
            make_grade(id="grade-q1", question_id="q-1", source=GradingSource.AI, confidence=0.0)
        )
        uow.commit()

    approved = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert approved.status_code == 201
    assert approved.json()["submission_state"] == "reviewed"


def test_submission_returns_to_needs_review_once_an_undo_unconfirms_a_question(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        # Carries its intake reason: see the note in
        # `test_submission_becomes_reviewed_only_once_every_question_is_confirmed`.
        uow.submissions.add(
            make_submission(
                state=SubmissionState.NEEDS_REVIEW,
                review_reason="answer_area_undefined:q-1",
            )
        )
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

    # The reason survives the round trip, so the submission goes back to being
    # flagged for the same thing intake flagged it for -- not to a NEEDS_REVIEW
    # nobody can explain (Issue #112).
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.review_reason == "answer_area_undefined:q-1"


# --------------------------------------------------------------------------- #
# Issue #118: a question AI could not grade at all
# --------------------------------------------------------------------------- #
def test_a_question_with_no_ai_grade_can_be_graded_by_a_person(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Issue #118 受入1/2: AI 採点が失敗した設問に、人が点数を入れられる。

    Nothing here seeds a `GradeResult`: this is exactly the state a
    permanently-failed grading job leaves behind, and Issue #97 is right to
    leave it that way rather than persist a grade nobody produced. What was
    missing is the way back out of it -- ``approve``/``edit`` both need an AI
    grade to confirm or correct, so the answer sheet stopped there.
    """
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/grade",
        headers=_AUTH,
        json={
            "expected_version": 0,
            "score_awarded": 3,
            "score_maximum": 5,
            "criteria": [{"criterion_id": "c-1", "outcome": "pass"}],
            "rationale": "AI採点が失敗したため人が採点した",
            "comment": "おおむね良い",
            "recognized_text": "人が読んだ答案",
            "note": "AI採点が失敗",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["review"]["action"] == "modified"
    assert body["grade"]["source"] == "human"
    assert body["grade"]["score"] == {"awarded": 3, "maximum": 5, "ratio": 0.6}
    assert body["grade"]["criteria"] == [
        {"criterion_id": "c-1", "outcome": "pass", "confidence": None}
    ]
    assert body["recognition"]["text"] == "人が読んだ答案"
    # Issue #118 受入5: the history says the AI produced nothing to base this
    # on -- a `modified` row with no AI grade behind it is a person grading
    # from scratch, not a correction of something.
    assert body["review"]["ai_grade_result_id"] is None
    assert body["review"]["human_grade_result_id"] == body["grade"]["id"]
    assert body["review"]["note"] == "AI採点が失敗"


def test_a_manually_graded_question_counts_as_confirmed_and_completes_the_answer(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Issue #118 受入3, kept consistent with Issue #112.

    A question a person graded from scratch is confirmed exactly like an
    approved one -- otherwise the one question AI could not read would hold
    the whole answer sheet out of 「確認済み」 forever.
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question(id="q-1", number="1"))
        uow.questions.add(make_question(id="q-2", number="2"))
        uow.rubrics.add(make_rubric())
        uow.submissions.add(make_submission(state=SubmissionState.AI_PROCESSED))
        # Only q-2 was graded: q-1's grading job failed permanently.
        uow.grades.add(make_grade(id="grade-q2", question_id="q-2", source=GradingSource.AI))
        uow.commit()

    manual = client.post(
        "/submissions/sub-1/questions/q-1/review/grade",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 5, "score_maximum": 5},
    )
    assert manual.status_code == 201
    assert manual.json()["submission_state"] == "ai_processed"

    approved = client.post(
        "/submissions/sub-1/questions/q-2/review/approve",
        headers=_AUTH,
        json={"expected_version": 0},
    )
    assert approved.status_code == 201
    assert approved.json()["submission_state"] == "reviewed"

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        submission = uow.submissions.get("sub-1")
    assert submission is not None
    assert submission.state is SubmissionState.REVIEWED


def test_manual_grading_is_refused_once_an_ai_grade_exists(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """This route exists for the "AI produced nothing" case only.

    Letting it through when an AI grade *does* exist would let a reviewer
    record a grade that silently ignores an AI attempt they never saw -- the
    same hazard ``expected_ai_grade_id`` guards on ``edit``/``approve``
    (Issue #22 P1 review). The reviewer is told to reload and use those
    instead.
    """
    _seed_question_and_submission(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(make_grade(id="grade-ai", source=GradingSource.AI))
        uow.commit()

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/grade",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 5, "score_maximum": 5},
    )

    assert response.status_code == 409

    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH).json()
    assert reviews == []
    grades = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH).json()
    assert [g["source"] for g in grades] == ["ai"]


def test_manual_grading_still_scores_against_the_registered_points(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The same trust-boundary check ``edit`` makes (AGENTS.md "Security"):
    a human grade is scored out of the question's own registered total, never
    out of one the request invented."""
    _seed_question_and_submission(session_factory)

    response = client.post(
        "/submissions/sub-1/questions/q-1/review/grade",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 7, "score_maximum": 7},
    )

    assert response.status_code == 422


def test_manual_grading_can_be_undone_back_to_unconfirmed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Undo has to reach this row too -- it is an ordinary ``modified`` row,
    and the append-only history keeps the human grade retrievable after it."""
    _seed_question_and_submission(session_factory, state=SubmissionState.AI_PROCESSED)

    created = client.post(
        "/submissions/sub-1/questions/q-1/review/grade",
        headers=_AUTH,
        json={"expected_version": 0, "score_awarded": 4, "score_maximum": 5},
    )
    assert created.status_code == 201

    undone = client.post(
        "/submissions/sub-1/questions/q-1/review/undo",
        headers=_AUTH,
        json={"expected_version": 1},
    )

    assert undone.status_code == 201
    assert undone.json()["submission_state"] == "ai_processed"
    grades = client.get("/submissions/sub-1/questions/q-1/grades", headers=_AUTH).json()
    assert [g["source"] for g in grades] == ["human"]
