"""a review disappears with the row it names, instead of being blanked

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-10

GitHub Issue #149 (parent #3). ``reviews`` holds four references that a CHECK
makes mandatory for one action each -- ``approved``/``ai_grade_result_id``,
``modified``/``human_grade_result_id``, ``regrade_requested``/``regrade_job_id``
and ``undone``/``undone_review_id`` -- and every one of them carried
``ON DELETE SET NULL``. SET NULL rewrites the review row while it still
exists, so deleting the row it names aborts the delete on that CHECK.

Whether it aborts was decided by the order SQLite walks the tables in, which
is the order they sit in ``sqlite_master`` -- whatever the last migration
happened to leave behind. Issue #136 measured the flip: rebuilding
``grade_results`` (the only way to add a CHECK in SQLite) moved it behind
``reviews`` and turned 8/8 green into 6/6 red. Worse, ``undone_review_id``
points into ``reviews`` itself, so no order ever saved it: deleting a test
that had a single undone review already failed on the head schema.

``ON DELETE CASCADE`` never produces the rewritten row at all. A review is a
decision *about* the row it names; when that row goes, the decision goes with
it, in every table order. Measured on the reduced schema (both orders, four
delete paths): SET NULL 8 red / 8, RESTRICT 8 red / 8, the CHECKs re-expressed
as triggers 8 red / 8, CASCADE 8 green / 8. The reasoning and the rejected
options are in ``docs/data-model-and-local-storage.md``.

No data migration: this changes what a *future* delete does, never a stored
value, and ``SET NULL`` guarantees no row is orphaned on the way in. The
recreate below copies every ``reviews`` row as it stands. It depends on
``migrations/env.py`` running with ``foreign_keys`` off for the reason that
file already gives -- the intermediate ``DROP TABLE`` is an implicit ``DELETE
FROM`` when enforcement is on, and ``reviews`` is now a CASCADE child of
``grade_results``/``jobs``/itself as well as of ``submissions``.

Recovery: the change is confined to ``reviews``. ``downgrade()`` puts the
SET NULL actions back with the same copy, so a database that has to go back
to 0017 loses nothing -- it only regains the ordering hazard.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: SQLite writes these FKs unnamed, and ``batch_alter_table`` can only drop a
#: constraint it can name. This is the convention Alembic renders reflected
#: foreign keys under so ``drop_constraint`` can find them.
_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}

#: ``(column, referred table)`` for each reference whose CHECK makes it
#: mandatory -- see the module docstring.
_REFERENCES = [
    ("ai_grade_result_id", "grade_results"),
    ("human_grade_result_id", "grade_results"),
    ("regrade_job_id", "jobs"),
    ("undone_review_id", "reviews"),
]


def _rewrite_ondelete(ondelete: str) -> None:
    with op.batch_alter_table(
        "reviews", recreate="always", naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        for column, referred in _REFERENCES:
            name = f"fk_reviews_{column}_{referred}"
            batch_op.drop_constraint(name, type_="foreignkey")
            batch_op.create_foreign_key(name, referred, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _rewrite_ondelete("CASCADE")


def downgrade() -> None:
    _rewrite_ondelete("SET NULL")
