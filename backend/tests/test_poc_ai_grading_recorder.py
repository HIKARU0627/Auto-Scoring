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
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from auto_scoring.domain.ai_grading import parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    GradingAnnotationCandidate,
    GradingCriterionOutcome,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderRateLimitedError,
    SchemaViolation,
)
from auto_scoring.domain.models import AnnotationKind, CriterionOutcome

#: Stands in for content only the provider could have put there -- a
#: student's transcribed answer, a name, a secret. The stub below returns it
#: in every string it controls, and the guard test asserts it never reaches
#: the file. Deliberately not split per field: the rule being pinned is
#: "nothing this run did not send is written", not "these particular fields
#: are redacted", so one marker checked against the whole file catches a
#: field that is added later and forgotten (code review finding).
_ANSWER_TEXT = "生徒答案の本文サンプル"

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

    def __init__(
        self,
        failure: Exception | None = None,
        *,
        failures: int = 10_000,
        hostile: bool = False,
    ) -> None:
        self._failure = failure
        self._remaining_failures = failures
        #: A schema-valid provider that returns content in every string it
        #: controls -- the ids and the deployment metadata included, not
        #: just the fields that obviously hold prose.
        self._hostile = hostile
        #: Overridden by the COMMENT-annotation regression test below.
        self.annotation_kind = AnnotationKind.UNDERLINE
        self.calls = 0

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model="stub-model",
            version=_ANSWER_TEXT if self._hostile else "stub-version",
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
            question_id=_ANSWER_TEXT if self._hostile else request.question_id,
            recognition_text=_ANSWER_TEXT,
            recognition_confidence=0.9,
            score=4,
            max_score=request.max_score,
            grading_confidence=0.8,
            rationale=f"{_ANSWER_TEXT}と模範解答を比較した。",
            comment=f"{_ANSWER_TEXT}の部分が惜しい。",
            # A criterion is required on the wire (`AIGradingResult`), and
            # what is recorded has to be re-readable by `report.py` -- a
            # stub returning none would write a cell that silently counts
            # as a schema violation.
            criteria=(
                GradingCriterionOutcome(
                    criterion_id=_ANSWER_TEXT if self._hostile else "c1",
                    outcome=CriterionOutcome.PASS,
                    confidence=0.9,
                    rationale=f"{_ANSWER_TEXT}が条件を満たす。",
                ),
            ),
            annotations=(
                GradingAnnotationCandidate(
                    target=_ANSWER_TEXT, type=self.annotation_kind, comment=_ANSWER_TEXT
                ),
            ),
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
    configured = record._configured_descriptors(provider)
    for cell in cells:
        provider_id, body, _elapsed = record._call_with_backoff(
            provider, cell, configured=configured, sleep=lambda _seconds: None
        )
        cell.document["questions"][cell.question_index]["recorded"].setdefault(provider_id, {})[
            cell.variant
        ] = body
        record._write_atomically(cell.path, cell.document)


@pytest.mark.parametrize("failure", [None, SchemaViolation("bad"), ProviderRateLimitedError("429")])
def test_no_provider_controlled_text_reaches_the_recorded_file(
    dataset: Path, failure: Exception | None
) -> None:
    """Issue #35 acceptance: "secret・答案本文・生徒識別情報がログ・出力・
    リポジトリに残らない".

    The provider here is schema-valid but hostile: it puts content in every
    string it controls -- the recognized reading, comment, rationale,
    criterion rationale, annotation target, **and** the ``questionId``, the
    ``criteria[].id`` and the deployment metadata. Those last three were
    waved through by the first fix on the grounds that "the metrics read
    them, so they are safe"; schema validation checks the *shape* of a
    value and says nothing about its content, so that reasoning does not
    hold (code review finding).

    Asserted against the whole file, not against the fields known to be
    redacted, so a field added later and forgotten is caught by this same
    test. Run for all three outcomes because a failed call still records a
    descriptor, and the deployment metadata leaked through that path even
    when the response itself was rejected.
    """
    _run(dataset, _StubProvider(failure, hostile=True))

    written = (dataset / "sample-01.json").read_text(encoding="utf-8")
    recorded = json.loads(written)["questions"][0]["recorded"]

    assert _ANSWER_TEXT not in json.dumps(recorded, ensure_ascii=False)


def test_an_unverifiable_id_is_recorded_as_a_marker_that_still_reads_as_a_mismatch(
    dataset: Path,
) -> None:
    """Replacing an unverifiable id must not also erase the disagreement it
    represents: ``evaluate_sample`` counts a response whose ``questionId``
    differs from the label's as ``mismatched``, and a marker that happened
    to equal the label's id would drive that column to zero by
    construction."""
    _run(dataset, _StubProvider(hostile=True))

    response = _cell(dataset, "stub", "ocr_clean")["response"]

    assert response["questionId"] == record._UNVERIFIED_QUESTION_ID
    assert response["questionId"] != "poc2-synth-01"
    assert response["criteria"][0]["id"].startswith(record._UNVERIFIED_CRITERION_ID_PREFIX)


