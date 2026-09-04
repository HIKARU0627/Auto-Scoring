"""add answer intake columns and answer_images table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

Issue #17 (answer PDF intake / storage / image preprocessing):

* ``submissions`` gains ``source_pdf_sha256`` (reintake dedupe key),
  ``page_count`` (learned once at intake), ``original_filename`` and
  ``review_reason`` (why intake routed a submission to ``needs_review``).
* new table ``answer_images``: the per-question answer-area image extracted
  from a submission (docs/answer-intake-and-preprocessing.md).

SQLite cannot add a ``CHECK`` constraint to an existing table without
recreating it, so the ``submissions`` alteration uses Alembic's batch mode
(``recreate="always"``), which reflects the existing table -- including its
``ck_submissions_state_valid`` check constraint -- and rebuilds it with the
new columns and the new ``ck_submissions_page_count_positive`` check.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("source_pdf_sha256", sa.String(), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("original_filename", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("review_reason", sa.String(), nullable=True))
        batch_op.create_check_constraint("ck_submissions_page_count_positive", "page_count >= 1")
        batch_op.create_index("ix_submissions_test_content_hash", ["test_id", "source_pdf_sha256"])

    op.create_table(
        "answer_images",
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
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("page >= 1", name="ck_answer_images_page_positive"),
        sa.CheckConstraint(
            "status IN ('ok', 'needs_review')", name="ck_answer_images_status_valid"
        ),
        sa.UniqueConstraint(
            "submission_id", "question_id", name="uq_answer_images_submission_question"
        ),
    )
    op.create_index("ix_answer_images_submission_id", "answer_images", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_images_submission_id", table_name="answer_images")
    op.drop_table("answer_images")

    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.drop_index("ix_submissions_test_content_hash")
        batch_op.drop_constraint("ck_submissions_page_count_positive", type_="check")
        batch_op.drop_column("review_reason")
        batch_op.drop_column("original_filename")
        batch_op.drop_column("page_count")
        batch_op.drop_column("source_pdf_sha256")
