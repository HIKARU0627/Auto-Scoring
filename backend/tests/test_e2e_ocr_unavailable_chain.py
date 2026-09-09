"""Issue #114 acceptance 7: a dependency chain finishes on a host with no OCR,
without a human pressing /resume on anything.

**This is the shipped composition, not a scenario.** `api.sidecar` used to
pass no ``ocr_provider`` to `create_app` at all, so every install ran the
placeholder adapter and the app behaved exactly the way the first test below
would have failed: scores and comments came out (the grading provider is
multimodal and reads the answer-area crop directly), but every question was
``usable=False`` -- Recognition Confidence 0.0 on an empty reading -- so every
dependent question sat `BLOCKED` until a human released its prerequisite one
at a time. For an app whose whole premise is 採点の自動化, that is the failure
that matters, and it is not one any test in the tree could see: they all
inject an OCR provider.

So these run the *real* stack (real queue, real `GradingJobProcessor`, real
SQLite, real crops) with the OCR half left exactly as an unconfigured machine
has it, and only the AI provider scripted -- because scripting that is what
makes the run deterministic, not what makes it representative.

Design references: section 24 ("OCR失敗: **採点は止めない。**"), section 8.1.5
(OCR is off the grading critical path since Issue #95 decision 10), and
business-rules-and-evaluation-data.md section 4.3 (with no OCR text, it is the
grading AI's own reading that carries into a dependent question).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from auto_scoring.adapters.ocr.unconfigured_provider import UnconfiguredOCRProvider
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from tests.test_e2e_acceptance import (
    _AUTH as E2E_AUTH,
)
from tests.test_e2e_acceptance import (
    ScriptedAIProvider,
    _jobs,
    _question_ids,
    _session_factory,
    build_app_client,
    register_ready_test,
    start_jobs,
    upload_answer,
    wait_until_settled,
)

#: The same bearer token `build_app_client` mints for this app.
_AUTH = dict(E2E_AUTH)


@pytest.fixture
def ai_provider() -> ScriptedAIProvider:
    return ScriptedAIProvider()


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(data_root: Path, ai_provider: ScriptedAIProvider) -> Iterator[TestClient]:
    """The app as an unconfigured machine builds it: no OCR provider, the
    reason an operator would actually see, and everything else real."""
    with build_app_client(
        data_root,
        UnconfiguredOCRProvider("AUTO_SCORING_DOCUMENT_AI_PROCESSOR is not set"),
        ai_provider,
    ) as test_client:
        yield test_client


def _register_chain(client: TestClient) -> str:
    test_id = register_ready_test(client)
    question_ids = _question_ids(test_id)
    # Re-confirm the graph with the edge in place. `register_ready_test`
    # confirms an edgeless graph first because the question ids are only
    # derived once the profile is confirmed.
    analyzed = client.post(
        f"/tests/{test_id}/dependency-graph/analyze", headers=_AUTH, json={"overrides": []}
    )
    assert analyzed.status_code == 200, analyzed.text
    confirmed = client.post(
        f"/tests/{test_id}/dependency-graph/confirm",
        headers=_AUTH,
        json={
            "version": analyzed.json()["version"],
            "edges": [
                {
                    "from_question_id": question_ids[0],
                    "to_question_id": question_ids[1],
                    "provides": ["score"],
                    "rationale": "(2) は (1) の答えを使う",
                }
            ],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    return test_id


def test_a_dependency_chain_finishes_without_ocr_and_without_a_human(
    client: TestClient, data_root: Path, ai_provider: ScriptedAIProvider
) -> None:
    """The regression this Issue exists for.

    No ``/resume`` is called anywhere in this test. If the OCR term were
    still gating -- which it was, against a fabricated confidence of 0.0 --
    the dependent question's job would still be `BLOCKED` when the queue goes
    quiet, and the last assertion would fail.
    """
    test_id = _register_chain(client)
    submission_id = upload_answer(client, test_id, marker="ans-a", student_label="A01")

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    jobs = _jobs(client, submission_id)
    assert {job["question_id"] for job in jobs} == set(_question_ids(test_id))
    assert [job["state"] for job in jobs] == ["succeeded", "succeeded"]
    assert all(job["usable"] for job in jobs)


def test_the_dependent_question_is_graded_with_its_prerequisite_s_result(
    client: TestClient, ai_provider: ScriptedAIProvider
) -> None:
    """The chain did not merely finish -- it carried something forward.

    With no OCR text to hand on, business-rules-and-evaluation-data.md
    section 4.3 says what crosses into a dependent question is the grading
    AI's own reading and the prerequisite's result. Asserting the edge was
    honoured, not just unblocked, is what keeps "released the dependent" from
    quietly becoming "released it against nothing".
    """
    test_id = _register_chain(client)
    submission_id = upload_answer(client, test_id, marker="ans-c", student_label="A03")

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    dependent_id = _question_ids(test_id)[1]
    dependent = next(r for r in ai_provider.requests if r.question_id == dependent_id)
    assert [entry.question_id for entry in dependent.prerequisite_context] == [
        _question_ids(test_id)[0]
    ]


def test_no_recognition_row_is_written_for_the_ocr_half(
    client: TestClient, data_root: Path, ai_provider: ScriptedAIProvider
) -> None:
    """Acceptance 8, at the level that actually distinguishes the two cases.

    "This host has no OCR" leaves no `RecognitionResult` for the OCR half at
    all. The deleted ``NullOCRProvider`` wrote one reading ``text=""``,
    ``confidence=0.0`` -- which in the review UI is indistinguishable from an
    OCR that looked at the crop and found nothing, and which design section
    8.1.4 forbids outright ("読めていないものに数値を与えない").

    What *is* written is the grading AI's own reading, under its own id --
    the one design section 8.1.3 says must never be mixed with the OCR's.
    """
    test_id = _register_chain(client)
    submission_id = upload_answer(client, test_id, marker="ans-b", student_label="A02")

    start_jobs(client, submission_id)
    wait_until_settled(client, submission_id)

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        for question_id in _question_ids(test_id):
            readings = uow.recognitions.history(submission_id, question_id)
            assert [reading.id.split(":")[0] for reading in readings] == ["grading-recognition"]


def test_the_app_says_ocr_is_unavailable_and_says_why(client: TestClient) -> None:
    """Acceptance 8, at the level a person sees.

    Not a blocker -- grading ran fine above. It is how an operator learns
    that verification on this machine is weaker than it looks: the
    cross-check against the grading AI's own reading is gone, and so are
    text-anchored annotation positions (design section 8.1.5).
    """
    body: dict[str, Any] = client.get("/ocr/availability", headers=_AUTH).json()

    assert body["available"] is False
    assert "AUTO_SCORING_DOCUMENT_AI_PROCESSOR" in body["reason"]