def test_deployment_metadata_is_recorded_as_a_content_free_fingerprint(
    dataset: Path,
) -> None:
    """``descriptor.version`` is whatever the provider reported it ran --
    validated by nothing but "non-blank" (code review finding). Hashing
    keeps what the field is for (two different deployments stay in two
    different ``descriptor_key`` buckets) without persisting a string this
    run cannot check."""
    _run(dataset, _StubProvider(hostile=True))
    hostile_version = _cell(dataset, "stub", "ocr_clean")["descriptor"]["version"]

    assert hostile_version == "sha256:" + hashlib.sha256(_ANSWER_TEXT.encode()).hexdigest()[:16]

    # Distinctness is the whole point: a different deployment must not fall
    # into the same bucket as this one.
    assert hostile_version != "sha256:" + hashlib.sha256(b"another-deployment").hexdigest()[:16]


def test_the_metric_bearing_fields_survive_redaction(dataset: Path) -> None:
    """Redaction must not cost the harness anything it actually scores:
    ``evaluate_sample`` reads the question id, the score/maxScore, the
    criterion ids and outcomes, and the two confidences."""
    _run(dataset, _StubProvider())

    response = _cell(dataset, "stub", "ocr_clean")["response"]

    assert response["questionId"] == "poc2-synth-01"
    assert response["grading"] == {"score": 4, "maxScore": 20, "confidence": 0.8}
    assert response["recognition"]["confidence"] == 0.9
    assert response["criteria"][0]["id"] == "c1"
    assert response["criteria"][0]["result"] == "pass"
    # An annotation's kind carries no content, so "the model proposed one
    # underline" survives even though what it pointed at does not.
    assert response["annotations"][0]["type"] == "underline"


def test_a_successful_call_is_recorded_in_the_shape_report_py_reads(dataset: Path) -> None:
    _run(dataset, _StubProvider())

    cell = _cell(dataset, "stub", "ocr_clean")
    assert cell["descriptor"] == {
        "model": "stub-model",
        # Response-derived, so recorded as a content-free fingerprint
        # rather than verbatim -- see the deployment-metadata test below.
        "version": "sha256:" + hashlib.sha256(b"stub-version").hexdigest()[:16],
        "prompt_version": "v1",
        "temperature": 0.0,
        "structured_output_mode": "json_schema",
    }
    # `provider` is not part of the descriptor block: report.py takes the
    # provider id from the cell's key and rejects the extra field.
    assert "provider" not in cell["descriptor"]
    assert cell["response"]["questionId"] == "poc2-synth-01"
    assert cell["latency_seconds"] == 1.25


def test_a_comment_annotation_stays_schema_valid_after_recording(dataset: Path) -> None:
    """`AnnotationCandidate` requires non-blank comment text on a
    COMMENT-kind annotation. Writing `null` there turned a perfectly good
    response into one `report.py` then counted as a schema violation,
    inflating that provider's violation rate -- a distortion of the
    adoption metrics, not a cosmetic issue (code review finding)."""
    provider = _StubProvider()
    provider.annotation_kind = AnnotationKind.COMMENT

    _run(dataset, provider)

    recorded = _cell(dataset, "stub", "ocr_clean")["response"]
    assert recorded["annotations"][0]["type"] == "comment"
    assert recorded["annotations"][0]["comment"] == record._REDACTED
    # The real check: what was written still parses, which is what
    # `report.py` does before scoring it.
    parse_ai_grading_result(json.dumps(recorded, ensure_ascii=False))


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

    with pytest.raises(record._DatasetError, match="does not hash to"):
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


@pytest.mark.parametrize(
    "ref",
    [
        "../secrets.png",
        "sub/dir.png",
        f"sha256:{_ANSWER_TEXT}",
        f"{_ANSWER_TEXT}.png",
    ],
)
def test_a_reference_that_is_a_path_or_a_malformed_digest_is_rejected(
    tmp_path: Path, ref: str
) -> None:
    """The dataset is untrusted input; a reference must not reach outside
    the crop directory it was given (AGENTS.md "Security").

    And the rejected reference must not appear in the message: `main()`
    prints these to stderr, and a reference that failed validation is by
    definition not known to be a content hash -- it could be answer text or
    a name a malformed dataset put there by mistake (code review finding).
    """
    with pytest.raises(record._DatasetError) as raised:
        record._load_image(tmp_path, ref, locator="sample-01.json question 0")

    assert ref not in str(raised.value)
    assert _ANSWER_TEXT not in str(raised.value)
    assert "sample-01.json question 0" in str(raised.value)


def test_a_verified_crop_is_returned_by_content_hash(tmp_path: Path) -> None:
    data = b"synthetic crop bytes"
    digest = hashlib.sha256(data).hexdigest()
    (tmp_path / f"{digest}.png").write_bytes(data)

    assert record._load_image(tmp_path, f"sha256:{digest}", locator="loc") == data


