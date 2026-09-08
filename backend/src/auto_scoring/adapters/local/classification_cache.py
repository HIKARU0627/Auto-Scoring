"""Remember what a classifier already said about a file, keyed by its content
(Issue #101).

Layout: ``app-data/cache/classification.json``.

Exists for one requirement: **do not ask the same question twice.** The same
file comes back through intake more often than it sounds -- a reviewer
re-selects a folder after fixing one row, retries a batch that failed
part-way, or is handed the same reference material again next term. Each of
those would otherwise spend another provider call, and another wait, on a
question already answered.

Keyed on the content digest, never on a path or a name: the same document
under a different name is the same document, and a *different* document that
happens to reuse a name is not.

The cache is advisory. It stores what the classifier proposed, never what the
reviewer confirmed -- a proposal is not a decision, and a cached proposal
still goes through the confirmation step exactly like a fresh one (Issue
#101: the human step is not an optimization that may be skipped). Losing this
file costs money and time, never correctness, so it is written
best-effort and read defensively.
"""

from __future__ import annotations

import json
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.intake_template import MaterialRole

#: Entries kept before the oldest are dropped. One batch of real material is
#: ~70 files, so this holds many terms' worth while keeping the document small
#: enough to rewrite atomically on every insert.
MAX_ENTRIES = 2000


class ClassificationCache:
    """Digest -> the role a classifier last proposed for that content.

    ``None`` as a stored role is meaningful and is cached like any other
    answer: it records "the classifier looked at this and could not tell",
    which is exactly the answer there is no point paying to re-ask.
    """

    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    def path(self) -> Path:
        return self._files.root / "cache" / "classification.json"

    def _read(self) -> dict[str, object]:
        try:
            raw = json.loads(self._files.read_bytes(self.path()))
        except FileNotFoundError:
            return {}
        except ValueError:
            # A truncated or hand-edited cache is not worth failing intake
            # over: the worst case of treating it as empty is paying for
            # calls that were already paid for once.
            return {}
        return raw.get("roles", {}) if isinstance(raw, dict) else {}

    def get_role(self, sha256: str) -> tuple[bool, MaterialRole | None]:
        """``(hit, role)``.

        Returns the hit flag separately because ``None`` is a real cached
        answer ("could not tell"), so ``role is None`` alone cannot
        distinguish a miss from it.
        """
        entry = self._read().get(sha256)
        if not isinstance(entry, dict) or "role" not in entry:
            return False, None
        raw_role = entry["role"]
        if raw_role is None:
            return True, None
        try:
            return True, MaterialRole(raw_role)
        except ValueError:
            # Written by a build whose role set differed. Treat as a miss
            # rather than guessing which current role it meant.
            return False, None

    def cached_digests(self) -> set[str]:
        """Every digest with a stored answer, for the pre-flight estimate."""
        return {key for key, value in self._read().items() if isinstance(value, dict)}

    def put_role(self, sha256: str, role: MaterialRole | None) -> None:
        roles = self._read()
        roles[sha256] = {"role": role.value if role is not None else None}
        if len(roles) > MAX_ENTRIES:
            # Plain insertion order, which for a dict loaded from JSON is the
            # order it was written in -- oldest first. Good enough for a cache
            # whose only job is to avoid paying twice; an LRU would need a
            # timestamp per entry and a reason to care about one.
            for key in list(roles)[: len(roles) - MAX_ENTRIES]:
                del roles[key]
        data = json.dumps({"roles": roles}, ensure_ascii=False).encode("utf-8")
        self._files.write_atomic(self.path(), data)
