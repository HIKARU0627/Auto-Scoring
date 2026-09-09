"""PoC 2 (issue #35) live-provider path -- call a real ``AIProvider`` and
record each response into a dataset's ``recorded`` cells, for
``report.py`` to aggregate afterwards.

Usage::

    uv run --env-file .env.local python poc/issue_14_ai_grading/record.py \\
        --dataset "<local eval-dataset dir>" --images "<local crops dir>" \\
        [--variant ocr_clean|ocr_noisy|both] [--limit N] [--overwrite] [--dry-run]

This is the half of PoC 2 that Issue #14 deferred: ``report.py`` has always
been able to aggregate ``recorded`` responses, but nothing in the repository
could produce them. The provider (or fallback chain) comes from
``adapters.ai_grading.factory.create_ai_provider()``, i.e. from
``AUTO_SCORING_AI_GRADING_TRANSPORT`` -- so the same configuration that will
run in the MVP is what gets measured here, rather than a second, harness-only
selection mechanism that could drift from it.

**Which provider a cell is filed under comes from the response, not from the
configuration**: every cell is keyed by ``response.descriptor.provider``, the
name of the adapter that actually graded. With a single adapter that is just
that adapter; with the Issue #81 fallback chain it is whichever link
answered, which is exactly what decision record section 3 (B) requires be
recorded ("どの provider で採点したかを結果に残す") and what keeps
``report.py``'s per-provider agreement metrics meaningful.

Safety properties this script is built around (AGENTS.md "Security";
docs/poc-2-ai-grading.md section 11):

* **It never prints student content.** Progress lines carry an index, the
  input variant, the provider id, the outcome, and a duration -- never
  question text, OCR text, a rubric, a score, or a response body.
* **It never writes into the repository.** Any ``--dataset`` that resolves
  to a path under the repository root is refused outright -- not just the
  bundled fixture directory -- so a copy of the fixtures made *inside* the
  working tree cannot become a place real provider output lands.
* **It verifies image identity.** An ``answer_image_ref`` of the form
  ``sha256:<hex>`` is checked against the bytes actually read, so a stale or
  swapped crop cannot silently make two providers look like they were
  compared on the same input (docs/poc-2-ai-grading.md section 3.12).
* **It never fabricates an outcome.** A response that fails schema
  validation is recorded as ``schema_violation: true`` and a call that
  exhausts its retries as ``unavailable: true`` -- never as a guessed grade,
  and never left indistinguishable from a cell nobody has tried yet.
* **It records nothing it cannot verify.** Every string a provider controls
  is a leak path -- an id and a piece of metadata just as much as a
  free-text field, because schema validation checks the *shape* of a value
  and says nothing about its content. So the rule is an allowlist, not a
  list of fields known to hold answer text: a provider-supplied value is
  written only when it is (a) a value this run sent, matched back (the
  descriptor's configured strings), or (b) constrained by type and range (a
  number, an enum, a bool). Since Issue #117 the wire format carries no
  provider-written identifier at all -- no ``questionId``, and a criterion
  is a 1-based ``index`` into the rubric this run sent -- so the two values
  that used to need matching back cannot carry provider content in the
  first place.
  Everything else is replaced with a fixed marker or a content-free
  fingerprint (:func:`_wire_response`, :func:`_wire_descriptor`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_grading_metrics import (
    GradingGroundTruth,
    GradingInputRecord,
    validate_input_matches_truth,
)
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
)
from auto_scoring.domain.models import AnnotationKind

#: The repository this script lives in. Nothing under it may be recorded
#: into: a real provider's response body must never reach a commit
#: (docs/poc-2-ai-grading.md section 11), and refusing only the bundled
#: fixture directory left "copy the fixtures somewhere else in the repo and
#: point --dataset there" wide open (code review finding). Resolved, so a
#: symlink pointing back inside the repository is caught too.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

#: Mirrors ``report.py``'s ``_INPUT_VARIANTS`` -- the two evaluation modes
#: docs/poc-2-ai-grading.md section 2.1 compares every candidate on.
_INPUT_VARIANTS = ("ocr_clean", "ocr_noisy")

#: docs/poc-2-ai-grading.md section 7.2, which assigns the retry policy to
#: this live-provider path (the adapters themselves deliberately raise once,
#: with no built-in backoff).
_MAX_ATTEMPTS = 5
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 32.0

#: Extensions searched for a crop named by its content hash. PNG first: this
#: project's own crop pipeline (``adapters.image.opencv_preprocessor``)
#: writes PNG.
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


class _DatasetError(Exception):
    """The dataset, or the crop directory it refers to, cannot be used.

    Never carries a field *value* from the dataset -- only file paths,
    question indices, and reference strings that are content hashes by
    construction (mirrors ``report.py``'s ``_sanitize_validation_error``).
    """


@dataclass(frozen=True, kw_only=True)
class _Cell:
    """One ``(submission file, question index, input variant)`` to record."""

    path: Path
    document: dict[str, Any]
    question_index: int
    variant: str
    request: GradingRequest


def _load_image(images: Path, ref: str, *, locator: str) -> bytes:
    """Read the answer-region crop named by an ``input.answer_image_ref``.

    ``sha256:<hex>`` is the form that can be *verified*: the file is read
    from ``<images>/<hex><ext>`` and its digest must equal the reference, so
    a crop that was re-generated or swapped between two providers' runs
    fails here instead of quietly producing an invalid same-data comparison
    (docs/poc-2-ai-grading.md section 3.12).

    Any other reference is treated as a plain file name inside ``images``
    (the decision record allows "an external, out-of-repo reference"), and
    its content is necessarily unverified -- the reference carries nothing
    to check it against. Path separators and ``..`` are rejected rather than
    resolved: the dataset is untrusted input, and a reference is not allowed
    to reach outside the crop directory it was given (AGENTS.md
    "Security").

    **The reference itself is never echoed in a raised message.** A
    reference that failed validation is by definition not known to be a
    content hash -- a malformed dataset could have answer text or a name
    there by mistake, and ``main()`` prints these messages to stderr (code
    review finding; mirrors ``report.py``'s ``_sanitize_validation_error``).
    Only ``locator`` (the file and question index, both authored by us) and
    a fixed reason are reported. A digest that *did* validate is safe to
    show, and is, since finding a missing crop is otherwise guesswork.
    """
    if ref.startswith("sha256:"):
        digest = ref[len("sha256:") :].strip().lower()
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise _DatasetError(
                f"{locator}: answer_image_ref starts with 'sha256:' but the rest is not a "
                "64-character hex digest. The value itself is not shown here."
            )
        for extension in _IMAGE_EXTENSIONS:
            candidate = images / f"{digest}{extension}"
            if candidate.is_file():
                data = candidate.read_bytes()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise _DatasetError(
                        f"{locator}: {candidate} does not hash to its answer_image_ref -- "
                        "the crop this sample was labelled against is not the crop on disk"
                    )
                return data
        raise _DatasetError(
            f"{locator}: no crop for {digest} under {images} "
            f"(looked for {digest}<{'|'.join(_IMAGE_EXTENSIONS)}>)"
        )

    if "/" in ref or "\\" in ref or ref in {".", ".."}:
        raise _DatasetError(
            f"{locator}: answer_image_ref is neither a 'sha256:' digest nor a plain file "
            "name -- a path is not accepted here. The value itself is not shown here."
        )
    candidate = images / ref
    if not candidate.is_file():
        raise _DatasetError(
            f"{locator}: answer_image_ref names no file under {images}. The value itself "
            "is not shown here."
        )
    return candidate.read_bytes()


def _ground_truth(question: dict[str, Any], *, locator: str) -> GradingGroundTruth:
    """The human label for this question, strictly validated.

    Validated here rather than only later by ``report.py``: the label
    supplies the rubric criteria this run grades against (and so the
    candidate set a response chooses a position from), so a malformed label
    has to stop the run *before* any paid call, not after.

    The ``ValidationError``'s own message is never shown: pydantic keeps the
    offending value under ``input_value``, and a human label file holds
    real, hand-transcribed grading data (AGENTS.md "Security"; mirrors
    ``report.py``'s ``_sanitize_validation_error``).
    """
    try:
        return GradingGroundTruth.from_mapping(question["ground_truth"])
    except KeyError:
        raise _DatasetError(f"{locator}: has no 'ground_truth' block") from None
    except ValidationError:
        raise _DatasetError(f"{locator}: 'ground_truth' failed validation") from None


def _validate_against_truth(
    input_record: GradingInputRecord, truth: GradingGroundTruth, *, locator: str
) -> None:
    """Reject a question whose ``input`` disagrees with its human label.

    The same check ``report.py`` runs (``validate_input_matches_truth``) --
    run here too, because the two scripts run at different times and only
    one of them spends money. Validating each block on its own is not
    enough: an ``input.max_score`` of 20 against a ``ground_truth.maxScore``
    of 30 passes both, so ``--dry-run`` reported success, the real run paid
    for every cell, and ``report.py`` then refused to score any of them
    (code review finding). This script spends someone else's money; a dry
    run that does not predict whether the real run's output is usable is
    worth much less.

    The underlying ``ValueError`` names the two scores and the question id;
    only the locator and a fixed reason are surfaced, the same as every
    other message here (the dataset is untrusted input).
    """
    try:
        validate_input_matches_truth(input_record, truth)
    except ValueError:
        raise _DatasetError(
            f"{locator}: input.max_score disagrees with ground_truth.maxScore -- report.py "
            "would refuse to score this question, so recording it would spend a call for "
            "nothing. The values themselves are not shown here."
        ) from None


def _ocr_text(input_record: GradingInputRecord, variant: str) -> str | None:
    return input_record.ocr_clean if variant == "ocr_clean" else input_record.ocr_noisy


def _plan(
    *,
    dataset: Path,
    images: Path,
    variants: tuple[str, ...],
    overwrite: bool,
    provider_id: str | None,
) -> list[_Cell]:
    """Every cell that still needs a call, in a stable order.

    Validates the whole dataset before the first call, the same way
    ``report.py`` does: a malformed sample must abort the run before any
    money or quota is spent, not halfway through it.
    """
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise _DatasetError(f"no *.json samples found under {dataset}")

    cells: list[_Cell] = []
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _DatasetError(f"{path}: cannot be read as JSON ({type(exc).__name__})") from None
        if not isinstance(document, dict):
            raise _DatasetError(f"{path}: top level must be a JSON object")
        questions = document.get("questions")
        if not isinstance(questions, list) or not questions:
            raise _DatasetError(f"{path}: 'questions' must be a non-empty array")

        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                raise _DatasetError(f"{path} question {index}: must be a JSON object")
            locator = f"{path} question {index}"
            try:
                input_record = GradingInputRecord.from_mapping(question["input"])
            except KeyError:
                raise _DatasetError(f"{locator}: has no 'input' block") from None
            except ValidationError:
                # Deliberately not the ValidationError's own message:
                # pydantic keeps the offending value under ``input_value``,
                # which here is transcribed student answer text (AGENTS.md
                # "Security"; report.py's `_sanitize_validation_error`).
                raise _DatasetError(f"{locator}: 'input' failed validation") from None
            truth = _ground_truth(question, locator=locator)
            _validate_against_truth(input_record, truth, locator=locator)
            image = _load_image(
                images, input_record.answer_image_ref, locator=f"{path} question {index}"
            )
            recorded = question.setdefault("recorded", {})
            if not isinstance(recorded, dict):
                raise _DatasetError(f"{path} question {index}: 'recorded' must be an object")

            for variant in variants:
                ocr_text = _ocr_text(input_record, variant)
                if ocr_text is None:
                    continue  # no noisy variant authored for this sample
                if not overwrite and _already_recorded(recorded, variant, provider_id):
                    continue
                cells.append(
                    _Cell(
                        path=path,
                        document=document,
                        question_index=index,
                        variant=variant,
                        request=GradingRequest(
                            question_id=truth.question_id,
                            prompt_text=input_record.prompt_text,
                            answer_image=image,
                            ocr_text=ocr_text,
                            model_answer=input_record.model_answer,
                            rubric_text=input_record.rubric_text,
                            criterion_ids=tuple(c.id for c in truth.criteria),
                            max_score=input_record.max_score,
                        ),
                    )
                )
    return cells


def _already_recorded(recorded: dict[str, Any], variant: str, provider_id: str | None) -> bool:
    """Whether this run's provider already has an outcome for this variant.

    Skipping what is already recorded is what makes a long run resumable
    after an interruption without paying for the completed cells twice, and
    what lets a second candidate be recorded onto a dataset the first one
    has already been run against (PoC 2 compares candidates on the *same*
    samples, so that second pass is the normal case, not an edge case).

    ``provider_id`` is the id this run would file under -- ``describe()``
    before any call. With a fallback chain that is the head of the chain,
    so a cell an earlier run happened to fill from a *lower* link is
    re-attempted; ``--overwrite`` is the blunt instrument for any case
    where that is not what was wanted. ``None`` (``--dry-run``, where no
    provider is built and no credentials are needed) falls back to "any
    provider has recorded this variant".
    """
    entries = recorded.values() if provider_id is None else [recorded.get(provider_id, {})]
    for cells in entries:
        if not isinstance(cells, dict):
            continue
        cell = cells.get(variant)
        if isinstance(cell, dict) and (
            "response" in cell
            or cell.get("unavailable") is True
            or cell.get("schema_violation") is True
        ):
            return True
    return False


#: Written in place of every free-text field a provider returns. Short,
#: fixed, and obviously not model output, so nobody reading a dataset can
#: mistake it for something a provider actually said. Must stay within
#: ``domain.models.MAX_COMMENT_CHARS`` -- it is written into ``comment``,
#: which the wire schema length-limits.
_REDACTED = "[redacted: PoC 2 records no free text]"


#: Written in place of a ``questionId`` that is not the one this run sent.
def _wire_response(response: GradingResponse, *, criterion_ids: Sequence[str]) -> dict[str, Any]:
    """The verifiable, metric-bearing part of a response -- and nothing else.

    **No provider-controlled string reaches disk.** Issue #35's acceptance
    condition is "secret・答案本文・生徒識別情報がログ・出力・リポジトリに
    残らない", and *出力* includes this file -- being outside the repository
    does not make an answer-text copy acceptable. Schema validation is not
    anonymization: it checks the *shape* of a value and says nothing about
    its content, so "this field is an id" or "this field is metadata" is not
    a safety argument. A provider can put the student's answer in
    ``questionId`` and pass validation (code review finding: the first
    version of this function redacted the fields known to hold prose and let
    the ids through on exactly that reasoning).

    So each value is written only if one of two things is true:

    * **it is a value this run sent, matched back** -- since Issue #117 the
      wire format has no field a provider fills in with an identifier at
      all, so nothing is left in this category here (the descriptor's own
      configured strings, handled by :func:`_wire_descriptor`, are the
      remaining case);
    * **its type and range constrain it** -- ``score``/``maxScore``
      (integers), the three ``confidence`` values (floats in 0..1),
      ``criteria[].index`` (a position in the rubric *this run* sent, which
      ``grading_response_from_result`` has already refused to map if it is
      out of range), ``criteria[].result`` and ``annotations[].type``
      (enums).

    Every other field carries :data:`_REDACTED`. They are replaced rather
    than dropped because the wire schema requires them: a cell has to stay
    readable by ``parse_ai_grading_result`` for ``report.py`` to score it at
    all (Issue #14 acceptance: a recorded cell is validated on the way back
    in, never trusted). Redacting rather than dropping also keeps one file
    format for hand-authored fixtures and live recordings, and keeps the
    redaction visible in the data instead of implicit in its absence.

    Built from the already-parsed :class:`GradingResponse`, never from the
    provider's raw body, so what is recorded is exactly what passed
    ``parse_ai_grading_result`` -- and no un-validated bytes from a remote
    service reach the disk.
    """
    body = {
        "recognition": {
            "text": _REDACTED,
            "confidence": response.recognition_confidence,
        },
        "grading": {
            "score": response.score,
            "maxScore": response.max_score,
            "confidence": response.grading_confidence,
        },
        "criteria": [
            {
                "index": _rubric_position(criterion.criterion_id, criterion_ids),
                "result": criterion.outcome.value,
                "confidence": criterion.confidence,
                "rationale": _REDACTED,
            }
            for criterion in response.criteria
        ],
        "comment": _REDACTED,
        "rationale": _REDACTED,
        "annotations": [
            {
                "target": _REDACTED,
                "type": annotation.type.value,
                # A COMMENT-kind annotation must carry non-blank comment
                # text (`AnnotationCandidate._comment_type_requires_comment_
                # text`). Writing `null` there turned a perfectly good
                # response into one `report.py` then counted as a schema
                # violation, quietly inflating that provider's violation
                # rate (code review finding). Keyed on the kind, not on
                # whether the original had a comment, so the recorded cell
                # is valid by construction rather than by the provider
                # having happened to fill it in.
                "comment": (
                    _REDACTED
                    if annotation.type is AnnotationKind.COMMENT or annotation.comment is not None
                    else None
                ),
            }
            for annotation in response.annotations
        ],
    }
    _assert_still_parses(body)
    return body


def _rubric_position(criterion_id: str, criterion_ids: Sequence[str]) -> int:
    """``criterion_id``'s 1-based position in this run's own rubric.

    Cannot fail for a response that came through
    ``grading_response_from_result``: since Issue #117 that function is what
    turns a provider's chosen position back into an id, from this same
    list. So an id it does not recognize means the caller assembled a
    ``GradingResponse`` some other way -- and the safe answer is to stop,
    not to write a string of unknown provenance into the dataset. The id
    itself is never included in the message: it is exactly the value this
    function has just decided it cannot vouch for.
    """
    try:
        return criterion_ids.index(criterion_id) + 1
    except ValueError:
        raise AssertionError(
            "a graded criterion is not one of the rubric criteria this run sent; "
            "the response was not mapped through grading_response_from_result"
        ) from None


def _assert_still_parses(body: dict[str, Any]) -> None:
    """Fail loudly if the projection above no longer satisfies the wire schema.

    ``report.py`` re-validates every recorded cell, so a projection that
    drifts out of the schema does not crash anything -- it silently
    reclassifies healthy responses as schema violations and inflates that
    provider's ``schema_violation_rate`` (code review finding: writing
    ``comment: null`` under a COMMENT-kind annotation did exactly that).
    Checking here turns that class of mistake into an immediate, local
    failure instead of a quiet distortion of the adoption metrics.

    The offending value is never included in the message: it is this
    function's own output, which should hold no provider content, and a bug
    that put some there must not then print it (mirrors ``report.py``'s
    ``_sanitize_validation_error``).
    """
    try:
        parse_ai_grading_result(json.dumps(body, ensure_ascii=False))
    except ValidationError as exc:
        locations = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors()
        )
        raise AssertionError(
            f"the recorded projection no longer satisfies AIGradingResult ({locations}) -- "
            "report.py would count these cells as schema violations"
        ) from None


def _fingerprint(value: str) -> str:
    """A content-free stand-in that still tells two different values apart.

    16 hex characters is 64 bits -- far more than enough to keep a handful
    of models and deployments in separate ``descriptor_key`` buckets, and
    short enough to stay readable in the results table's ``config`` column.
    """
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _wire_descriptor(descriptor: ProviderDescriptor) -> dict[str, Any]:
    """The ``descriptor`` block ``report.py`` requires on every recorded cell.

    **A pure function of the descriptor.** ``report.py`` derives its
    aggregation identity (``descriptor_key``) from these fields, so the same
    response must produce the same identity every time -- whatever this run
    happened to be configured with. An earlier version wrote a value
    verbatim when it appeared in the run's own provider configuration and a
    fingerprint when it did not, which made one real configuration take two
    different shapes: Codex's default model resolved to ``gpt-5-codex`` and
    was hashed on one run, while naming that same model in
    ``AUTO_SCORING_CODEX_MODEL`` recorded it verbatim on the next -- and
    merely adding an *unused* fallback link that named it was enough to flip
    the representation. ``report.py`` then split one model's samples into
    two buckets and the comparison across a resumed run fell apart (code
    review finding). The rule now depends on the *field*, never on the run:

    * ``model`` and ``version`` are **always** fingerprinted. Both can carry
      a value the service chose -- ``version`` by definition (Gemini's
      ``modelVersion``, OpenRouter's routed model + upstream, Codex's CLI
      user agent), and ``model`` whenever the adapter learns it from the
      service rather than from configuration (``CodexAppServerProvider``
      reports ``"default"`` until Codex resolves it). Hashing unconditionally
      is what makes the identity independent of the run, and it also means
      no adapter can leak an unverified string through either field, now or
      later.
    * ``prompt_version``, ``temperature`` and ``structured_output_mode`` are
      written verbatim. No adapter derives them from a response: the first
      two are constructor arguments this repository's own configuration
      supplies, the third is a constant in each adapter module. Recording
      them as-is keeps the results table's ``config`` column readable where
      it can be.

    Which model a fingerprint stands for is printed once at the end of a run
    (see :func:`main`) and can be recomputed at any time -- see
    ``docs/poc-2-ai-grading.md`` section 4.3. It is deliberately not written
    into the dataset file, which sits next to student work.

    ``provider`` is deliberately *not* part of this block: ``report.py``
    takes the provider id from the cell's key in ``recorded`` and would
    reject an extra field here (``_DescriptorInput``, ``extra="forbid"``).
    """
    return {
        "model": _fingerprint(descriptor.model),
        "version": None if descriptor.version is None else _fingerprint(descriptor.version),
        "prompt_version": descriptor.prompt_version,
        "temperature": descriptor.temperature,
        "structured_output_mode": descriptor.structured_output_mode,
    }


def _call_with_backoff(
    provider: AIProvider,
    cell: _Cell,
    *,
    sleep: Callable[[float], None],
) -> tuple[ProviderDescriptor, dict[str, Any], float]:
    """One cell's outcome, retrying transient failures per section 7.2.

    Returns ``(descriptor, cell body, wall-clock seconds)``. The wall-clock
    figure is for the progress line only -- it includes any backoff waits,
    which the cell's own ``latency_seconds`` deliberately does not.

    The descriptor's ``provider`` is the ``recorded`` key this outcome
    belongs under: for a success, the descriptor of whichever adapter
    answered (with a fallback chain, not necessarily the first link); for a
    failure, which has no response to read it from, the provider's own
    ``describe()``, which for a chain follows the last attempted child
    (``FallbackAIProvider.describe``). The whole descriptor comes back, not
    just that id, so the caller can print the fingerprint legend without
    re-deriving anything.

    Exponential backoff (1s initial, 32s cap, 5 attempts) applies to
    :class:`ProviderUnavailable` only. A :class:`SchemaViolation` is *not*
    retried: re-sending the same request to the same model reproduces it
    (docs/ai-grading-pipeline.md), and retrying would only add to the bill.
    """
    started_at = time.monotonic()
    backoff = _INITIAL_BACKOFF_SECONDS
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        # Timed per attempt, not from `started_at`: what belongs in the cell
        # is how long the provider took, and folding in this loop's own
        # backoff sleeps (up to 15s before the final attempt) would inflate
        # the p50/p95 latency of every bucket that ever had to retry --
        # numbers section 8.1 gates adoption on.
        attempt_started_at = time.monotonic()
        try:
            response = provider.grade(cell.request)
        except SchemaViolation:
            descriptor = provider.describe()
            return (
                descriptor,
                {
                    "schema_violation": True,
                    "descriptor": _wire_descriptor(descriptor),
                    "latency_seconds": time.monotonic() - attempt_started_at,
                },
                time.monotonic() - started_at,
            )
        except ProviderUnavailable:
            if attempt == _MAX_ATTEMPTS:
                descriptor = provider.describe()
                return (
                    descriptor,
                    {
                        "unavailable": True,
                        "descriptor": _wire_descriptor(descriptor),
                        "latency_seconds": time.monotonic() - attempt_started_at,
                    },
                    time.monotonic() - started_at,
                )
            sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
            continue
        return (
            response.descriptor,
            {
                "response": _wire_response(response, criterion_ids=cell.request.criterion_ids),
                "descriptor": _wire_descriptor(response.descriptor),
                # `GradingResponse` carries the successful call's own
                # measurement, taken inside the adapter around the HTTP
                # call itself.
                "latency_seconds": response.latency_seconds,
            },
            time.monotonic() - started_at,
        )
    raise AssertionError("unreachable: the loop always returns")  # pragma: no cover


def _write_atomically(path: Path, document: dict[str, Any]) -> None:
    """Replace ``path`` only once the new content is fully on disk.

    A crash midway through a long recording run must not leave a truncated
    dataset file: the ground-truth labels in it are hand-made and, for the
    real dataset, expensive to reproduce.
    """
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(document, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _is_inside_repository(dataset: Path) -> bool:
    """Whether ``dataset`` resolves to somewhere inside this repository.

    ``resolve()`` on both sides is the point: an earlier version compared
    the bundled fixture directory for equality only, so copying the
    fixtures to any other directory in the working tree -- or pointing a
    symlink from outside back into it -- was enough to write live provider
    output into a tracked path (code review finding).
    """
    try:
        return dataset.resolve().is_relative_to(_REPOSITORY_ROOT)
    except OSError:
        # An unresolvable path is not a "safe" path; let the dataset loader
        # report it properly instead of treating it as outside the repo.
        return False


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="PoC 2 live-provider path: call a real AIProvider and record its responses"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--images", type=Path, required=True, help="directory of answer-region crops"
    )
    parser.add_argument("--variant", choices=[*_INPUT_VARIANTS, "both"], default="both")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many calls")
    parser.add_argument(
        "--overwrite", action="store_true", help="re-record cells that already have an outcome"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the dataset and report what would be called; make no provider call",
    )
    args = parser.parse_args(argv)

    dataset: Path = args.dataset
    if _is_inside_repository(dataset):
        raise SystemExit(
            "refusing to record into a dataset inside this repository -- a real provider's "
            "response body must never reach a commit (docs/poc-2-ai-grading.md section 11). "
            "Copy the dataset to a directory outside the repository first."
        )
    variants = _INPUT_VARIANTS if args.variant == "both" else (args.variant,)

    # Built before planning, not after: which cells still need a call
    # depends on which provider this run files under (`_already_recorded`).
    # A dry run deliberately skips this, so validating a dataset needs no
    # credentials at all.
    provider: AIProvider | None = None
    if not args.dry_run:
        try:
            provider = create_ai_provider()
        except AIProviderConfigError as exc:
            raise SystemExit(f"AI provider is not configured: {exc}") from None

    try:
        cells = _plan(
            dataset=dataset,
            images=args.images,
            variants=variants,
            overwrite=args.overwrite,
            provider_id=None if provider is None else provider.describe().provider,
        )
    except _DatasetError as exc:
        raise SystemExit(str(exc)) from None
    if args.limit is not None:
        cells = cells[: max(args.limit, 0)]

    print(f"cells to record: {len(cells)}")
    if provider is None or not cells:
        print("dry run: no provider call was made" if args.dry_run else "nothing to do")
        return 0

    outcomes = {"response": 0, "schema_violation": 0, "unavailable": 0}
    touched: dict[Path, dict[str, Any]] = {}
    #: What each recorded ``model``/``version`` fingerprint stands for.
    #: Printed once at the end and never written to a file: the dataset sits
    #: next to student work, this terminal does not.
    legend: dict[str, str] = {}
    for number, cell in enumerate(cells, start=1):
        descriptor, body, elapsed = _call_with_backoff(provider, cell, sleep=time.sleep)
        provider_id = descriptor.provider
        legend[_fingerprint(descriptor.model)] = descriptor.model
        if descriptor.version is not None:
            legend[_fingerprint(descriptor.version)] = descriptor.version
        question = cell.document["questions"][cell.question_index]
        question["recorded"].setdefault(provider_id, {})[cell.variant] = body
        touched[cell.path] = cell.document

        outcome = next(key for key in outcomes if key in body)
        outcomes[outcome] += 1
        # Counts, ids, and a duration only -- never question text, OCR text,
        # a score, or a response body (AGENTS.md "Security").
        print(f"[{number}/{len(cells)}] {cell.variant} -> {provider_id} {outcome} ({elapsed:.1f}s)")

        # Written after every call, not once at the end: a run against the
        # real dataset costs real money, and losing it to a crash on the
        # last cell would mean paying for all of it again.
        _write_atomically(cell.path, cell.document)

    print(
        f"\nrecorded: {outcomes['response']} response, "
        f"{outcomes['schema_violation']} schema violation, "
        f"{outcomes['unavailable']} unavailable "
        f"across {len(touched)} file(s)"
    )
    if legend:
        # The one place a fingerprint is resolved back to what it stands
        # for. Recomputable later from the model/deployment name itself
        # (docs/poc-2-ai-grading.md section 4.3), so nothing is lost by
        # keeping it out of the dataset.
        print("\nfingerprints recorded in this run:")
        for fingerprint, value in sorted(legend.items(), key=lambda item: item[1]):
            print(f"  {fingerprint}  {value}")
    print("\nrun report.py --dataset <the same directory> to aggregate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
