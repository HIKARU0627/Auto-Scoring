"""Validation for a registration material that is **not** necessarily a PDF
(Issue #101).

``domain.pdf_intake`` validates one uploaded answer PDF and is deliberately
PDF-only. Registration now also accepts the 添削資料 that real reviewers quote
their comments from, and those arrive as **Word or Excel** -- in the observed
material, the same role was a spreadsheet for some subjects and a prose
document for others. Rejecting them would drop the single most useful optional
input on the floor; accepting them without checking what they are would put an
unvalidated upload on disk.

So this module answers two questions ``pdf_intake`` cannot:

* **which extensions a given role accepts.** Not every role may be anything:
  a student answer becomes a `Submission`, which the whole downstream
  pipeline reads as a PDF, and the grading criteria is read as a PDF too. The
  optional roles are where Word/Excel are allowed, because that is where they
  actually occur.
* **whether the bytes match the extension.** A declared content type is not
  evidence (some upload paths send none at all), so each accepted extension
  carries the signature its container format actually starts with.

Framework-free (``AGENTS.md`` "Architecture").
"""

from __future__ import annotations

from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.models import MAX_ORIGINAL_FILENAME_LENGTH, DomainError
from auto_scoring.domain.pdf_intake import IntakeLimits

#: Leading bytes each accepted container format starts with.
#:
#: ``docx``/``xlsx`` are ZIP containers and ``doc``/``xls`` are OLE2 compound
#: files, so the two pairs share a signature -- which is fine: the point is to
#: reject a file that is not the *kind* of thing it claims to be (an
#: executable renamed to ``.xlsx``), not to distinguish Word from Excel.
_SIGNATURES: dict[str, bytes] = {
    "pdf": b"%PDF-",
    "docx": b"PK\x03\x04",
    "xlsx": b"PK\x03\x04",
    "doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
    "xls": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
}

#: Which extensions each role accepts.
#:
#: ``STUDENT_ANSWER`` and ``GRADING_CRITERIA`` are PDF-only because what reads
#: them downstream reads PDFs: an answer becomes a `Submission` that gets
#: rendered page by page, and the criteria is what profile analysis opens.
#: Accepting a ``.docx`` there would register something that cannot be used,
#: and the reviewer would only find out much later.
#:
#: The optional roles accept Word and Excel because that is what real material
#: contains -- 添削資料 was a spreadsheet for some subjects and a prose
#: document for others.
ROLE_EXTENSIONS: dict[MaterialRole, frozenset[str]] = {
    MaterialRole.STUDENT_ANSWER: frozenset({"pdf"}),
    MaterialRole.GRADING_CRITERIA: frozenset({"pdf"}),
    MaterialRole.ANNOTATION_RESOURCE: frozenset({"pdf", "docx", "doc", "xlsx", "xls"}),
    MaterialRole.ANNOTATION_SAMPLE: frozenset({"pdf"}),
    MaterialRole.REFERENCE: frozenset({"pdf", "docx", "doc", "xlsx", "xls"}),
}


class MaterialIntakeError(DomainError):
    """An uploaded material was rejected."""


class MaterialTooLargeError(MaterialIntakeError):
    """The upload exceeds the configured size limit."""


def material_extension(filename: str) -> str:
    """The lower-cased, dot-less extension of ``filename``.

    Only the *last* extension is taken, which is what makes a doubled
    extension (``....pdf.pdf``, present in the real material) resolve to the
    same ``"pdf"`` a single one does.
    """
    stem, dot, extension = filename.rpartition(".")
    if not dot or not stem:
        raise MaterialIntakeError("filename must have an extension")
    return extension.strip().lower()


def validate_material_upload(
    *,
    role: MaterialRole,
    filename: str,
    data: bytes,
    limits: IntakeLimits,
) -> str:
    """Check one upload against ``role`` and return its normalized extension.

    Raises :class:`MaterialIntakeError` (or :class:`MaterialTooLargeError`)
    describing what was wrong. The message names the role and the extension,
    both of which this repository wrote; it never quotes the file name, which
    carries the school's own course names.
    """
    if role is MaterialRole.IGNORE:
        raise MaterialIntakeError("a file marked as not-imported cannot be uploaded")
    if not filename or not filename.strip():
        raise MaterialIntakeError("filename is required")
    if "/" in filename or "\\" in filename or "\x00" in filename or filename in {".", ".."}:
        raise MaterialIntakeError("filename must not contain path separators or a null byte")
    if len(filename) > MAX_ORIGINAL_FILENAME_LENGTH:
        raise MaterialIntakeError(
            f"filename must be at most {MAX_ORIGINAL_FILENAME_LENGTH} characters"
        )

    extension = material_extension(filename)
    accepted = ROLE_EXTENSIONS[role]
    if extension not in accepted:
        raise MaterialIntakeError(f"role {role.value} accepts {sorted(accepted)}, not .{extension}")

    if not data:
        raise MaterialIntakeError("uploaded file is empty")
    if len(data) > limits.max_size_bytes:
        raise MaterialTooLargeError(f"file size {len(data)} exceeds limit {limits.max_size_bytes}")
    if not data.startswith(_SIGNATURES[extension]):
        raise MaterialIntakeError(
            f"file content does not match the .{extension} format's own signature"
        )
    return extension
