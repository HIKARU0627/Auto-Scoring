"""Submission-scoped DAG scheduling (Issue #18).

Pure functions only: given a confirmed `DependencyGraph` and each question's
current standing, decide which questions may run now, which must keep
waiting, and which direct dependents to re-check after one question
finishes. No I/O, no asyncio -- `auto_scoring.jobs.queue` is the engine that
actually drives `Job` rows through these decisions.

Design decisions: docs/job-queue.md.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from auto_scoring.domain.dependency_graph import DependencyGraph
from auto_scoring.domain.models import ErrorCategory, Job, JobState

if TYPE_CHECKING:
    from datetime import datetime


class QuestionStatus(StrEnum):
    """One question's current standing for DAG-readiness purposes."""

    #: Not finished yet (queued, running, or itself still blocked).
    PENDING = "pending"
    #: Finished with a result a dependent may rely on (Issue #18 §4.4).
    USABLE = "usable"
    #: Finished but not usable: low confidence, failed, or cancelled -- a
    #: dependent must stay locked and never call the external provider.
    UNUSABLE = "unusable"


@dataclass(frozen=True, kw_only=True)
class Readiness:
    """Whether one question may start (or resume) now."""

    ready: bool
    #: Set only when ``ready`` is ``False``: the first (sorted) prerequisite
    #: that is not yet USABLE, for display (`Job.blocked_on_question_id`).
    blocking_question_id: str | None = None


def _prerequisites(graph: DependencyGraph, question_id: str) -> list[str]:
    return sorted(
        edge.from_question_id for edge in graph.edges if edge.to_question_id == question_id
    )


def direct_dependents(graph: DependencyGraph, question_id: str) -> list[str]:
    """Questions with a direct edge from ``question_id`` -- the only
    candidates that could possibly change status when ``question_id``
    finishes."""
    return sorted(
        {edge.to_question_id for edge in graph.edges if edge.from_question_id == question_id}
    )


def evaluate_readiness(
    graph: DependencyGraph, question_id: str, statuses: Mapping[str, QuestionStatus]
) -> Readiness:
    """Whether ``question_id`` may run now, given the latest known
    ``statuses`` of every question in ``graph``.

    A question with no prerequisites is always ready. One with prerequisites
    is ready only once *every* direct prerequisite is USABLE -- a merge point
    (``A, C -> B``) needs both, not just one (business-rules-and-evaluation-
    data.md §4.4). A question missing from ``statuses`` is treated as
    PENDING (not yet attempted), never as an error -- this lets the same
    function answer both "what should this submission's jobs look like when
    first created" (nothing has run yet) and "what changed after one job
    finished".
    """
    prerequisites = _prerequisites(graph, question_id)
    if not prerequisites:
        return Readiness(ready=True)
    unmet = [
        qid
        for qid in prerequisites
        if statuses.get(qid, QuestionStatus.PENDING) is not QuestionStatus.USABLE
    ]
    if not unmet:
        return Readiness(ready=True)
    return Readiness(ready=False, blocking_question_id=unmet[0])


def question_statuses(jobs: Sequence[Job]) -> dict[str, QuestionStatus]:
    """Map each job's ``question_id`` to its current `QuestionStatus`.

    Jobs with ``question_id is None`` (not part of Submission-DAG
    scheduling) are skipped. When more than one job exists for the same
    question (should not happen for the currently-active dependency-graph
    version -- see the ``uq_jobs_submission_question_graph_version``
    constraint -- but can for stale, already-cancelled versions), the most
    recently updated one wins.
    """
    latest: dict[str, Job] = {}
    for job in jobs:
        if job.question_id is None:
            continue
        current = latest.get(job.question_id)
        if current is None or job.updated_at >= current.updated_at:
            latest[job.question_id] = job

    result: dict[str, QuestionStatus] = {}
    for question_id, job in latest.items():
        if job.state is JobState.SUCCEEDED:
            result[question_id] = QuestionStatus.USABLE if job.usable else QuestionStatus.UNUSABLE
        elif job.state in (JobState.FAILED, JobState.CANCELLED):
            result[question_id] = QuestionStatus.UNUSABLE
        else:
            result[question_id] = QuestionStatus.PENDING
    return result


@dataclass(frozen=True, kw_only=True)
class InitialPlan:
    """What state a brand-new per-question job should start in."""

    question_id: str
    ready: bool
    blocking_question_id: str | None = None


def plan_submission_jobs(graph: DependencyGraph) -> list[InitialPlan]:
    """One `InitialPlan` per question in ``graph``, in a stable (sorted)
    order -- nothing has run yet, so this is `evaluate_readiness` against an
    empty status map for every question.
    """
    plans: list[InitialPlan] = []
    for question_id in sorted(graph.question_ids):
        readiness = evaluate_readiness(graph, question_id, {})
        plans.append(
            InitialPlan(
                question_id=question_id,
                ready=readiness.ready,
                blocking_question_id=readiness.blocking_question_id,
            )
        )
    return plans


def recover_running_job(job: Job, *, at: datetime) -> Job:
    """Recover one job left ``RUNNING`` by a killed process (Issue #18
    acceptance: "起動時にrunningのまま残ったjobを規則どおり回収し…").

    The interrupted attempt already counted (``transitioned_to(RUNNING)``
    incremented ``attempts`` when it started), so this never increments it
    again. Requeues if attempts remain; otherwise fails it as exhausted so a
    human decides via the manual retry API rather than looping forever.
    """
    if job.state is not JobState.RUNNING:
        raise ValueError(f"job {job.id!r} is not RUNNING (got {job.state!s})")
    if job.attempts < job.max_attempts:
        return job.transitioned_to(JobState.QUEUED, updated_at=at)
    return job.transitioned_to(
        JobState.FAILED,
        updated_at=at,
        error="startup recovery: exhausted retries after an interrupted run",
        error_code=ErrorCategory.PERMANENT,
    )
