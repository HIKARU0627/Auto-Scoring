"""Persists a `Profile` under `app-data/`, following Issue #11's storage layout.

Layout (`docs/data-model-and-local-storage.md` §5, branch
`HIKARU0627/issue-11-data-model`, PR open/unmerged at the time Issue #15 needed
somewhere to save a profile): ``app-data/tests/<test-id>/profile.json``. This
PoC has no real ``Test`` entity yet, so `Profile.format_id` stands in for
``test-id``.

Only the piece of Issue #11's `LocalFileStore` this PoC needs: atomic write
(temp file in the same directory, flushed and `fsync`-ed, then `os.replace`
onto the final name -- atomic on Windows and POSIX, so a reader never sees a
half-written file) and read-back. `delete_*`, `sweep_temp`, and the
submission/export paths belong to Issue #11's fuller store; once that PR
merges, replace this module with `LocalFileStore` instead of keeping two
copies of the same technique.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from auto_scoring.domain.profile import Profile

_TEMP_SUFFIX = ".part"


class ProfileStore:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def profile_path(self, test_id: str) -> Path:
        """The on-disk location for `test_id`'s profile, without creating it."""
        return self._ensure_within_root(self._root / "tests" / test_id / "profile.json")

    def save(self, profile: Profile) -> Path:
        """Atomically write `profile` to `profile_path(profile.format_id)`.

        Overwrites whatever was there -- a DRAFT profile saved after detection
        and the CONFIRMED profile saved after human review live at the same
        path, one replacing the other, matching how a real "confirm" action
        would update the same test's stored profile in place.
        """
        target = self.profile_path(profile.format_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        temp = target.parent / f".{target.name}.{uuid4().hex}{_TEMP_SUFFIX}"
        try:
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return target

    def load(self, test_id: str) -> Profile:
        """Read back the profile saved for `test_id`, from a fresh JSON parse.

        No in-memory object is reused -- this is a real deserialize, so a
        caller that only has `test_id` (e.g. a different process, or this one
        after a restart) gets the same profile a save() produced.
        """
        target = self.profile_path(test_id)
        data = json.loads(target.read_text(encoding="utf-8"))
        return Profile.from_dict(data)

    def _ensure_within_root(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError(f"path {path} escapes storage root {self._root}")
        return resolved
