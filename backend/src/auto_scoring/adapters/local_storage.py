"""On-disk layout for `app-data/`, with atomic writes and a crash sweep.

Layout (simplified-design-specification.md §23)::

    app-data/
      database.sqlite
      tests/<test-id>/{model-answer.pdf, manual.pdf, profile.json}
      submissions/<submission-id>/source.pdf
      exports/<original-stem>_corrected[_N].pdf

Rules this class enforces:

* **Atomic write** — data is written to a hidden temp file in the *same*
  directory, flushed and ``fsync``-ed, then ``os.replace``-d onto the final
  name (atomic on Windows and POSIX). A reader never sees a half-written file.
* **Crash recovery** — :meth:`sweep_temp` deletes leftover ``*.part`` files from
  a write that was interrupted before the rename. Run it on startup.
* **Delete** — :meth:`delete_test` / :meth:`delete_submission` remove a whole
  subtree; the caller records the deletion in the audit log (business-rules §2
  (11)).
* **No path escape** — every path is checked to stay under the root.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

_TEMP_SUFFIX = ".part"

#: Bound on the file extension `test_material_path` interpolates. Short and
#: alphanumeric: the value comes from a reviewer-chosen file name, and
#: everything else about that name is deliberately not used (see that method).
_MATERIAL_EXTENSION_PATTERN = re.compile(r"[a-z0-9]{1,8}")

#: Windows device names reserved regardless of extension (``CON.png`` still
#: addresses the ``CON`` device via most Win32 APIs). Checked against the
#: segment's stem, case-insensitively.
_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _ensure_safe_path_segment(value: str) -> None:
    """Reject a value that isn't safe to use as a single path segment.

    Ids that end up embedded in a path here (``Question.id``, submission/test
    ids) are only required by the domain layer to be non-empty -- nothing
    stops a value like ``"../pages/page-1"`` from resolving, once
    interpolated into a filename, to a completely different file elsewhere
    under the store root. ``_ensure_within_root`` only catches escaping the
    root entirely; it would accept a path like that since it still lands
    inside ``app-data/``, just silently overwriting the wrong file (AGENTS.md
    "Validate every input that crosses a trust boundary").

    A colon is rejected outright rather than just "/" and "\\": on Windows, a
    drive-relative segment like ``"C:foo"`` carries no path separator at all,
    yet ``Path.joinpath(root, "C:foo.png")`` resolves to the same path as
    plain ``"foo.png"`` -- two different ids would silently collide on one
    file. Windows' reserved device names (``CON``, ``COM1``, ...) are
    rejected too: many Win32 APIs address the device through a name like
    that regardless of extension (``CON.png`` still means ``CON``).
    """
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or ":" in value
    ):
        raise ValueError(f"unsafe path segment: {value!r}")
    stem = value.split(".", 1)[0]
    if stem.upper() in _WINDOWS_RESERVED_STEMS:
        raise ValueError(f"unsafe path segment: {value!r}")


def _encode_filename_component(value: str) -> str:
    """Deterministically encode ``value`` for use as a filename stem.

    ``Question.id`` is only required by the domain layer to be non-empty --
    nothing stops it from containing characters Windows forbids in a
    filename (``? * " < > | :``, checked above only when they'd also be
    unsafe as a bare *path segment*, which ``<id>.png`` is not) or from two
    ids differing only by case: NTFS resolves filenames case-insensitively,
    so ``"Q-1"`` and ``"q-1"`` would address the same file on Windows even
    though they are two distinct rows in the DB, each retry of the
    forbidden-character case would fail finalization again, and the
    case-collision case would silently overwrite one question's crop with
    the other's. Hex-encoding the id's UTF-8 bytes sidesteps both: the
    result is always composed of ``[0-9a-f]`` (always a valid filename on
    every platform), and it is byte-exact, so differently-cased or
    differently-punctuated inputs always encode to different strings.
    """
    return value.encode("utf-8").hex()


class LocalFileStore:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # -- locations -------------------------------------------------------- #
    def database_path(self) -> Path:
        return self._resolve("database.sqlite")

    def test_dir(self, test_id: str) -> Path:
        return self._resolve("tests", test_id)

    def test_model_answer_pdf_path(self, test_id: str) -> Path:
        """The registered model-answer PDF (Issue #16, simplified-design-spec.md §23)."""
        return self._resolve("tests", test_id, "model-answer.pdf")

    def test_manual_pdf_path(self, test_id: str) -> Path:
        """The registered marking-manual PDF (Issue #16, simplified-design-spec.md §23)."""
        return self._resolve("tests", test_id, "manual.pdf")

    def test_material_path(self, test_id: str, material_id: str, extension: str) -> Path:
        """Where one role-tagged registration file lives (Issue #101).

        Named by the material's own id rather than by its role, because a
        test may hold several files of the same role (four 添削サンプル in
        one real subject folder) and because the reviewer's own file name is
        not safe to use as a path segment -- real material contains a name
        with a doubled extension and one with whitespace before its
        extension. The name they chose is kept as
        `TestMaterial.original_filename`, for display only.

        ``extension`` is bounded to a short alphanumeric run: it is the one
        part of this path derived from the uploaded file rather than from an
        id this app minted, so it is validated here rather than trusted.
        """
        if not _MATERIAL_EXTENSION_PATTERN.fullmatch(extension):
            raise ValueError(f"unsafe material extension: {extension!r}")
        return self._resolve("tests", test_id, "materials", f"{material_id}.{extension}")

    def resolve_stored_path(self, stored_path: str) -> Path:
        """A root-relative ``*_path`` field (``TestMaterial.stored_path``,
        ``Submission.source_pdf_path``) back to an absolute path.

        Goes through ``_resolve`` so a stored value that has been tampered
        with cannot address a file outside the store root.
        """
        return self._resolve(*stored_path.split("/"))

    def test_answer_layout_pdf_path(self, test_id: str) -> Path:
        """The reference student answer sheet a test's answer areas were laid
        out against (Issue #105).

        One per test, deliberately: the reviewer picks a single representative
        answer, confirms the boxes on it, and every later submission of the
        same format is cropped with those same coordinates -- so this file's
        only job is to be the page the overlay editor draws on, and to be
        re-detectable against without asking for the file again after a
        provider failure.

        Stored under the *test*, not the submissions tree, because it is not a
        submission: it is never graded, never gets a `Submission` row, and can
        be uploaded while the test is still `draft` -- which it has to be,
        since `adapters.submission_intake.intake_submission` refuses a test
        that is not `ready` and a test cannot become `ready` until these
        boxes exist.
        """
        return self._resolve("tests", test_id, "answer-layout.pdf")

    def submission_dir(self, submission_id: str) -> Path:
        return self._resolve("submissions", submission_id)

    def submission_source_pdf_path(self, submission_id: str) -> Path:
        return self._resolve("submissions", submission_id, "source.pdf")

    def submission_page_image_path(self, submission_id: str, page: int) -> Path:
        """Preprocessed full-page preview image (Issue #17 §7.1), 1-based ``page``."""
        return self._resolve("submissions", submission_id, "pages", f"page-{page}.png")

    def submission_question_image_path(self, submission_id: str, question_id: str) -> Path:
        """Cropped answer-area image for one question of one submission."""
        encoded = _encode_filename_component(question_id)
        return self._resolve("submissions", submission_id, "questions", f"{encoded}.png")

    def exports_dir(self) -> Path:
        return self._resolve("exports")

    def allocate_export_path(self, original_name: str, *, reserved: Iterable[str] = ()) -> Path:
        """Next free ``<stem>_corrected.pdf`` / ``<stem>_corrected_N.pdf`` (§2 (14)).

        ``reserved`` is a set of already-recorded ``Export.file_path``
        values (root-relative, forward-slash -- the same format that field
        is stored in) for the same submission, in addition to whatever this
        method's own ``.exists()`` check already sees on disk (Issue #23 P1
        review, round 3). A path some other `Export` row already claims
        must never be handed out again here, even when that row's own file
        write is exactly what failed and left nothing on disk for
        ``.exists()`` to catch -- otherwise a second, unrelated export could
        silently claim (and, once written, occupy) the same path, and a
        later repair of the first row would overwrite the second one's
        file out from under it.
        """
        stem = Path(original_name).stem or "submission"
        exports = self.exports_dir()
        reserved_paths = set(reserved)
        candidate = exports / f"{stem}_corrected.pdf"
        counter = 2
        while candidate.exists() or self.relative_path(candidate) in reserved_paths:
            candidate = exports / f"{stem}_corrected_{counter}.pdf"
            counter += 1
        return candidate

    # -- io -------------------------------------------------------------- #
    def write_atomic(self, path: Path, data: bytes) -> Path:
        """Write ``data`` to ``path`` atomically; return ``path``."""
        target = self._ensure_within_root(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / f".{target.name}.{uuid4().hex}{_TEMP_SUFFIX}"
        try:
            with open(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return target

    def read_bytes(self, path: Path) -> bytes:
        return self._ensure_within_root(path).read_bytes()

    def delete_test(self, test_id: str) -> None:
        self._delete_tree(self.test_dir(test_id))

    def delete_submission(self, submission_id: str) -> None:
        self._delete_tree(self.submission_dir(submission_id))

    def sweep_temp(self) -> list[Path]:
        """Delete leftover temp files from interrupted writes; return what was removed."""
        removed: list[Path] = []
        for temp in self._root.rglob(f"*{_TEMP_SUFFIX}"):
            if temp.is_file():
                temp.unlink(missing_ok=True)
                removed.append(temp)
        return removed

    # -- internals ----------------------------------------------------- #
    def _resolve(self, *parts: str) -> Path:
        for part in parts:
            _ensure_safe_path_segment(part)
        return self._ensure_within_root(self._root.joinpath(*parts))

    def _ensure_within_root(self, path: Path) -> Path:
        resolved = (path if path.is_absolute() else self._root / path).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"path {path} escapes storage root {self._root}")
        return resolved

    def relative_path(self, path: Path) -> str:
        """``path`` (already under this store's root) as the same
        root-relative, forward-slash string every stored ``*_path`` field
        (``Submission.source_pdf_path``, ``TestMaterial.stored_path``,
        ``Export.file_path``, ...) uses.

        The inverse of :meth:`resolve_stored_path`.
        """
        return str(path.relative_to(self._root)).replace("\\", "/")

    @staticmethod
    def _delete_tree(path: Path) -> None:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            if path.exists():
                raise


def file_matches_sha256(path: Path, expected_sha256: str) -> bool:
    """Whether ``path`` exists and its content's sha256 digest equals
    ``expected_sha256`` (Issue #23 P1/P2 review).

    Shared by `jobs.export_processor.ExportJobProcessor` (idempotent-replay
    safety: an `Export` row surviving a crash between its own DB commit and
    the file write that follows it) and `api.export_router` (never telling a
    reviewer a `reuse_existing` export is ready when its recorded file has
    since gone missing or been corrupted) so both agree on exactly one
    definition of "this recorded output is actually still there, intact".
    """
    if not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
