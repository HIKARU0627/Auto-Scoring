"""PoC 2 (issue #14) harness -- aggregate AI grading metrics from recorded
provider responses + human labels.

Usage::

    uv run python poc/issue_14_ai_grading/report.py [--dataset DIR] [--out FILE]

Every ``*.json`` under ``DIR`` is one real answer sheet ("1 答案 = 1 JSON
ファイル", business-rules-and-evaluation-data.md section 6.3) -- one
``submissionId`` commonly answers several questions (section 6.2's "60 答案
・のべ 300 設問以上"), so one file holds a non-empty ``questions`` array, one
entry per graded question (see ``tests/fixtures/ai_grading/README.md`` for
the shape)::

    {
      "subject": "...",
      "submissionId": "opaque id, no PII -- identifies the answer sheet",
      "testId": "opaque id -- identifies which test this submission belongs to",
      "questions": [
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
      ]
    }

An earlier version of this loader read exactly one ``ground_truth``/``input``
per file, which could only represent "1 answer sheet = 1 question" -- an
undocumented split from the decision record's actual file format, and one
that could never consume the required 60 submissions / 300+ questions
without silently multiplying files per real answer sheet (code review
finding; AGENTS.md "Source of truth"). Each ``questions[]`` entry is
validated exactly as a single-question file previously was.

``ground_truth`` follows the wire schema business-rules-and-evaluation-data.md
section 6.3 documents for a real human-grader label file (``questionId`` /
``score`` / ``maxScore`` / ``criteria[].{id,result}``, plus optional
``comment`` / ``annotations`` / ``handwritingQuality`` / ``layoutType`` /
``source``) so a real label file produced per that section can be used as-is
-- ``subject`` (which subject this submission belongs to) is deliberately a
sibling of ``questions``, not a field inside each ``ground_truth``, since
section 6.3's per-question item list has no such field (code review finding:
a ``ground_truth`` model that instead invented its own field names and
forbade the documented ones rejected every correctly-formed real label file,
making the real-data harness impossible to run at all).

``submissionId`` is likewise a required, non-blank, whitespace-normalized
sibling field: section 6.3 identifies each real answer sheet by a non-PII
``submissionId``, and the harness needs it to tell "30 distinct submissions"
(section 6.2's minimum dataset size) apart from "30 questions on 6
submissions" -- ``questionId`` alone identifies which question, not which
answer sheet it came from (code review finding). It is stripped of
surrounding whitespace before being counted, the same as a provider id (see
below): ``"sub-1"`` and ``" sub-1 "`` can only mean the same submission, and
counting them as two would overstate coverage against the 30-per-subject
minimum (code review finding). The aggregate report includes a
distinct-submission count per subject for exactly this coverage check.

``testId`` is likewise a required, non-blank, whitespace-normalized sibling
field (business-rules-and-evaluation-data.md section 6.1 metadata: テストID
alongside 教科). This PoC's evaluation design is exactly one test per
subject (section 6.2: "2 教科 x 各 1 テスト"), and the results table buckets
only by (subject, provider, config, input_variant) -- not by ``testId`` --
so a dataset that accidentally mixes two different tests' submissions under
the same subject label would otherwise be silently pooled into one
same-data comparison bucket, even though the two tests' rubric or
difficulty may differ. The harness rejects a dataset where one subject
spans more than one distinct ``testId`` (code review finding).

Within one submission, every ``questions[]`` entry must have a distinct
``ground_truth.questionId`` -- a duplicate (e.g. a copy-paste mistake) would
otherwise be parsed as two independent samples and double-count that
question's weight in every aggregate (code review finding). Across the
whole dataset, no two files may reuse the same normalized
``(subject, submissionId)`` pair either: one answer sheet is one JSON file
(section 6.3), so two files claiming the same submission would have every
one of both files' questions parsed and pooled into every provider's
metrics as if they were independent answers, while the distinct-submission
coverage count still counts that id only once (code review finding).
``subject`` (like ``submissionId``/``testId``) is stripped of surrounding
whitespace before this and every other check runs, so ``"history"`` and
``" history "`` are treated as the one subject they can only mean, rather
than silently splitting one subject's coverage and metrics into two
buckets (code review finding).

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
placeholder rather than echoed (code review finding). That rule now lives in
``domain.ai_grading.describe_schema_violation``, shared with the live
``AIProvider`` adapters, which needed the same summary for the same reason
(Issue #121). An unrecognized ``recorded`` input-variant key is rejected the
same way, without echoing the key itself (see below).

``input.answer_image_ref`` is required and non-blank: every grading call is
supposed to receive the cropped answer-region image alongside the OCR text
(docs/poc-2-ai-grading.md section 2.1), and a recorded sample with no
reference to *which* image was used cannot show whether every candidate was
actually run against the same crop -- a candidate silently graded against a
stale or different crop would still look like a valid same-data comparison
(code review finding). This is a content hash (``"sha256:<hex>"``) or an
external, out-of-repo reference, never the image bytes themselves
(business-rules-and-evaluation-data.md section 6.7).

The expected comparison matrix is every provider seen anywhere in the dataset
times both input variants (``ocr_clean`` / ``ocr_noisy``) -- not just the
cells a given sample happens to define. A cell missing from that matrix (no
``recorded[provider][variant]`` entry at all, or one with no ``response`` key
and no ``unavailable`` marker) is "pending", never silently skipped. The PoC
requires comparing at least 2 candidates *on the same data, on the same
input variant* (docs/poc-2-ai-grading.md section 2): an empty or all-pending
``recorded`` entry does not count as a candidate, and neither does a pair of
providers recorded only on disjoint samples, or recorded on the same sample
but under different variants (provider A only on ``ocr_clean``, provider B
only on ``ocr_noisy``) -- ``clean`` and ``noisy`` are different evaluation
modes (section 2.1), so that is still not a comparison. A recorded
``ocr_noisy`` response for a sample whose ``input.ocr_noisy`` is ``null`` (no
noisy-OCR variant was ever authored) is rejected the same way: it cannot be
a real same-data comparison either. All of these are refused outright rather
than printed as if the comparison were complete (code review finding).

A cell may instead record ``{"unavailable": true, "descriptor": {...},
"latency_seconds": ..., "cost_usd": ...}`` (no ``response``) for a call
attempt that exhausted retries against a persistent failure
(docs/poc-2-ai-grading.md section 7.2: "恒常的な 429 / quota 超過は失敗と
して記録し、推測で埋めない"). This is counted separately from "pending": a
call that was attempted and failed is not the same as one nobody has tried
yet, and folding the two together would silently drop a
persistently-unreliable provider's failures from the report, making it look
better than it is (code review finding). Unlike a truly pending cell, an
"unavailable" one requires a ``descriptor`` (the same as a real response),
so its ``latency_seconds``/``cost_usd`` are still attributed to, and
aggregated under, the ``(provider, config_key)`` bucket that was attempted
-- an earlier version discarded these measurements entirely, letting a
provider with frequent long-timeout failures look faster and cheaper than
it really is (code review finding).

Every recorded cell's own shape is validated up front too: an unrecognized
field (a typo such as ``"respnose"`` instead of ``"response"``), a
non-boolean ``"unavailable"`` marker (e.g. the string ``"true"``), a
non-object cell value, a cell recording both ``response`` and
``unavailable: true`` at once, or a cell recording ``descriptor``/
``latency_seconds``/``cost_usd`` (evidence a call was attempted) while
omitting both ``response`` and ``unavailable: true`` are all rejected
outright, rather than silently misclassified as an ordinary pending cell
and reported as if the dataset were complete (code review finding;
AGENTS.md trust-boundary validation).

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
resolution could hide a real inconsistency in the dataset. For any
``--dataset`` other than the bundled synthetic fixtures, the normalized id
must also be one of the canonical candidate ids docs/poc-2-ai-grading.md
section 2 defines (``gemini`` / ``codex-app-server`` / ``openrouter`` /
    ``openai``, case-sensitive):
whitespace normalization alone does not catch a case difference, so
``"gemini"`` and ``"Gemini"`` would otherwise still count as two separate
candidates for the same real service (code review finding). The bundled
fixtures are an explicit exception, since they intentionally use placeholder
names (``synthetic-a`` / ``synthetic-b``) that are not real vendor ids. A
raw provider key -- whether it collides after normalization or fails the
canonical-id check -- is never echoed in the raised message: it is a
``recorded`` JSON *key*, the same untrusted ``--dataset`` content as any
other key or value, and a malformed real dataset could have a secret or
real student text there by mistake (AGENTS.md "Security"; code review
finding). Only the offending count and the allowed canonical ids are
reported.

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
``temperature: true`` into ``1.0``) -- and is required on every non-pending,
non-``unavailable`` cell (even one that turns out to be a schema violation):
two cells for the same ``provider`` name recorded under different settings
-- including a prompt template edit alone -- are aggregated as separate
buckets, keyed on :func:`auto_scoring.domain.ai_provider.descriptor_key`,
never pooled (Issue #14 "再現条件"). ``cost_usd`` / ``latency_seconds`` are
validated as finite, non-negative numbers before they reach any aggregate
(code review finding): a negative, non-finite, or non-numeric recorded value
raises rather than silently skewing the adoption-gate metrics.

Only counts and averaged scores are printed. Provider response bodies (and
any real answer text they might embed) are read only long enough to compute
these aggregates, and are never logged.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from auto_scoring.domain.ai_grading import describe_schema_violation, parse_ai_grading_result
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
    SchemaViolation,
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

#: The exact candidate ids docs/poc-2-ai-grading.md section 2 defines: the
#: four links of the fallback chain the project owner adopted in Issue #81
#: (business-rules-and-evaluation-data.md section 3 (B)), each spelled the
#: way its adapter's ``AIProvider.name`` spells it -- ``gemini``
#: (``adapters.ai_grading.vertex_gemini_provider``), ``codex-app-server``,
#: ``openrouter``, ``openai``. Real (non-bundled-fixture) ``--dataset`` runs
#: must use exactly these, case sensitively -- see
#: :func:`_validate_canonical_provider_ids`.
#:
#: The earlier set (``gemini``/``claude``/``gpt``) named three *vendors*
#: rather than three call paths, and two of those ids could never be
#: produced by any adapter this repository has: a live recording made
#: through ``record.py`` keys each cell by the descriptor of the adapter
#: that answered, so a dataset recorded by the OpenRouter adapter would
#: have been rejected outright while a hand-written ``claude`` cell (which
#: nothing can reproduce) passed.
_CANONICAL_PROVIDER_IDS = frozenset({"gemini", "codex-app-server", "openrouter", "openai"})


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
    """A submission's top-level ``subject`` field is missing or blank.

    ``subject`` lives alongside ``questions``, not inside each
    ``ground_truth``: business-rules-and-evaluation-data.md section 6.3's
    per-question label schema has no ``subject`` field (it is test-level
    metadata, section 6.1), so :class:`GradingGroundTruth` cannot carry it
    without rejecting every correctly-formed real label file (code review
    finding). The harness still needs it to bucket the results table by
    教科 (section 3.3), so it is read as a sibling field instead.
    """


class _InvalidSubmissionId(Exception):
    """A submission's top-level ``submissionId`` field is missing or blank,
    or the same normalized ``(subject, submissionId)`` pair is reused by
    more than one file.

    business-rules-and-evaluation-data.md section 6.3: one answer sheet is
    one JSON file, identified by a non-PII ``submissionId``. Without a
    validated, dataset-wide submission identity, the harness has no way to
    establish -- or even report -- real coverage against the section 6.2
    minimum (30 distinct submissions per subject) (code review finding). Not
    part of :class:`GradingGroundTruth` for the same reason ``subject`` is
    not: it is read as a sibling field, alongside ``subject``.

    Two files that reuse the same ``(subject, submissionId)`` would have
    every one of both files' questions parsed and pooled into every
    provider's metrics as if they were separate, independent answers, while
    :func:`_submission_coverage` still counts that id only once -- a real
    duplicated answer sheet would silently double a submission's weight in
    every aggregate without inflating the coverage count that is supposed
    to reflect it (code review finding).
    """


class _InvalidSubmission(Exception):
    """A submission file's top-level ``questions`` field is missing, not a
    list, empty, contains a non-object entry, or contains two entries with
    the same ``ground_truth.questionId``.

    One real answer sheet commonly spans several questions
    (business-rules-and-evaluation-data.md section 6.2: "60 答案・のべ 300
    設問以上"), so one submission file must hold a non-empty list of
    per-question ``ground_truth``/``input``/``recorded`` entries, not just
    one (code review finding). A duplicate ``questionId`` within that list
    (a copy-paste mistake) would otherwise be parsed as two independent
    samples and double-count that question's weight in every aggregate
    (code review finding).
    """


class _InvalidTestId(Exception):
    """A submission's top-level ``testId`` field is missing or blank, or one
    ``subject`` spans more than one distinct ``testId`` across the dataset.

    business-rules-and-evaluation-data.md section 6.1 lists テストID as
    per-test metadata alongside 教科 (subject), and this PoC's evaluation
    design is exactly one test per subject (section 6.2: "2 教科 x 各 1
    テスト"). ``summarize_by_provider`` buckets only by (subject, provider,
    config, input_variant) -- not by ``testId`` -- so two different tests
    accidentally recorded under the same subject label would be silently
    pooled into one same-data comparison bucket even though their rubric or
    difficulty may differ (code review finding).
    """


class _InvalidRecordedVariant(Exception):
    """A provider's ``recorded`` entry has an input-variant key outside
    :data:`_INPUT_VARIANTS` (e.g. a typo like ``"ocr_nosiy"``).

    ``_load_cell``/``_responder_configs_by_variant`` only ever look up the
    fixed ``ocr_clean``/``ocr_noisy`` keys by name -- a typo'd key is never
    matched by either lookup, so the recorded response under it would
    otherwise be silently ignored: the expected cell stays "pending" and the
    harness can exit 0 printing an incomplete aggregate, even though a real
    response for that (provider, variant) was actually recorded (AGENTS.md
    "Verification"; code review finding).
    """


class _InvalidProviderId(Exception):
    """Two different raw ``recorded`` provider keys normalize to the same
    id (e.g. ``"gemini"`` and ``"gemini "``), a key is blank once whitespace
    is stripped, or (for a real, non-bundled-fixture ``--dataset``) a
    normalized id is not one of the canonical candidate ids
    docs/poc-2-ai-grading.md section 2 defines.

    ``ProviderDescriptor.__post_init__`` only rejects an entirely blank
    provider name -- it does not strip surrounding whitespace from an
    otherwise non-blank one, so ``"gemini"`` and ``"gemini "`` remain two
    distinct strings there and would count as two separate candidates for
    the >= 2 same-data comparison gate, when they can only ever mean the
    same real provider. Whitespace normalization alone still does not catch
    a case difference (``"gemini"`` vs ``"Gemini"``), which is why real runs
    are further checked against the fixed candidate id set (code review
    finding). Silently merging an inconsistent key would just as silently
    hide it, so all of these are rejected outright instead.
    """


class _InvalidRecordedCell(Exception):
    """A recorded ``(provider, input_variant)`` cell has an internally
    inconsistent shape -- e.g. both a ``response`` and ``unavailable: true``
    at once, which cannot both be true of the same call attempt."""


def _descriptor_from_cell(
    cell: dict[str, Any], *, provider: str, path: Path | str
) -> ProviderDescriptor:
    """Read and strictly validate a cell's ``descriptor``.

    Required on every attempted cell -- a ``response`` *or* an
    ``unavailable: true`` marker -- not just a successfully-parsed response:
    even a call that failed (schema violation or unavailable) still needs
    to be attributed to the configuration that was attempted, so its
    latency/cost measurements are aggregated under the right
    ``(provider, config_key)`` bucket rather than a globally
    unattributed count (code review finding).
    """
    raw = cell.get("descriptor")
    if raw is None:
        raise _InvalidDescriptor(
            f"{path}: provider {provider!r} has a recorded cell but no 'descriptor' "
            "(model/version/prompt_version/temperature/structured_output_mode) -- cannot "
            "be reproduced or safely bucketed (Issue #14 '再現条件'). Add a descriptor "
            "object to this cell."
        )
    try:
        return parse_provider_descriptor(json.dumps(raw), provider=provider)
    except ValidationError as exc:
        raise _InvalidDescriptor(
            f"{path}: provider {provider!r} has an invalid 'descriptor' "
            f"({describe_schema_violation(exc)})"
        ) from None


def _validated_measurement(
    value: object, *, field: str, provider: str, path: Path | str
) -> float | None:
    """Validate one recorded ``cost_usd``/``latency_seconds`` value.

    Never embeds the raw recorded ``value`` in a raised message: it comes
    from the same untrusted ``--dataset`` file as everything else, and a
    malformed dataset could put a string containing real answer text there
    by mistake -- that text must not reach a raised exception, a chained
    traceback, or a log line any more than a ``ValidationError``'s raw input
    value may (AGENTS.md "Security"; code review finding; mirrors
    ``domain.ai_grading.describe_schema_violation``). Only the field name and the offending
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


@dataclass(frozen=True, kw_only=True)
class _CellResult:
    """One parsed ``(provider, input_variant)`` cell -- see :func:`_load_cell`."""

    response: GradingResponse | None
    config_key: str | None
    cost_usd: float | None
    latency_seconds: float | None
    is_pending: bool
    is_unavailable: bool


def _load_cell(
    cell: dict[str, Any] | None,
    *,
    provider: str,
    path: Path | str,
    truth: GradingGroundTruth,
) -> _CellResult:
    """Parse one recorded ``(provider, input_variant)`` cell.

    A cell is one of three states (its shape is already validated by
    :func:`_validate_cell_shape` before this runs, so a typo'd or
    self-contradictory cell never reaches here):

    * **pending** -- entirely absent, or present with neither a ``response``
      nor an ``unavailable`` marker. Expected but not yet recorded.
    * **unavailable** -- ``{"unavailable": true, ...}``, no ``response``: a
      call attempt that exhausted retries against a persistent failure
      (docs/poc-2-ai-grading.md section 7.2). Explicitly recorded, not
      silently indistinguishable from "never attempted" (code review
      finding). ``descriptor`` (and so ``config_key``) is required here too,
      the same as an attempted response: even a failed call is attributable
      to the configuration that was tried, so its latency/cost still
      aggregate under that ``(provider, config_key)`` bucket instead of
      vanishing from every provider-level metric (code review finding).
    * **attempted** -- a ``response`` key is present: parsed and validated;
      a malformed response is a schema violation, not a pending measurement.
      ``descriptor`` (and so ``config_key``) is required as soon as
      ``response`` is present, even if that response goes on to fail schema
      validation, so schema-violating cells are still bucketed by the
      configuration that produced them.

    ``latency_seconds``/``cost_usd`` are read independent of which state the
    cell is in, and are ``None`` (not a fabricated ``0.0``) when the cell
    records none.
    """
    if cell is None:
        return _CellResult(
            response=None,
            config_key=None,
            cost_usd=None,
            latency_seconds=None,
            is_pending=True,
            is_unavailable=False,
        )

    has_response = "response" in cell
    is_unavailable = cell.get("unavailable") is True
    is_schema_violation = cell.get("schema_violation") is True

    if not has_response and not is_unavailable and not is_schema_violation:
        cost_usd = _validated_measurement(
            cell.get("cost_usd"), field="cost_usd", provider=provider, path=path
        )
        return _CellResult(
            response=None,
            config_key=None,
            cost_usd=cost_usd,
            latency_seconds=None,
            is_pending=True,
            is_unavailable=False,
        )

    cost_usd = _validated_measurement(
        cell.get("cost_usd"), field="cost_usd", provider=provider, path=path
    )
    latency_seconds = _validated_measurement(
        cell.get("latency_seconds"), field="latency_seconds", provider=provider, path=path
    )
    descriptor = _descriptor_from_cell(cell, provider=provider, path=path)
    config_key = descriptor_key(descriptor)

    if is_unavailable or is_schema_violation:
        # Both leave ``response`` empty; only ``is_unavailable`` separates
        # "the call never returned" from "it returned something that failed
        # validation", which is exactly the distinction
        # ``evaluate_sample`` keys ``schema_violation`` vs ``unavailable``
        # on.
        return _CellResult(
            response=None,
            config_key=config_key,
            cost_usd=cost_usd,
            latency_seconds=latency_seconds,
            is_pending=False,
            is_unavailable=is_unavailable,
        )

    try:
        parsed = parse_ai_grading_result(json.dumps(cell["response"]))
        # Since Issue #117 a recorded cell names a rubric criterion by its
        # 1-based position, and this is where that position is resolved back
        # to the human label's own criterion ids. A position outside the
        # label's rubric raises `SchemaViolation` -- counted here exactly
        # like any other unparseable cell, which is the same treatment the
        # previous "unrecognized ``criteria[].id``" marker got.
        response = grading_response_from_result(
            parsed,
            question_id=truth.question_id,
            criterion_ids=tuple(criterion.id for criterion in truth.criteria),
            descriptor=descriptor,
            latency_seconds=latency_seconds or 0.0,
        )
    except (ValidationError, SchemaViolation):
        return _CellResult(
            response=None,
            config_key=config_key,
            cost_usd=cost_usd,
            latency_seconds=latency_seconds,
            is_pending=False,
            is_unavailable=False,
        )
    return _CellResult(
        response=response,
        config_key=config_key,
        cost_usd=cost_usd,
        latency_seconds=latency_seconds,
        is_pending=False,
        is_unavailable=False,
    )


@dataclass(frozen=True, kw_only=True)
class _ParsedSample:
    """One question's validated ``subject`` + ``submissionId`` + ``testId`` +
    ``ground_truth`` + ``input``, plus its raw ``recorded`` dict (still
    unparsed -- ``_load_cell`` handles that per provider/variant cell).

    ``path`` is a display locator (the submission file, plus which
    ``questions[]`` entry) used only for messages -- never for file I/O.
    """

    path: str
    subject: str
    submission_id: str
    test_id: str
    truth: GradingGroundTruth
    input_record: GradingInputRecord
    recorded: dict[str, dict[str, Any]]


def _load_subject(raw: dict[str, Any], *, path: Path) -> str:
    """Validate and return this file's ``subject``, whitespace-stripped.

    Stripped before being returned (not just checked), mirroring
    :func:`_load_submission_id`/:func:`_load_test_id`: two files whose
    ``subject`` differs only by surrounding whitespace (``"history"`` vs
    ``" history "``) can only mean the same subject, and returning the raw,
    unstripped value would split what should be one subject's coverage and
    metrics into two buckets, and could let two different ``testId`` values
    slip past :func:`_validate_single_test_per_subject` as if they belonged
    to different subjects (code review finding).
    """
    subject = raw.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise _InvalidSubject(
            f"{path}: submission has no non-blank top-level 'subject' field (needed to "
            "bucket this question's metrics by 教科, docs/poc-2-ai-grading.md section 3.3)"
        )
    return subject.strip()


def _load_submission_id(raw: dict[str, Any], *, path: Path) -> str:
    """Validate and return this file's ``submissionId``, whitespace-stripped.

    Stripped before being returned (not just checked): two files whose
    ``submissionId`` differ only by surrounding whitespace (``"sub-1"`` vs
    ``" sub-1 "``) can only mean the same submission, and counting them as
    two would overstate the section 6.2 per-subject submission coverage
    (code review finding; mirrors :func:`_normalized_provider_id`).
    """
    submission_id = raw.get("submissionId")
    if not isinstance(submission_id, str) or not submission_id.strip():
        raise _InvalidSubmissionId(
            f"{path}: submission has no non-blank top-level 'submissionId' field "
            "(business-rules-and-evaluation-data.md section 6.3: each real answer sheet "
            "is identified by a non-PII submissionId) -- needed to tell distinct "
            "submissions apart from distinct questions for the section 6.2 "
            "minimum-dataset-size check"
        )
    return submission_id.strip()


def _load_test_id(raw: dict[str, Any], *, path: Path) -> str:
    """Validate and return this file's ``testId``, whitespace-stripped.

    business-rules-and-evaluation-data.md section 6.1 lists テストID as
    per-test metadata alongside 教科 (subject), and this PoC's evaluation
    design is exactly one test per subject (section 6.2: "2 教科 x 各 1
    テスト"). Without a validated test identity, a dataset that accidentally
    mixes two different tests' submissions under the same subject label
    would be silently pooled into one same-data comparison bucket, even
    though the two tests' rubric or difficulty may differ (code review
    finding). See :func:`_validate_single_test_per_subject` for the
    cross-sample check this enables.
    """
    test_id = raw.get("testId")
    if not isinstance(test_id, str) or not test_id.strip():
        raise _InvalidTestId(
            f"{path}: submission has no non-blank top-level 'testId' field "
            "(business-rules-and-evaluation-data.md section 6.1 metadata: テストID -- "
            "this PoC's evaluation design is exactly one test per subject, section 6.2) "
            "-- needed to detect a dataset that accidentally mixes two different tests' "
            "submissions under the same subject label into one same-data comparison bucket"
        )
    return test_id.strip()


def _load_questions(raw: dict[str, Any], *, path: Path) -> list[dict[str, Any]]:
    """Validate and return this submission file's per-question entry list.

    business-rules-and-evaluation-data.md section 6.3: one real answer
    sheet -- one JSON file -- commonly spans several questions (section
    6.2's "60 答案・のべ 300 設問以上"). A loader that only ever reads one
    ``ground_truth``/``input`` per file cannot consume that many questions
    without an undocumented one-file-per-question split, and so cannot
    actually claim to follow the real-data layout (code review finding).
    Each element is one question's ``ground_truth`` + ``input`` (+
    ``recorded``), validated the same way a single-question file previously
    was.
    """
    questions = raw.get("questions")
    if not isinstance(questions, list) or not questions:
        raise _InvalidSubmission(
            f"{path}: submission has no non-empty top-level 'questions' array -- one "
            "submission file holds one or more per-question ground_truth/input/recorded "
            "entries (business-rules-and-evaluation-data.md section 6.3; section 6.2's "
            "60-submission/300-question dataset size)"
        )
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            raise _InvalidSubmission(
                f"{path}: 'questions[{index}]' must be an object, got {type(question).__name__}"
            )
    return questions


def _load_ground_truth(raw: dict[str, Any], *, path: Path | str) -> GradingGroundTruth:
    try:
        return GradingGroundTruth.from_mapping(raw["ground_truth"])
    except ValidationError as exc:
        raise _InvalidGroundTruth(
            f"{path}: invalid 'ground_truth' block ({describe_schema_violation(exc)})"
        ) from None


def _load_input_record(
    raw: dict[str, Any], *, truth: GradingGroundTruth, path: Path | str
) -> GradingInputRecord:
    """Parse this question's ``input`` block and cross-check it against ``truth``.

    Raises :class:`_InvalidInput` if ``input`` is missing, fails strict
    validation, disagrees with ``ground_truth`` (e.g. a different
    ``max_score``), or if any provider has a recorded ``ocr_noisy`` attempt
    (any of the three outcome markers :func:`_recorded_outcomes` reads)
    while this sample's ``input.ocr_noisy`` is ``null``: a same-data comparison
    requires the underlying question material -- including which OCR
    variants actually exist -- to match, not just the final score (code
    review finding). An ``unavailable`` noisy-variant attempt counts here
    too: calling a provider requires a noisy input to have existed in the
    first place, so an "unavailable" marker recorded against a variant that
    was never authored cannot be a real provider outage against real input
    either (code review finding).
    """
    if "input" not in raw:
        raise _InvalidInput(f"{path}: question has no 'input' block to validate against")
    try:
        input_record = GradingInputRecord.from_mapping(raw["input"])
    except ValidationError as exc:
        raise _InvalidInput(
            f"{path}: invalid 'input' block ({describe_schema_violation(exc)})"
        ) from None
    try:
        validate_input_matches_truth(input_record, truth)
    except ValueError as exc:
        raise _InvalidInput(f"{path}: {exc}") from None

    if input_record.ocr_noisy is None:
        for provider, variants in raw.get("recorded", {}).items():
            cell = variants.get("ocr_noisy")
            if isinstance(cell, dict) and _recorded_outcomes(cell):
                raise _InvalidInput(
                    f"{path}: provider {provider!r} has a recorded 'ocr_noisy' attempt "
                    "(response, schema_violation, or unavailable), but this sample's "
                    "input.ocr_noisy is null "
                    "-- no noisy-OCR variant was authored for this sample, so a recorded "
                    "noisy-variant attempt cannot be a real same-data comparison"
                )
    return input_record


#: Fields a recorded cell may contain. An unrecognized field (a typo such as
#: ``"respnose"`` instead of ``"response"``) is rejected outright rather than
#: silently misclassifying the cell -- see :func:`_validate_cell_shape`.
_KNOWN_CELL_KEYS = frozenset(
    {"response", "descriptor", "latency_seconds", "cost_usd", "unavailable", "schema_violation"}
)


def _recorded_outcomes(cell: dict[str, Any]) -> list[str]:
    """Which of the three mutually exclusive call outcomes this cell records.

    A ``response`` key (whatever its value) means "the call returned
    something to validate"; ``unavailable: true`` means "the call never
    returned"; ``schema_violation: true`` means "the call returned, and what
    it returned failed :func:`parse_ai_grading_result`, with the raw body
    deliberately not retained" -- the shape ``record.py`` writes for a
    :class:`~auto_scoring.domain.ai_provider.SchemaViolation`, since the
    adapters never expose the offending body (it can hold OCR'd student
    answer text; ``domain.ai_provider.SchemaViolation``). Without that third
    marker, a live-recorded schema violation could only be represented by
    inventing a response that happens to fail validation -- writing a
    fabricated body into the dataset to record a real failure.
    """
    outcomes = ["response"] if "response" in cell else []
    outcomes += [
        marker for marker in ("schema_violation", "unavailable") if cell.get(marker) is True
    ]
    return sorted(outcomes)


def _validate_cell_shape(cell: object, *, provider: str, variant: str, path: Path | str) -> None:
    """Reject a recorded ``(provider, input_variant)`` cell whose shape is
    internally inconsistent, instead of silently misclassifying it.

    A cell with an unrecognized field -- a typo such as ``"respnose"``
    instead of ``"response"``, or a non-boolean ``"unavailable": "true"``
    (the string, not ``true``) -- previously satisfied neither the "has a
    response" nor the "is unavailable" check in :func:`_load_cell`, so a
    real recorded attempt was silently classified as ordinary "pending" and
    the harness could exit 0 using only the other cells, as if the dataset
    had been fully and correctly reported (code review finding; AGENTS.md
    trust-boundary validation). A non-object cell value (e.g. a bare string)
    previously reached a ``.get()`` call directly and failed with an
    unhandled ``TypeError`` instead of a clear validation error. A cell that
    records ``descriptor``/``latency_seconds``/``cost_usd`` (evidence a call
    was actually attempted) but omits both ``response`` and
    ``unavailable: true`` is rejected the same way: it is not a genuinely
    pending cell (one nobody has tried yet), but a contradictory one whose
    outcome was never recorded, and silently accepting it would drop that
    attempt's descriptor/latency entirely and exclude the call from every
    provider latency/cost/unavailability metric (code review finding).
    """
    if cell is None:
        return  # absent cell -- legitimately pending
    if not isinstance(cell, dict):
        raise _InvalidRecordedCell(
            f"{path}: provider {provider!r}'s {variant!r} cell must be an object, got "
            f"{type(cell).__name__}"
        )
    unknown = sorted(set(cell) - _KNOWN_CELL_KEYS)
    if unknown:
        # Never echo the unknown field name(s) themselves -- untrusted
        # ``--dataset`` content the same as any other key or value (AGENTS.md
        # "Security"; code review finding).
        raise _InvalidRecordedCell(
            f"{path}: provider {provider!r}'s {variant!r} cell has {len(unknown)} "
            f"unrecognized field(s) -- only {sorted(_KNOWN_CELL_KEYS)} are recognized (a "
            "typo such as 'respnose' would otherwise leave a real recorded attempt "
            "silently classified as pending). The unrecognized field name(s) are not "
            "shown here."
        )
    for marker in ("unavailable", "schema_violation"):
        if marker in cell and not isinstance(cell[marker], bool):
            raise _InvalidRecordedCell(
                f"{path}: provider {provider!r}'s {variant!r} cell has a non-boolean "
                f"{marker!r} marker (got {type(cell[marker]).__name__}) -- expected "
                'a strict true/false, not e.g. the string "true"'
            )
    recorded_outcomes = _recorded_outcomes(cell)
    if len(recorded_outcomes) > 1:
        raise _InvalidRecordedCell(
            f"{path}: provider {provider!r}'s {variant!r} cell records {recorded_outcomes} "
            "at once -- one call attempt has exactly one outcome (it returned a parseable "
            "response, or it returned an unparseable one, or it never returned at all)"
        )
    if not recorded_outcomes:
        attempt_evidence = sorted({"descriptor", "latency_seconds", "cost_usd"} & set(cell))
        if attempt_evidence:
            raise _InvalidRecordedCell(
                f"{path}: provider {provider!r}'s {variant!r} cell has {attempt_evidence} "
                "recorded but neither a 'response' nor 'unavailable: true' -- this looks "
                "like a call that was attempted (someone recorded its descriptor/latency/"
                "cost) but never had its outcome recorded, not a genuinely pending cell "
                "that simply has not been tried yet. A truly pending cell should be "
                "entirely absent, or an empty object."
            )


def _validate_recorded_cells(recorded: dict[str, dict[str, Any]], *, path: Path | str) -> None:
    """Reject a provider's ``recorded`` entry with an input-variant key
    outside :data:`_INPUT_VARIANTS`, or an individual cell with an
    inconsistent shape, instead of silently misclassifying either.

    ``_load_cell``/``_responder_configs_by_variant`` only ever look up the
    fixed ``ocr_clean``/``ocr_noisy`` keys by name, never iterate whatever
    keys happen to be present -- so a typo'd key (e.g. ``"ocr_nosiy"``
    instead of ``"ocr_noisy"``) is never matched by either lookup. Without
    this check, a real recorded response under that key would simply never
    be found: the expected cell stays "pending" forever, and the harness can
    exit 0 printing an incomplete aggregate as if the dataset had been fully
    reported (code review finding).
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
        for variant in _INPUT_VARIANTS:
            if variant in variants:
                _validate_cell_shape(
                    variants[variant], provider=provider, variant=variant, path=path
                )


def _load_all_samples(files: list[Path]) -> list[_ParsedSample]:
    """Parse and validate every submission file's questions.

    Called before the harness decides whether the dataset has anything to
    report (including the "every ``recorded`` is ``{}``" staged-pilot case):
    a dataset made of nothing but malformed or inconsistent samples must not
    exit 0 as if it were valid, uninspected evidence (code review finding).
    """
    parsed: list[_ParsedSample] = []
    seen_submissions: dict[tuple[str, str], Path] = {}
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        subject = _load_subject(raw, path=path)
        submission_id = _load_submission_id(raw, path=path)
        submission_key = (subject, submission_id)
        earlier_path = seen_submissions.get(submission_key)
        if earlier_path is not None:
            raise _InvalidSubmissionId(
                f"{path}: reuses the same (subject, submissionId) as {earlier_path} -- "
                "business-rules-and-evaluation-data.md section 6.3 defines one answer "
                "sheet as one JSON file, so two files must never claim the same "
                "submission (a real duplicate would double that submission's weight in "
                "every provider metric without inflating the coverage count meant to "
                "reflect it)"
            )
        seen_submissions[submission_key] = path
        test_id = _load_test_id(raw, path=path)
        questions = _load_questions(raw, path=path)
        seen_question_ids: set[str] = set()
        for index, question in enumerate(questions):
            locator = f"{path}#{index}"
            _validate_recorded_cells(question.get("recorded", {}), path=locator)
            truth = _load_ground_truth(question, path=locator)
            if truth.question_id in seen_question_ids:
                raise _InvalidSubmission(
                    f"{locator}: duplicate questionId {truth.question_id!r} within this "
                    "submission's 'questions' array -- a copy-paste mistake would "
                    "otherwise double-count this question's weight in every aggregate"
                )
            seen_question_ids.add(truth.question_id)
            input_record = _load_input_record(question, truth=truth, path=locator)
            parsed.append(
                _ParsedSample(
                    path=locator,
                    subject=subject,
                    submission_id=submission_id,
                    test_id=test_id,
                    truth=truth,
                    input_record=input_record,
                    recorded=question.get("recorded", {}),
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
    commonly spans several questions).
    """
    submissions_by_subject: dict[str, set[str]] = {}
    for sample in samples:
        submissions_by_subject.setdefault(sample.subject, set()).add(sample.submission_id)
    return {subject: len(ids) for subject, ids in submissions_by_subject.items()}


def _validate_single_test_per_subject(samples: list[_ParsedSample]) -> None:
    """Reject a dataset where one ``subject`` spans more than one ``testId``.

    ``summarize_by_provider`` buckets only by (subject, provider, config,
    input_variant) -- not by ``testId`` -- so two different tests
    accidentally recorded under the same subject label would be silently
    pooled into one same-data comparison bucket even though their rubric or
    difficulty may differ (business-rules-and-evaluation-data.md section
    6.1: exactly one test per subject in this PoC's evaluation design;
    code review finding).
    """
    test_ids_by_subject: dict[str, set[str]] = {}
    for sample in samples:
        test_ids_by_subject.setdefault(sample.subject, set()).add(sample.test_id)
    for subject, test_ids in test_ids_by_subject.items():
        if len(test_ids) > 1:
            raise _InvalidTestId(
                f"subject {subject!r} spans {len(test_ids)} different testId values "
                f"({sorted(test_ids)}) -- this PoC's evaluation design is exactly one "
                "test per subject (business-rules-and-evaluation-data.md section 6.2); "
                "pooling submissions from different tests under one subject bucket could "
                "mix different rubrics/difficulty into one misleading adoption metric"
            )


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
                # Never echo the two colliding keys themselves: they are
                # untrusted ``--dataset`` content the same as any other key
                # or value (AGENTS.md "Security"; code review finding).
                raise _InvalidProviderId(
                    f"{sample.path}: two different 'recorded' provider keys normalize to "
                    "the same id -- this looks like an inconsistently spelled duplicate of "
                    "the same provider, not two distinct candidates. The keys themselves "
                    "are not shown here."
                )
            raw_for_normalized[normalized] = raw_key
    return raw_for_normalized


def _validate_canonical_provider_ids(providers: Iterable[str], *, dataset: Path) -> None:
    """Real ``--dataset`` runs must use exactly the candidate ids
    docs/poc-2-ai-grading.md section 2 defines (case-sensitive) -- the
    bundled synthetic fixtures (``_DEFAULT_DATASET``) are an explicit,
    documented exception, since they intentionally use placeholder names
    (``synthetic-a`` / ``synthetic-b``) that are not real vendor identifiers.

    Whitespace normalization alone (:func:`_canonical_providers`) does not
    catch a case difference: ``"gemini"`` and ``"Gemini"`` would still count
    as two separate candidates for the same real service, letting one
    service satisfy the >= 2 comparison gate on its own (code review
    finding).
    """
    if dataset.resolve() == _DEFAULT_DATASET.resolve():
        return
    unknown = sorted(set(providers) - _CANONICAL_PROVIDER_IDS)
    if unknown:
        # Never echo the offending id(s) themselves: a malformed real
        # dataset could have a secret or student text as a 'recorded' key
        # by mistake, and this is the same untrusted --dataset trust
        # boundary as any other key or value (AGENTS.md "Security"; code
        # review finding).
        raise _InvalidProviderId(
            f"{len(unknown)} provider id(s) recorded in this dataset are not among the "
            f"canonical candidate ids {sorted(_CANONICAL_PROVIDER_IDS)} "
            "(docs/poc-2-ai-grading.md section 2) -- a normalized-but-non-canonical id "
            "(e.g. a case difference) could let one real service masquerade as two "
            "separate candidates. Rename the 'recorded' key(s) to the canonical id. The "
            "offending id(s) are not shown here."
        )


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
                    cells_for_provider.get(variant),
                    provider=provider,
                    path=sample.path,
                    truth=sample.truth,
                )
                for variant in _INPUT_VARIANTS
            }
        grid.append(cells_for_sample)
    return grid


