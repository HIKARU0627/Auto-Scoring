"""initial MVP schema

Revision ID: 0001
Revises:
Create Date: 2026-09-04

Creates the ten core tables (Test, Question, Rubric, RubricCriterion,
Submission, RecognitionResult, GradeResult, Annotation, Review, Job) with the
foreign keys, NOT NULL / UNIQUE / CHECK constraints and indexes that guarantee
the issue #11 invariants at the database level.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_scoring_method = sa.Enum("additive", "subtractive", name="scoringmethod", native_enum=False)
_grading_source = sa.Enum("ai", "human", name="gradingsource", native_enum=False)
_annotation_kind = sa.Enum(
    "circle",
    "cross",
    "triangle",
    "score",
    "comment",
    "underline",
    "box",
    name="annotationkind",
    native_enum=False,
)
_submission_state = sa.Enum(
    "unprocessed",
    "ai_processing",
    "ai_processed",
    "needs_review",
    "reviewed",
    "exported",
    "error",
    name="submissionstate",
    native_enum=False,
)
_job_kind = sa.Enum("recognition", "grading", "export", name="jobkind", native_enum=False)
_job_state = sa.Enum(
    "queued",
    "running",
    "blocked",
    "succeeded",
    "failed",
    "cancelled",
    name="jobstate",
    native_enum=False,
)
_review_action = sa.Enum("approved", "modified", "rejected", name="reviewaction", native_enum=False)

_CONFIDENCE_RANGE = "confidence >= 0.0 AND confidence <= 1.0"


def upgrade() -> None:
    op.create_table(
        "tests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("default_scoring_method", _scoring_method, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "test_id",
            sa.String(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.String(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("scoring_method", _scoring_method, nullable=False),
        sa.Column("model_answer", sa.String(), nullable=True),
        sa.Column("answer_area", sa.JSON(), nullable=True),
        sa.Column("score_area", sa.JSON(), nullable=True),
        sa.Column("comment_area", sa.JSON(), nullable=True),
        sa.UniqueConstraint("test_id", "number", name="uq_questions_test_number"),
        sa.CheckConstraint("page >= 1", name="ck_questions_page_positive"),
        sa.CheckConstraint("points >= 0", name="ck_questions_points_non_negative"),
    )
    op.create_index("ix_questions_test_id", "questions", ["test_id"])

    op.create_table(
        "rubrics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("question_id", name="uq_rubrics_question"),
    )

    op.create_table(
        "rubric_criteria",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "rubric_id",
            sa.String(),
            sa.ForeignKey("rubrics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("max_points", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("rubric_id", "position", name="uq_rubric_criteria_position"),
        sa.CheckConstraint("max_points >= 0", name="ck_rubric_criteria_max_points_non_negative"),
        sa.CheckConstraint("position >= 0", name="ck_rubric_criteria_position"),
    )
    op.create_index("ix_rubric_criteria_rubric_id", "rubric_criteria", ["rubric_id"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "test_id",
            sa.String(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_pdf_path", sa.String(), nullable=False),
        sa.Column("state", _submission_state, nullable=False),
        sa.Column("student_label", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_submissions_test_id", "submissions", ["test_id"])
    op.create_index("ix_submissions_state", "submissions", ["state"])

    op.create_table(
        "recognition_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", _grading_source, nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("boxes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(_CONFIDENCE_RANGE, name="ck_recognition_confidence_range"),
    )
    op.create_index(
        "ix_recognition_results_submission_question",
        "recognition_results",
        ["submission_id", "question_id"],
    )

    op.create_table(
        "grade_results",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", _grading_source, nullable=False),
        sa.Column("awarded", sa.Integer(), nullable=False),
        sa.Column("maximum", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("maximum >= 0", name="ck_grade_results_maximum_non_negative"),
        sa.CheckConstraint(
            "awarded >= 0 AND awarded <= maximum",
            name="ck_grade_results_awarded_in_range",
        ),
        sa.CheckConstraint(_CONFIDENCE_RANGE, name="ck_grade_results_confidence_range"),
    )
    op.create_index(
        "ix_grade_results_submission_question",
        "grade_results",
        ["submission_id", "question_id"],
    )

    op.create_table(
        "annotations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", _grading_source, nullable=False),
        sa.Column("kind", _annotation_kind, nullable=False),
        sa.Column("rect", sa.JSON(), nullable=True),
        sa.Column("anchor_text", sa.String(), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_annotations_submission_question",
        "annotations",
        ["submission_id", "question_id"],
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", _review_action, nullable=False),
        sa.Column(
            "ai_grade_result_id",
            sa.String(),
            sa.ForeignKey("grade_results.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "human_grade_result_id",
            sa.String(),
            sa.ForeignKey("grade_results.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_reviews_submission_question",
        "reviews",
        ["submission_id", "question_id"],
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", _job_kind, nullable=False),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("state", _job_state, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column(
            "blocked_on_question_id",
            sa.String(),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts_positive"),
    )
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_index("ix_jobs_submission_id", "jobs", ["submission_id"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("reviews")
    op.drop_table("annotations")
    op.drop_table("grade_results")
    op.drop_table("recognition_results")
    op.drop_table("submissions")
    op.drop_table("rubric_criteria")
    op.drop_table("rubrics")
    op.drop_table("questions")
    op.drop_table("tests")
