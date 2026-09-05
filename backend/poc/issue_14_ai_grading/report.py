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

Every sample's ``ground_truth`` and ``input`` are parsed and validated --
including a real-data pilot sample whose ``recorded`` is entirely ``{}``
(credentials not yet configured) -- *before* the harness decides whether the
dataset has anything to report. A dataset made of nothing but malformed or
inconsistent staged samples must not exit 0 as if it were valid, uninspected
evidence (code review finding).

Validation-error messages never embed the value that failed validation: a
malformed ``input.ocr_clean``/``ocr_noisy`` field is real (if manually
transcribed) student answer text, and pydantic's default
``str(ValidationError)`` embeds each failing field's raw value. That value
must never reach a raised exception, a chained traceback, a log line, or a
CI console (AGENTS.md "Security"; code review finding) -- only the field
path and error type code are kept.

The expected comparison matrix is every provider seen anywhere in the dataset
times both input variants (``ocr_clean`` / ``ocr_noisy``) -- not just the
cells a given sample happens to define. A cell missing from that matrix (no
``recorded[provider][variant]`` entry at all, or one with no ``response`` key)
is "pending", never silently skipped. The PoC requires comparing at least 2
candidates *on the same data, on the same input variant* (docs/poc-2-ai-grading.md
section 2): an empty or all-pending ``recorded`` entry does not count as a
candidate, and neither does a pair of providers recorded only on disjoint
samples, or recorded on the same sample but under different variants
(provider A only on ``ocr_clean``, provider B only on ``ocr_noisy``) -- ``clean``
and ``noisy`` are different evaluation modes (section 2.1), so that is still
not a comparison. A recorded ``ocr_noisy`` response for a sample whose
``input.ocr_noisy`` is ``null`` (no noisy-OCR variant was ever authored) is
rejected the same way: it cannot be a real same-data comparison either. All
of these are refused outright rather than printed as if the comparison were
complete (code review finding).

