"""limit submissions.original_filename length

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05

Issue #17 review round 8 (P2 "永続化するoriginal filenameに上限を設ける"):
``original_filename`` has accepted any length since it was introduced (0001)
as long as the name ended in ``.pdf`` and used no path separators or null
bytes -- there is no per-part-header size limit in multipart parsing, so a
client posting directly to the API (bypassing the Flutter picker, which
never sends more than a normal filename) could pack most of the ~50MiB
overall body limit into this one field. It's stored verbatim and returned in
full on every submission response, the same bloat risk 0004 fixed for
``student_label``.

``domain.models.MAX_ORIGINAL_FILENAME_LENGTH`` (255) and
``domain.pdf_intake.validate_filename`` are the first line of defence,
checked before anything else about the upload; this DB CHECK constraint is
the second, the same layered pattern 0003/0004 used. SQLite can't add a CHECK
constraint to an existing column without recreating the table, hence
Alembic's batch mode.

No backfill/preflight is needed here for the same reason as 0004: this is an
actively-developed MVP with no real user data yet, so a legacy row that
happens to already exceed the new limit fails the batch recreate loudly with
an ``IntegrityError`` rather than being silently truncated. Resolve it by
hand (trim or clear the offending ``original_filename``) and re-run the
upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors domain.models.MAX_ORIGINAL_FILENAME_LENGTH. Migrations hardcode
#: their own literals rather than importing application code (a migration
#: must stay reproducible even after that code changes later), so this is
#: kept in sync by hand -- see that constant's docstring if the limit ever
#: changes.
_MAX_ORIGINAL_FILENAME_LENGTH = 255


def upgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_submissions_original_filename_length",
            "original_filename IS NULL OR length(original_filename) <= "
            f"{_MAX_ORIGINAL_FILENAME_LENGTH}",
        )


def downgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_submissions_original_filename_length", type_="check")
