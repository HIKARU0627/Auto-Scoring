"""PoC 2 (issue #14) harness -- aggregate AI grading metrics from recorded
provider responses + human labels.

Usage::

    uv run python poc/issue_14_ai_grading/report.py [--dataset DIR] [--out FILE]

Every ``*.json`` under ``DIR`` is one graded question (see
``tests/fixtures/ai_grading/README.md`` for the shape)::

    {
      "ground_truth": {...},
      "input": {...},
      "recorded": {"<provider>": {"ocr_clean": {...}, "ocr_noisy": {...}}}
    }

``DIR`` defaults to the committed synthetic fixtures, so the command runs with
no credentials and no dataset and reproduces a secret-free aggregate table
(Issue #14 verification: "secretと答案本文を出力せず、同じデータから
集計結果を再生成できることを確認する"). Point ``--dataset`` at the local,
licensed real-data pilot directory (see ``docs/poc-2-ai-grading.md``) for the
real numbers once an ``AIProvider`` adapter has recorded responses into it.

A ``recorded`` cell that is missing its ``response`` entirely (no provider
output yet -- e.g. a real-data sample staged ahead of API credentials) is
skipped and counted as "pending", never treated as a zero or a failure. A
cell whose raw JSON fails
:func:`auto_scoring.domain.ai_grading.parse_ai_grading_result` is a schema
violation and is scored as such -- never as a free-text-parsed guess
(Issue #14 acceptance).

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
from auto_scoring.domain.ai_provider import ProviderDescriptor, grading_response_from_result

_DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_grading"


def _load_cell(cell: dict[str, Any], *, provider: str) -> tuple[Any | None, float | None, bool]:
    """Parse one recorded ``(provider, input_variant)`` cell.

    Returns ``(GradingResponse | None, cost_usd, pending)``. ``pending`` is
    true only when the cell has no ``response`` key at all; a malformed
    ``response`` yields ``(None, cost, False)`` -- a schema violation, not a
    pending measurement.
    """
    cost_usd = cell.get("cost_usd")
    if "response" not in cell:
        return None, cost_usd, True

    latency_seconds = float(cell.get("latency_seconds", 0.0))
    try:
        parsed = parse_ai_grading_result(json.dumps(cell["response"]))
    except ValidationError:
        return None, cost_usd, False

    descriptor = ProviderDescriptor(
        provider=provider,
        model=provider,
        version=None,
        temperature=0.0,
        structured_output_mode="json_schema",
    )
    response = grading_response_from_result(
        parsed, descriptor=descriptor, latency_seconds=latency_seconds
    )
    return response, cost_usd, False


def _load_samples(dataset: Path) -> tuple[list[SampleOutcome], int, int]:
    """Return ``(evaluated outcomes, pending-cell count, files with no provider
    cell at all)`` from every ``*.json``.

    The third count covers a real-data pilot staged ahead of any ``AIProvider``
    call (ground truth transcribed, ``recorded`` left ``{}``) -- distinct from
    "pending" cells, which have a provider entry but no ``response`` yet.
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")

    outcomes: list[SampleOutcome] = []
    pending = 0
    staged_without_recorded = 0
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = GradingGroundTruth.from_mapping(raw["ground_truth"])
        recorded: dict[str, dict[str, Any]] = raw.get("recorded", {})
        if not recorded:
            staged_without_recorded += 1
            continue
        for provider, variants in recorded.items():
            for variant, cell in variants.items():
                response, cost_usd, is_pending = _load_cell(cell, provider=provider)
                if is_pending:
                    pending += 1
                    continue
                outcomes.append(
                    evaluate_sample(
                        truth,
                        response,
                        provider=provider,
                        input_variant=variant,
                        cost_usd=float(cost_usd) if cost_usd is not None else None,
                    )
                )
    return outcomes, pending, staged_without_recorded


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
        notes += f"\npending (recorded but no response yet, awaiting credentials): {pending}\n"
    if staged:
        notes += (
            f"\nstaged ground truth with no provider cell at all "
            f"(no AIProvider call recorded yet): {staged}\n"
        )
    report = f"# PoC 2 AI grading aggregate\n\nevaluated cells: {len(outcomes)}\n{notes}\n{table}\n"

    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