@pytest.mark.parametrize(
    "inside_repo",
    [
        _FIXTURES,
        _FIXTURES.parent,
        Path(__file__).resolve().parents[2],
    ],
)
def test_recording_anywhere_inside_the_repository_is_refused(inside_repo: Path) -> None:
    """A real provider's response body must never reach a commit
    (docs/poc-2-ai-grading.md section 11).

    Refusing only the bundled fixture directory was not enough: copying the
    fixtures to any other directory in the working tree and pointing
    ``--dataset`` there was enough to write live provider output into a
    tracked path (code review finding)."""
    with pytest.raises(SystemExit, match="refusing to record"):
        record.main(["--dataset", str(inside_repo), "--images", str(_FIXTURES / "images")])


def test_a_symlink_pointing_back_into_the_repository_is_refused(tmp_path: Path) -> None:
    """The check resolves before comparing, so an out-of-tree name is not a
    way around it."""
    link = tmp_path / "looks-external"
    link.symlink_to(_FIXTURES, target_is_directory=True)

    with pytest.raises(SystemExit, match="refusing to record"):
        record.main(["--dataset", str(link), "--images", str(_FIXTURES / "images")])


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


# --- anonymisation must not cost the harness its ability to measure ---


class _LateResolvingProvider(_StubProvider):
    """Reports a placeholder model until the service resolves the real one.

    This is ``CodexAppServerProvider``: with ``AUTO_SCORING_CODEX_MODEL``
    unset, ``describe()`` answers ``"default"`` until the first
    ``thread/start`` comes back, and the real model name afterwards.
    """

    def __init__(self, resolved_model: str) -> None:
        super().__init__()
        self._resolved_model = resolved_model
        self.name = "codex-app-server"

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model="default",
            version="codex-cli/1.2.3",
            prompt_version="v1",
            temperature=0.0,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        response = super().grade(request)
        return replace(
            response, descriptor=replace(response.descriptor, model=self._resolved_model)
        )


def test_two_late_resolved_models_stay_in_two_buckets(dataset: Path, tmp_path: Path) -> None:
    """A model this run could not know up front must still be *distinguished*.

    Matching the descriptor as one ``(model, prompt_version,
    structured_output_mode)`` triple failed on every Codex response -- the
    model differs before and after the call -- and collapsed all three
    fields onto a single marker, so two runs against different Codex models
    landed in the same ``descriptor_key`` bucket and had their metrics
    pooled (code review finding). Safe and measurable are not in tension:
    a fingerprint gives both.
    """
    other = tmp_path / "other"
    other.mkdir()
    (other / "sample-01.json").write_text(
        (dataset / "sample-01.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    _run(dataset, _LateResolvingProvider("gpt-5-codex"))
    _run(other, _LateResolvingProvider("gpt-5-codex-mini"))

    first = _cell(dataset, "codex-app-server", "ocr_clean")["descriptor"]
    second = json.loads((other / "sample-01.json").read_text(encoding="utf-8"))["questions"][0][
        "recorded"
    ]["codex-app-server"]["ocr_clean"]["descriptor"]

    # Neither model name reaches the file...
    assert "gpt-5-codex" not in json.dumps([first, second])
    # ...and the two configurations are still two configurations.
    assert first["model"] != second["model"]
    # The fields this run *did* configure keep their real values, instead of
    # being dragged into the marker with the model.
    assert first["prompt_version"] == second["prompt_version"] == "v1"
    assert first["structured_output_mode"] == second["structured_output_mode"] == "json_schema"


def test_a_max_score_disagreement_is_refused_before_any_call(dataset: Path) -> None:
    """``report.py`` rejects a question whose ``input`` disagrees with its
    label, so recording one spends a call whose result can never be scored.
    Validating each block on its own passed it, which made ``--dry-run``
    report success for a dataset the real run could not use (code review
    finding). This script spends someone else's money."""
    path = dataset / "sample-01.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["questions"][0]["input"]["max_score"] = 999
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(record._DatasetError) as raised:
        record._plan(
            dataset=dataset,
            images=_FIXTURES / "images",
            variants=("ocr_clean",),
            overwrite=False,
            provider_id="stub",
        )

    assert "999" not in str(raised.value)
    assert "sample-01.json question 0" in str(raised.value)


def test_the_dry_run_refuses_the_same_dataset_the_real_run_would(dataset: Path) -> None:
    """The point of the previous test: `--dry-run` has to predict whether
    the paid run's output will be usable, or it is not worth much."""
    path = dataset / "sample-01.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["questions"][0]["input"]["max_score"] = 999
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(SystemExit, match="max_score"):
        record.main(
            [
                "--dataset",
                str(dataset),
                "--images",
                str(_FIXTURES / "images"),
                "--dry-run",
            ]
        )
