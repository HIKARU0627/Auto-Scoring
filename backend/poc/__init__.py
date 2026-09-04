"""PoC 2 harness — AI grading accuracy & structured-output comparison (Issue #14).

This package is a **technical probe**, not shipped product code. It is excluded
from the backend wheel (``[tool.hatch.build.targets.wheel]`` packages only
``src/auto_scoring``). Promoted artifacts are the domain schema
(``auto_scoring.domain.ai_grading``), the ``AIProvider`` port
(``auto_scoring.domain.ai_provider``), and their contract tests.

See ``docs/ai-grading-poc.md`` for the repro command, thresholds, and results.
"""
