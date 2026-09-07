"""add review-history columns for edit/reject/regrade/undo

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-06

GitHub Issue #22 (parent #3): the review screen's edit/reject/regrade/
approve-and-next actions, plus Ctrl+Z undo, need three things the ``reviews``
table (0001) did not yet carry:

- ``version``: the optimistic-concurrency token (Issue #22 acceptance:
  "同時/重複requestが履歴を二重作成せず、古いversionの更新を拒否する"). The
  ``n``-th review ever recorded for one ``(submission_id, question_id)`` pair
  is always ``version=n``; ``uq_reviews_submission_question_version`` is the
  real constraint that rejects a second row at the same version, not just an
  application-level check (``domain.review_workflow.next_review_version``).
  Backfilled per-pair via a window-function-equivalent correlated subquery
  (SQLite has no ``ROW_NUMBER()`` need here since every existing row predates
  this feature and none has been assigned a version yet) so any pre-existing
  rows (from Issue #21's domain groundwork, if ever exercised against a real
  database) still satisfy the new unique constraint.
- ``regrade_job_id``: the `Job` a ``regrade_requested`` row queued.
- ``undone_review_id``: the prior `Review` row an ``undone`` row reverts
  (never physically removed -- append-only, same as every other table here).

Also widens ``reviews.action`` to allow the two new `ReviewAction` values
this issue adds (``regrade_requested``, ``undone``) via the explicit named
CHECK constraint pattern already used for ``jobs.state``/``jobs.error_code``
(0001/0008) -- ``0001`` never added one for ``reviews.action`` at all (the
enum's own ``native_enum=False`` does not itself enforce anything at the DB
layer; see ``db.orm._enum``'s neighbouring columns), so this is the first one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors domain.models.MAX_COMMENT_CHARS. Migrations hardcode their own
#: literals rather than importing application code.
_MAX_COMMENT_CHARS = 120

#: 0001's ``_review_action`` sized the underlying VARCHAR to fit only its
#: three original values (8 chars, "approved"/"modified"/"rejected"); with
#: ``native_enum=False``, SQLAlchemy derives the column's VARCHAR *length*
#: from the longest member, so widening the enum without also widening the
#: column leaves a column too narrow for ``"regrade_requested"`` (17 chars)
#: to ever actually fit -- and `alembic check` (`test_head_schema_matches_
#: orm_metadata`) would keep reporting a type diff against `db.orm`'s
#: `_enum(ReviewAction)`, which recomputes the length from all five values.
_review_action_v1 = sa.Enum(
    "approved", "modified", "rejected", name="reviewaction", native_enum=False
)
_review_action_v2 = sa.Enum(
    "approved",
    "modified",
    "rejected",
    "regrade_requested",
    "undone",
    name="reviewaction",
    native_enum=False,
)


def upgrade() -> None:
    with op.batch_alter_table("reviews", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        # Batch mode's table-recreate needs every constraint it (re)creates to
        # be named, including a new column's own `ForeignKey` -- unlike the
        # earlier migrations' FK columns, which were only ever added at
        # table-*creation* time (`op.create_table`, where SQLAlchemy accepts
        # an unnamed one).
        batch_op.add_column(
            sa.Column(
                "regrade_job_id",
                sa.String(),
                sa.ForeignKey(
                    "jobs.id", ondelete="SET NULL", name="fk_reviews_regrade_job_id_jobs"
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "undone_review_id",
                sa.String(),
                sa.ForeignKey(
                    "reviews.id", ondelete="SET NULL", name="fk_reviews_undone_review_id_reviews"
                ),
            )
        )

    # Backfill: number each (submission_id, question_id) pair's existing rows
    # 1..n in `created_at` order, so any rows written before this migration
    # (all implicitly `server_default='1'` above) satisfy the unique
    # constraint added next. Correlated-subquery count-of-earlier-rows is the
    # SQLite-portable equivalent of `ROW_NUMBER() OVER (...)` here.
    op.execute(
        """
        UPDATE reviews
        SET version = (
            SELECT COUNT(*) FROM reviews AS earlier
            WHERE earlier.submission_id = reviews.submission_id
              AND earlier.question_id = reviews.question_id
              AND (
                earlier.created_at < reviews.created_at
                OR (earlier.created_at = reviews.created_at AND earlier.id < reviews.id)
              )
        ) + 1
        """
    )

    with op.batch_alter_table("reviews", recreate="always") as batch_op:
        batch_op.alter_column("version", server_default=None)
        batch_op.alter_column(
            "action", existing_type=_review_action_v1, type_=_review_action_v2, nullable=False
        )
        batch_op.create_unique_constraint(
            "uq_reviews_submission_question_version",
            ["submission_id", "question_id", "version"],
        )
        batch_op.create_check_constraint("ck_reviews_version_positive", "version >= 1")
        batch_op.create_check_constraint(
            "ck_reviews_action_valid",
            "action IN ('approved', 'modified', 'rejected', 'regrade_requested', 'undone')",
        )
        batch_op.create_check_constraint(
            "ck_reviews_confirmed_requires_ai_grade",
            "action NOT IN ('approved', 'modified') OR ai_grade_result_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_reviews_modified_requires_human_grade",
            "action != 'modified' OR human_grade_result_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_reviews_regrade_requires_job",
            "action != 'regrade_requested' OR regrade_job_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_reviews_undone_requires_target",
            "action != 'undone' OR undone_review_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_reviews_note_length", f"note IS NULL OR length(note) <= {_MAX_COMMENT_CHARS}"
        )


def downgrade() -> None:
    # Any row still carrying a 0013-only action value would violate 0001's
    # narrower CHECK the moment `alter_column` below re-applies it -- normalize
    # those rows away first, the same "sanitize before narrowing" pattern
    # `0009`'s own downgrade uses for `jobs.usable`.
    op.execute("DELETE FROM reviews WHERE action IN ('regrade_requested', 'undone')")
    with op.batch_alter_table("reviews", recreate="always") as batch_op:
        batch_op.alter_column(
            "action", existing_type=_review_action_v2, type_=_review_action_v1, nullable=False
        )
        batch_op.drop_constraint("ck_reviews_note_length", type_="check")
        batch_op.drop_constraint("ck_reviews_undone_requires_target", type_="check")
        batch_op.drop_constraint("ck_reviews_regrade_requires_job", type_="check")
        batch_op.drop_constraint("ck_reviews_modified_requires_human_grade", type_="check")
        batch_op.drop_constraint("ck_reviews_confirmed_requires_ai_grade", type_="check")
        batch_op.drop_constraint("ck_reviews_action_valid", type_="check")
        batch_op.drop_constraint("ck_reviews_version_positive", type_="check")
        batch_op.drop_constraint("uq_reviews_submission_question_version", type_="unique")
        batch_op.drop_column("undone_review_id")
        batch_op.drop_column("regrade_job_id")
        batch_op.drop_column("version")
