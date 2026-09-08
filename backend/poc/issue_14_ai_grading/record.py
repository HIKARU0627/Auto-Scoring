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
* **It never writes into the repository.** ``--dataset`` pointing at the
  committed synthetic fixtures is refused outright: a real provider's
  response body must not end up in a commit.
* **It verifies image identity.** An ``answer_image_ref`` of the form
  ``sha256:<hex>`` is checked against the bytes actually read, so a stale or
  swapped crop cannot silently make two providers look like they were
  compared on the same input (docs/poc-2-ai-grading.md section 3.12).
* **It never fabricates an outcome.** A response that fails schema
  validation is recorded as ``schema_violation: true`` and a call that
  exhausts its retries as ``unavailable: true`` -- never as a guessed grade,
  and never left indistinguishable from a cell nobody has tried yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.domain.ai_grading_metrics import GradingInputRecord
from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
)

_BUNDLED_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_grading"

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


def _load_image(images: Path, ref: str) -> bytes:
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
    """
    if ref.startswith("sha256:"):
        digest = ref[len("sha256:") :].strip().lower()
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            raise _DatasetError(f"answer_image_ref {ref!r} is not a valid sha256 hex digest")
        for extension in _IMAGE_EXTENSIONS:
            candidate = images / f"{digest}{extension}"
            if candidate.is_file():
                data = candidate.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != digest:
                    raise _DatasetError(
                        f"{candidate}: content hash does not match its answer_image_ref -- "
                        "the crop this sample was labelled against is not the crop on disk"
                    )
                return data
        raise _DatasetError(
            f"no crop for answer_image_ref {ref!r} under {images} "
            f"(looked for {digest}<{'|'.join(_IMAGE_EXTENSIONS)}>)"
        )

    if "/" in ref or "\\" in ref or ref in {".", ".."}:
        raise _DatasetError(
            f"answer_image_ref {ref!r} is neither a sha256: digest nor a plain file name; "
            "a path is not accepted here"
        )
    candidate = images / ref
    if not candidate.is_file():
        raise _DatasetError(f"no crop named {ref!r} under {images}")
    return candidate.read_bytes()


def _question_id(question: dict[str, Any], *, path: Path, index: int) -> str:
    """The opaque question id this cell's response must echo back.

    Read from ``ground_truth`` (the human label), not invented here: the
    request's ``questionId`` is what ``report.py`` later cross-checks the
    response against to reject an answer to a different question
    (``evaluate_sample``'s ``mismatched``).
    """
    truth = question.get("ground_truth")
    question_id = truth.get("questionId") if isinstance(truth, dict) else None
    if not isinstance(question_id, str) or not question_id.strip():
        raise _DatasetError(
            f"{path} question {index}: ground_truth.questionId is missing or not a non-blank string"
        )
    return question_id


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
            try:
                input_record = GradingInputRecord.from_mapping(question["input"])
            except KeyError:
                raise _DatasetError(f"{path} question {index}: has no 'input' block") from None
            except ValidationError:
                # Deliberately not the ValidationError's own message:
                # pydantic keeps the offending value under ``input_value``,
                # which here is transcribed student answer text (AGENTS.md
                # "Security"; report.py's `_sanitize_validation_error`).
                raise _DatasetError(f"{path} question {index}: 'input' failed validation") from None
            question_id = _question_id(question, path=path, index=index)
            image = _load_image(images, input_record.answer_image_ref)
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
                            question_id=question_id,
                            prompt_text=input_record.prompt_text,
                            answer_image=image,
                            ocr_text=ocr_text,
                            model_answer=input_record.model_answer,
                            rubric_text=input_record.rubric_text,
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


def _wire_response(response: GradingResponse) -> dict[str, Any]:
    """The validated response, back in its camelCase wire shape.

    Round-tripped from the already-parsed :class:`GradingResponse` rather
    than from the provider's raw body: what is recorded is then exactly what
    passed ``parse_ai_grading_result``, so ``report.py`` re-reading the file
    cannot disagree with what this run scored (and no un-validated bytes
    from a remote service are written to disk).
    """
    return {
        "questionId": response.question_id,
        "recognition": {
            "text": response.recognition_text,
            "confidence": response.recognition_confidence,
        },
        "grading": {
            "score": response.score,
            "maxScore": response.max_score,
            "confidence": response.grading_confidence,
        },
        "criteria": [
            {
                "id": criterion.criterion_id,
                "result": criterion.outcome.value,
                "confidence": criterion.confidence,
                "rationale": criterion.rationale,
            }
            for criterion in response.criteria
        ],
        "comment": response.comment,
        "rationale": response.rationale,
        "annotations": [
            {"target": a.target, "type": a.type.value, "comment": a.comment}
            for a in response.annotations
        ],
    }


def _wire_descriptor(descriptor: ProviderDescriptor) -> dict[str, Any]:
    """The ``descriptor`` block ``report.py`` requires on every recorded cell.

    ``provider`` is deliberately *not* part of it: ``report.py`` takes the
    provider id from the cell's key in ``recorded`` and would reject an
    extra field here (``_DescriptorInput``, ``extra="forbid"``).
    """
    return {
        "model": descriptor.model,
        "version": descriptor.version,
        "prompt_version": descriptor.prompt_version,
        "temperature": descriptor.temperature,
        "structured_output_mode": descriptor.structured_output_mode,
    }


def _call_with_backoff(
    provider: AIProvider, request: GradingRequest, *, sleep: Callable[[float], None]
) -> tuple[str, dict[str, Any], float]:
    """One cell's outcome, retrying transient failures per section 7.2.

    Returns ``(provider id, cell body, wall-clock seconds)``. The wall-clock
    figure is for the progress line only -- it includes any backoff waits,
    which the cell's own ``latency_seconds`` deliberately does not.

    The provider id is the ``recorded`` key this outcome belongs under: for
    a success, the descriptor of whichever adapter answered (with a
    fallback chain, not necessarily the first link); for a failure, which
    has no response to read it from, the provider's own ``describe()``,
    which for a chain follows the last attempted child
    (``FallbackAIProvider.describe``).

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
            response = provider.grade(request)
        except SchemaViolation:
            descriptor = provider.describe()
            return (
                descriptor.provider,
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
                    descriptor.provider,
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
            response.descriptor.provider,
            {
                "response": _wire_response(response),
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
    if dataset.resolve() == _BUNDLED_FIXTURES.resolve():
        # The bundled fixtures are committed, and a real provider's response
        # body must never be (docs/poc-2-ai-grading.md section 11). Copy
        # them elsewhere first to rehearse the wiring.
        raise SystemExit(
            "refusing to record into the committed synthetic fixtures "
            f"({_BUNDLED_FIXTURES}) -- copy them to a directory outside the repository first"
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
    for number, cell in enumerate(cells, start=1):
        provider_id, body, elapsed = _call_with_backoff(provider, cell.request, sleep=time.sleep)
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
    print("run report.py --dataset <the same directory> to aggregate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
