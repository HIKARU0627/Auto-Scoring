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

import os
import shutil
from pathlib import Path
from uuid import uuid4

_TEMP_SUFFIX = ".part"


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

    def submission_dir(self, submission_id: str) -> Path:
        return self._resolve("submissions", submission_id)

    def exports_dir(self) -> Path:
        return self._resolve("exports")

    def allocate_export_path(self, original_name: str) -> Path:
        """Next free ``<stem>_corrected.pdf`` / ``<stem>_corrected_N.pdf`` (§2 (14))."""
        stem = Path(original_name).stem or "submission"
        exports = self.exports_dir()
        candidate = exports / f"{stem}_corrected.pdf"
        counter = 2
        while candidate.exists():
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
        return self._ensure_within_root(self._root.joinpath(*parts))

    def _ensure_within_root(self, path: Path) -> Path:
        resolved = (path if path.is_absolute() else self._root / path).resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"path {path} escapes storage root {self._root}")
        return resolved

    @staticmethod
    def _delete_tree(path: Path) -> None:
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            if path.exists():
                raise
