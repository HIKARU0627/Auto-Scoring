"""allow jobs.usable on FAILED as well as SUCCEEDED

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-05

Issue #18 review round 2, P1 ("サポートされる全ての使用不能な前提を再開できる
ようにする"): a human can approve/correct a *failed* prerequisite's downstream
effect (business-rules-and-evaluation-data.md §4.4), not only a low-confidence
*succeeded* one. `mark_usable` needs to be able to flip `usable` on a FAILED
row without that row lying about its own `state` -- the attempt really did
fail; only whether dependents may now proceed changes. See
`auto_scoring.domain.models.Job.usable` and
`auto_scoring.domain.job_scheduling.question_statuses`.

SQLite cannot alter a CHECK constraint in place; batch mode recreates the
table under the hood.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_jobs_usable_matches_state", type_="check")
        batch_op.create_check_constraint(
            "ck_jobs_usable_matches_state", "usable IS NULL OR state IN ('succeeded', 'failed')"
        )


def downgrade() -> None:
    # A FAILED row's `usable` (set via a human /resume approval -- only
    # possible once this migration's upgrade() has run) has no
    # representation in the schema being downgraded to. Batch mode's
    # "recreate" copies every existing row into the new table as part of
    # dropping/recreating the constraint below; left unnormalized, such a
    # row would violate the stricter constraint being restored and abort
    # the downgrade with an IntegrityError partway through (review round 3,
    # P2). Clear it first so the downgrade always completes -- the
    # information doesn't fit the older schema either way, so this is a
    # normalization, not a silent invention of new data (AGENTS.md "Confirm
    # scope…before destructive…changes"; this only ever runs on an explicit
    # downgrade request).
    op.execute("UPDATE jobs SET usable = NULL WHERE state = 'failed' AND usable IS NOT NULL")
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_jobs_usable_matches_state", type_="check")
        batch_op.create_check_constraint(
            "ck_jobs_usable_matches_state", "usable IS NULL OR state = 'succeeded'"
        )
