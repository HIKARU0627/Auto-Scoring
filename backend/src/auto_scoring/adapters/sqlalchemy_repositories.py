"""SQLAlchemy implementations of the domain repository ports.

Each repository takes domain dataclasses in and hands domain dataclasses back;
callers never see an ORM row. The append-only repositories expose only ``add`` +
readers, so an AI proposal and the human-confirmed value always coexist as
separate rows (issue #11 acceptance).

Every ``add`` flushes immediately. The tables are wired with plain
``ForeignKey`` columns and no ``relationship()``, so the session's unit of work
does not reorder inserts across mappers; flushing per ``add`` makes the caller's
order (parents first) the order that reaches the database, and surfaces a
constraint violation at the offending call rather than at ``commit``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

import auto_scoring.adapters._mappers as m
from auto_scoring.db.orm import (
    AnnotationRow,
    DependencyEdgeRow,
    DependencyGraphRow,
    GradeResultRow,
    JobRow,
    QuestionRow,
    RecognitionResultRow,
    ReviewRow,
    RubricCriterionRow,
    RubricRow,
    SubmissionRow,
    TestRow,
)
from auto_scoring.domain.dependency_graph import (
    DependencyGraph,
    DependencyGraphError,
    DependencyGraphStatus,
)
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
    ensure_job_transition,
    ensure_submission_transition,
)


class SqlAlchemyTestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, test: Test) -> None:
        self._session.add(m.test_to_row(test))
        self._session.flush()

    def get(self, test_id: str) -> Test | None:
        row = self._session.get(TestRow, test_id)
        return m.test_from_row(row) if row is not None else None

    def list_all(self) -> list[Test]:
        rows = self._session.scalars(select(TestRow).order_by(TestRow.created_at))
        return [m.test_from_row(row) for row in rows]


class SqlAlchemyQuestionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, question: Question) -> None:
        self._session.add(m.question_to_row(question))
        self._session.flush()

    def get(self, question_id: str) -> Question | None:
        row = self._session.get(QuestionRow, question_id)
        return m.question_from_row(row) if row is not None else None

    def list_for_test(self, test_id: str) -> list[Question]:
        rows = self._session.scalars(
            select(QuestionRow)
            .where(QuestionRow.test_id == test_id)
            .order_by(QuestionRow.page, QuestionRow.number)
        )
        return [m.question_from_row(row) for row in rows]


class SqlAlchemyRubricRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, rubric: Rubric) -> None:
        parent, children = m.rubric_rows(rubric)
        self._session.add(parent)
        self._session.flush()  # rubric row before its criteria
        self._session.add_all(children)
        self._session.flush()

    def get_for_question(self, question_id: str) -> Rubric | None:
        row = self._session.scalars(
            select(RubricRow).where(RubricRow.question_id == question_id)
        ).one_or_none()
        if row is None:
            return None
        criteria = list(
            self._session.scalars(
                select(RubricCriterionRow).where(RubricCriterionRow.rubric_id == row.id)
            )
        )
        return m.rubric_from_rows(row, criteria)


class SqlAlchemySubmissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, submission: Submission) -> None:
        self._session.add(m.submission_to_row(submission))
        self._session.flush()

    def get(self, submission_id: str) -> Submission | None:
        row = self._session.get(SubmissionRow, submission_id)
        return m.submission_from_row(row) if row is not None else None

    def list_for_test(self, test_id: str) -> list[Submission]:
        rows = self._session.scalars(
            select(SubmissionRow)
            .where(SubmissionRow.test_id == test_id)
            .order_by(SubmissionRow.created_at)
        )
        return [m.submission_from_row(row) for row in rows]

    def set_state(self, submission_id: str, state: SubmissionState) -> None:
        row = self._session.get(SubmissionRow, submission_id)
        if row is None:
            raise LookupError(f"submission {submission_id!r} not found")
        ensure_submission_transition(SubmissionState(row.state), state)
        row.state = state


class SqlAlchemyRecognitionResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: RecognitionResult) -> None:
        self._session.add(m.recognition_to_row(result))
        self._session.flush()

    def get(self, result_id: str) -> RecognitionResult | None:
        row = self._session.get(RecognitionResultRow, result_id)
        return m.recognition_from_row(row) if row is not None else None

    def history(self, submission_id: str, question_id: str) -> list[RecognitionResult]:
        rows = self._session.scalars(
            select(RecognitionResultRow)
            .where(
                RecognitionResultRow.submission_id == submission_id,
                RecognitionResultRow.question_id == question_id,
            )
            .order_by(RecognitionResultRow.created_at)
        )
        return [m.recognition_from_row(row) for row in rows]


class SqlAlchemyGradeResultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: GradeResult) -> None:
        self._session.add(m.grade_to_row(result))
        self._session.flush()

    def get(self, result_id: str) -> GradeResult | None:
        row = self._session.get(GradeResultRow, result_id)
        return m.grade_from_row(row) if row is not None else None

    def history(self, submission_id: str, question_id: str) -> list[GradeResult]:
        rows = self._session.scalars(
            select(GradeResultRow)
            .where(
                GradeResultRow.submission_id == submission_id,
                GradeResultRow.question_id == question_id,
            )
            .order_by(GradeResultRow.created_at)
        )
        return [m.grade_from_row(row) for row in rows]

    def latest(
        self, submission_id: str, question_id: str, source: GradingSource
    ) -> GradeResult | None:
        row = self._session.scalars(
            select(GradeResultRow)
            .where(
                GradeResultRow.submission_id == submission_id,
                GradeResultRow.question_id == question_id,
                GradeResultRow.source == source,
            )
            .order_by(GradeResultRow.created_at.desc())
            .limit(1)
        ).one_or_none()
        return m.grade_from_row(row) if row is not None else None


class SqlAlchemyAnnotationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, annotation: Annotation) -> None:
        self._session.add(m.annotation_to_row(annotation))
        self._session.flush()

    def list_for(self, submission_id: str, question_id: str) -> list[Annotation]:
        rows = self._session.scalars(
            select(AnnotationRow)
            .where(
                AnnotationRow.submission_id == submission_id,
                AnnotationRow.question_id == question_id,
            )
            .order_by(AnnotationRow.created_at)
        )
        return [m.annotation_from_row(row) for row in rows]


class SqlAlchemyReviewRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, review: Review) -> None:
        self._session.add(m.review_to_row(review))
        self._session.flush()

    def history(self, submission_id: str, question_id: str) -> list[Review]:
        rows = self._session.scalars(
            select(ReviewRow)
            .where(
                ReviewRow.submission_id == submission_id,
                ReviewRow.question_id == question_id,
            )
            .order_by(ReviewRow.created_at)
        )
        return [m.review_from_row(row) for row in rows]


class SqlAlchemyJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, job: Job) -> None:
        self._session.add(m.job_to_row(job))
        self._session.flush()

    def get(self, job_id: str) -> Job | None:
        row = self._session.get(JobRow, job_id)
        return m.job_from_row(row) if row is not None else None

    def save(self, job: Job) -> None:
        row = self._session.get(JobRow, job.id)
        if row is None:
            raise LookupError(f"job {job.id!r} not found")
        current_state = JobState(row.state)
        if job.state is not current_state:
            ensure_job_transition(current_state, job.state)
        row.state = job.state
        row.attempts = job.attempts
        row.max_attempts = job.max_attempts
        row.last_error = job.last_error
        row.blocked_on_question_id = job.blocked_on_question_id
        row.updated_at = job.updated_at

    def list_by_state(self, state: JobState) -> list[Job]:
        rows = self._session.scalars(
            select(JobRow).where(JobRow.state == state).order_by(JobRow.created_at)
        )
        return [m.job_from_row(row) for row in rows]

    def list_incomplete_for_stale_versions(self, test_id: str, current_version: int) -> list[Job]:
        rows = self._session.scalars(
            select(JobRow)
            .join(SubmissionRow, JobRow.submission_id == SubmissionRow.id)
            .where(
                SubmissionRow.test_id == test_id,
                JobRow.dependency_graph_version.is_not(None),
                JobRow.dependency_graph_version != current_version,
                JobRow.state.in_([JobState.QUEUED, JobState.RUNNING, JobState.BLOCKED]),
            )
            .order_by(JobRow.created_at)
        )
        return [m.job_from_row(row) for row in rows]


class SqlAlchemyDependencyGraphRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, graph: DependencyGraph) -> None:
        """Upsert on ``(test_id, version)``.

        Inserts a new row when this version has never been saved. When it
        has, the existing row's edges are replaced and its status/unresolved
        fields updated -- unless it is already CONFIRMED, in which case this
        raises: a confirmed version is immutable (see `DependencyGraph.confirm`).
        """
        existing = self._session.scalars(
            select(DependencyGraphRow).where(
                DependencyGraphRow.test_id == graph.test_id,
                DependencyGraphRow.version == graph.version,
            )
        ).one_or_none()

        if existing is None:
            parent, children = m.dependency_graph_rows(graph)
            self._session.add(parent)
            self._session.flush()  # graph row before its edges
            self._session.add_all(children)
            self._session.flush()
            return

        if DependencyGraphStatus(existing.status) is DependencyGraphStatus.CONFIRMED:
            raise DependencyGraphError(
                f"dependency graph {graph.test_id!r} v{graph.version} is already confirmed "
                "and cannot be overwritten; save a new version instead"
            )

        for edge_row in self._session.scalars(
            select(DependencyEdgeRow).where(DependencyEdgeRow.graph_id == existing.id)
        ):
            self._session.delete(edge_row)
        self._session.flush()  # old edges gone before the new ones land

        existing.status = graph.status
        existing.question_ids = sorted(graph.question_ids)
        existing.unresolved = [u.to_dict() for u in graph.unresolved]
        existing.created_at = graph.created_at
        existing.confirmed_at = graph.confirmed_at
        _, children = m.dependency_graph_rows(graph)
        for child in children:
            child.graph_id = existing.id
            child.id = f"{existing.id}:{child.from_question_id}:{child.to_question_id}"
        self._session.add_all(children)
        self._session.flush()

    def _hydrate(self, row: DependencyGraphRow) -> DependencyGraph:
        edges = list(
            self._session.scalars(
                select(DependencyEdgeRow).where(DependencyEdgeRow.graph_id == row.id)
            )
        )
        return m.dependency_graph_from_rows(row, edges)

    def get(self, graph_id: str) -> DependencyGraph | None:
        row = self._session.get(DependencyGraphRow, graph_id)
        return self._hydrate(row) if row is not None else None

    def get_latest(self, test_id: str) -> DependencyGraph | None:
        row = self._session.scalars(
            select(DependencyGraphRow)
            .where(DependencyGraphRow.test_id == test_id)
            .order_by(DependencyGraphRow.version.desc())
            .limit(1)
        ).one_or_none()
        return self._hydrate(row) if row is not None else None

    def get_latest_confirmed(self, test_id: str) -> DependencyGraph | None:
        row = self._session.scalars(
            select(DependencyGraphRow)
            .where(
                DependencyGraphRow.test_id == test_id,
                DependencyGraphRow.status == DependencyGraphStatus.CONFIRMED,
            )
            .order_by(DependencyGraphRow.version.desc())
            .limit(1)
        ).one_or_none()
        return self._hydrate(row) if row is not None else None

    def list_versions(self, test_id: str) -> list[DependencyGraph]:
        rows = self._session.scalars(
            select(DependencyGraphRow)
            .where(DependencyGraphRow.test_id == test_id)
            .order_by(DependencyGraphRow.version)
        )
        return [self._hydrate(row) for row in rows]
