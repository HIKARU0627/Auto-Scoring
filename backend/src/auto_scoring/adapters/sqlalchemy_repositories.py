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

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

import auto_scoring.adapters._mappers as m
from auto_scoring.db.orm import (
    AnnotationRow,
    AnswerImageRow,
    DependencyEdgeRow,
    DependencyGraphRow,
    ExportRow,
    GradeResultRow,
    JobRow,
    QuestionRow,
    RecognitionResultRow,
    ReviewRow,
    RubricCriterionRow,
    RubricRow,
    SubmissionRow,
    TestMaterialRow,
    TestRow,
)
from auto_scoring.domain.dependency_graph import (
    DependencyGraph,
    DependencyGraphError,
    DependencyGraphStatus,
)
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.models import (
    Annotation,
    AnswerImage,
    AnswerImageStatus,
    Export,
    GradeResult,
    GradingSource,
    Job,
    JobSaveConflict,
    JobState,
    Question,
    RecognitionResult,
    Review,
    Rubric,
    Submission,
    SubmissionState,
    Test,
    TestStatus,
    ensure_job_transition,
    ensure_submission_transition,
)
from auto_scoring.domain.test_material import TestMaterial


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

    def delete(self, test_id: str) -> None:
        row = self._session.get(TestRow, test_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def mark_ready(self, test_id: str) -> bool:
        result = cast(
            "CursorResult[Any]",
            self._session.execute(
                update(TestRow)
                .where(TestRow.id == test_id, TestRow.status == TestStatus.DRAFT)
                .values(status=TestStatus.READY)
            ),
        )
        cached = self._session.get(TestRow, test_id)
        if cached is not None:
            self._session.refresh(cached)
        return result.rowcount == 1


class SqlAlchemyTestMaterialRepository:
    """The role-tagged files registered for a test (Issue #101)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, material: TestMaterial) -> None:
        self._session.add(m.test_material_to_row(material))
        self._session.flush()

    def list_for_test(self, test_id: str) -> list[TestMaterial]:
        rows = self._session.scalars(
            select(TestMaterialRow)
            .where(TestMaterialRow.test_id == test_id)
            .order_by(TestMaterialRow.created_at, TestMaterialRow.id)
        )
        return [m.test_material_from_row(row) for row in rows]

    def find_by_content(
        self, test_id: str, *, role: MaterialRole, sha256: str
    ) -> TestMaterial | None:
        """The material already holding this exact content under this role.

        What makes retrying a partially-failed batch safe: the intake screen
        re-runs only the rows that failed, but a row can fail *after* its
        write committed (a dropped response), so the retry must recognize its
        own earlier success instead of attaching a second copy.
        """
        row = self._session.scalars(
            select(TestMaterialRow).where(
                TestMaterialRow.test_id == test_id,
                TestMaterialRow.role == role,
                TestMaterialRow.sha256 == sha256,
            )
        ).first()
        return m.test_material_from_row(row) if row is not None else None


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

    def delete_for_test(self, test_id: str) -> None:
        self._session.execute(delete(QuestionRow).where(QuestionRow.test_id == test_id))
        self._session.flush()


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

    def find_by_content_hash(self, test_id: str, source_pdf_sha256: str) -> Submission | None:
        row = self._session.scalars(
            select(SubmissionRow).where(
                SubmissionRow.test_id == test_id,
                SubmissionRow.source_pdf_sha256 == source_pdf_sha256,
            )
        ).first()
        return m.submission_from_row(row) if row is not None else None

    def mark_intake_outcome(
        self, submission_id: str, state: SubmissionState, review_reason: str | None
    ) -> None:
        row = self._session.get(SubmissionRow, submission_id)
        if row is None:
            raise LookupError(f"submission {submission_id!r} not found")
        ensure_submission_transition(SubmissionState(row.state), state)
        row.state = state
        row.review_reason = review_reason

    def claim_for_retry(self, submission_id: str) -> bool:
        """Atomically move ``submission_id`` from ``error`` to ``unprocessed``,
        as a single conditional ``UPDATE ... WHERE state = 'error'`` rather
        than a read-then-write -- so two concurrent retries of the same
        errored submission can't both read "error" and both go on to run (and
        commit) the full intake pipeline. Returns whether *this* call won the
        race; the loser should treat that as a conflict, not retry again
        itself, since the winner is already handling it.
        """
        result = cast(
            "CursorResult[Any]",
            self._session.execute(
                update(SubmissionRow)
                .where(
                    SubmissionRow.id == submission_id, SubmissionRow.state == SubmissionState.ERROR
                )
                .values(state=SubmissionState.UNPROCESSED)
            ),
        )
        # The raw UPDATE above bypasses the ORM, so a SubmissionRow already
        # cached in this session's identity map (e.g. from an earlier
        # find_by_content_hash) would otherwise keep showing the stale
        # pre-claim state to later session.get() calls in this same session.
        cached = self._session.get(SubmissionRow, submission_id)
        if cached is not None:
            self._session.refresh(cached)
        return result.rowcount == 1

    def has_downstream_processing(self, submission_id: str) -> bool:
        row_types: tuple[type[RecognitionResultRow | GradeResultRow | ReviewRow | JobRow], ...] = (
            RecognitionResultRow,
            GradeResultRow,
            ReviewRow,
            JobRow,
        )
        return any(
            self._session.execute(
                select(row_type.id).where(row_type.submission_id == submission_id).limit(1)
            ).first()
            is not None
            for row_type in row_types
        )


class SqlAlchemyAnswerImageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, image: AnswerImage) -> None:
        self._session.add(m.answer_image_to_row(image))
        self._session.flush()

    def list_for_submission(self, submission_id: str) -> list[AnswerImage]:
        rows = self._session.scalars(
            select(AnswerImageRow)
            .where(AnswerImageRow.submission_id == submission_id)
            .order_by(AnswerImageRow.page, AnswerImageRow.question_id)
        )
        return [m.answer_image_from_row(row) for row in rows]

    def mark_needs_review(self, submission_id: str, question_id: str, reason: str) -> None:
        # A plain UPDATE rather than read-modify-write: nothing else about
        # the row is being changed, and the ``status``/``reason`` pair the
        # DB CHECK constraint requires to agree is set in the same
        # statement.
        self._session.execute(
            update(AnswerImageRow)
            .where(
                AnswerImageRow.submission_id == submission_id,
                AnswerImageRow.question_id == question_id,
            )
            .values(status=AnswerImageStatus.NEEDS_REVIEW, reason=reason)
        )
        self._session.flush()

    def replace_for_submission(self, submission_id: str, images: Sequence[AnswerImage]) -> None:
        self._session.execute(
            delete(AnswerImageRow).where(AnswerImageRow.submission_id == submission_id)
        )
        self._session.flush()
        for image in images:
            self._session.add(m.answer_image_to_row(image))
        self._session.flush()


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

    def list_ai_for_submission(self, submission_id: str) -> list[GradeResult]:
        rows = self._session.scalars(
            select(GradeResultRow)
            .where(
                GradeResultRow.submission_id == submission_id,
                GradeResultRow.source == GradingSource.AI,
            )
            .order_by(GradeResultRow.created_at)
        )
        return [m.grade_from_row(row) for row in rows]

    def list_ai_since(self, since: datetime) -> list[GradeResult]:
        rows = self._session.scalars(
            select(GradeResultRow)
            .where(
                GradeResultRow.source == GradingSource.AI,
                GradeResultRow.created_at >= since,
            )
            .order_by(GradeResultRow.created_at)
        )
        return [m.grade_from_row(row) for row in rows]


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

    def save(
        self,
        job: Job,
        *,
        expected_state: JobState,
        expected_attempts: int | None = None,
        require_usable_unset: bool = False,
    ) -> None:
        """Compare-and-set on ``expected_state`` -- the state the *caller*
        observed before deciding on this transition -- not a state this call
        re-reads from the row itself.

        Re-reading "current state" from the row inside `save()` (the
        previous implementation) reopens the exact race it was meant to
        close: if two workers both read the same job as QUEUED and both
        decide to move it to RUNNING, whichever `save()` runs second would
        re-read the row *after* the first has already committed RUNNING, see
        its own freshly re-read ``current_state`` already equal to its own
        target state (RUNNING), skip the `ensure_job_transition` check
        entirely (``job.state is not current_state`` is false), and then its
        own ``WHERE state = 'running'`` would match the row the first writer
        just produced -- silently "succeeding" a claim this call never
        actually observed permission for (Issue #26 review). Requiring the
        caller to pass the state it read via `get()` before calling
        `Job.transitioned_to(...)` ties the compare-and-set to what was
        actually observed, so the second worker's ``WHERE state = 'queued'``
        no longer matches and it correctly loses the race.

        ``expected_attempts`` adds ``attempts ==`` that value to the same
        ``WHERE``: for a non-terminal state a job can return to (FAILED,
        via a retry), ``state`` alone cannot tell the row the caller read
        apart from a *different*, later occupant of that same state -- a
        concurrent FAILED -> QUEUED -> RUNNING -> FAILED cycle changes
        ``attempts`` (only ever bumped on a transition through RUNNING)
        even though it lands back on the same ``state``, so pinning both
        together closes the ABA hole `mark_usable`'s own
        ``expected_attempts`` already closes for the same reason (review
        round 6, P1; round 9, P1 applies it here too).

        ``require_usable_unset`` adds ``usable IS NULL`` to that same
        ``WHERE``: `mark_usable` never changes `state`, so without this a
        `retry_job` call that read ``usable=None`` and this call's own
        state-only precondition could both still commit even though
        `mark_usable` committed ``usable=True`` in between -- this call's
        `WHERE` never noticed, because it never looked at that column
        (Issue #18 review round 5, P1).
        """
        if job.state is not expected_state:
            ensure_job_transition(expected_state, job.state)

        conditions = [JobRow.id == job.id, JobRow.state == expected_state]
        if expected_attempts is not None:
            conditions.append(JobRow.attempts == expected_attempts)
        if require_usable_unset:
            conditions.append(JobRow.usable.is_(None))
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(JobRow)
                .where(*conditions)
                .values(
                    state=job.state,
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                    last_error=job.last_error,
                    error_code=job.error_code,
                    blocked_on_question_id=job.blocked_on_question_id,
                    usable=job.usable,
                    updated_at=job.updated_at,
                )
            ),
        )
        row = self._session.get(JobRow, job.id)
        if result.rowcount != 1:
            if row is None:
                raise LookupError(f"job {job.id!r} not found")
            raise JobSaveConflict(job.id, expected_state)
        if row is not None:
            self._session.expire(row)

    def list_by_state(self, state: JobState) -> list[Job]:
        rows = self._session.scalars(
            select(JobRow).where(JobRow.state == state).order_by(JobRow.created_at)
        )
        return [m.job_from_row(row) for row in rows]

    def list_for_submission(self, submission_id: str) -> list[Job]:
        rows = self._session.scalars(
            select(JobRow).where(JobRow.submission_id == submission_id).order_by(JobRow.created_at)
        )
        return [m.job_from_row(row) for row in rows]

    def mark_usable(
        self, job_id: str, *, usable: bool, expected_state: JobState, expected_attempts: int
    ) -> bool:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(JobRow)
                .where(
                    JobRow.id == job_id,
                    JobRow.state == expected_state,
                    JobRow.attempts == expected_attempts,
                )
                .values(usable=usable)
            ),
        )
        row = self._session.get(JobRow, job_id)
        if row is not None and result.rowcount == 1:
            self._session.expire(row)
        return result.rowcount == 1

    def list_incomplete_for_stale_versions(self, test_id: str, current_version: int) -> list[Job]:
        # FAILED is not terminal here in general: FAILED -> QUEUED is a
        # valid retry transition (see `auto_scoring.domain.models.
        # _JOB_TRANSITIONS` and docs/data-model-and-local-storage.md), so a
        # stale FAILED job left unlisted could still be retried later and
        # run against the superseded graph version (Issue #26 review).
        #
        # A FAILED job whose `usable` is already set is the one exception:
        # a human approved its downstream effect via `mark_question_usable`
        # (`retry_job`/`cancel_job` already refuse to touch such a job for
        # the same reason -- review rounds 4/5), and any dependent that was
        # BLOCKED on it may already be running or done. Treating it as
        # "incomplete" here would let `confirm`'s reissue path cancel and
        # replace it, silently clearing that approval while its already-
        # released dependent keeps processing against a prerequisite that
        # no longer has any record of ever having been approved (review
        # round 6, P1). It is, for scheduling purposes, as terminal as
        # SUCCEEDED/CANCELLED -- the exact same status `question_statuses`
        # already reads it as.
        rows = self._session.scalars(
            select(JobRow)
            .join(SubmissionRow, JobRow.submission_id == SubmissionRow.id)
            .where(
                SubmissionRow.test_id == test_id,
                JobRow.dependency_graph_version.is_not(None),
                JobRow.dependency_graph_version != current_version,
                or_(
                    JobRow.state.in_([JobState.QUEUED, JobState.RUNNING, JobState.BLOCKED]),
                    and_(JobRow.state == JobState.FAILED, JobRow.usable.is_(None)),
                ),
            )
            .order_by(JobRow.created_at)
        )
        return [m.job_from_row(row) for row in rows]


class SqlAlchemyExportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, export: Export) -> None:
        self._session.add(m.export_to_row(export))
        self._session.flush()

    def get(self, export_id: str) -> Export | None:
        row = self._session.get(ExportRow, export_id)
        return m.export_from_row(row) if row is not None else None

    def list_for_submission(self, submission_id: str) -> list[Export]:
        rows = self._session.scalars(
            select(ExportRow)
            .where(ExportRow.submission_id == submission_id)
            .order_by(ExportRow.created_at)
        )
        return [m.export_from_row(row) for row in rows]

    def latest_for_submission(self, submission_id: str) -> Export | None:
        row = self._session.scalars(
            select(ExportRow)
            .where(ExportRow.submission_id == submission_id)
            .order_by(ExportRow.created_at.desc())
            .limit(1)
        ).first()
        return m.export_from_row(row) if row is not None else None

    def all_file_paths(self) -> frozenset[str]:
        return frozenset(self._session.scalars(select(ExportRow.file_path)))

    def repair_file_hash(self, export_id: str, file_sha256: str) -> None:
        self._session.execute(
            update(ExportRow).where(ExportRow.id == export_id).values(file_sha256=file_sha256)
        )
        self._session.flush()


class SqlAlchemyDependencyGraphRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, graph: DependencyGraph) -> None:
        """Upsert on ``(test_id, version)``.

        Inserts a new row when this version has never been saved. When it
        has, the existing row is overwritten -- unless it is already
        CONFIRMED, in which case this raises: a confirmed version is
        immutable (see `DependencyGraph.confirm`).

        The overwrite itself is a compare-and-set (``WHERE status =
        'draft'``), not a blind PK update: the early ``existing.status``
        check above only proves the row was DRAFT *when this call read it*,
        and says nothing about whether another transaction (`try_confirm`)
        confirmed it in the meantime. Without the ``WHERE``, this call's
        edge-delete-then-unconditional-UPDATE would still run against a row
        that has since become CONFIRMED, deleting its reviewed edges and
        writing this call's (stale, pre-confirm) status back over CONFIRMED
        -- silently un-confirming a graph a human already signed off on
        (Issue #26 review; the same class of bug `try_confirm` and
        `JobRepository.save` were already hardened against). A rowcount of 0
        means the row moved on since the read above; report it as the same
        `DependencyGraphError` as the early check rather than corrupting
        whichever write actually won.
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

        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(DependencyGraphRow)
                .where(
                    DependencyGraphRow.id == existing.id,
                    DependencyGraphRow.status == DependencyGraphStatus.DRAFT,
                )
                .values(
                    status=graph.status,
                    question_ids=sorted(graph.question_ids),
                    unresolved=[u.to_dict() for u in graph.unresolved],
                    created_at=graph.created_at,
                    confirmed_at=graph.confirmed_at,
                )
            ),
        )
        if result.rowcount != 1:
            raise DependencyGraphError(
                f"dependency graph {graph.test_id!r} v{graph.version} was confirmed by another "
                "request while this save was in flight and cannot be overwritten"
            )
        self._session.expire(existing)

        for edge_row in self._session.scalars(
            select(DependencyEdgeRow).where(DependencyEdgeRow.graph_id == existing.id)
        ):
            self._session.delete(edge_row)
        self._session.flush()  # old edges gone before the new ones land

        _, children = m.dependency_graph_rows(graph)
        for child in children:
            child.graph_id = existing.id
        self._session.add_all(children)
        self._session.flush()

    def try_confirm(self, confirmed: DependencyGraph) -> bool:
        """Atomically transition one DRAFT row to CONFIRMED, or refuse.

        Unlike ``save``, this is a compare-and-set: the ``UPDATE ... WHERE``
        below is evaluated by SQLite against the row's *actual* current state
        at execution time, not against whatever this session read earlier --
        so it is safe even when another `/confirm` for the same test raced
        this one and reached the database first (Issue #26 review: without
        this, two concurrent confirms could both pass their application-level
        checks -- read before either writes -- and then both blindly
        overwrite via plain ORM attribute mutation, since a normal ORM
        ``UPDATE`` only matches on primary key, not on the state it was read
        with).

        Returns ``True`` (and replaces the edges) if, at the moment this
        statement executed: the row was still DRAFT; no higher version for
        the same test was already CONFIRMED; and the test's *current*
        questions are still exactly ``confirmed.question_ids`` (a question
        added/removed between the application-level check and this write
        would otherwise let a stale snapshot get CONFIRMED -- Issue #26
        review). Returns ``False`` -- touching nothing -- if any precondition
        had already stopped holding; the caller reports a conflict for the
        loser to re-fetch and retry.
        """
        newer_confirmed_exists = (
            select(DependencyGraphRow.id)
            .where(
                DependencyGraphRow.test_id == confirmed.test_id,
                DependencyGraphRow.status == DependencyGraphStatus.CONFIRMED,
                DependencyGraphRow.version > confirmed.version,
            )
            .exists()
        )
        # Set equality via cardinality + one-way containment: if the test's
        # current question count equals len(confirmed.question_ids) *and*
        # none of the test's current questions falls outside that set, the
        # two sets are identical (both finite, no duplicates).
        expected_question_ids = sorted(confirmed.question_ids)
        current_question_count = (
            select(func.count(QuestionRow.id))
            .where(QuestionRow.test_id == confirmed.test_id)
            .scalar_subquery()
        )
        question_outside_expected_exists = (
            select(QuestionRow.id)
            .where(
                QuestionRow.test_id == confirmed.test_id,
                QuestionRow.id.not_in(expected_question_ids),
            )
            .exists()
        )
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(DependencyGraphRow)
                .where(
                    DependencyGraphRow.id == confirmed.id,
                    DependencyGraphRow.status == DependencyGraphStatus.DRAFT,
                    ~newer_confirmed_exists,
                    current_question_count == len(expected_question_ids),
                    ~question_outside_expected_exists,
                )
                .values(
                    status=DependencyGraphStatus.CONFIRMED,
                    unresolved=[],
                    confirmed_at=confirmed.confirmed_at,
                )
            ),
        )
        if result.rowcount != 1:
            return False

        for edge_row in self._session.scalars(
            select(DependencyEdgeRow).where(DependencyEdgeRow.graph_id == confirmed.id)
        ):
            self._session.delete(edge_row)
        self._session.flush()  # old candidate edges gone before the reviewed ones land

        _, children = m.dependency_graph_rows(confirmed)
        self._session.add_all(children)
        self._session.flush()
        return True

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
