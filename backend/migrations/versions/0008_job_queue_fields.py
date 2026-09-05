"""add jobs.error_code, jobs.usable, and the submission/question/graph-version
unique constraint

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-05

Issue #18 (parallel AI processing queue):

* ``error_code`` persists the retry classification (timeout/rate_limited/
  server_error/permanent) for the most recent FAILED attempt, distinct from
  the free-text ``last_error`` -- see
  ``auto_scoring.domain.models.ErrorCategory`` and docs/job-queue.md
  "retry対象の分類".
* ``usable`` records whether a SUCCEEDED job's result may release a
  dependent question in the same submission's confirmed dependency graph
  (Issue #18 §4.4) -- see ``auto_scoring.domain.job_scheduling``.
* ``uq_jobs_submission_question_graph_version`` is this issue's idempotency
  key for Submission-DAG job creation (docs/job-queue.md "二重処理防止"):
  re-running job creation for the same submission/question/confirmed-graph-
  version must hit this constraint instead of creating a duplicate row.
  SQLite treats NULLs as distinct, so pre-existing jobs with a NULL
  ``question_id`` or ``dependency_graph_version`` are unaffected.

SQLite cannot add a column with a CHECK constraint, nor add a table-level
UNIQUE constraint, to an existing table without recreating it; batch mode
does the copy/rename under the hood.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_error_category = sa.Enum(
    "timeout", "rate_limited", "server_error", "permanent", name="errorcategory", native_enum=False
)


def upgrade() -> None:
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("error_code", _error_category, nullable=True))
        batch_op.add_column(sa.Column("usable", sa.Boolean(), nullable=True))
        batch_op.create_check_constraint(
            "ck_jobs_error_code_valid",
            "error_code IS NULL OR error_code IN "
            "('timeout', 'rate_limited', 'server_error', 'permanent')",
        )
        batch_op.create_check_constraint(
            "ck_jobs_error_code_matches_state", "error_code IS NULL OR state = 'failed'"
        )
        batch_op.create_check_constraint(
            "ck_jobs_usable_matches_state", "usable IS NULL OR state = 'succeeded'"
        )
        batch_op.create_unique_constraint(
            "uq_jobs_submission_question_graph_version",
            ["submission_id", "question_id", "dependency_graph_version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_jobs_submission_question_graph_version", type_="unique")
        batch_op.drop_constraint("ck_jobs_usable_matches_state", type_="check")
        batch_op.drop_constraint("ck_jobs_error_code_matches_state", type_="check")
        batch_op.drop_constraint("ck_jobs_error_code_valid", type_="check")
        batch_op.drop_column("usable")
        batch_op.drop_column("error_code")
