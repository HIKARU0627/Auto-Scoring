"""Persist a `Profile` under `app-data/` using the shared local file store.

Layout: ``app-data/tests/<test-id>/profile.json``. This PoC has no real
``Test`` entity yet, so `Profile.format_id` stands in for ``test-id``.
`ProfileStore` owns JSON serialization; Issue #11's `LocalFileStore` owns path
validation and atomic file I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.profile import Profile


class ProfileStore:
    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    @property
    def root(self) -> Path:
        return self._files.root

    def profile_path(self, test_id: str) -> Path:
        """The on-disk location for `test_id`'s profile, without creating it."""
        return self._files.test_dir(test_id) / "profile.json"

    def save(self, profile: Profile) -> Path:
        """Atomically write `profile` to `profile_path(profile.format_id)`.

        Overwrites whatever was there -- a DRAFT profile saved after detection
        and the CONFIRMED profile saved after human review live at the same
        path, one replacing the other, matching how a real "confirm" action
        would update the same test's stored profile in place.
        """
        data = json.dumps(profile.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        return self._files.write_atomic(self.profile_path(profile.format_id), data)

    def load(self, test_id: str) -> Profile:
        """Read back the profile saved for `test_id`, from a fresh JSON parse.

        No in-memory object is reused -- this is a real deserialize, so a
        caller that only has `test_id` (e.g. a different process, or this one
        after a restart) gets the same profile a save() produced.
        """
        data = json.loads(self._files.read_bytes(self.profile_path(test_id)))
        return Profile.from_dict(data)
