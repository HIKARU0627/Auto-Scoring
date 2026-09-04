"""Persistence ports for the MVP entities.

The domain only ever sees these protocols; concrete SQLAlchemy adapters live in
`auto_scoring.adapters` (see `AGENTS.md` "Architecture"). A :class:`UnitOfWork`
owns one transaction boundary: mutations are invisible until :meth:`commit`, and
`__exit__` rolls back anything not committed.

Result repositories (:class:`RecognitionResultRepository`,
:class:`GradeResultRepository`, :class:`ReviewRepository`) are append-only:
``add`` inserts a new row and nothing updates an existing one, so an AI proposal
and the human-confirmed value are always retrievable side by side
(simplified-design-specification.md §19, §35-5).
"""

from __future__ import annotations

from typing import Protocol

from auto_scoring.domain.dependency_graph import DependencyGraph
from auto_scoring.domain.models import (
    Annotation,
    GradeResult,
    GradingSource,
    Job,
    JobState,
    Question,
    RecognitionResult,
    Review,
    Rubric,
    Submission,
    SubmissionState,
    Test,
)


class TestRepository(Protocol):
    def add(self, test: Test) -> None: ...
    def get(self, test_id: str) -> Test | None: ...
    def list_all(self) -> list[Test]: ...


class QuestionRepository(Protocol):
    def add(self, question: Question) -> None: ...
    def get(self, question_id: str) -> Question | None: ...
    def list_for_test(self, test_id: str) -> list[Question]: ...


class RubricRepository(Protocol):
    def add(self, rubric: Rubric) -> None: ...
    def get_for_question(self, question_id: str) -> Rubric | None: ...


class SubmissionRepository(Protocol):
    def add(self, submission: Submission) -> None: ...
    def get(self, submission_id: str) -> Submission | None: ...
    def list_for_test(self, test_id: str) -> list[Submission]: ...
    def set_state(self, submission_id: str, state: SubmissionState) -> None: ...


class RecognitionResultRepository(Protocol):
    """Append-only."""

    def add(self, result: RecognitionResult) -> None: ...
    def get(self, result_id: str) -> RecognitionResult | None: ...
    def history(self, submission_id: str, question_id: str) -> list[RecognitionResult]: ...


class GradeResultRepository(Protocol):
    """Append-only."""

    def add(self, result: GradeResult) -> None: ...
    def get(self, result_id: str) -> GradeResult | None: ...
    def history(self, submission_id: str, question_id: str) -> list[GradeResult]: ...
    def latest(
        self, submission_id: str, question_id: str, source: GradingSource
    ) -> GradeResult | None: ...


class AnnotationRepository(Protocol):
    def add(self, annotation: Annotation) -> None: ...
    def list_for(self, submission_id: str, question_id: str) -> list[Annotation]: ...


class ReviewRepository(Protocol):
    """Append-only operation history."""

    def add(self, review: Review) -> None: ...
    def history(self, submission_id: str, question_id: str) -> list[Review]: ...


class JobRepository(Protocol):
    def add(self, job: Job) -> None: ...
    def get(self, job_id: str) -> Job | None: ...
    def save(self, job: Job) -> None: ...
    def list_by_state(self, state: JobState) -> list[Job]: ...

    def list_incomplete_for_stale_versions(self, test_id: str, current_version: int) -> list[Job]:
        """Jobs for ``test_id`` still QUEUED/RUNNING/BLOCKED against a
        `dependency_graph_version` other than ``current_version`` (Issue #26:
        superseded-graph job invalidation). Jobs never tagged with a graph
        version (``dependency_graph_version is None``) are not "stale" by
        this definition and are excluded.
        """
        ...


class DependencyGraphRepository(Protocol):
    """One test's dependency-graph versions (Issue #26).

    ``save`` upserts on ``(test_id, version)``: a DRAFT row for that version is
    replaced in place (new candidates, or the human's confirm), but a
    CONFIRMED row is immutable -- ``save`` raises rather than overwrite one, so
    changing a confirmed graph always means a new, higher version.
    """

    def save(self, graph: DependencyGraph) -> None: ...
    def get(self, graph_id: str) -> DependencyGraph | None: ...
    def get_latest(self, test_id: str) -> DependencyGraph | None: ...

    def get_latest_confirmed(self, test_id: str) -> DependencyGraph | None:
        """The highest-versioned CONFIRMED graph, regardless of whether a
        newer DRAFT also exists (Issue #26: `confirm` must reject a version
        older than this -- see `auto_scoring.api.dependency_graph_router`).
        """
        ...

    def try_confirm(self, confirmed: DependencyGraph) -> bool:
        """Atomic compare-and-set DRAFT -> CONFIRMED (Issue #26 review).

        Returns ``True`` and replaces the row's edges only if it is still
        DRAFT and no higher version for the same test is already CONFIRMED at
        the moment of the write; returns ``False`` -- unchanged -- otherwise,
        so two concurrent confirms can never both succeed.
        """
        ...

    def list_versions(self, test_id: str) -> list[DependencyGraph]: ...


class UnitOfWork(Protocol):
    """One transaction boundary over every repository."""

    tests: TestRepository
    questions: QuestionRepository
    rubrics: RubricRepository
    submissions: SubmissionRepository
    recognitions: RecognitionResultRepository
    grades: GradeResultRepository
    annotations: AnnotationRepository
    reviews: ReviewRepository
    jobs: JobRepository
    dependency_graphs: DependencyGraphRepository

    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *exc_info: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
