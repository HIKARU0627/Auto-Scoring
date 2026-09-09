"""add grade_results.answer_image_finding

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10

GitHub Issue #136 (parent #3): what the grading AI says the answer image it
was given actually *shows*, recorded alongside the score it produced from
that image (``auto_scoring.domain.models.AnswerImageFinding``).

Nullable, with no backfill and no default: ``NULL`` means "nothing was
reported", which is the truth for every row written before this column
existed, for a human-confirmed grade, and for a provider that ignores the
field. It must not read as "the crop was vouched for" -- that is the very
claim this Issue stopped inventing.

The trigger is the point of storing it here rather than in a log. A grade
may never carry ``not_the_answer``: a score produced from an image the
grader itself said is not this question's answer is exactly the
"0 点・確信度 1.00" failure this Issue removes, and a response that says both
("not the answer" *and* a score above zero) must not be resolved in favour
of the score. ``jobs.grading_processor`` routes that case to a human and
persists no grade at all; this trigger is what keeps a later code path from
persisting one anyway.

**Why a trigger and not a CHECK constraint** (this cost a red CI run to
find, and the first explanation written here was wrong; this one is the
measured one). SQLite cannot add a CHECK to an existing table, so a CHECK
would need ``batch_alter_table`` to rebuild ``grade_results`` -- which drops
and recreates it, moving it to the *end* of ``sqlite_master``, after
``reviews``. Deleting a test then fails outright::

    DELETE FROM tests WHERE tests.id = ?
    IntegrityError: CHECK constraint failed: ck_reviews_confirmed_requires_ai_grade

because SQLite applies the resulting cascade in schema order: with
``grade_results`` now behind ``reviews``, its rows are deleted *before* the
review rows that reference them, so ``reviews.ai_grade_result_id``'s
``ON DELETE SET NULL`` blanks an ``approved`` review's grade reference while
that row still exists, and ``ck_reviews_confirmed_requires_ai_grade``
(Issue #118) aborts the whole statement. With ``ADD COLUMN`` -- which needs
no rebuild -- every other table's schema is left exactly as it was, and the
delete behaves as it always has.

The underlying contradiction is older than this revision and is not fixed
here: ``DELETE FROM grade_results`` for a row an ``approved`` review points
at violates that CHECK in *either* schema (measured). Deleting a test
normally survives only because the review rows happen to go first. Removing
that dependence means changing ``reviews``, which belongs to its own
change.

Why the column exists even though only ``blank`` and ``answer`` can ever
reach it: deciding whether ``blank`` should also stop a grade needs the
frequency of genuinely unanswered questions, and without a stored value the
only way to obtain that number is another full run on real material. See
docs/ai-grading-pipeline.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The values a stored grade may carry -- ``not_the_answer`` is deliberately
#: absent (see the docstring). Mirrors ``domain.models.AnswerImageFinding``;
#: migrations hardcode their own literals rather than importing application
#: code, and `db.orm` holds the identical pair of triggers for a freshly
#: created database.
_GRADABLE_FINDINGS = ("answer", "blank")

_GRADABLE_MESSAGE = "grade_results.answer_image_finding must be NULL, ''answer'' or ''blank''"

_TRIGGERS = {
    "trg_grade_results_answer_image_finding_gradable_insert": "INSERT ON grade_results",
    "trg_grade_results_answer_image_finding_gradable_update": (
        "UPDATE OF answer_image_finding ON grade_results"
    ),
}


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    # A plain ADD COLUMN, deliberately not ``batch_alter_table`` -- see the
    # docstring: a rebuild of this table rewrites ``reviews``' foreign-key
    # declarations and breaks deleting a test.
    op.add_column("grade_results", sa.Column("answer_image_finding", sa.String(), nullable=True))
    for name, event in _TRIGGERS.items():
        op.execute(
            f"""
            CREATE TRIGGER {name}
            BEFORE {event}
            FOR EACH ROW
            WHEN NEW.answer_image_finding IS NOT NULL
                AND NEW.answer_image_finding NOT IN ({_in_list(_GRADABLE_FINDINGS)})
            BEGIN
                SELECT RAISE(ABORT, '{_GRADABLE_MESSAGE}');
            END;
            """
        )


def downgrade() -> None:
    for name in _TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    # ``ALTER TABLE ... DROP COLUMN`` (SQLite 3.35+, which the runtime already
    # requires for every other migration here) rather than a batch rebuild,
    # for the same reason ``upgrade`` avoids one.
    op.drop_column("grade_results", "answer_image_finding")
