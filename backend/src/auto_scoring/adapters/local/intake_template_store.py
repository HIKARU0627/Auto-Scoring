"""Persist the reviewer's 取込の型 under ``app-data/`` (Issue #101).

Layout: ``app-data/settings/intake-templates.json`` -- one document holding
every saved template, written atomically through `LocalFileStore` so a
half-written file is never readable.

**Why the sidecar and not the Flutter app.** These are the user's own
settings, and the app is the thing with a settings screen -- but the app has
no persistence layer at all today, and adding one would mean a new
dependency for a single JSON document (``AGENTS.md``: a new dependency is a
last resort). The rules are also evaluated in `domain.intake_template`, so
keeping the rules and the store on the same side avoids sending a template
across the boundary just to have it interpreted back where it came from.

**API keys do not belong here.** Issue #96 decided they go in the OS
credential store (Windows Credential Locker), which is a different place on
purpose: this file is plain JSON in the user's data directory, appropriate
for "which folder layout do I use" and not for a secret. Nothing in this
module should ever grow a field for one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.intake_template import (
    DEFAULT_TEMPLATE,
    IntakeRule,
    IntakeTemplate,
    IntakeTemplateError,
    MaterialRole,
    Requirement,
    RuleScope,
)

#: Bound on how many templates one installation may hold. A template is a
#: reusable folder layout; a reviewer has a handful, not thousands, and the
#: whole file is read and rewritten on every save.
MAX_TEMPLATES = 50


def _rule_to_dict(rule: IntakeRule) -> dict[str, str]:
    return {
        "scope": rule.scope.value,
        "pattern": rule.pattern,
        "role": rule.role.value,
        "requirement": rule.requirement.value,
    }


def _rule_from_dict(raw: object) -> IntakeRule:
    if not isinstance(raw, dict):
        raise IntakeTemplateError("each rule must be a JSON object")
    try:
        return IntakeRule(
            scope=RuleScope(raw["scope"]),
            pattern=str(raw["pattern"]),
            role=MaterialRole(raw["role"]),
            requirement=Requirement(raw.get("requirement", Requirement.OPTIONAL.value)),
        )
    except (KeyError, ValueError) as exc:
        # The file is the user's own, but it is still parsed input: a
        # hand-edited or partially-written document must fail as a domain
        # error the caller can report, not as a raw KeyError/ValueError
        # escaping from a settings read (AGENTS.md "Security": validate
        # every input that crosses a trust boundary).
        raise IntakeTemplateError(f"a saved rule is not usable: {type(exc).__name__}") from None


def _template_to_dict(template: IntakeTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "split_child_directories": template.split_child_directories,
        "rules": [_rule_to_dict(rule) for rule in template.rules],
    }


def _template_from_dict(raw: object) -> IntakeTemplate:
    if not isinstance(raw, dict):
        raise IntakeTemplateError("each template must be a JSON object")
    try:
        return IntakeTemplate(
            id=str(raw["id"]),
            name=str(raw["name"]),
            rules=tuple(_rule_from_dict(rule) for rule in raw.get("rules", [])),
            split_child_directories=bool(raw.get("split_child_directories", True)),
        )
    except (KeyError, TypeError) as exc:
        raise IntakeTemplateError(f"a saved template is not usable: {type(exc).__name__}") from None


class IntakeTemplateStore:
    """Read and write the saved templates as one atomic document."""

    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    def path(self) -> Path:
        return self._files.root / "settings" / "intake-templates.json"

    def load(self) -> list[IntakeTemplate]:
        """Every saved template, seeded with the built-in default on first use.

        Seeding happens in memory and is *not* written back: a reviewer who
        deletes every template should see the default offered again next
        time rather than an empty screen, and writing on read would turn a
        listing into a mutation.
        """
        try:
            raw = json.loads(self._files.read_bytes(self.path()))
        except FileNotFoundError:
            return [DEFAULT_TEMPLATE]
        if not isinstance(raw, dict) or not isinstance(raw.get("templates"), list):
            raise IntakeTemplateError("intake-templates.json is not a template document")
        templates = [_template_from_dict(entry) for entry in raw["templates"]]
        return templates or [DEFAULT_TEMPLATE]

    def save(self, templates: list[IntakeTemplate]) -> Path:
        """Replace the saved set with ``templates``.

        Whole-document replace rather than per-template upsert: the settings
        screen edits a list (rules are reordered, rows are removed), and a
        merge would have to guess whether a template missing from the request
        was deleted or simply not sent.
        """
        if len(templates) > MAX_TEMPLATES:
            raise IntakeTemplateError(f"at most {MAX_TEMPLATES} templates can be saved")
        ids = [template.id for template in templates]
        if len(set(ids)) != len(ids):
            # Templates are referenced by id when a batch is planned; two
            # rows sharing one id would make "which template did I use?"
            # unanswerable.
            raise IntakeTemplateError("two templates share the same id")
        document = {"templates": [_template_to_dict(template) for template in templates]}
        data = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        return self._files.write_atomic(self.path(), data)

    def get(self, template_id: str) -> IntakeTemplate | None:
        for template in self.load():
            if template.id == template_id:
                return template
        return None


class IntakeCostStore:
    """The per-call price the reviewer told us their provider charges.

    Layout: ``app-data/settings/intake-cost.json``.

    Exists because Issue #101 requires the pre-flight display to show a cost,
    and **this app cannot know one**. The price depends on the provider, the
    model and the day; hard-coding a number would put a figure on screen that
    nobody verified, which is the exact failure this project has repeated. So
    the number comes from the person paying the bill, and until they enter one
    the screen says the price is unknown rather than guessing it.

    ``None`` -- the default -- means "not set", and is distinct from ``0``,
    which is a reviewer stating their usage is free (a covered quota, a local
    model).
    """

    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    def path(self) -> Path:
        return self._files.root / "settings" / "intake-cost.json"

    def load(self) -> float | None:
        try:
            raw = json.loads(self._files.read_bytes(self.path()))
        except (FileNotFoundError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        value = raw.get("classification_unit_cost")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value) if value >= 0 else None

    def save(self, unit_cost: float | None) -> None:
        if unit_cost is not None and (unit_cost < 0 or unit_cost != unit_cost):
            raise IntakeTemplateError("the unit cost must be zero or more")
        data = json.dumps({"classification_unit_cost": unit_cost}).encode("utf-8")
        self._files.write_atomic(self.path(), data)
