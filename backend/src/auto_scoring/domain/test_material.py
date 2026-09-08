"""One registered file of a test, with the role a human confirmed for it
(Issue #101).

Replaces the fixed two-slot registration this app started with (a model
answer PDF plus a marking manual PDF). Two things were wrong with that shape:

* **the model-answer PDF does not exist** in real grading material -- the
  criteria PDF already contains the model answer, and no separate "answers
  written into the answer boxes" document is distributed (Issue #95
  decision 1);
* **more than two files matter.** The 添削資料 (Word/Excel) that real
  reviewers quote their comments from had nowhere to go at all, and neither
  did the 添削サンプル.

So a test now owns a *list* of materials, each tagged with its
:class:`~auto_scoring.domain.intake_template.MaterialRole`. What is required
is expressed by the API that creates a test (grading criteria is a required
form field), not by a shape here that would have to be widened again the next
time a school distributes something new.

Note what this module does **not** do: it does not read, parse or extract
anything from the files. Turning a criteria PDF into per-question points and
rubrics is a separate piece of work (Issue #95 decision A) that this Issue
deliberately leaves undone -- so a test whose materials are all attached is
registered, but **not yet gradable**. Screens must say so rather than implying
grading can start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.models import MAX_ORIGINAL_FILENAME_LENGTH, DomainError


class TestMaterialError(DomainError):
    """A material could not be described."""


@dataclass(frozen=True, kw_only=True)
class TestMaterial:
    """One file attached to a test.

    ``original_filename`` is kept for the reviewer's sake -- after import,
    "which of my files became the grading criteria?" is only answerable if
    the name they chose it by survives. It is display data only: nothing
    matches on it, because names in real material are not reliable evidence
    (see ``domain.intake_template``).
    """

    id: str
    test_id: str
    role: MaterialRole
    #: Root-relative, forward-slash location under ``app-data/`` -- the same
    #: convention every other stored path field uses
    #: (``Submission.source_pdf_path``, ``Export.file_path``). Recorded rather
    #: than recomputed from the id, so a row registered before this Issue can
    #: point at where its file actually is without anything having to
    #: special-case a legacy name.
    stored_path: str
    sha256: str
    size_bytes: int
    original_filename: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        for field_name, value in (("id", self.id), ("test_id", self.test_id)):
            if not value.strip():
                raise TestMaterialError(f"TestMaterial.{field_name} must be a non-blank string")
        if self.role is MaterialRole.IGNORE:
            # An IGNORE file is one the reviewer chose *not* to import;
            # persisting one would mean the role no longer describes what the
            # row is for.
            raise TestMaterialError("a material cannot be stored with role IGNORE")
        if not self.stored_path.strip():
            raise TestMaterialError("TestMaterial.stored_path must be a non-blank string")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise TestMaterialError("TestMaterial.sha256 must be a lowercase hex digest")
        if self.size_bytes < 0:
            raise TestMaterialError("TestMaterial.size_bytes must be >= 0")
        if (
            self.original_filename is not None
            and len(self.original_filename) > MAX_ORIGINAL_FILENAME_LENGTH
        ):
            raise TestMaterialError(
                f"TestMaterial.original_filename must be at most "
                f"{MAX_ORIGINAL_FILENAME_LENGTH} characters"
            )
