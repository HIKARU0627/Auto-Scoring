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
            "descriptor": {
              "model": "...",
              "version": "... or null",
              "prompt_version": "...",
              "temperature": 0.0,
              "structured_output_mode": "json_schema"
            },
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
is "pending", never silently skipped. The PoC requires comparing at least 2
candidates *on the same data* (docs/poc-2-ai-grading.md section 2): an empty
or all-pending ``recorded`` entry does not count as a candidate, and two
providers recorded only on disjoint samples (never together on one question)
do not count as a comparison either -- both are refused outright rather than
printed as if the comparison were complete (code review finding).

A cell whose raw JSON fails
:func:`auto_scoring.domain.ai_grading.parse_ai_grading_result` is a schema
violation and is scored as such -- never as a free-text-parsed guess
(Issue #14 acceptance). A cell's ``descriptor`` (model / version / prompt
version / temperature / structured-output mode) is read from the recorded
data itself, never fabricated here, and is required on every non-pending
cell (even one that turns out to be a schema violation): two cells for the
same ``provider`` name recorded under different settings -- including a
prompt template edit alone -- are aggregated as separate buckets, keyed on
:func:`auto_scoring.domain.ai_provider.descriptor_key`, never pooled
(Issue #14 "再現条件"). ``cost_usd`` / ``latency_seconds`` are validated as
finite, non-negative numbers before they reach any aggregate (code review
finding): a negative, non-finite, or non-numeric recorded value raises
rather than silently skewing the adoption-gate metrics.

Only counts and averaged scores are printed. Provider response bodies (and
any real answer text they might embed) are read only long enough to compute
these aggregates, and are never logged.
"""

from __future__ import annotations

import argparse
import json
import math
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
    descriptor_key,
    grading_response_from_result,
)

_DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_grading"

#: The two input variants every provider is compared on (docs/poc-2-ai-grading.md
#: section 2.1). Fixed rather than derived from whatever keys happen to be
#: present, so a variant missing for one provider is still reported.
_INPUT_VARIANTS = ("ocr_clean", "ocr_noisy")

#: The PoC requires comparing at least this many candidates on the same data
#: (docs/poc-2-ai-grading.md section 2: "Gemini、Claude、OpenAI GPTのうち
#: 利用可能な最低2候補を...比較する").
_MINIMUM_PROVIDERS = 2


class _MissingDescriptor(Exception):
    """A recorded cell has a ``response`` but no ``descriptor`` metadata."""


def _descriptor_from_cell(cell: dict[str, Any], *, provider: str, path: Path) -> ProviderDescriptor:
    raw = cell.get("descriptor")
    if raw is None:
        raise _MissingDescriptor(
            f"{path}: provider {provider!r} has a recorded response but no 'descriptor' "
            "(model/version/prompt_version/temperature/structured_output_mode) -- cannot "
            "be reproduced or safely bucketed (Issue #14 '再現条件'). Add a descriptor "
            "object to this cell."
        )
    return ProviderDescriptor(
        provider=provider,
        model=str(raw["model"]),
        version=None if raw.get("version") is None else str(raw["version"]),
        prompt_version=str(raw["prompt_version"]),
        temperature=float(raw["temperature"]),
        structured_output_mode=str(raw["structured_output_mode"]),
    )


class _InvalidMeasurement(Exception):
    """A recorded ``cost_usd`` or ``latency_seconds`` value is not a finite,
    non-negative number.

    Both fields cross the ``--dataset`` trust boundary the same as any other
    recorded value: a negative cost, a bool masquerading as a number
    (``bool`` is a Python ``int`` subclass, so ``float(True) == 1.0`` would
    otherwise pass silently), a string, or a non-finite float (``nan`` /
    ``inf``) must be rejected before it reaches the adoption-gate metrics,
    not coerced or fed into ``statistics.fmean`` as-is (code review finding).
    """


def _validated_measurement(value: object, *, field: str, provider: str, path: Path) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _InvalidMeasurement(
            f"{path}: provider {provider!r} has a non-numeric {field!r}: {value!r}"
        )
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _InvalidMeasurement(
            f"{path}: provider {provider!r} has an invalid {field!r} "
            f"(must be finite and >= 0): {value!r}"
        )
    return number


def _load_cell(
    cell: dict[str, Any] | None, *, provider: str, path: Path
) -> tuple[GradingResponse | None, str | None, float | None, float | None, bool]:
    """Parse one recorded ``(provider, input_variant)`` cell.

    Returns ``(GradingResponse | None, config_key, cost_usd, latency_seconds,
    pending)``. ``pending`` is true when the cell is entirely absent or has
    no ``response`` key; a malformed ``response`` yields ``(None, config_key,
    cost, latency, False)`` -- a schema violation, not a pending measurement.
    ``descriptor`` (and so ``config_key``) is required as soon as a
    ``response`` key is present, even if that response goes on to fail
    schema validation, so schema-violating cells are still bucketed by the
    configuration that produced them. ``latency_seconds`` is read independent
    of whether the response parsed, and is ``None`` (not a fabricated
    ``0.0``) when the cell records none.
    """
    if cell is None or "response" not in cell:
        cost_usd = (
            None
            if cell is None
            else _validated_measurement(
                cell.get("cost_usd"), field="cost_usd", provider=provider, path=path
            )
        )
        return None, None, cost_usd, None, True

    cost_usd = _validated_measurement(
        cell.get("cost_usd"), field="cost_usd", provider=provider, path=path
    )
    latency_seconds = _validated_measurement(
        cell.get("latency_seconds"), field="latency_seconds", provider=provider, path=path
    )
    descriptor = _descriptor_from_cell(cell, provider=provider, path=path)
    config_key = descriptor_key(descriptor)

    try:
        parsed = parse_ai_grading_result(json.dumps(cell["response"]))
    except ValidationError:
        return None, config_key, cost_usd, latency_seconds, False

    response = grading_response_from_result(
        parsed, descriptor=descriptor, latency_seconds=latency_seconds or 0.0
    )
    return response, config_key, cost_usd, latency_seconds, False


def _all_providers(files: list[Path]) -> set[str]:
    """Every provider name recorded anywhere in the dataset (raw ``recorded``
    dict keys, including an empty or all-pending entry).

    This -- not the keys present in any single file -- defines the expected
    comparison matrix, so a provider missing from one sample's ``recorded``
    still shows up as a pending cell for that sample. It is deliberately
    *not* used to decide whether the dataset qualifies as a real comparison
    (see :func:`_providers_with_overlapping_recordings`): an empty
    ``"claude": {}`` placeholder, or a provider recorded only on samples no
    other provider ever touched, is a key here but must not count as a
    second candidate being compared (code review finding).
    """
    providers: set[str] = set()
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        providers.update(raw.get("recorded", {}).keys())
    return providers


def _providers_with_response_in_file(raw: dict[str, Any]) -> set[str]:
    """Providers that have an actual (non-pending) ``response`` recorded
    somewhere in this one file, for at least one input variant."""
    providers: set[str] = set()
    for provider, variants in raw.get("recorded", {}).items():
        if any(isinstance(cell, dict) and "response" in cell for cell in variants.values()):
            providers.add(provider)
    return providers


def _providers_with_overlapping_recordings(files: list[Path]) -> set[str]:
    """Providers that qualify as one side of a real, same-data comparison.

    A provider qualifies only if it has recorded an actual response (not
    just an empty or all-pending ``recorded`` entry) *and* shares at least
    one sample with another such provider -- i.e. there is at least one
    question both providers were actually run against. Two providers each
    recorded only on disjoint samples are never compared on the same data,
    so neither counts (code review finding: `len(providers) >= 2` on raw
    dict keys passed even when the dataset had an empty placeholder entry,
    or two providers that never appeared together on one question).
    """
    per_file: list[set[str]] = []
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        per_file.append(_providers_with_response_in_file(raw))

    overlapping: set[str] = set()
    for providers_in_file in per_file:
        if len(providers_in_file) >= _MINIMUM_PROVIDERS:
            overlapping.update(providers_in_file)
    return overlapping


def _load_samples(dataset: Path) -> tuple[list[SampleOutcome], int, int]:
    """Return ``(evaluated outcomes, pending-cell count, files with no
    provider recorded anywhere in the dataset)`` from every ``*.json``.

    The third count covers a real-data pilot staged ahead of any
    ``AIProvider`` call (ground truth transcribed, ``recorded`` left ``{}``
    dataset-wide) -- distinct from "pending" cells, which are expected
    (some other sample recorded that provider) but missing for this one.

    Raises ``SystemExit`` unless at least
    :data:`_MINIMUM_PROVIDERS` providers each have a real recorded response
    on a *shared* sample (see :func:`_providers_with_overlapping_recordings`):
    the PoC requires comparing candidates on the same data, so a dataset
    where only one provider (or several, but never together on one
    question) has actually been run is refused outright rather than printed
    as if the comparison were complete (code review finding).
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")

    providers = _all_providers(files)
    if not providers:
        return [], 0, len(files)

    comparable = _providers_with_overlapping_recordings(files)
    if len(comparable) < _MINIMUM_PROVIDERS:
        raise SystemExit(
            f"only {len(comparable)} provider(s) have a real recorded response on a "
            f"shared sample ({sorted(comparable)}) -- PoC 2 requires comparing >= "
            f"{_MINIMUM_PROVIDERS} candidates on the same data (docs/poc-2-ai-grading.md "
            "section 2). Refusing to report a result that is not a same-data comparison; "
            "an empty/placeholder provider entry, or providers recorded only on disjoint "
            "samples, do not count. Record at least one more provider on a shared sample "
            "before re-running."
        )

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
                response, config_key, cost_usd, latency_seconds, is_pending = _load_cell(
                    cell, provider=provider, path=path
                )
                if is_pending:
                    pending += 1
                    continue
                assert config_key is not None  # only None when is_pending
                outcomes.append(
                    evaluate_sample(
                        truth,
                        response,
                        provider=provider,
                        config_key=config_key,
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
