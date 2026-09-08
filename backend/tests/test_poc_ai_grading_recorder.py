"""Tests for the PoC 2 live-provider path (``poc/issue_14_ai_grading/record.py``,
Issue #35).

``poc/`` holds technical probes, not shipped code, and most of them are
verified only by their documented repro command. This one is tested because
its failure modes are silent and expensive: a mis-resolved crop makes two
candidates look compared when they were not, a lost outcome makes a real
(paid) call vanish, and a fabricated outcome would put a number that no
provider produced in front of an adoption decision. None of those show up as
a crash.

The provider is always a stub -- no network call, no credentials.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from auto_scoring.domain.ai_provider import (
    GradingCriterionOutcome,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderRateLimitedError,
    SchemaViolation,
)
from auto_scoring.domain.models import CriterionOutcome

_FIXTURES = Path(__file__).parent / "fixtures" / "ai_grading"
_RECORD_PY = Path(__file__).resolve().parents[1] / "poc" / "issue_14_ai_grading" / "record.py"


def _load_record_module() -> ModuleType:
    """Import ``record.py`` by path -- ``poc/`` is deliberately not a package
    (it is not shipped and nothing in ``src/`` may import it)."""
    spec = importlib.util.spec_from_file_location("poc_ai_grading_record", _RECORD_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


record = _load_record_module()


class _StubProvider:
    """Returns a canned grade, or raises ``failure`` a fixed number of times."""

    name = "stub"

    def __init__(self, failure: Exception | None = None, *, failures: int = 10_000) -> None:
        self._failure = failure
        self._remaining_failures = failures
        self.calls = 0

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model="stub-model",
            version="stub-version",
            prompt_version="v1",
            temperature=0.0,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        self.calls += 1
        if self._failure is not None and self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise self._failure
        return GradingResponse(
            question_id=request.question_id,
            recognition_text=request.ocr_text,
            recognition_confidence=0.9,
            score=4,
            max_score=request.max_score,
            grading_confidence=0.8,
            rationale="根拠",
            comment="コメント",
            # A criterion is required on the wire (`AIGradingResult`), and
            # what is recorded has to be re-readable by `report.py` -- a
            # stub returning none would write a cell that silently counts
            # as a schema violation.
            criteria=(
                GradingCriterionOutcome(
                    criterion_id="c1",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale="根拠",
                ),
            ),
            annotations=(),
            descriptor=self.describe(),
            latency_seconds=1.25,
        )


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """A copy of one synthetic fixture with its ``recorded`` block emptied."""
    directory = tmp_path / "dataset"
    directory.mkdir()
    document = json.loads((_FIXTURES / "sample-01.json").read_text(encoding="utf-8"))
    for question in document["questions"]:
        question["recorded"] = {}
    (directory / "sample-01.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return directory


def _cell(dataset: Path, provider: str, variant: str) -> dict[str, Any]:
    document = json.loads((dataset / "sample-01.json").read_text(encoding="utf-8"))
    cell = document["questions"][0]["recorded"][provider][variant]
    assert isinstance(cell, dict)
    return cell


def _run(dataset: Path, provider: _StubProvider, **kwargs: Any) -> None:
    cells = record._plan(
        dataset=dataset,
        images=_FIXTURES / "images",
        variants=("ocr_clean",),
        overwrite=bool(kwargs.get("overwrite")),
        provider_id=provider.describe().provider,
    )
    for cell in cells:
        provider_id, body, _elapsed = record._call_with_backoff(
            provider, cell.request, sleep=lambda _seconds: None
        )
        cell.document["questions"][cell.question_index]["recorded"].setdefault(provider_id, {})[
            cell.variant
        ] = body
        record._write_atomically(cell.path, cell.document)


def test_a_successful_call_is_recorded_in_the_shape_report_py_reads(dataset: Path) -> None:
    _run(dataset, _StubProvider())

    cell = _cell(dataset, "stub", "ocr_clean")
    assert cell["descriptor"] == {
        "model": "stub-model",
        "version": "stub-version",
        "prompt_version": "v1",
        "temperature": 0.0,
        "structured_output_mode": "json_schema",
    }
    # `provider` is not part of the descriptor block: report.py takes the
    # provider id from the cell's key and rejects the extra field.
    assert "provider" not in cell["descriptor"]
    assert cell["response"]["questionId"] == "poc2-synth-01"
    assert cell["latency_seconds"] == 1.25


def test_a_schema_violation_is_recorded_as_such_not_as_a_guessed_grade(dataset: Path) -> None:
    """Issue #14 acceptance. The adapters never expose the offending body
    (it can hold OCR'd student text), so the alternative to this explicit
    marker would be inventing a response that happens to fail validation."""
    _run(dataset, _StubProvider(SchemaViolation("bad")))

    cell = _cell(dataset, "stub", "ocr_clean")
    assert cell["schema_violation"] is True
    assert "response" not in cell
    assert cell["descriptor"]["model"] == "stub-model"


def test_a_schema_violation_is_never_retried(dataset: Path) -> None:
    """Re-sending the same request to the same model reproduces it
    (docs/ai-grading-pipeline.md); retrying would inflate the latency
    measurement and the bill for no new information."""
    provider = _StubProvider(SchemaViolation("bad"))
    _run(dataset, provider)
    assert provider.calls == 1


def test_a_transient_failure_is_retried_and_then_succeeds(dataset: Path) -> None:
    """docs/poc-2-ai-grading.md section 7.2 assigns the backoff to this
    live-provider path -- the adapters raise once, with no built-in retry."""
    provider = _StubProvider(ProviderRateLimitedError("429"), failures=2)
    _run(dataset, provider)

    assert provider.calls == 3
    assert "response" in _cell(dataset, "stub", "ocr_clean")


def test_a_persistent_failure_is_recorded_as_unavailable(dataset: Path) -> None:
    """Section 7.2: "恒常的な 429 / quota 超過は失敗として記録し、推測で
    埋めない" -- and never left indistinguishable from a pending cell."""
    provider = _StubProvider(ProviderRateLimitedError("429"))
    _run(dataset, provider)

    cell = _cell(dataset, "stub", "ocr_clean")
    assert cell["unavailable"] is True
    assert "response" not in cell
    assert provider.calls == record._MAX_ATTEMPTS


def test_an_already_recorded_cell_is_skipped_so_a_run_can_resume(dataset: Path) -> None:
    provider = _StubProvider()
    _run(dataset, provider)
    _run(dataset, provider)
    assert provider.calls == 1

    _run(dataset, provider, overwrite=True)
    assert provider.calls == 2


def test_a_second_candidate_records_alongside_the_first(dataset: Path) -> None:
    """PoC 2 compares candidates on the *same* samples, so recording a
    second provider onto a dataset the first has already run against is the
    normal case -- it must not be skipped as "already recorded"."""
    first = _StubProvider()
    second = _StubProvider()
    second.name = "stub-2"

    _run(dataset, first)
    _run(dataset, second)

    document = json.loads((dataset / "sample-01.json").read_text(encoding="utf-8"))
    assert sorted(document["questions"][0]["recorded"]) == ["stub", "stub-2"]


def test_a_crop_whose_hash_does_not_match_its_reference_is_rejected(
    dataset: Path, tmp_path: Path
) -> None:
    """docs/poc-2-ai-grading.md section 3.12: two candidates silently graded
    against different or stale crops would still look like a same-data
    comparison."""
    images = tmp_path / "images"
    images.mkdir()
    document = json.loads((dataset / "sample-01.json").read_text(encoding="utf-8"))
    digest = document["questions"][0]["input"]["answer_image_ref"].removeprefix("sha256:")
    (images / f"{digest}.png").write_bytes(b"different bytes entirely")

    with pytest.raises(record._DatasetError, match="content hash"):
        record._plan(
            dataset=dataset,
            images=images,
            variants=("ocr_clean",),
            overwrite=False,
            provider_id="stub",
        )


def test_a_missing_crop_aborts_before_any_call_is_made(dataset: Path, tmp_path: Path) -> None:
    """The whole dataset is validated up front: a malformed sample must
    abort the run before money is spent, not halfway through it."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(record._DatasetError, match="no crop"):
        record._plan(
            dataset=dataset,
            images=empty,
            variants=("ocr_clean",),
            overwrite=False,
            provider_id="stub",
        )


@pytest.mark.parametrize("ref", ["../secrets.png", "sub/dir.png", "sha256:not-a-digest"])
def test_a_reference_that_is_a_path_or_a_malformed_digest_is_rejected(
    tmp_path: Path, ref: str
) -> None:
    """The dataset is untrusted input; a reference must not reach outside
    the crop directory it was given (AGENTS.md "Security")."""
    with pytest.raises(record._DatasetError):
        record._load_image(tmp_path, ref)


def test_a_verified_crop_is_returned_by_content_hash(tmp_path: Path) -> None:
    data = b"synthetic crop bytes"
    digest = hashlib.sha256(data).hexdigest()
    (tmp_path / f"{digest}.png").write_bytes(data)

    assert record._load_image(tmp_path, f"sha256:{digest}") == data


def test_recording_into_the_committed_fixtures_is_refused() -> None:
    """A real provider's response body must never reach a commit
    (docs/poc-2-ai-grading.md section 11)."""
    with pytest.raises(SystemExit, match="refusing to record"):
        record.main(["--dataset", str(_FIXTURES), "--images", str(_FIXTURES / "images")])


def test_a_dry_run_validates_without_credentials_or_calls(
    dataset: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = record.main(
        [
            "--dataset",
            str(dataset),
            "--images",
            str(_FIXTURES / "images"),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert "no provider call was made" in capsys.readouterr().out
    # Nothing was written.
    document = json.loads((dataset / "sample-01.json").read_text(encoding="utf-8"))
    assert document["questions"][0]["recorded"] == {}


# --- the two halves have to agree about what was recorded ---


def _load_report_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "poc_ai_grading_report", _RECORD_PY.with_name("report.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_py_reads_back_exactly_what_record_py_wrote(dataset: Path) -> None:
    """The round trip is the point of both scripts, and the two halves live
    in separate files: a cell shape ``record.py`` writes but ``report.py``
    classifies differently would show up as a wrong adoption number, not as
    an error. Two candidates on the same sample and variant, one of them
    schema-violating, is the smallest case that exercises the comparison
    gate, the schema-violation count, and the descriptor bucketing at once.
    """
    report = _load_report_module()

    good = _StubProvider()
    bad = _StubProvider(SchemaViolation("bad"))
    bad.name = "gemini"
    good.name = "openrouter"
    _run(dataset, good)
    _run(dataset, bad)

    outcomes, pending, staged, excluded, unavailable, _coverage = report._load_samples(dataset)

    assert staged == 0 and excluded == 0 and unavailable == 0
    # One cell per candidate for `ocr_clean`; `ocr_noisy` was never run, so
    # it is pending for both -- reported, never silently dropped.
    assert pending == 2
    assert len(outcomes) == 2
    assert sorted(outcome.provider for outcome in outcomes) == ["gemini", "openrouter"]
    violations = [outcome for outcome in outcomes if outcome.schema_violation]
    assert [outcome.provider for outcome in violations] == ["gemini"]
    assert not any(outcome.unavailable for outcome in outcomes)
