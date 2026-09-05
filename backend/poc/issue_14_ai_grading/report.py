"""PoC 2 (issue #14) harness -- aggregate AI grading metrics from recorded
provider responses + human labels.

Usage::

    uv run python poc/issue_14_ai_grading/report.py [--dataset DIR] [--out FILE]

Every ``*.json`` under ``DIR`` is one graded question (see
``tests/fixtures/ai_grading/README.md`` for the shape)::

    {
      "ground_truth": {...},
      "input": {...},
      "recorded": {
        "<provider>": {
          "ocr_clean": {
            "response": {...},
            "descriptor": {...},
            "latency_seconds": 1.1,
            "cost_usd": 0.0008
          },
          "ocr_noisy": {...}
        }
      }
    }

``DIR`` defaults to the committed synthetic fixtures, so the command runs with
no credentials and no dataset and reproduces a secret-free aggregate table
(Issue #14 verification: "secretと答案本文を出力せず、同じデータから
集計結果を再生成できることを確認する"). Point ``--dataset`` at the local,
licensed real-data pilot directory (see ``docs/poc-2-ai-grading.md``) for the
real numbers once an ``AIProvider`` adapter has recorded responses into it.

The expected comparison matrix is every provider seen anywhere in the dataset
times both input variants (``ocr_clean`` / ``ocr_noisy``) -- not just the
cells a given sample happens to define. A cell missing from that matrix (no
``recorded[provider][variant]`` entry at all, or one with no ``response`` key)
is "pending", never silently skipped: comparing only 2 candidates when the
PoC requires >= 2 x both input modes must be visible in the output, not
inferred from an incomplete loop (code review finding).

A cell whose raw JSON fails
:func:`auto_scoring.domain.ai_grading.parse_ai_grading_result` is a schema
violation and is scored as such -- never as a free-text-parsed guess
(Issue #14 acceptance). A cell's ``descriptor`` (model / version / temperature
/ structured-output mode) is read from the recorded data itself, never
fabricated here: two cells for the same ``provider`` name recorded under
different settings must stay distinguishable (Issue #14 "再現条件").

Only counts and averaged scores are printed. Provider response bodies (and
any real answer text they might embed) are read only long enough to compute
these aggregates, and are never logged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_grading_metrics import (
    GradingGroundTruth,
    SampleOutcome,
    evaluate_sample,
    summarize_by_provider,
    to_markdown_table,
)
from auto_scoring.domain.ai_provider import (
    GradingResponse,
    ProviderDescriptor,
    grading_response_from_result,
)

_DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_grading"

#: The two input variants every provider is compared on (docs/poc-2-ai-grading.md
#: section 2.1). Fixed rather than derived from whatever keys happen to be
#: present, so a variant missing for one provider is still reported.
_INPUT_VARIANTS = ("ocr_clean", "ocr_noisy")


class _MissingDescriptor(Exception):
    """A recorded cell has a ``response`` but no ``descriptor`` metadata."""


def _descriptor_from_cell(cell: dict[str, Any], *, provider: str, path: Path) -> ProviderDescriptor:
    raw = cell.get("descriptor")
    if raw is None:
        raise _MissingDescriptor(
            f"{path}: provider {provider!r} has a recorded response but no 'descriptor' "
            "(model/version/temperature/structured_output_mode) -- cannot be reproduced "
            "(Issue #14 '再現条件'). Add a descriptor object to this cell."
        )
    return ProviderDescriptor(
        provider=provider,
        model=str(raw["model"]),
        version=None if raw.get("version") is None else str(raw["version"]),
        temperature=float(raw["temperature"]),
        structured_output_mode=str(raw["structured_output_mode"]),
    )


def _load_cell(
    cell: dict[str, Any] | None, *, provider: str, path: Path
) -> tuple[GradingResponse | None, float | None, float | None, bool]:
    """Parse one recorded ``(provider, input_variant)`` cell.

    Returns ``(GradingResponse | None, cost_usd, latency_seconds, pending)``.
    ``pending`` is true when the cell is entirely absent or has no
    ``response`` key; a malformed ``response`` yields ``(None, cost,
    latency, False)`` -- a schema violation, not a pending measurement.
    ``latency_seconds`` is read independent of whether the response parsed,
    and is ``None`` (not a fabricated ``0.0``) when the cell records none.
    """
    if cell is None or "response" not in cell:
        cost_usd = None if cell is None else cell.get("cost_usd")
        return None, cost_usd, None, True

    cost_usd = cell.get("cost_usd")
    latency_raw = cell.get("latency_seconds")
    latency_seconds = float(latency_raw) if latency_raw is not None else None

    try:
        parsed = parse_ai_grading_result(json.dumps(cell["response"]))
    except ValidationError:
        return None, cost_usd, latency_seconds, False

    descriptor = _descriptor_from_cell(cell, provider=provider, path=path)
    response = grading_response_from_result(
        parsed, descriptor=descriptor, latency_seconds=latency_seconds or 0.0
    )
    return response, cost_usd, latency_seconds, False


def _all_providers(files: list[Path]) -> set[str]:
    """Every provider name recorded anywhere in the dataset.

    This -- not the keys present in any single file -- defines the expected
    comparison matrix, so a provider missing from one sample's ``recorded``
    still shows up as a pending cell for that sample.
    """
    providers: set[str] = set()
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        providers.update(raw.get("recorded", {}).keys())
    return providers


def _load_samples(dataset: Path) -> tuple[list[SampleOutcome], int, int]:
    """Return ``(evaluated outcomes, pending-cell count, files with no
    provider recorded anywhere in the dataset)`` from every ``*.json``.

    The third count covers a real-data pilot staged ahead of any
    ``AIProvider`` call (ground truth transcribed, ``recorded`` left ``{}``
    dataset-wide) -- distinct from "pending" cells, which are expected
    (some other sample recorded that provider) but missing for this one.
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")

    providers = _all_providers(files)
    if not providers:
        return [], 0, len(files)

    outcomes: list[SampleOutcome] = []
    pending = 0
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = GradingGroundTruth.from_mapping(raw["ground_truth"])
        recorded: dict[str, dict[str, Any]] = raw.get("recorded", {})
        for provider in sorted(providers):
            cells_for_provider = recorded.get(provider, {})
            for variant in _INPUT_VARIANTS:
                cell = cells_for_provider.get(variant)
                response, cost_usd, latency_seconds, is_pending = _load_cell(
                    cell, provider=provider, path=path
                )
                if is_pending:
                    pending += 1
                    continue
                outcomes.append(
                    evaluate_sample(
                        truth,
                        response,
                        provider=provider,
                        input_variant=variant,
                        cost_usd=cost_usd,
                        latency_seconds=latency_seconds,
                    )
                )
    return outcomes, pending, 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # keep the JP table readable on Windows

    parser = argparse.ArgumentParser(description="PoC 2 AI grading metric aggregator")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    outcomes, pending, staged = _load_samples(args.dataset)
    table = to_markdown_table(summarize_by_provider(outcomes))
    notes = ""
    if pending:
        notes += (
            f"\npending (expected provider/input-variant cell has no recorded response "
            f"yet): {pending}\n"
        )
    if staged:
        notes += (
            f"\nstaged ground truth with no provider recorded anywhere in the dataset "
            f"(no AIProvider call made yet): {staged}\n"
        )
    report = f"# PoC 2 AI grading aggregate\n\nevaluated cells: {len(outcomes)}\n{notes}\n{table}\n"

    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
