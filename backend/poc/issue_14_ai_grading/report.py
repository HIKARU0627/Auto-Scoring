"""PoC 2 (issue #14) harness -- aggregate AI grading metrics from recorded
provider responses + human labels.

Usage::

    uv run python poc/issue_14_ai_grading/report.py [--dataset DIR] [--out FILE]

Every ``*.json`` under ``DIR`` is one graded question (see
``tests/fixtures/ai_grading/README.md`` for the shape)::

    {
      "subject": "...",
      "submissionId": "opaque id, no PII -- identifies the answer sheet, not the question",
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

``ground_truth`` follows the wire schema business-rules-and-evaluation-data.md
section 6.3 documents for a real human-grader label file (``questionId`` /
``score`` / ``maxScore`` / ``criteria[].{id,result}``, plus optional
``comment`` / ``annotations`` / ``handwritingQuality`` / ``layoutType`` /
``source``) so a real label file produced per that section can be used as-is
-- ``subject`` (which subject this question belongs to) is deliberately a
sibling of ``ground_truth``, not a field inside it, since section 6.3's
per-answer label schema has no such field (code review finding: a
``ground_truth`` model that instead invented its own field names and forbade
the documented ones rejected every correctly-formed real label file, making
the real-data harness impossible to run at all).

``submissionId`` is likewise a sibling field, required and non-blank: section
6.3 identifies each real answer sheet by a non-PII ``submissionId``, and one
real submission commonly spans several questions, each its own sample file
here. Without it, the harness cannot tell "30 distinct submissions" (section
6.2's minimum dataset size) apart from "30 questions on 6 submissions" --
``questionId`` alone identifies which question, not which answer sheet it
came from (code review finding). The aggregate report includes a distinct-
submission count per subject for exactly this coverage check.

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
path and error type code are kept. The field *path* itself can leak
untrusted content too: for an ``extra_forbidden`` error (an unrecognized
key on a strict model), pydantic's ``loc`` for that error is exactly the
offending key itself, copied verbatim from the untrusted mapping -- a
misplaced note accidentally left as a JSON key could carry real student
text straight into an otherwise "sanitized" message. Only the final ``loc``
segment of such an error is ever untrusted; it is replaced with a fixed
placeholder rather than echoed (code review finding). An unrecognized
``recorded`` input-variant key is rejected the same way, without echoing
the key itself (see below).

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

The dataset-wide overlap check above only gates whether the dataset has
*any* real comparison at all -- it does not mean every recorded cell for a
qualifying provider is safe to aggregate. A provider can overlap with
another on one sample while also carrying extra recorded responses on
samples nobody else ever answered; those extra cells are excluded from the
aggregate one sample-and-variant at a time (never pooled into that
provider's own metrics as if they were part of a same-data comparison),
and counted separately as "excluded" rather than silently dropped (code
review finding). With 3+ providers, ">= 2 responders" alone is not enough
either: if A and B answer sample X together, and B and C answer a
*different* sample Y together, both cells would pass an ">= 2" check even
though A and C were never run on the same data at all -- reporting all
three side by side would let a difference in sample difficulty masquerade
as a difference in provider quality (code review finding). A cell is only
counted when its responders are *exactly* the dataset-wide comparable set,
not merely some 2-of-N subset of it -- and that identity is keyed by
``(provider, config_key)``, not provider name alone: a provider that
switches configuration between samples (A/v1 grades X, then A/v2 grades Y,
while B/v1 grades both) must not have its X and Y cells treated as "the
same candidate" just because the provider name matches, since
``summarize_by_provider`` buckets them into two different config rows drawn
from two different sample pools either way (code review finding;
docs/poc-2-ai-grading.md section 3.3).

Every raw ``recorded`` provider key is normalized (whitespace-stripped)
before it is counted as a candidate: ``ProviderDescriptor`` only rejects an
entirely blank name, so ``"gemini"`` and ``"gemini "`` would otherwise count
as two separate candidates for the same real provider, letting a single
inconsistently-spelled key satisfy the >= 2 comparison gate on its own
(code review finding). Two different raw keys that normalize to the same
id are rejected outright, rather than silently merged, since either
resolution could hide a real inconsistency in the dataset.

A provider's ``recorded`` entry may only use the two recognized input-variant
keys (``ocr_clean`` / ``ocr_noisy``) -- an unrecognized key (a typo such as
``"ocr_nosiy"``) is rejected outright rather than silently ignored: neither
lookup used elsewhere in this module iterates arbitrary keys, so a response
recorded under a misspelled key would otherwise never be found, leaving its
cell "pending" forever while the harness still exits 0 as if the aggregate
were complete (code review finding). The unrecognized key itself is never
echoed in the raised message, for the same reason a validation error's
``loc`` is not (see above).

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


class _InvalidSubject(Exception):
    """A sample's top-level ``subject`` field is missing or blank.

    ``subject`` lives alongside ``ground_truth``/``input``/``recorded``, not
    inside ``ground_truth`` itself: business-rules-and-evaluation-data.md
    section 6.3's per-answer human-label schema has no ``subject`` field (it
    is test-level metadata, section 6.1), so :class:`GradingGroundTruth`
    cannot carry it without rejecting every correctly-formed real label file
    (code review finding). The harness still needs it to bucket the results
    table by 教科 (section 3.3), so it is read as a sibling field instead.
    """


class _InvalidSubmissionId(Exception):
    """A sample's top-level ``submissionId`` field is missing or blank.

    business-rules-and-evaluation-data.md section 6.3: one answer sheet is
    one JSON file, identified by a non-PII ``submissionId`` -- one real
    submission (a student's answered sheet) commonly spans several
    questions, each recorded as its own sample file here, so ``questionId``
    alone cannot tell "30 distinct submissions" (section 6.2's minimum
    dataset size) apart from "30 questions on 6 submissions". Without a
    validated, dataset-wide submission identity, the harness has no way to
    establish -- or even report -- real coverage against that minimum (code
    review finding). Not part of :class:`GradingGroundTruth` for the same
    reason ``subject`` is not (section 6.3's per-answer item list does not
    include it, so this model would otherwise be validating a fabricated
    field the documented schema itself never mentions): it is read as a
    sibling field, alongside ``subject``.
    """


class _InvalidRecordedVariant(Exception):
    """A provider's ``recorded`` entry has an input-variant key outside
    :data:`_INPUT_VARIANTS` (e.g. a typo like ``"ocr_nosiy"``).

    ``_load_cell``/``_providers_with_response_by_variant`` only ever look up
    the fixed ``ocr_clean``/``ocr_noisy`` keys by name -- a typo'd key is
    never matched by either lookup, so the recorded response under it would
    otherwise be silently ignored: the expected cell stays "pending" and the
    harness can exit 0 printing an incomplete aggregate, even though a real
    response for that (provider, variant) was actually recorded (AGENTS.md
    "Verification"; code review finding).
    """


#: Placeholder standing in for an ``extra_forbidden`` error's own ``loc``
#: segment (see ``_sanitize_validation_error``) -- never the real key.
_REDACTED_FIELD_LABEL = "<unexpected field>"


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

    The dotted field path itself is not always safe to echo verbatim
    either: for an ``extra_forbidden`` error (a model's ``extra="forbid"``
    rejecting an unrecognized key), pydantic's ``loc`` for that error is
    exactly the offending key itself, copied verbatim from the untrusted
    ``--dataset`` mapping -- e.g. a stray note accidentally left as a JSON
    key could carry real student text or a secret straight into this
    "sanitized" message (code review finding). Every other segment of
    ``loc`` leading up to it (a known schema field name, or a tuple/list
    index) is safe, since those come from this module's own model
    definitions, not from the untrusted input -- only the final segment of
    an ``extra_forbidden`` error's ``loc`` is replaced with a fixed
    placeholder.
    """
    parts = []
    for error in exc.errors():
        loc = list(error["loc"])
        if error["type"] == "extra_forbidden" and loc:
            loc[-1] = _REDACTED_FIELD_LABEL
        parts.append(f"{'.'.join(str(p) for p in loc)}: {error['type']}")
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
    """Validate one recorded ``cost_usd``/``latency_seconds`` value.

    Never embeds the raw recorded ``value`` in a raised message: it comes
    from the same untrusted ``--dataset`` file as everything else, and a
    malformed dataset could put a string containing real answer text there
    by mistake -- that text must not reach a raised exception, a chained
    traceback, or a log line any more than a ``ValidationError``'s raw input
    value may (AGENTS.md "Security"; code review finding; mirrors
    ``_sanitize_validation_error``). Only the field name and the offending
    value's type (never its content) are reported.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _InvalidMeasurement(
            f"{path}: provider {provider!r} has a non-numeric {field!r} "
            f"(got {type(value).__name__})"
        )
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise _InvalidMeasurement(
            f"{path}: provider {provider!r} has an invalid {field!r} (must be finite and >= 0)"
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


class _InvalidProviderId(Exception):
    """Two different raw ``recorded`` provider keys normalize to the same
    id (e.g. ``"gemini"`` and ``"gemini "``), or a key is blank once
    whitespace is stripped.

    ``ProviderDescriptor.__post_init__`` only rejects an entirely blank
    provider name -- it does not strip surrounding whitespace from an
    otherwise non-blank one, so ``"gemini"`` and ``"gemini "`` remain two
    distinct strings there and would count as two separate candidates for
    the >= 2 same-data comparison gate, when they can only ever mean the
    same real provider (docs/poc-2-ai-grading.md section 2 defines a fixed
    candidate identity). Silently merging them would just as silently hide
    an inconsistently-spelled key, so this is rejected outright instead
    (code review finding).
    """


def _normalized_provider_id(raw: str) -> str:
    """Normalize a ``recorded`` provider key for identity/counting purposes
    (leading/trailing whitespace stripped). See :class:`_InvalidProviderId`."""
    return raw.strip()


def _canonical_providers(samples: list[_ParsedSample]) -> dict[str, str]:
    """Map every normalized provider id seen anywhere in the dataset to the
    one raw ``recorded`` key it came from.

    Raises :class:`_InvalidProviderId` if a key is blank after stripping, or
    if two different raw keys normalize to the same id -- in either case,
    counting candidates before normalizing could accept a dataset where the
    same provider was recorded under two different spellings as if two
    distinct candidates had been compared.
    """
    raw_for_normalized: dict[str, str] = {}
    for sample in samples:
        for raw_key in sample.recorded:
            normalized = _normalized_provider_id(raw_key)
            if not normalized:
                raise _InvalidProviderId(
                    f"{sample.path}: a 'recorded' provider key is blank or whitespace-only"
                )
            existing = raw_for_normalized.get(normalized)
            if existing is not None and existing != raw_key:
                raise _InvalidProviderId(
                    f"{sample.path}: provider keys {existing!r} and {raw_key!r} both "
                    f"normalize to {normalized!r} -- this looks like an inconsistently "
                    "spelled duplicate of the same provider, not two distinct candidates"
                )
            raw_for_normalized[normalized] = raw_key
    return raw_for_normalized


#: One parsed ``(provider, input_variant)`` cell -- see ``_load_cell``.
_CellResult = tuple[GradingResponse | None, str | None, float | None, float | None, bool]


def _parse_cell_grid(
    samples: list[_ParsedSample], raw_for_normalized: dict[str, str]
) -> list[dict[str, dict[str, _CellResult]]]:
    """Parse every ``(sample, provider, input_variant)`` cell exactly once.

    Returns one dict per sample (same order as ``samples``), keyed by
    normalized provider id then input variant. Parsing every cell up front
    -- instead of once for a same-data-comparison identity check and again
    for scoring -- means both uses see the identical, already-validated
    ``config_key`` for a given cell: computing it twice from the same raw
    JSON would be redundant, and keeping two separate parses in sync would
    be an easy way to reintroduce the very drift this module guards against
    (code review finding).
    """
    grid: list[dict[str, dict[str, _CellResult]]] = []
    for sample in samples:
        cells_for_sample: dict[str, dict[str, _CellResult]] = {}
        for provider, raw_key in raw_for_normalized.items():
            cells_for_provider = sample.recorded.get(raw_key, {})
            cells_for_sample[provider] = {
                variant: _load_cell(
                    cells_for_provider.get(variant), provider=provider, path=sample.path
                )
                for variant in _INPUT_VARIANTS
            }
        grid.append(cells_for_sample)
    return grid


def _responder_configs_by_variant(
    cells_for_sample: dict[str, dict[str, _CellResult]],
) -> dict[str, set[tuple[str, str]]]:
    """``(provider, config_key)`` pairs with an actual (non-pending) response
    for one sample, split by input variant.

    Split by variant, not merged: a provider recorded only on ``ocr_clean``
    and another recorded only on ``ocr_noisy`` for the same sample have
    never actually been compared against each other -- ``ocr_clean`` and
    ``ocr_noisy`` are different evaluation modes (docs/poc-2-ai-grading.md
    section 2.1), so overlap must be checked within one variant at a time
    (code review finding).

    Keyed by ``(provider, config_key)``, not provider name alone: two
    recordings under the same provider name but a different configuration
    are different candidates for same-data-comparison purposes too, so a
    provider that quietly switches configuration between samples must not
    still "match" across those samples by name alone (code review finding;
    docs/poc-2-ai-grading.md section 3.3's config-bucket separation).
    """
    by_variant: dict[str, set[tuple[str, str]]] = {variant: set() for variant in _INPUT_VARIANTS}
    for provider, by_variant_cell in cells_for_sample.items():
        for variant, (
            _response,
            config_key,
            _cost,
            _latency,
            is_pending,
        ) in by_variant_cell.items():
            if not is_pending:
                assert config_key is not None
                by_variant[variant].add((provider, config_key))
    return by_variant


def _comparable_provider_configs(
    responders_by_sample: list[dict[str, set[tuple[str, str]]]],
) -> set[tuple[str, str]]:
    """``(provider, config_key)`` pairs that qualify as one side of a real,
    same-data comparison, used only to decide whether the dataset has *any*
    real comparison at all.

    A pair qualifies only if its sample+variant was also answered by >= 1
    *other distinct provider* there -- never just another configuration of
    the same provider against itself (docs/poc-2-ai-grading.md section 2
    requires comparing candidates, i.e. different providers). Two providers
    each recorded only on disjoint samples, or only under different
    variants of the same sample, are never compared on the same data, so
    neither counts (code review finding: `len(providers) >= 2` on raw dict
    keys passed even when the dataset had an empty placeholder entry, two
    providers that never appeared together on one question, or two
    providers recorded on the same question but under different input
    variants).

    This is a dataset-wide existence check only (the gate in
    :func:`_load_samples`) -- it does *not* mean every recorded cell for a
    qualifying pair is safe to aggregate: see the per-sample, per-variant
    check in :func:`_load_samples`'s own loop (code review finding: a
    provider that overlaps with another on one sample, but also has extra
    recorded responses on samples nobody else answered -- or answered under
    a different configuration -- must not have *those* extra responses
    pooled into its own aggregate metrics as if they too were part of a
    same-data comparison).
    """
    overlapping: set[tuple[str, str]] = set()
    for by_variant in responders_by_sample:
        for responders in by_variant.values():
            if len({provider for provider, _config_key in responders}) >= _MINIMUM_PROVIDERS:
                overlapping.update(responders)
    return overlapping


@dataclass(frozen=True, kw_only=True)
class _ParsedSample:
    """One sample's validated ``subject`` + ``submissionId`` + ``ground_truth``
    + ``input``, plus its raw ``recorded`` dict (still unparsed --
    ``_load_cell`` handles that per provider/variant cell)."""

    path: Path
    subject: str
    submission_id: str
    truth: GradingGroundTruth
    input_record: GradingInputRecord
    recorded: dict[str, dict[str, Any]]


def _load_subject(raw: dict[str, Any], *, path: Path) -> str:
    subject = raw.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise _InvalidSubject(
            f"{path}: sample has no non-blank top-level 'subject' field (needed to bucket "
            "this question's metrics by 教科, docs/poc-2-ai-grading.md section 3.3)"
        )
    return subject


def _load_submission_id(raw: dict[str, Any], *, path: Path) -> str:
    submission_id = raw.get("submissionId")
    if not isinstance(submission_id, str) or not submission_id.strip():
        raise _InvalidSubmissionId(
            f"{path}: sample has no non-blank top-level 'submissionId' field "
            "(business-rules-and-evaluation-data.md section 6.3: each real answer is "
            "identified by a non-PII submissionId) -- needed to tell distinct submissions "
            "(answer sheets) apart from distinct questions for the section 6.2 "
            "minimum-dataset-size check"
        )
    return submission_id


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


def _validate_recorded_variant_keys(recorded: dict[str, dict[str, Any]], *, path: Path) -> None:
    """Reject a provider's ``recorded`` entry with an input-variant key
    outside :data:`_INPUT_VARIANTS`, instead of silently ignoring it.

    ``_load_cell``/``_providers_with_response_by_variant`` only ever look up
    the fixed ``ocr_clean``/``ocr_noisy`` keys by name, never iterate
    whatever keys happen to be present -- so a typo'd key (e.g.
    ``"ocr_nosiy"`` instead of ``"ocr_noisy"``) is never matched by either
    lookup. Without this check, a real recorded response under that key
    would simply never be found: the expected cell stays "pending" forever,
    and the harness can exit 0 printing an incomplete aggregate as if the
    dataset had been fully reported (code review finding).
    """
    for provider, variants in recorded.items():
        if not isinstance(variants, dict):
            raise _InvalidRecordedVariant(
                f"{path}: provider {provider!r}'s recorded entry must be an object "
                f"keyed by input variant ({_INPUT_VARIANTS}), got {type(variants).__name__}"
            )
        unknown = sorted(set(variants) - set(_INPUT_VARIANTS))
        if unknown:
            # Never echo the unknown key(s) themselves: they are untrusted
            # ``--dataset`` content the same as any other key or value, and
            # a malformed real dataset could put student text or a secret in
            # a mistyped key (AGENTS.md "Security"; code review finding).
            raise _InvalidRecordedVariant(
                f"{path}: provider {provider!r} has {len(unknown)} recorded response(s) "
                f"under {len(unknown)} unrecognized input-variant key(s) -- only "
                f"{_INPUT_VARIANTS} are recognized (this looks like a typo; a response "
                "recorded there would otherwise be silently ignored rather than counted). "
                "The unrecognized key(s) are not shown here."
            )


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
        _validate_recorded_variant_keys(raw.get("recorded", {}), path=path)
        subject = _load_subject(raw, path=path)
        submission_id = _load_submission_id(raw, path=path)
        truth = _load_ground_truth(raw, path=path)
        input_record = _load_input_record(raw, truth=truth, path=path)
        parsed.append(
            _ParsedSample(
                path=path,
                subject=subject,
                submission_id=submission_id,
                truth=truth,
                input_record=input_record,
                recorded=raw.get("recorded", {}),
            )
        )
    return parsed


def _submission_coverage(samples: list[_ParsedSample]) -> dict[str, int]:
    """Distinct ``submissionId`` count per ``subject``, for the section 6.2
    minimum-dataset-size check ("各教科 30 答案以上").

    Computed from every validated sample regardless of whether any provider
    has recorded a response yet: a project owner staging real ground truth
    ahead of credentials still needs to see real submission coverage, not
    just a question/file count that could overstate it (one submission
    commonly spans several questions, each its own sample file here).
    """
    submissions_by_subject: dict[str, set[str]] = {}
    for sample in samples:
        submissions_by_subject.setdefault(sample.subject, set()).add(sample.submission_id)
    return {subject: len(ids) for subject, ids in submissions_by_subject.items()}


def _load_samples(
    dataset: Path,
) -> tuple[list[SampleOutcome], int, int, int, dict[str, int]]:
    """Return ``(evaluated outcomes, pending-cell count, files with no
    provider recorded anywhere in the dataset, excluded-cell count,
    distinct-submission count per subject)`` from every ``*.json``.

    The third count covers a real-data pilot staged ahead of any
    ``AIProvider`` call (ground truth transcribed, ``recorded`` left ``{}``
    dataset-wide) -- distinct from "pending" cells, which are expected
    (some other sample recorded that provider) but missing for this one.

    The fourth count ("excluded") covers a real recorded response whose
    *own* ``(sample, input_variant)`` was not answered by *exactly* the full
    set of ``(provider, config_key)`` pairs found comparable dataset-wide
    (see :func:`_comparable_provider_configs`). Requiring an exact match,
    keyed by configuration and not just provider name, matters in two ways:
    with 3+ providers, if A and B both answer sample X, and B and C both
    answer a *different* sample Y, a plain ">= 2 providers" check alone
    would accept both cells and report A, B, and C side by side as if they
    had been compared together -- but A and C were never run on the same
    data at all. And if a single provider switches configuration between
    samples (A/v1 grades X, then A/v2 grades Y, while B/v1 grades both), a
    check keyed on provider name alone would still treat A's cells on X and
    Y as "the same candidate", even though ``summarize_by_provider`` buckets
    them into two different config rows drawing from different sample
    pools. Either way, sample-difficulty differences could masquerade as a
    provider- or configuration-quality difference (code review finding;
    docs/poc-2-ai-grading.md section 2's same-data requirement, section
    3.3's config-bucket separation). A cell failing this check is never
    added to ``outcomes``: pooling it into its own aggregate metrics would
    silently blend a compared sample with an uncompared one. It is still
    counted (never silently dropped), same as ``pending``/``staged``.

    Raises unless at least :data:`_MINIMUM_PROVIDERS` distinct providers
    each have a real recorded response on a *shared sample and input
    variant* (see :func:`_comparable_provider_configs`): the PoC requires
    comparing candidates on the same data, so a dataset where only one
    provider (or several, but never together on one question and variant)
    has actually been run is refused outright rather than printed as if the
    comparison were complete (code review finding).
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")

    samples = _load_all_samples(files)
    submission_coverage = _submission_coverage(samples)

    raw_for_normalized = _canonical_providers(samples)
    if not raw_for_normalized:
        return [], 0, len(files), 0, submission_coverage

    cell_grid = _parse_cell_grid(samples, raw_for_normalized)
    pending = sum(
        1
        for cells_for_sample in cell_grid
        for by_variant_cell in cells_for_sample.values()
        for _response, _config_key, _cost_usd, _latency_seconds, is_pending in (
            by_variant_cell.values()
        )
        if is_pending
    )

    responders_by_sample = [_responder_configs_by_variant(cells) for cells in cell_grid]
    comparable = _comparable_provider_configs(responders_by_sample)
    comparable_providers = {provider for provider, _config_key in comparable}
    if len(comparable_providers) < _MINIMUM_PROVIDERS:
        raise SystemExit(
            f"only {len(comparable_providers)} provider(s) have a real recorded response "
            f"on a shared sample, input variant, and configuration "
            f"({sorted(comparable_providers)}) -- PoC 2 requires comparing >= "
            f"{_MINIMUM_PROVIDERS} candidates on the same data (docs/poc-2-ai-grading.md "
            "section 2). Refusing to report a result that is not a same-data comparison; "
            "an empty/placeholder provider entry, providers recorded only on disjoint "
            "samples, providers recorded under different input variants of the same "
            "sample, or a provider that switched configuration between samples, do not "
            "count. Record at least one more provider on a shared sample, variant, and "
            "configuration before re-running."
        )

    outcomes: list[SampleOutcome] = []
    excluded = 0
    for sample, cells_for_sample, by_variant in zip(
        samples, cell_grid, responders_by_sample, strict=True
    ):
        for provider in sorted(cells_for_sample):
            by_variant_cell = cells_for_sample[provider]
            for variant, (
                response,
                config_key,
                cost_usd,
                latency_seconds,
                is_pending,
            ) in by_variant_cell.items():
                if is_pending:
                    continue
                assert config_key is not None  # only None when is_pending
                if by_variant[variant] != comparable:
                    excluded += 1
                    continue
                outcomes.append(
                    evaluate_sample(
                        sample.truth,
                        response,
                        subject=sample.subject,
                        provider=provider,
                        config_key=config_key,
                        input_variant=variant,
                        cost_usd=cost_usd,
                        latency_seconds=latency_seconds,
                    )
                )
    return outcomes, pending, 0, excluded, submission_coverage


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # keep the JP table readable on Windows

    parser = argparse.ArgumentParser(description="PoC 2 AI grading metric aggregator")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    outcomes, pending, staged, excluded, submission_coverage = _load_samples(args.dataset)
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
    if excluded:
        notes += (
            f"\nexcluded (a real response was recorded, but its sample+input-variant+config "
            f"has no matching cohort of comparable candidates there, so it is not a "
            f"same-data comparison and is never pooled into that candidate's own metrics): "
            f"{excluded}\n"
        )
    if submission_coverage:
        coverage_lines = "\n".join(
            f"  {subject}: {count}" for subject, count in sorted(submission_coverage.items())
        )
        notes += (
            f"\ndistinct submissions (answers, by submissionId) per subject -- decision "
            f"record section 6.2 requires >= 30 per subject:\n{coverage_lines}\n"
        )
    report = f"# PoC 2 AI grading aggregate\n\nevaluated cells: {len(outcomes)}\n{notes}\n{table}\n"

    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
