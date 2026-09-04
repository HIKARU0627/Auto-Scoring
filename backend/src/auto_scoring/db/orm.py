"""SQLAlchemy 2.0 tables for the MVP schema.

Invariants are guaranteed here with real constraints, not application checks
(``AGENTS.md`` "Architecture"): foreign keys reject orphan rows, ``CHECK``
constraints reject out-of-range scores and confidences, ``UNIQUE`` constraints
reject duplicates, and every state column is a ``CHECK ... IN (...)`` produced by
:class:`sqlalchemy.Enum`.

``Base.metadata`` here is the full head schema. The Alembic migrations under
``backend/migrations/versions`` build it up revision by revision; keep the two in
step (run ``uv run alembic revision --autogenerate`` when you change a table).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from auto_scoring.db.base import Base
from auto_scoring.domain.dependency_graph import DependencyGraphStatus, DependencyProvision
from auto_scoring.domain.models import (
    AnnotationKind,
    GradingSource,
    JobKind,
    JobState,
    ReviewAction,
    ScoringMethod,
    SubmissionState,
)

_CONFIDENCE_RANGE = "confidence >= 0.0 AND confidence <= 1.0"


def _enum(enum_cls: type[enum.StrEnum]) -> SAEnum:
    """A VARCHAR column constrained to the enum's *values* via ``CHECK ... IN``."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def _pk() -> Mapped[str]:
    return mapped_column(String, primary_key=True)


def _json_list() -> Mapped[list[dict[str, Any]]]:
    return mapped_column(JSON, nullable=False, default=list)


class TestRow(Base):
    __tablename__ = "tests"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    default_scoring_method: Mapped[ScoringMethod] = mapped_column(
        _enum(ScoringMethod), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class QuestionRow(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("test_id", "number", name="uq_questions_test_number"),
        CheckConstraint("page >= 1", name="ck_questions_page_positive"),
        CheckConstraint("points >= 0", name="ck_questions_points_non_negative"),
        Index("ix_questions_test_id", "test_id"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_method: Mapped[ScoringMethod] = mapped_column(_enum(ScoringMethod), nullable=False)
    model_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    score_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    comment_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)


class RubricRow(Base):
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("question_id", name="uq_rubrics_question"),)

    id: Mapped[str] = _pk()
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )


class RubricCriterionRow(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "position", name="uq_rubric_criteria_position"),
        CheckConstraint("max_points >= 0", name="ck_rubric_criteria_max_points_non_negative"),
        CheckConstraint("position >= 0", name="ck_rubric_criteria_position"),
        Index("ix_rubric_criteria_rubric_id", "rubric_id"),
    )

    id: Mapped[str] = _pk()
    rubric_id: Mapped[str] = mapped_column(
        ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    max_points: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class SubmissionRow(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('unprocessed', 'ai_processing', 'ai_processed', "
            "'needs_review', 'reviewed', 'exported', 'error')",
            name="ck_submissions_state_valid",
        ),
        Index("ix_submissions_test_id", "test_id"),
        Index("ix_submissions_state", "state"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    source_pdf_path: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[SubmissionState] = mapped_column(_enum(SubmissionState), nullable=False)
    student_label: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RecognitionResultRow(Base):
    __tablename__ = "recognition_results"
    __table_args__ = (
        CheckConstraint(_CONFIDENCE_RANGE, name="ck_recognition_confidence_range"),
        Index(
            "ix_recognition_results_submission_question",
            "submission_id",
            "question_id",
        ),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    boxes: Mapped[list[dict[str, Any]]] = _json_list()
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GradeResultRow(Base):
    __tablename__ = "grade_results"
    __table_args__ = (
        CheckConstraint("maximum >= 0", name="ck_grade_results_maximum_non_negative"),
        CheckConstraint(
            "awarded >= 0 AND awarded <= maximum",
            name="ck_grade_results_awarded_in_range",
        ),
        CheckConstraint(_CONFIDENCE_RANGE, name="ck_grade_results_confidence_range"),
        Index("ix_grade_results_submission_question", "submission_id", "question_id"),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    criteria: Mapped[list[dict[str, Any]]] = _json_list()
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AnnotationRow(Base):
    __tablename__ = "annotations"
    __table_args__ = (Index("ix_annotations_submission_question", "submission_id", "question_id"),)

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    kind: Mapped[AnnotationKind] = mapped_column(_enum(AnnotationKind), nullable=False)
    rect: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    anchor_text: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewRow(Base):
    __tablename__ = "reviews"
    __table_args__ = (Index("ix_reviews_submission_question", "submission_id", "question_id"),)

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[ReviewAction] = mapped_column(_enum(ReviewAction), nullable=False)
    ai_grade_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("grade_results.id", ondelete="SET NULL"), nullable=True
    )
    human_grade_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("grade_results.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'blocked', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_state_valid",
        ),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts_positive"),
        Index("ix_jobs_state", "state"),
        Index("ix_jobs_submission_id", "submission_id"),
    )

    id: Mapped[str] = _pk()
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind), nullable=False)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=True
    )
    state: Mapped[JobState] = mapped_column(_enum(JobState), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    blocked_on_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DependencyGraphRow(Base):
    """One version of one test's dependency graph (Issue #26).

    ``(test_id, version)`` is the real identity a repository upserts against:
    a DRAFT row is replaced in place by later analysis/confirm calls for the
    same version, but a CONFIRMED row is never updated again -- changing a
    confirmed graph means inserting a new, higher version (see
    ``domain.dependency_graph.DependencyGraph.confirm`` and
    docs/dependency-graph.md).
    """

    __tablename__ = "dependency_graphs"
    __table_args__ = (
        UniqueConstraint("test_id", "version", name="uq_dependency_graphs_test_version"),
        CheckConstraint("version >= 1", name="ck_dependency_graphs_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'confirmed')", name="ck_dependency_graphs_status_valid"
        ),
        Index("ix_dependency_graphs_test_id", "test_id"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DependencyGraphStatus] = mapped_column(
        _enum(DependencyGraphStatus), nullable=False
    )
    question_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unresolved: Mapped[list[dict[str, Any]]] = _json_list()
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DependencyEdgeRow(Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "graph_id",
            "from_question_id",
            "to_question_id",
            name="uq_dependency_edges_pair",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_dependency_edges_confidence_range",
        ),
        Index("ix_dependency_edges_graph_id", "graph_id"),
    )

    id: Mapped[str] = _pk()
    graph_id: Mapped[str] = mapped_column(
        ForeignKey("dependency_graphs.id", ondelete="CASCADE"), nullable=False
    )
    from_question_id: Mapped[str] = mapped_column(String, nullable=False)
    to_question_id: Mapped[str] = mapped_column(String, nullable=False)
    provides: Mapped[list[DependencyProvision]] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class OperationLogRow(Base):
    """Audit trail for destructive operations (business-rules §2 (11), §28).

    Added in migration ``0002`` — see that revision for the upgrade-an-existing-DB
    path exercised by the migration tests.
    """

    __tablename__ = "operation_log"
    __table_args__ = (Index("ix_operation_log_occurred_at", "occurred_at"),)

    id: Mapped[str] = _pk()
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
