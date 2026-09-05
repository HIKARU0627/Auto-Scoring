"""Unit tests for `auto_scoring.domain.job_scheduling` (Issue #18).

Pure DAG-readiness logic -- no DB, no asyncio. Fixtures cover the Issue's
acceptance scenarios directly: independent questions, a simple chain,
branch/merge, and multi-page graphs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyProvision,
)
from auto_scoring.domain.job_scheduling import (
    QuestionStatus,
    direct_dependents,
    evaluate_readiness,
    plan_submission_jobs,
    question_statuses,
    recover_running_job,
)
from auto_scoring.domain.models import ErrorCategory, Job, JobKind, JobState

EPOCH = datetime(2026, 1, 1)


def _edge(a: str, b: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=a,
        to_question_id=b,
        provides=(DependencyProvision.SCORE,),
        rationale="test fixture",
    )


def _confirmed_graph(question_ids: list[str], edges: list[DependencyEdge]) -> DependencyGraph:
    draft = DependencyGraph.from_candidates(
        id="g1",
        test_id="test-1",
        version=1,
        question_ids=question_ids,
        edges=edges,
        created_at=EPOCH,
    )
    return draft.confirm(edges=edges, confirmed_at=EPOCH)


def _job(**overrides: object) -> Job:
    values: dict[str, object] = {
        "id": "job-1",
        "kind": JobKind.GRADING,
        "submission_id": "sub-1",
        "created_at": EPOCH,
        "updated_at": EPOCH,
    }
    values.update(overrides)
    return Job(**values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# All independent
# --------------------------------------------------------------------------- #
def test_all_independent_questions_are_all_ready_immediately() -> None:
    graph = _confirmed_graph(["q1", "q2", "q3"], [])
    plans = plan_submission_jobs(graph)
    assert {p.question_id: p.ready for p in plans} == {"q1": True, "q2": True, "q3": True}


# --------------------------------------------------------------------------- #
# Simple chain: A -> B, independent C
# --------------------------------------------------------------------------- #
def test_a_to_b_and_independent_c_only_b_waits() -> None:
    graph = _confirmed_graph(["qa", "qb", "qc"], [_edge("qa", "qb")])
    plans = {p.question_id: p for p in plan_submission_jobs(graph)}
    assert plans["qa"].ready is True
    assert plans["qc"].ready is True
    assert plans["qb"].ready is False
    assert plans["qb"].blocking_question_id == "qa"


def test_b_is_released_only_once_a_is_usable() -> None:
    graph = _confirmed_graph(["qa", "qb"], [_edge("qa", "qb")])
    not_done = evaluate_readiness(graph, "qb", {"qa": QuestionStatus.PENDING})
    assert not_done.ready is False
    unusable = evaluate_readiness(graph, "qb", {"qa": QuestionStatus.UNUSABLE})
    assert unusable.ready is False
    usable = evaluate_readiness(graph, "qb", {"qa": QuestionStatus.USABLE})
    assert usable.ready is True


def test_direct_dependents_of_a_is_just_b() -> None:
    graph = _confirmed_graph(["qa", "qb", "qc"], [_edge("qa", "qb")])
    assert direct_dependents(graph, "qa") == ["qb"]
    assert direct_dependents(graph, "qc") == []


# --------------------------------------------------------------------------- #
# Merge point: A, C -> B
# --------------------------------------------------------------------------- #
def test_merge_point_needs_every_prerequisite_usable() -> None:
    graph = _confirmed_graph(["qa", "qb", "qc"], [_edge("qa", "qb"), _edge("qc", "qb")])
    only_a = evaluate_readiness(
        graph, "qb", {"qa": QuestionStatus.USABLE, "qc": QuestionStatus.PENDING}
    )
    assert only_a.ready is False
    assert only_a.blocking_question_id == "qc"
    both = evaluate_readiness(
        graph, "qb", {"qa": QuestionStatus.USABLE, "qc": QuestionStatus.USABLE}
    )
    assert both.ready is True


def test_merge_point_blocking_question_id_is_deterministic_sorted_first() -> None:
    graph = _confirmed_graph(["qa", "qb", "qc"], [_edge("qa", "qb"), _edge("qc", "qb")])
    readiness = evaluate_readiness(graph, "qb", {})
    assert readiness.blocking_question_id == "qa"


# --------------------------------------------------------------------------- #
# Branch: A -> B, A -> C
# --------------------------------------------------------------------------- #
def test_branch_releases_both_dependents_once_prerequisite_usable() -> None:
    graph = _confirmed_graph(["qa", "qb", "qc"], [_edge("qa", "qb"), _edge("qa", "qc")])
    assert direct_dependents(graph, "qa") == ["qb", "qc"]
    statuses = {"qa": QuestionStatus.USABLE}
    assert evaluate_readiness(graph, "qb", statuses).ready is True
    assert evaluate_readiness(graph, "qc", statuses).ready is True


# --------------------------------------------------------------------------- #
# Multi-page DAG: p1q1 -> p2q1, independent p1q2
# --------------------------------------------------------------------------- #
def test_multi_page_dag_respects_cross_page_dependency() -> None:
    graph = _confirmed_graph(["p1q1", "p1q2", "p2q1"], [_edge("p1q1", "p2q1")])
    plans = {p.question_id: p for p in plan_submission_jobs(graph)}
    assert plans["p1q1"].ready is True
    assert plans["p1q2"].ready is True
    assert plans["p2q1"].ready is False


# --------------------------------------------------------------------------- #
# question_statuses
# --------------------------------------------------------------------------- #
def test_question_statuses_maps_succeeded_usable_to_usable() -> None:
    job = _job(question_id="qa", state=JobState.SUCCEEDED, usable=True)
    assert question_statuses([job]) == {"qa": QuestionStatus.USABLE}


def test_question_statuses_maps_succeeded_low_confidence_to_unusable() -> None:
    job = _job(question_id="qa", state=JobState.SUCCEEDED, usable=False)
    assert question_statuses([job]) == {"qa": QuestionStatus.UNUSABLE}


@pytest.mark.parametrize("state", [JobState.FAILED, JobState.CANCELLED])
def test_question_statuses_maps_failed_and_cancelled_to_unusable(state: JobState) -> None:
    job = _job(question_id="qa", state=state)
    assert question_statuses([job]) == {"qa": QuestionStatus.UNUSABLE}


@pytest.mark.parametrize("state", [JobState.QUEUED, JobState.RUNNING, JobState.BLOCKED])
def test_question_statuses_maps_in_flight_states_to_pending(state: JobState) -> None:
    job = _job(question_id="qa", state=state)
    assert question_statuses([job]) == {"qa": QuestionStatus.PENDING}


def test_question_statuses_ignores_jobs_without_a_question_id() -> None:
    job = _job(question_id=None, state=JobState.SUCCEEDED, usable=True)
    assert question_statuses([job]) == {}


def test_question_statuses_prefers_the_most_recently_updated_job_per_question() -> None:
    stale = _job(id="job-old", question_id="qa", state=JobState.FAILED, updated_at=EPOCH)
    fresh = _job(
        id="job-new",
        question_id="qa",
        state=JobState.SUCCEEDED,
        usable=True,
        updated_at=EPOCH + timedelta(seconds=10),
    )
    assert question_statuses([stale, fresh]) == {"qa": QuestionStatus.USABLE}


# --------------------------------------------------------------------------- #
# Crash recovery
# --------------------------------------------------------------------------- #
def test_recover_running_job_requeues_when_attempts_remain() -> None:
    job = _job(state=JobState.RUNNING, attempts=1, max_attempts=3)
    recovered = recover_running_job(job, at=EPOCH)
    assert recovered.state is JobState.QUEUED
    assert recovered.attempts == 1  # not incremented again


def test_recover_running_job_fails_permanently_once_attempts_exhausted() -> None:
    job = _job(state=JobState.RUNNING, attempts=3, max_attempts=3)
    recovered = recover_running_job(job, at=EPOCH)
    assert recovered.state is JobState.FAILED
    assert recovered.error_code is ErrorCategory.PERMANENT


def test_recover_running_job_rejects_a_job_not_currently_running() -> None:
    job = _job(state=JobState.QUEUED)
    with pytest.raises(ValueError, match="RUNNING"):
        recover_running_job(job, at=EPOCH)
