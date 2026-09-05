"""add jobs.dependency_graph_version

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05

Records which confirmed `DependencyGraph` version a job was queued against
(Issue #26 acceptance: invalidate/recreate incomplete jobs when a test's
confirmed graph advances to a new version). See
`auto_scoring.domain.models.reissue_job_for_graph_version` and
`auto_scoring.api.dependency_graph_router.confirm`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite cannot ADD CONSTRAINT on an existing table; batch mode recreates
    # it under the hood (copy, rename) to add the column, check, and index
    # together.
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("dependency_graph_version", sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            "ck_jobs_dependency_graph_version_positive",
            "dependency_graph_version IS NULL OR dependency_graph_version >= 1",
        )
        batch_op.create_index("ix_jobs_dependency_graph_version", ["dependency_graph_version"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index("ix_jobs_dependency_graph_version")
        batch_op.drop_constraint("ck_jobs_dependency_graph_version_positive", type_="check")
        batch_op.drop_column("dependency_graph_version")