def _responder_configs_by_variant(
    cells_for_sample: dict[str, dict[str, _CellResult]],
) -> dict[str, set[tuple[str, str]]]:
    """``(provider, config_key)`` pairs with an actual, attempted
    (non-pending) cell for one sample, split by input variant.

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
    docs/poc-2-ai-grading.md section 3.3's config-bucket separation). An
    ``unavailable`` cell now has a real ``config_key`` too (``_load_cell``
    requires a ``descriptor`` for it, the same as a real response), so it
    contributes here exactly like a schema-violating response does: a
    persistently-unreliable provider's failed attempts are still
    attributable to (and can still gate or exclude) a same-data comparison,
    rather than being invisible to it (code review finding).
    """
    by_variant: dict[str, set[tuple[str, str]]] = {variant: set() for variant in _INPUT_VARIANTS}
    for provider, by_variant_cell in cells_for_sample.items():
        for variant, result in by_variant_cell.items():
            if not result.is_pending:
                assert result.config_key is not None
                by_variant[variant].add((provider, result.config_key))
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


def _load_samples(
    dataset: Path,
) -> tuple[list[SampleOutcome], int, int, int, int, dict[str, int]]:
    """Return ``(evaluated outcomes, pending-cell count, files with no
    provider recorded anywhere in the dataset, excluded-cell count,
    unavailable-cell count, distinct-submission count per subject)`` from
    every ``*.json``.

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

    The fifth count ("unavailable") covers a call attempt explicitly
    recorded as failed (``{"unavailable": true, ...}``, docs/poc-2-ai-grading.md
    section 7.2) -- distinct from "pending" (never attempted) so a
    persistently-unreliable provider's failures cannot silently vanish from
    the report (code review finding). Unlike an earlier version, an
    unavailable attempt is not simply discarded after being counted here: it
    is also passed to :func:`~auto_scoring.domain.ai_grading_metrics.
    evaluate_sample` (``unavailable=True``) so its ``latency_seconds``/
    ``cost_usd`` are attributed to the ``(provider, config_key)`` bucket
    that was attempted and aggregated into that bucket's p50/p95 latency and
    cost columns -- an earlier version dropped these measurements after
    incrementing only this top-line count, letting a provider with frequent
    long-timeout failures look faster and cheaper than it really is in the
    per-provider table (code review finding).

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
    _validate_single_test_per_subject(samples)
    submission_coverage = _submission_coverage(samples)

    raw_for_normalized = _canonical_providers(samples)
    _validate_canonical_provider_ids(raw_for_normalized, dataset=dataset)
    if not raw_for_normalized:
        return [], 0, len(files), 0, 0, submission_coverage

    cell_grid = _parse_cell_grid(samples, raw_for_normalized)
    pending = sum(
        1
        for cells_for_sample in cell_grid
        for by_variant_cell in cells_for_sample.values()
        for result in by_variant_cell.values()
        if result.is_pending
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
    unavailable = 0
    for sample, cells_for_sample, by_variant in zip(
        samples, cell_grid, responders_by_sample, strict=True
    ):
        for provider in sorted(cells_for_sample):
            by_variant_cell = cells_for_sample[provider]
            for variant, result in by_variant_cell.items():
                if result.is_pending:
                    continue
                if result.is_unavailable:
                    unavailable += 1
                assert result.config_key is not None  # only None when pending
                if by_variant[variant] != comparable:
                    excluded += 1
                    continue
                outcomes.append(
                    evaluate_sample(
                        sample.truth,
                        result.response,
                        subject=sample.subject,
                        provider=provider,
                        config_key=result.config_key,
                        input_variant=variant,
                        cost_usd=result.cost_usd,
                        latency_seconds=result.latency_seconds,
                        unavailable=result.is_unavailable,
                    )
                )
    return outcomes, pending, 0, excluded, unavailable, submission_coverage


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # keep the JP table readable on Windows

    parser = argparse.ArgumentParser(description="PoC 2 AI grading metric aggregator")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    outcomes, pending, staged, excluded, unavailable, submission_coverage = _load_samples(
        args.dataset
    )
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
    if unavailable:
        notes += (
            f"\nunavailable (a call attempt exhausted retries against a persistent failure "
            f"and was explicitly recorded as such, docs/poc-2-ai-grading.md section 7.2 -- "
            f"never scored, never silently folded into 'pending'): {unavailable}\n"
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
