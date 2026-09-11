"""Per-1000-token unit price for AI grading cost display (Issue #187)."""

from __future__ import annotations

import json
from pathlib import Path

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.local.intake_template_store import IntakeTemplateError


class GradingCostStore:
    """The price per 1000 tokens the reviewer entered for grading display.

    Layout: ``app-data/settings/grading-cost.json``.

    ``None`` means "not set" -- distinct from zero, for the same reasons as
    `IntakeCostStore`.
    """

    def __init__(self, root: Path | str) -> None:
        self._files = LocalFileStore(root)

    def path(self) -> Path:
        return self._files.root / "settings" / "grading-cost.json"

    def load(self) -> float | None:
        try:
            raw = json.loads(self._files.read_bytes(self.path()))
        except (FileNotFoundError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        value = raw.get("token_unit_cost")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value) if value >= 0 else None

    def save(self, token_unit_cost: float | None) -> None:
        if token_unit_cost is not None and (token_unit_cost < 0 or token_unit_cost != token_unit_cost):
            raise IntakeTemplateError("the token unit cost must be zero or more")
        data = json.dumps({"token_unit_cost": token_unit_cost}).encode("utf-8")
        self._files.write_atomic(self.path(), data)
