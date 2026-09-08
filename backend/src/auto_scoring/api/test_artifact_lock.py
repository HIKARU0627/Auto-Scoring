"""One per-test lock namespace, shared by every router that rewrites a
test's `Question`/`Rubric` rows (Issue #103).

`Profile` and `CriteriaDraft` are both JSON files that their endpoints read,
transform, and overwrite whole, and **both** confirm steps rebuild the same
`Question`/`Rubric` rows by deleting them and re-inserting from those two
files (`domain.test_registration.build_questions_and_rubrics`). Issue #16
already serialized the profile's own three endpoints against each other for
that reason. Once a second router could rebuild the same rows, a private
lock per router stopped being enough:

    /criteria/confirm reads the profile        (not confirmed yet)
    /profile/confirm  reads the criteria draft (not confirmed yet)
    /criteria/confirm commits questions built from the draft alone
    /profile/confirm  commits questions built from the regions alone
                      -> the confirmed points are gone, and nothing says so

Both handlers taking the *same* lock for the same test id makes the
interleave impossible, and leaves the two confirms order-independent: each
one reads whatever the other has already committed.

Grown lazily per test id and never evicted, exactly like the registry it
replaces: the number of distinct tests a sidecar process ever sees is small.
"""

from __future__ import annotations

import threading


class TestArtifactLocks:
    """A lazily-grown ``test_id -> Lock`` registry, safe to share between
    routers built by the same ``create_app`` call."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def for_test(self, test_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(test_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[test_id] = lock
            return lock
