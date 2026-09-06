"""limit recognition_results.text length

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-06

Issue #19: a human's manual-entry recognition text
(``POST /submissions/{submission_id}/questions/{question_id}/recognitions``)
is, like ``submissions.student_label`` (0006) and
``submissions.original_filename`` (0007), a free-text field a client posting
directly to the API could otherwise pack without bound -- stored verbatim and
returned on every recognition-history read.
``domain.models.MAX_RECOGNIZED_TEXT_LENGTH`` (10,000) is the first line of
defence, checked in ``RecognitionResult.__post_init__``; this DB CHECK
constraint is the second, the same layered pattern 0006/0007 used. SQLite
can't add a CHECK constraint to an existing column without recreating the
table, hence Alembic's batch mode.

No backfill/preflight, same reasoning as 0006/0007: this is an
actively-developed MVP with no real user data yet.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors domain.models.MAX_RECOGNIZED_TEXT_LENGTH. Migrations hardcode
#: their own literals rather than importing application code (a migration
#: must stay reproducible even after that code changes later).
_MAX_RECOGNIZED_TEXT_LENGTH = 10_000


def upgrade() -> None:
    with op.batch_alter_table("recognition_results", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_recognition_results_text_length",
            f"length(text) <= {_MAX_RECOGNIZED_TEXT_LENGTH}",
        )


def downgrade() -> None:
    with op.batch_alter_table("recognition_results", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_recognition_results_text_length", type_="check")
