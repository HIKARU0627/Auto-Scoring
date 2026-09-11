"""add error_catalogs

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-11

GitHub Issue #209 (parent #3). The 誤答カタログ Issue #106 read out of an
Excel 添削資料 at grading time becomes a persisted, human-editable artefact:
one row per test holding the whole reviewed tuple as JSON, with a
``revision`` for the compare-and-set the review API saves against.

The Excel file stops being the grading-time source of truth (judgment 2).
Grading reads this table; an import writes it. No backfill -- a test that
already holds a 添削資料 simply has no row until someone imports it, which is
the same "no catalogue" state it was graded with before.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "error_catalogs",
        sa.Column(
            "test_id",
            sa.String(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("imported", sa.Boolean(), nullable=False),
        sa.Column("import_error", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("entries", sa.JSON(), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_error_catalogs_revision_positive"),
        sa.CheckConstraint(
            "json_valid(entries) AND json_type(entries) = 'array'",
            name="ck_error_catalogs_entries_is_array",
        ),
    )


def downgrade() -> None:
    op.drop_table("error_catalogs")
