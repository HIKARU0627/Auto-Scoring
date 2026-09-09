"""let a ``modified`` review exist without an AI grade behind it

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-09

GitHub Issue #118 (parent #3): when AI grading fails permanently, no
``GradeResult`` is written at all -- Issue #97 decided that deliberately,
so that nothing that looks like a grade exists unless something actually
produced one, and that decision stands. But every way a person could record
their own decision went through the AI's row: ``approve`` confirms it,
``edit`` corrects it, and ``ck_reviews_confirmed_requires_ai_grade`` (0013)
refused any ``approved``/``modified`` row without one. So a question the AI
could not grade could not be graded by a person either, and the answer sheet
stopped there.

This narrows that CHECK to ``approved`` only. ``modified`` keeps
``ck_reviews_modified_requires_human_grade`` -- what a confirmed row decided
is still never optional -- and ``ai_grade_result_id`` goes back to meaning
exactly what its name says: *the AI attempt this decision was made against*,
which is NULL when there was none. See ``domain.models.Review`` and
``docs/review-edit-history.md`` section 3.

The constraint keeps its 0013 name. Renaming it would recreate the table for
no behavioural gain, and ``db.orm.ReviewRow`` carries the same name with the
same, narrowed expression -- which is what ``alembic check``
(``test_head_schema_matches_orm_metadata``) compares.

Widening a CHECK needs no data migration: every existing row already
satisfies the narrower predicate. The downgrade does: a ``modified`` row
written under this revision may have no AI grade, and would violate 0013's
CHECK the moment it is re-applied. Those rows are deleted first -- the same
"sanitize before narrowing" pattern 0009's and 0013's own downgrades use.
That loses a person's manual grade, which is exactly why it is only ever
reached by an explicit downgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_reviews_confirmed_requires_ai_grade"


def upgrade() -> None:
    with op.batch_alter_table("reviews", recreate="always") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(
            _CONSTRAINT, "action != 'approved' OR ai_grade_result_id IS NOT NULL"
        )


def downgrade() -> None:
    op.execute("DELETE FROM reviews WHERE action = 'modified' AND ai_grade_result_id IS NULL")
    with op.batch_alter_table("reviews", recreate="always") as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(
            _CONSTRAINT, "action NOT IN ('approved', 'modified') OR ai_grade_result_id IS NOT NULL"
        )
