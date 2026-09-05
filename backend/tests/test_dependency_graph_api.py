"""API/DB integration tests for the dependency-graph endpoints (Issue #26).

Exercises the four required fixture shapes (independent / serial /
branch-merge / cycle) end to end through HTTP + real SQLite, plus the
"AI candidate is wrong, a human corrects it, only the confirmed graph is
usable" acceptance scenario.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.sqlalchemy_repositories import (
    SqlAlchemyDependencyGraphRepository,
    SqlAlchemyJobRepository,
)
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.dependency_graph import DependencyGraph, can_start_submission_processing
from auto_scoring.domain.models import Job, JobSaveConflict, JobState, Rubric, RubricCriterion
from tests.support import make_job, make_question, make_submission, make_test

_TOKEN = "dag-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

UowFactory = Callable[[], SqlAlchemyUnitOfWork]


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app(api_token=_TOKEN, session_factory=session_factory)
    return TestClient(app)


def _seed_questions(make_uow: UowFactory, numbers: list[tuple[str, str, int]]) -> None:
    """``numbers`` is a list of ``(question_id, number, page)``."""
    with make_uow() as uow:
        uow.tests.add(make_test())
        for question_id, number, page in numbers:
            uow.questions.add(make_question(id=question_id, number=number, page=page))
        uow.commit()


def _analyze(client: TestClient, overrides: list[dict[str, str]] | None = None) -> dict[str, Any]:
    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={"overrides": overrides or []},
        headers=_AUTH,
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# --------------------------------------------------------------------------- #
# Fixture 1: all independent
# --------------------------------------------------------------------------- #
def test_all_independent_questions_land_in_one_layer(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 1)])

    body = _analyze(client)

    assert body["status"] == "draft"
    assert body["edges"] == []
    assert body["layers"] == [["q1", "q2", "q3"]]


# --------------------------------------------------------------------------- #
# Fixture 2: fully serial (also covers the multi-page acceptance criterion)
# --------------------------------------------------------------------------- #
def test_fully_serial_chain_across_pages(client: TestClient, make_uow: UowFactory) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 2)])

    body = _analyze(
        client,
        overrides=[
            {"question_id": "q2", "prompt_text": "問1の答えを踏まえて説明せよ。"},
            {"question_id": "q3", "prompt_text": "問2の結果を用いて英作文せよ。"},
        ],
    )

    assert body["layers"] == [["q1"], ["q2"], ["q3"]]
    assert {(e["from_question_id"], e["to_question_id"]) for e in body["edges"]} == {
        ("q1", "q2"),
        ("q2", "q3"),
    }


# --------------------------------------------------------------------------- #
# Fixture 3: branch and merge
# --------------------------------------------------------------------------- #
def test_branch_and_merge(client: TestClient, make_uow: UowFactory) -> None:
    _seed_questions(
        make_uow, [("q1", "問1", 1), ("q2", "問2", 1), ("q3", "問3", 1), ("q4", "問4", 1)]
    )

    body = _analyze(
        client,
        overrides=[
            {"question_id": "q2", "prompt_text": "問1を踏まえて答えよ。"},
            {"question_id": "q3", "prompt_text": "問1を踏まえて答えよ。"},
            {"question_id": "q4", "prompt_text": "問2に基づいて、また問3に基づいて答えよ。"},
        ],
    )

    assert body["layers"] == [["q1"], ["q2", "q3"], ["q4"]]


# --------------------------------------------------------------------------- #
# Fixture 4: cycle is rejected, not saved
# --------------------------------------------------------------------------- #
def test_cyclic_candidates_are_rejected_and_not_saved(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])

    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={
            "overrides": [
                {"question_id": "q1", "prompt_text": "問2を参照して答えよ。"},
                {"question_id": "q2", "prompt_text": "問1を参照して答えよ。"},
            ]
        },
        headers=_AUTH,
    )
    assert response.status_code == 422
    assert "cycle" in response.json()["detail"].lower()

    # Nothing was persisted.
    get_response = client.get("/tests/test-1/dependency-graph", headers=_AUTH)
    assert get_response.status_code == 404


# --------------------------------------------------------------------------- #
# Human corrects an AI candidate; only the confirmed graph is usable
# --------------------------------------------------------------------------- #
def test_human_correction_confirm_gates_submission_processing(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])

    draft = _analyze(
        client,
        overrides=[{"question_id": "q2", "prompt_text": "問1を参照して答えよ(誤検出)。"}],
    )
    assert draft["status"] == "draft"
    assert {(e["from_question_id"], e["to_question_id"]) for e in draft["edges"]} == {("q1", "q2")}

    # The AI candidate is wrong (no real dependency): a human confirms with an
    # empty edge list, correcting it.
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirmed = confirm_response.json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["edges"] == []

    # A second confirm on the now-CONFIRMED graph is rejected: a new version
    # must be analyzed first.
    conflict = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert conflict.status_code == 409

    with make_uow() as uow:
        stored = uow.dependency_graphs.get_latest("test-1")
        current_question_ids = {q.id for q in uow.questions.list_for_test("test-1")}
        active_confirmed = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert stored is not None and active_confirmed is not None
    assert (
        can_start_submission_processing(
            stored,
            current_question_ids=current_question_ids,
            active_confirmed_version=active_confirmed.version,
        )
        is True
    )


def test_draft_alone_does_not_allow_submission_processing(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    with make_uow() as uow:
        latest = uow.dependency_graphs.get_latest("test-1")
        current_question_ids = {q.id for q in uow.questions.list_for_test("test-1")}
        active_confirmed = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert (
        can_start_submission_processing(
            latest,
            current_question_ids=current_question_ids,
            active_confirmed_version=active_confirmed.version if active_confirmed else None,
        )
        is False
    )


def test_confirmed_processing_gate_goes_stale_after_a_question_is_added(
    client: TestClient, make_uow: UowFactory
) -> None:
    """A confirmed graph's own `status` never changes on its own, but a
    question added to the test afterwards must still block processing --
    otherwise a job could be started against a DAG missing a real question of
    the test indefinitely (Issue #26 review).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )

    with make_uow() as uow:
        confirmed = uow.dependency_graphs.get_latest("test-1")
        current_question_ids = {q.id for q in uow.questions.list_for_test("test-1")}
        active_confirmed = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert confirmed is not None and active_confirmed is not None
    assert (
        can_start_submission_processing(
            confirmed,
            current_question_ids=current_question_ids,
            active_confirmed_version=active_confirmed.version,
        )
        is True
    )

    with make_uow() as uow:
        uow.questions.add(make_question(id="q2", test_id="test-1", number="問2"))
        uow.commit()

    with make_uow() as uow:
        still_confirmed = uow.dependency_graphs.get_latest("test-1")
        current_question_ids = {q.id for q in uow.questions.list_for_test("test-1")}
        active_confirmed = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert still_confirmed is not None and active_confirmed is not None
    assert still_confirmed.status.value == "confirmed"  # status alone did not change
    assert (
        can_start_submission_processing(
            still_confirmed,
            current_question_ids=current_question_ids,
            active_confirmed_version=active_confirmed.version,
        )
        is False
    )


def test_processing_gate_rejects_a_superseded_confirmed_version(
    client: TestClient, make_uow: UowFactory
) -> None:
    """v1 stays CONFIRMED forever -- confirming v2 never mutates or
    un-confirms it. Checking v1's own `status`/`question_ids` in isolation
    would still allow it even after v2 became the test's active version, so
    the gate must also compare against the *currently* active confirmed
    version (Issue #26 review).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)
    v1_confirm = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert v1_confirm.status_code == 200, v1_confirm.text

    with make_uow() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
    assert v1 is not None and v1.status.value == "confirmed"

    _analyze(client)
    v2_confirm = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 2, "edges": []},
        headers=_AUTH,
    )
    assert v2_confirm.status_code == 200, v2_confirm.text

    with make_uow() as uow:
        v1_after_v2 = uow.dependency_graphs.get("test-1:v1")
        current_question_ids = {q.id for q in uow.questions.list_for_test("test-1")}
        active_confirmed = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert v1_after_v2 is not None and active_confirmed is not None
    assert v1_after_v2.status.value == "confirmed"  # v1's own status never changed
    assert v1_after_v2.question_ids == current_question_ids  # question set never changed either
    assert active_confirmed.version == 2
    assert (
        can_start_submission_processing(
            v1_after_v2,
            current_question_ids=current_question_ids,
            active_confirmed_version=active_confirmed.version,
        )
        is False
    )


# --------------------------------------------------------------------------- #
# Versioning
# --------------------------------------------------------------------------- #
def test_reanalyzing_after_confirm_starts_a_new_version(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )

    second = _analyze(client)
    assert second["version"] == 2
    assert second["status"] == "draft"

    versions = client.get("/tests/test-1/dependency-graph/versions", headers=_AUTH).json()
    assert [v["version"] for v in versions] == [1, 2]
    assert versions[0]["status"] == "confirmed"
    assert versions[1]["status"] == "draft"


def test_reanalyzing_a_pending_draft_starts_a_new_version_and_leaves_it_intact(
    client: TestClient, make_uow: UowFactory
) -> None:
    """A concurrent /analyze must never mutate a draft another client is reviewing."""
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])

    first = _analyze(
        client, overrides=[{"question_id": "q2", "prompt_text": "問1を参照して答えよ。"}]
    )
    assert first["version"] == 1
    first_pairs = {(e["from_question_id"], e["to_question_id"]) for e in first["edges"]}
    assert first_pairs == {("q1", "q2")}

    # A different client re-analyzes (e.g. with corrected input) before anyone
    # confirmed v1. This must land as a new version, not overwrite v1.
    second = _analyze(client, overrides=[])
    assert second["version"] == 2
    assert second["edges"] == []

    versions = client.get("/tests/test-1/dependency-graph/versions", headers=_AUTH).json()
    v1 = next(v for v in versions if v["version"] == 1)
    v1_pairs = {(e["from_question_id"], e["to_question_id"]) for e in v1["edges"]}
    assert v1_pairs == {("q1", "q2")}, "v1 must still be exactly what the first analyze produced"

    # Confirming v1 as originally reviewed still works, unaffected by v2.
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": first["edges"]},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["status"] == "confirmed"


def test_stale_confirm_after_reanalyze_does_not_touch_the_new_version(
    client: TestClient, make_uow: UowFactory
) -> None:
    """A confirm pinned to v1 must never land on a v2 an analyze created meanwhile."""
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    _analyze(client)  # starts v2 (draft), simulating a concurrent re-analysis

    stale_confirm = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert stale_confirm.status_code == 409

    with make_uow() as uow:
        v2 = uow.dependency_graphs.get("test-1:v2")
    assert v2 is not None
    assert v2.status.value == "draft"


def test_confirming_an_older_draft_after_a_newer_version_was_confirmed_is_rejected(
    client: TestClient, make_uow: UowFactory
) -> None:
    """v2 confirms first; a delayed confirm of v1 must not create a second
    "active" confirmed version (Issue #26 review: graph/job version would
    otherwise disagree about which version is actually active).
    """
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)  # v1 draft
    _analyze(client)  # v2 draft

    confirm_v2 = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 2, "edges": []},
        headers=_AUTH,
    )
    assert confirm_v2.status_code == 200, confirm_v2.text

    stale_confirm_v1 = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert stale_confirm_v1.status_code == 409

    with make_uow() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
        active = uow.dependency_graphs.get_latest_confirmed("test-1")
    assert v1 is not None
    assert v1.status.value == "draft"
    assert active is not None and active.version == 2


def test_confirm_returns_409_when_it_loses_the_atomic_race(
    client: TestClient, make_uow: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when every application-level pre-check passes, the atomic
    compare-and-set can still lose to a concurrent confirm that reached the
    database first -- the loser must get 409, never a silent 200 or a raw
    500 (Issue #26 review: atomic confirm). Forced deterministically since a
    real two-request race is not reliable through TestClient.
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    monkeypatch.setattr(
        SqlAlchemyDependencyGraphRepository,
        "try_confirm",
        lambda self, confirmed: False,
    )

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert response.status_code == 409

    with make_uow() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
    assert v1 is not None
    assert v1.status.value == "draft"


def test_confirming_after_the_test_gained_a_question_requires_reanalysis(
    client: TestClient, make_uow: UowFactory
) -> None:
    """A question added between /analyze and /confirm must invalidate the
    snapshot: confirming it anyway would produce a CONFIRMED graph missing a
    real question of the test (Issue #26 review).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    draft = _analyze(client)
    assert draft["version"] == 1

    with make_uow() as uow:
        uow.questions.add(make_question(id="q2", test_id="test-1", number="問2"))
        uow.commit()

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert response.status_code == 409

    with make_uow() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
    assert v1 is not None
    assert v1.status.value == "draft"


def test_confirm_returns_409_when_a_question_is_added_in_the_toctou_window(
    client: TestClient, make_uow: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A question added strictly *after* this request's own application-level
    pre-check (already passed) but *before* the atomic write must still be
    caught -- by `try_confirm`'s own embedded check -- not silently
    confirmed against a stale snapshot (Issue #26 review). Forced
    deterministically by committing the new question from inside a
    monkeypatched `try_confirm`, right before delegating to the real one.
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    real_try_confirm = SqlAlchemyDependencyGraphRepository.try_confirm

    def _sneak_in_a_question_then_try_confirm(
        self: SqlAlchemyDependencyGraphRepository, confirmed: DependencyGraph
    ) -> bool:
        with make_uow() as sneaky_uow:
            sneaky_uow.questions.add(make_question(id="q2", test_id="test-1", number="問2"))
            sneaky_uow.commit()
        return real_try_confirm(self, confirmed)

    monkeypatch.setattr(
        SqlAlchemyDependencyGraphRepository,
        "try_confirm",
        _sneak_in_a_question_then_try_confirm,
    )

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert response.status_code == 409

    with make_uow() as uow:
        v1 = uow.dependency_graphs.get("test-1:v1")
    assert v1 is not None
    assert v1.status.value == "draft"


# --------------------------------------------------------------------------- #
# Concurrency: version allocation must not collide (Issue #26 review)
# --------------------------------------------------------------------------- #
def test_analyze_retries_past_a_simulated_version_conflict(
    client: TestClient, make_uow: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`save()` raises `IntegrityError` when two concurrent /analyze calls
    both read the same "next version" and both attempt to insert it -- SQLite
    serializes the writes, so only the second insert violates the
    `(test_id, version)` unique constraint (a real two-thread reproduction
    is not reliable through TestClient, which effectively serializes
    requests). This forces that exact failure once and checks analyze()
    retries onto a fresh version instead of surfacing a raw 500 (Issue #26
    review: atomic version allocation).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])

    real_save = SqlAlchemyDependencyGraphRepository.save
    failed_once = {"done": False}

    def _conflict_once_then_real(
        self: SqlAlchemyDependencyGraphRepository, graph: DependencyGraph
    ) -> None:
        if not failed_once["done"]:
            failed_once["done"] = True
            raise IntegrityError(
                "INSERT INTO dependency_graphs ...", {}, Exception("UNIQUE constraint failed")
            )
        real_save(self, graph)

    monkeypatch.setattr(SqlAlchemyDependencyGraphRepository, "save", _conflict_once_then_real)

    response = client.post(
        "/tests/test-1/dependency-graph/analyze", json={"overrides": []}, headers=_AUTH
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1
    assert failed_once["done"] is True

    with make_uow() as uow:
        assert {g.version for g in uow.dependency_graphs.list_versions("test-1")} == {1}


# --------------------------------------------------------------------------- #
# Job invalidation on a superseded confirmed version (Issue #26 acceptance:
# "確定graphを変更した場合はversionを更新し、古いgraphで未完了の採点jobを
# 無効化・再作成できるようにする")
# --------------------------------------------------------------------------- #
def test_confirming_a_new_version_cancels_and_requeues_stale_incomplete_jobs(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )

    # A job was queued for a submission against the just-confirmed v1.
    with make_uow() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(
            make_job(
                id="job-v1-blocked",
                state=JobState.BLOCKED,
                blocked_on_question_id="q1",
                dependency_graph_version=1,
            )
        )
        uow.commit()

    # The test's questions change; a human re-analyzes and confirms v2.
    _analyze(client)
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 2, "edges": []},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text

    with make_uow() as uow:
        # The stale v1 job is cancelled -- never left dangling as "still
        # incomplete" against a graph version nobody can act on anymore.
        old_job = uow.jobs.get("job-v1-blocked")
        assert old_job is not None
        assert old_job.state is JobState.CANCELLED

        assert uow.jobs.list_incomplete_for_stale_versions("test-1", current_version=2) == []

        # A fresh replacement was queued against the new version, in the same
        # transaction as the confirmation.
        queued = uow.jobs.list_by_state(JobState.QUEUED)
        replacement = next(job for job in queued if job.id != old_job.id)
        assert replacement.dependency_graph_version == 2
        assert replacement.submission_id == old_job.submission_id
        assert replacement.kind == old_job.kind
        assert replacement.attempts == 0
        assert replacement.blocked_on_question_id is None


def test_confirming_a_new_version_also_reissues_a_stale_failed_job(
    client: TestClient, make_uow: UowFactory
) -> None:
    """FAILED is not terminal: FAILED -> QUEUED is a valid retry, so a stale
    FAILED job must be cancelled/replaced too, or a later retry would run it
    against the superseded graph version (Issue #26 review).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )

    with make_uow() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(
            make_job(
                id="job-v1-failed",
                state=JobState.FAILED,
                last_error="transient error",
                dependency_graph_version=1,
            )
        )
        uow.commit()

    _analyze(client)
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 2, "edges": []},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text

    with make_uow() as uow:
        old_job = uow.jobs.get("job-v1-failed")
        assert old_job is not None
        assert old_job.state is JobState.CANCELLED

        queued = uow.jobs.list_by_state(JobState.QUEUED)
        replacement = next(job for job in queued if job.id != old_job.id)
        assert replacement.dependency_graph_version == 2


def test_confirming_when_nothing_is_stale_creates_no_extra_jobs(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)
    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )
    assert response.status_code == 200

    with make_uow() as uow:
        assert uow.jobs.list_by_state(JobState.QUEUED) == []
        assert uow.jobs.list_by_state(JobState.CANCELLED) == []


def test_confirm_skips_reissue_when_cancelling_a_stale_job_loses_a_race(
    client: TestClient, make_uow: UowFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If cancelling a stale job conflicts (e.g. a worker changed its state
    in the meantime), /confirm must not crash and must not create a
    duplicate replacement for that job -- it should simply leave it alone
    and still succeed for the graph itself (Issue #26 review).
    """
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},
        headers=_AUTH,
    )

    with make_uow() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(
            make_job(id="job-v1-running", state=JobState.RUNNING, dependency_graph_version=1)
        )
        uow.commit()

    def _always_conflict(
        self: SqlAlchemyJobRepository, job: Job, *, expected_state: JobState
    ) -> None:
        raise JobSaveConflict(job.id, expected_state)

    monkeypatch.setattr(SqlAlchemyJobRepository, "save", _always_conflict)

    _analyze(client)
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 2, "edges": []},
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text

    with make_uow() as uow:
        job = uow.jobs.get("job-v1-running")
        queued = uow.jobs.list_by_state(JobState.QUEUED)
    assert job is not None
    assert job.state is JobState.RUNNING  # untouched: the cancel attempt conflicted
    assert queued == []  # no duplicate replacement was created for it


