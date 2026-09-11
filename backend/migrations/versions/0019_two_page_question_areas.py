"""support question answer area spanning two pages

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-11

GitHub Issue #108 (parent #3). In multi-page tests (such as a 3-page subject
exam where question 3 spans across page 2 and page 3), a single question's
answer area may span across two pages.

Previously, `questions` only stored a single `page` and `answer_area`.
Confirming a 2-page area was rejected with 422, prompting users to delete one
page's region, which left the other page with 0 questions and led to
`extra_pages:3>2` upon submission intake.

This migration adds nullable `page_2` (Integer) and `answer_area_2` (JSON) to
`questions`, protected by check constraints:
- `ck_questions_page_2_positive`: `page_2 IS NULL OR page_2 >= 1`
- `ck_questions_page_2_greater`: `page_2 IS NULL OR page_2 > page`
- `ck_questions_page_2_and_area_2_paired`:
  `(page_2 IS NULL AND answer_area_2 IS NULL) OR (page_2 IS NOT NULL AND answer_area_2 IS NOT NULL)`

Existing rows have `page_2 = NULL` and `answer_area_2 = NULL`, cleanly satisfying
all constraints without requiring any data backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("questions", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("page_2", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("answer_area_2", sa.JSON(), nullable=True))
        batch_op.create_check_constraint(
            "ck_questions_page_2_positive",
            "page_2 IS NULL OR page_2 >= 1",
        )
        batch_op.create_check_constraint(
            "ck_questions_page_2_greater",
            "page_2 IS NULL OR page_2 > page",
        )
        batch_op.create_check_constraint(
            "ck_questions_page_2_and_area_2_paired",
            "(page_2 IS NULL AND (answer_area_2 IS NULL OR answer_area_2 = 'null')) OR "
            "(page_2 IS NOT NULL AND answer_area_2 IS NOT NULL AND answer_area_2 != 'null')",
        )


def downgrade() -> None:
    with op.batch_alter_table("questions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_questions_page_2_and_area_2_paired", type_="check")
        batch_op.drop_constraint("ck_questions_page_2_greater", type_="check")
        batch_op.drop_constraint("ck_questions_page_2_positive", type_="check")
        batch_op.drop_column("answer_area_2")
        batch_op.drop_column("page_2")
