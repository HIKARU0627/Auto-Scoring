"""add test_materials

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-09

Registration stops being "one model-answer PDF plus one marking-manual PDF"
and becomes a list of role-tagged files (Issue #101). The model-answer PDF is
no longer required at all: it does not exist in real grading material, and the
criteria PDF already contains the model answer (Issue #95 decision 1).

**Existing rows are backfilled, not stranded.** A test registered under the
old flow has its two PDFs on disk at fixed paths, and both remain readable and
useful -- the marking manual *is* the grading criteria under the new
vocabulary, and the model answer becomes a reference material. Losing that
mapping would leave an already-registered test looking like it has no criteria
at all, and `POST /tests` is the only way to attach one, so it could never
regain them (the same failure mode migration 0011 had to be corrected for).

The backfill runs against the DB only. It cannot read `app-data/` -- Alembic
has a database URL and nothing else -- so it records each file's well-known
location in ``stored_path`` (the same root-relative convention
``submissions.source_pdf_path`` uses), which is exactly why that column exists
rather than the path being recomputed from the row's id:

* ``tests/<id>/manual.pdf``       -> ``grading_criteria``
* ``tests/<id>/model-answer.pdf`` -> ``reference``

``sha256`` is recorded as all zeroes, which no digest of real content can
collide with; it is what tells a reader "this row predates content hashing,
do not treat its hash as meaningful".

**Every** ``tests`` row is backfilled, including rows old enough to predate the
two-PDF flow entirely (migration 0011's own concern), whose files were never
written. Telling the two apart would need the on-disk registration marker
``adapters.test_intake`` uses, and a migration has a database connection and
nothing else -- so the choice is between guessing and over-covering.
Over-covering is the safer error here: a material row whose file turns out to
be absent is a state every reader already has to handle (a disk failure
produces the same thing) and the reviewer can fix it by attaching the file,
whereas a row that was never created cannot be recovered by anyone.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Digest recorded for a backfilled row, whose real content hash is unknown
#: to a migration that cannot read `app-data/`. Chosen rather than NULL so the
#: column stays NOT NULL like every other row's, and chosen as all-zeroes
#: because no SHA-256 of real content can be it.
_UNKNOWN_DIGEST = "0" * 64

#: Mirrors `domain.intake_template.MaterialRole` minus ``ignore`` -- the role
#: of a file the reviewer chose *not* to import, which no stored row carries.
#: Spelled out here rather than imported so this migration keeps describing
#: the schema as it was at this revision even if the enum later grows a member.
_material_role = sa.Enum(
    "student_answer",
    "grading_criteria",
    "annotation_resource",
    "annotation_sample",
    "reference",
    name="materialrole",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "test_materials",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "test_id",
            sa.String(),
            sa.ForeignKey("tests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", _material_role, nullable=False),
        sa.Column("stored_path", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "role IN ('student_answer', 'grading_criteria', 'annotation_resource', "
            "'annotation_sample', 'reference')",
            name="ck_test_materials_role_valid",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_test_materials_size_non_negative"),
        sa.CheckConstraint(
            "original_filename IS NULL OR length(original_filename) <= 255",
            name="ck_test_materials_original_filename_length",
        ),
        sa.UniqueConstraint("test_id", "role", "sha256", name="uq_test_materials_test_role_hash"),
    )
    op.create_index("ix_test_materials_test_id", "test_materials", ["test_id"])

    # Backfill. `id` is derived from the test id and the role rather than a
    # random uuid so re-running this migration (downgrade + upgrade) is
    # idempotent in the only way that matters: it produces the same rows.
    connection = op.get_bind()
    tests = connection.execute(sa.text("SELECT id, created_at FROM tests")).fetchall()
    for test_id, created_at in tests:
        for role, legacy_name in (
            ("grading_criteria", "manual.pdf"),
            ("reference", "model-answer.pdf"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO test_materials "
                    "(id, test_id, role, stored_path, sha256, size_bytes, "
                    " original_filename, created_at) "
                    "VALUES (:id, :test_id, :role, :stored_path, :digest, 0, "
                    ":original_filename, :created_at)"
                ),
                {
                    "id": f"{test_id}-{role}",
                    "test_id": test_id,
                    "role": role,
                    "stored_path": f"tests/{test_id}/{legacy_name}",
                    "digest": _UNKNOWN_DIGEST,
                    "original_filename": legacy_name,
                    "created_at": created_at,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_test_materials_test_id", table_name="test_materials")
    op.drop_table("test_materials")
