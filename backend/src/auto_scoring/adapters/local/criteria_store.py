"""Persist a `CriteriaDraft` under `app-data/` using the shared local file
store (Issue #103).

Layout: ``app-data/tests/<test-id>/criteria.json`` -- deliberately the same
shape, and the same class, as `ProfileStore`'s ``profile.json`` next to it.

**Why a file and not a table.** The draft is human-review state for one
test, exactly like the profile: it is written whole, read whole, never
queried across tests, and it stops changing the moment it is confirmed. The
rows it *becomes* (`Question`/`Rubric`) already have tables. Adding a schema
migration for the intermediate artefact would buy nothing here and would
have collided with the migration Issue #101 is adding on its own branch at
the same time.
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.criteria_extraction import CriteriaDraft


class CriteriaStore:
    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    @property
    def root(self) -> Path:
        return self._files.root

    def criteria_path(self, test_id: str) -> Path:
        """The on-disk location for `test_id`'s criteria draft, without
        creating it."""
        return self._files.test_dir(test_id) / "criteria.json"

    def save(self, draft: CriteriaDraft) -> Path:
        """Atomically write `draft` to `criteria_path(draft.test_id)`.

        Overwrites whatever was there: a re-run of the extraction and a
        reviewer's own edit replace the same file, matching `ProfileStore`'s
        contract and the one-artefact-per-test model both screens present.
        """
        data = json.dumps(draft.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
        return self._files.write_atomic(self.criteria_path(draft.test_id), data)

    def load(self, test_id: str) -> CriteriaDraft:
        """Read back the draft saved for `test_id`, from a fresh JSON parse.

        Raises ``FileNotFoundError`` when no extraction has been run and
        nothing has been typed in by hand -- the caller decides whether that
        is a 404 or simply "this test has no criteria yet".
        """
        data = json.loads(self._files.read_bytes(self.criteria_path(test_id)))
        return CriteriaDraft.from_dict(data)
