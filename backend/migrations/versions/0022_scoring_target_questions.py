"""add questions.is_scoring_target

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-12

GitHub Issue #449 (parent #3). The owner asked for the questions to grade to
be selectable, defaulting to every question. A `Question` owns its own
"is this graded" bit -- the same lifetime and granularity as its ``points``
and ``scoring_method`` -- so this adds a positive boolean column rather than a
separate table and a join.

Existing rows get a transient ``server_default`` of true, so every test that
predates this column keeps grading exactly the questions it graded before
("デフォルトはすべて"). The default is dropped in a second batch pass, the
same two-pass pattern ``0011_test_status.py`` used: a later ``INSERT`` that
omits the column must fail NOT NULL instead of silently becoming a scoring
target.

Rollback: ``downgrade()`` drops the column. Excluded questions become
indistinguishable from included ones and are graded again; no grade or review
row is touched by either direction, so the data is unchanged either way.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(
            sa.Column("is_scoring_target", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    # Drop the transient default once every existing row has a concrete value
    # -- a later INSERT that omits the column must fail NOT NULL rather than
    # silently land on true (same reasoning as 0011's and 0005's second pass).
    with op.batch_alter_table("questions") as batch_op:
        batch_op.alter_column("is_scoring_target", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_column("is_scoring_target")
