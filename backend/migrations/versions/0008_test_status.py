"""add tests.status

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-05

Registration lifecycle for a test (Issue #16): a test starts ``draft`` and
moves one-way to ``ready`` only once its profile and dependency graph are
both confirmed (see ``auto_scoring.domain.models.Test.mark_ready``, driven at
the API by ``auto_scoring.api.test_registration_router``). Existing rows (all
created before this column existed) get the transient ``server_default`` of
``draft`` -- the safe starting point of the lifecycle, since none of them
have been through the confirm/ready flow this Issue introduces. The default
is dropped in a second batch pass once every row has a real value, the same
two-pass pattern ``0005_answer_intake.py`` used for its own new columns --
an ``INSERT`` that omits ``status`` after this migration must fail loudly
(``NOT NULL``) rather than silently default to ``draft``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tests") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="draft")
        )
        batch_op.create_check_constraint("ck_tests_status_valid", "status IN ('draft', 'ready')")

    # Drop the transient default now that every existing row has a concrete
    # value -- a later INSERT that omits `status` should fail NOT NULL, not
    # silently land on `draft` (same reasoning as 0005's second batch pass).
    with op.batch_alter_table("tests") as batch_op:
        batch_op.alter_column("status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("tests") as batch_op:
        batch_op.drop_constraint("ck_tests_status_valid", type_="check")
        batch_op.drop_column("status")
