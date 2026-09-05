"""limit submissions.student_label length

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05

Issue #17 review round 7 (P2 "student labelに上限を設ける"): ``student_label``
has been nullable free text with no length bound since it was introduced
(0001). A client posting directly to the API (bypassing the Flutter UI,
which never sends more than a short label) could otherwise pack most of the
request size limit into this one field -- it's stored verbatim and returned
in full on every ``/tests/{test_id}/submissions`` list response, so a
handful of megabyte-scale labels would bloat both the database and every
list response's memory footprint.

``domain.models.MAX_STUDENT_LABEL_LENGTH`` (200) and ``api/app.py``'s
``Form(..., max_length=...)`` on the same value are the first line of
defence; this DB CHECK constraint is the second, the same layered pattern
0003 used for ``ck_submissions_page_count_positive``. SQLite can't add a
CHECK constraint to an existing column without recreating the table, hence
Alembic's batch mode.

No backfill/preflight is needed here (contrast 0003's duplicate-content
check before its own batch pass): the previous absence of *any* limit means
a legacy row could in principle already exceed this one, in which case the
batch recreate below fails loudly with an ``IntegrityError`` rather than
silently truncating data -- acceptable given this is, in practice, an
actively-developed MVP with no real user data yet. Resolve it by hand (trim
or clear the offending ``student_label``) and re-run the upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrors domain.models.MAX_STUDENT_LABEL_LENGTH. Migrations hardcode their
#: own literals rather than importing application code (a migration must
#: stay reproducible even after that code changes later), so this is kept in
#: sync by hand -- see that constant's docstring if the limit ever changes.
_MAX_STUDENT_LABEL_LENGTH = 200


def upgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_submissions_student_label_length",
            f"student_label IS NULL OR length(student_label) <= {_MAX_STUDENT_LABEL_LENGTH}",
        )


def downgrade() -> None:
    with op.batch_alter_table("submissions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_submissions_student_label_length", type_="check")