def test_confirming_a_new_version_with_an_added_edge_blocks_the_new_dependent(
    client: TestClient, make_uow: UowFactory
) -> None:
    """Issue #18 review round 1 (P1): `reissue_job_for_graph_version` always
    builds its replacement as QUEUED -- it knows nothing about the *new*
    version's dependency structure. If v2 adds an edge v1 didn't have
    (q1 -> q2) and both q1's and q2's jobs were incomplete under v1, q2's
    replacement must come back BLOCKED on q1, not QUEUED -- otherwise q2
    could reach the processor before q1 has a usable result, bypassing the
    DAG gate entirely.
    """
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)
    client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1, "edges": []},  # v1: independent
        headers=_AUTH,
    )

    with make_uow() as uow:
        uow.submissions.add(make_submission())
        uow.jobs.add(
            make_job(
                id="job-q1-v1",
                question_id="q1",
                state=JobState.QUEUED,
                dependency_graph_version=1,
            )
        )
        uow.jobs.add(
            make_job(
                id="job-q2-v1",
                question_id="q2",
                state=JobState.QUEUED,
                dependency_graph_version=1,
            )
        )
        uow.commit()

    _analyze(client)
    confirm_response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={
            "version": 2,
            "edges": [
                {
                    "from_question_id": "q1",
                    "to_question_id": "q2",
                    "provides": ["score"],
                    "rationale": "q2はq1の結果を使用",
                }
            ],
        },
        headers=_AUTH,
    )
    assert confirm_response.status_code == 200, confirm_response.text

    with make_uow() as uow:
        jobs = uow.jobs.list_for_submission("sub-1")
        q1_replacement = next(
            j for j in jobs if j.question_id == "q1" and j.dependency_graph_version == 2
        )
        q2_replacement = next(
            j for j in jobs if j.question_id == "q2" and j.dependency_graph_version == 2
        )
    assert q1_replacement.state is JobState.QUEUED
    assert q2_replacement.state is JobState.BLOCKED
    assert q2_replacement.blocked_on_question_id == "q1"


