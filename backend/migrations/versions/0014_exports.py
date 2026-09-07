"""add exports table

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-07

GitHub Issue #23 (parent #3): the annotated-PDF export feature needs
somewhere to record each successfully generated output -- "出力job、hash、
生成時刻、元Submission、review versionを保存する" (Issue #23 実施内容).

A `Job` (kind=``EXPORT``, added to the `JobKind` enum back in migration
`0001_initial_schema` even though nothing produced one until now) tracks an
in-flight or failed attempt; this new ``exports`` table records only
*successful* ones -- there is no "failed export" row, matching the pattern
``docs/pdf-export.md`` documents. ``job_id`` is unique: the `Job` that
produced a row is looked up by id before regenerating anything, so a crash-
recovery replay of the same job never produces a second `Export` for it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("file_sha256", sa.String(), nullable=False),
        sa.Column("review_versions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", name="uq_exports_job_id"),
    )
    op.create_index("ix_exports_submission_id", "exports", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_exports_submission_id", table_name="exports")
    op.drop_table("exports")
