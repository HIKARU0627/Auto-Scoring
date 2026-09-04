"""add operation_log audit table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04

Adds the destructive-operation audit trail (business-rules-and-evaluation-data.md
§2 (11), §28). This is the "apply to a one-generation-old database" path: a DB
stamped at 0001 upgrades to 0002 by gaining this one table, and `downgrade`
drops it again.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("target_kind", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
    )
    op.create_index("ix_operation_log_occurred_at", "operation_log", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_operation_log_occurred_at", table_name="operation_log")
    op.drop_table("operation_log")