def test_confirming_unknown_version_is_not_found(client: TestClient, make_uow: UowFactory) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 99, "edges": []},
        headers=_AUTH,
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Request validation
# --------------------------------------------------------------------------- #
def test_confirm_requires_an_explicit_edges_list(client: TestClient, make_uow: UowFactory) -> None:
    """Omitting `edges` must fail validation, not silently confirm as empty."""
    _seed_questions(make_uow, [("q1", "問1", 1)])
    _analyze(client)

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={"version": 1},
        headers=_AUTH,
    )
    assert response.status_code == 422


def test_confirm_rejects_an_unknown_provision_with_422_not_500(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    _analyze(client)

    response = client.post(
        "/tests/test-1/dependency-graph/confirm",
        json={
            "version": 1,
            "edges": [
                {
                    "from_question_id": "q1",
                    "to_question_id": "q2",
                    "provides": ["bogus"],
                    "rationale": "手動追加",
                }
            ],
        },
        headers=_AUTH,
    )
    assert response.status_code == 422


def test_analyze_rejects_duplicate_override_question_id(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])

    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={
            "overrides": [
                {"question_id": "q1", "prompt_text": "テキストA"},
                {"question_id": "q1", "prompt_text": "テキストB"},
            ]
        },
        headers=_AUTH,
    )
    assert response.status_code == 422
    assert "duplicate" in response.json()["detail"].lower()