A cell whose raw JSON fails
:func:`auto_scoring.domain.ai_grading.parse_ai_grading_result` is a schema
violation and is scored as such -- never as a free-text-parsed guess
(Issue #14 acceptance). A cell's ``descriptor`` (model / version / prompt
version / temperature / structured-output mode) is parsed and strictly
validated by :func:`auto_scoring.domain.ai_provider.parse_provider_descriptor`
-- never coerced (code review finding: a naive ``str()``/``float()`` cast
would turn ``model: null`` into the literal string ``"None"``, or
``temperature: true`` into ``1.0``) -- and is required on every non-pending
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_grading_metrics import (
    GradingGroundTruth,
    GradingInputRecord,
    SampleOutcome,
    evaluate_sample,
    summarize_by_provider,
    to_markdown_table,
    validate_input_matches_truth,
)
from auto_scoring.domain.ai_provider import (
    GradingResponse,
    ProviderDescriptor,
    descriptor_key,
    grading_response_from_result,
    parse_provider_descriptor,
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


class _InvalidGroundTruth(Exception):
    """A recorded sample's ``ground_truth`` block fails strict validation."""


class _InvalidDescriptor(Exception):
    """A recorded cell's ``descriptor`` is missing or fails strict validation."""


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


class _InvalidInput(Exception):
    """A recorded sample's ``input`` block is missing, malformed, disagrees
    with its ``ground_truth``, or has a recorded ``ocr_noisy`` response with
    no corresponding noisy-OCR input (code review finding)."""


def _sanitize_validation_error(exc: ValidationError) -> str:
    """Summarize a ``pydantic.ValidationError`` without the value that failed.

    ``str(exc)`` (and so any f-string embedding it, or any default traceback
    printed for a chained exception) includes each error's raw
    ``input_value`` -- for ``GradingInputRecord`` that can be real, manually
    transcribed student answer text (``ocr_clean`` / ``ocr_noisy``). That
    text must never reach a raised message, a log, or a terminal/CI
    traceback (AGENTS.md "Security"; code review finding). Only the
    dotted field path and pydantic's error type code are kept -- never
    ``error["input"]``.
    """
    parts = [f"{'.'.join(str(p) for p in error['loc'])}: {error['type']}" for error in exc.errors()]
    return "; ".join(parts) if parts else "validation failed"


def _descriptor_from_cell(cell: dict[str, Any], *, provider: str, path: Path) -> ProviderDescriptor:
    raw = cell.get("descriptor")
    if raw is None:
        raise _InvalidDescriptor(
            f"{path}: provider {provider!r} has a recorded response but no 'descriptor' "
            "(model/version/prompt_version/temperature/structured_output_mode) -- cannot "
            "be reproduced or safely bucketed (Issue #14 '再現条件'). Add a descriptor "
            "object to this cell."
        )
    try:
        return parse_provider_descriptor(json.dumps(raw), provider=provider)
    except ValidationError as exc:
        raise _InvalidDescriptor(
            f"{path}: provider {provider!r} has an invalid 'descriptor' "
            f"({_sanitize_validation_error(exc)})"
        ) from None


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
    other provider ever touched (or under a different input variant), is a
    key here but must not count as a second candidate being compared
    (code review finding).
    """
    providers: set[str] = set()
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        providers.update(raw.get("recorded", {}).keys())
    return providers


def _providers_with_response_by_variant(raw: dict[str, Any]) -> dict[str, set[str]]:
    """Providers that have an actual (non-pending) ``response`` recorded in
    this one file, split by input variant.

    Split by variant, not merged: a provider recorded only on ``ocr_clean``
    and another recorded only on ``ocr_noisy`` for the same sample have
    never actually been compared against each other -- ``ocr_clean`` and
    ``ocr_noisy`` are different evaluation modes (docs/poc-2-ai-grading.md
    section 2.1), so overlap must be checked within one variant at a time
    (code review finding).
    """
    by_variant: dict[str, set[str]] = {variant: set() for variant in _INPUT_VARIANTS}
    for provider, variants in raw.get("recorded", {}).items():
        for variant in _INPUT_VARIANTS:
            cell = variants.get(variant)
            if isinstance(cell, dict) and "response" in cell:
                by_variant[variant].add(provider)
    return by_variant


def _providers_with_overlapping_recordings(files: list[Path]) -> set[str]:
    """Providers that qualify as one side of a real, same-data comparison.

    A provider qualifies only if it has recorded an actual response (not
    just an empty or all-pending ``recorded`` entry) *and* shares at least
    one sample *and input variant* with another such provider -- i.e. there
    is at least one (question, variant) pair both providers were actually
    run against. Two providers each recorded only on disjoint samples, or
    only under different variants of the same sample, are never compared on
    the same data, so neither counts (code review finding: `len(providers)
    >= 2` on raw dict keys passed even when the dataset had an empty
    placeholder entry, two providers that never appeared together on one
    question, or two providers recorded on the same question but under
    different input variants).
    """
    overlapping: set[str] = set()
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        by_variant = _providers_with_response_by_variant(raw)
        for providers_in_variant in by_variant.values():
            if len(providers_in_variant) >= _MINIMUM_PROVIDERS:
                overlapping.update(providers_in_variant)
    return overlapping


@dataclass(frozen=True, kw_only=True)
class _ParsedSample:
    """One sample's validated ``ground_truth`` + ``input``, plus its raw
    ``recorded`` dict (still unparsed -- ``_load_cell`` handles that per
    provider/variant cell)."""

    path: Path
    truth: GradingGroundTruth
    input_record: GradingInputRecord
    recorded: dict[str, dict[str, Any]]


def _load_ground_truth(raw: dict[str, Any], *, path: Path) -> GradingGroundTruth:
    try:
        return GradingGroundTruth.from_mapping(raw["ground_truth"])
    except ValidationError as exc:
        raise _InvalidGroundTruth(
            f"{path}: invalid 'ground_truth' block ({_sanitize_validation_error(exc)})"
        ) from None


def _load_input_record(
    raw: dict[str, Any], *, truth: GradingGroundTruth, path: Path
) -> GradingInputRecord:
    """Parse this sample's ``input`` block and cross-check it against ``truth``.

    Raises :class:`_InvalidInput` if ``input`` is missing, fails strict
    validation, disagrees with ``ground_truth`` (e.g. a different
    ``max_score``), or if any provider has a recorded ``ocr_noisy`` response
    while this sample's ``input.ocr_noisy`` is ``null``: a same-data
    comparison requires the underlying question material -- including which
    OCR variants actually exist -- to match, not just the final score
    (code review finding).
    """
    if "input" not in raw:
        raise _InvalidInput(f"{path}: sample has no 'input' block to validate against")
    try:
        input_record = GradingInputRecord.from_mapping(raw["input"])
    except ValidationError as exc:
        raise _InvalidInput(
            f"{path}: invalid 'input' block ({_sanitize_validation_error(exc)})"
        ) from None
    try:
        validate_input_matches_truth(input_record, truth)
    except ValueError as exc:
        raise _InvalidInput(f"{path}: {exc}") from None

    if input_record.ocr_noisy is None:
        for provider, variants in raw.get("recorded", {}).items():
            cell = variants.get("ocr_noisy")
            if isinstance(cell, dict) and "response" in cell:
                raise _InvalidInput(
                    f"{path}: provider {provider!r} has a recorded 'ocr_noisy' response, "
                    "but this sample's input.ocr_noisy is null -- no noisy-OCR variant was "
                    "authored for this sample, so a recorded noisy-variant response cannot "
                    "be a real same-data comparison"
                )
    return input_record


def _load_all_samples(files: list[Path]) -> list[_ParsedSample]:
    """Parse and validate every file's ``ground_truth`` and ``input`` block.

    Called before the harness decides whether the dataset has anything to
    report (including the "every ``recorded`` is ``{}``" staged-pilot case):
    a dataset made of nothing but malformed or inconsistent samples must not
    exit 0 as if it were valid, uninspected evidence (code review finding).
    """
    parsed: list[_ParsedSample] = []
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        truth = _load_ground_truth(raw, path=path)
        input_record = _load_input_record(raw, truth=truth, path=path)
        parsed.append(
            _ParsedSample(
                path=path,
                truth=truth,
                input_record=input_record,
                recorded=raw.get("recorded", {}),
            )
        )
    return parsed


def _load_samples(dataset: Path) -> tuple[list[SampleOutcome], int, int]:
    """Return ``(evaluated outcomes, pending-cell count, files with no
    provider recorded anywhere in the dataset)`` from every ``*.json``.

    The third count covers a real-data pilot staged ahead of any
    ``AIProvider`` call (ground truth transcribed, ``recorded`` left ``{}``
    dataset-wide) -- distinct from "pending" cells, which are expected
    (some other sample recorded that provider) but missing for this one.

    Raises unless at least :data:`_MINIMUM_PROVIDERS` providers each have a
    real recorded response on a *shared sample and input variant* (see
    :func:`_providers_with_overlapping_recordings`): the PoC requires
    comparing candidates on the same data, so a dataset where only one
    provider (or several, but never together on one question and variant)
    has actually been run is refused outright rather than printed as if the
    comparison were complete (code review finding).
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")

    samples = _load_all_samples(files)

    providers = _all_providers(files)
    if not providers:
        return [], 0, len(files)

    comparable = _providers_with_overlapping_recordings(files)
    if len(comparable) < _MINIMUM_PROVIDERS:
        raise SystemExit(
            f"only {len(comparable)} provider(s) have a real recorded response on a "
            f"shared sample and input variant ({sorted(comparable)}) -- PoC 2 requires "
            f"comparing >= {_MINIMUM_PROVIDERS} candidates on the same data "
            "(docs/poc-2-ai-grading.md section 2). Refusing to report a result that is "
            "not a same-data comparison; an empty/placeholder provider entry, providers "
            "recorded only on disjoint samples, or providers recorded under different "
            "input variants of the same sample, do not count. Record at least one more "
            "provider on a shared sample and variant before re-running."
        )

    outcomes: list[SampleOutcome] = []
    pending = 0
    for sample in samples:
        for provider in sorted(providers):
            cells_for_provider = sample.recorded.get(provider, {})
            for variant in _INPUT_VARIANTS:
                cell = cells_for_provider.get(variant)
                response, config_key, cost_usd, latency_seconds, is_pending = _load_cell(
                    cell, provider=provider, path=sample.path
                )
                if is_pending:
                    pending += 1
                    continue
                assert config_key is not None  # only None when is_pending
                outcomes.append(
                    evaluate_sample(
                        sample.truth,
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