def test_analyze_rejects_unknown_override_question_id(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])

    response = client.post(
        "/tests/test-1/dependency-graph/analyze",
        json={"overrides": [{"question_id": "q-not-in-test", "prompt_text": "テキスト"}]},
        headers=_AUTH,
    )
    assert response.status_code == 422
    assert "unknown" in response.json()["detail"].lower()


def test_analyze_respects_an_explicit_empty_rubric_override(
    client: TestClient, make_uow: UowFactory
) -> None:
    """An explicit `rubric_text: ""` override must exclude the saved rubric
    text from analysis, not silently fall back to it (Issue #26 review: `or`
    treated a deliberate "" the same as "no override was sent").
    """
    _seed_questions(make_uow, [("q1", "問1", 1), ("q2", "問2", 1)])
    with make_uow() as uow:
        uow.rubrics.add(
            Rubric(
                id="rubric-q2",
                question_id="q2",
                criteria=(
                    RubricCriterion(
                        id="c-1", description="問1を踏まえて評価する", max_points=5, position=0
                    ),
                ),
            )
        )
        uow.commit()

    draft = _analyze(client, overrides=[{"question_id": "q2", "rubric_text": ""}])

    # If the saved rubric text ("問1を踏まえて評価する") had leaked through
    # despite the explicit "", this would produce a q1 -> q2 edge instead.
    assert draft["edges"] == []
    assert "q2" in {u["question_id"] for u in draft["unresolved"]}


# --------------------------------------------------------------------------- #
# Auth / not-found
# --------------------------------------------------------------------------- #
def test_dependency_graph_routes_require_bearer_token(
    client: TestClient, make_uow: UowFactory
) -> None:
    _seed_questions(make_uow, [("q1", "問1", 1)])
    response = client.post("/tests/test-1/dependency-graph/analyze", json={"overrides": []})
    assert response.status_code == 401


def test_analyze_with_no_questions_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/tests/missing-test/dependency-graph/analyze", json={"overrides": []}, headers=_AUTH
    )
    assert response.status_code == 404
