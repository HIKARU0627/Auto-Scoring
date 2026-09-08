"""Batch intake planning and classification over HTTP (Issue #101).

The load-bearing test here is
`test_planning_a_rule_matched_batch_never_calls_the_classifier`: acceptance
criterion 8 is that a file whose name a template rule matched is not sent to
a provider, and a fake classifier that records every call is the only way to
assert the *absence* of one.

Every file name in this file is synthetic.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from auto_scoring.api.app import create_app
from auto_scoring.domain.ai_provider import ProviderDescriptor, ProviderUnavailable
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_classifier import (
    AttributionCandidate,
    AttributionProposal,
    ClassifierUnavailable,
    MaterialClassifier,
    RoleProposal,
)
from auto_scoring.domain.pdf_intake import IntakeLimits

_TOKEN = "intake-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


def _descriptor() -> ProviderDescriptor:
    return ProviderDescriptor(
        provider="fake",
        model="fake-model",
        version=None,
        prompt_version="test",
        temperature=0.0,
        structured_output_mode="json_schema",
    )


class _RecordingClassifier:
    """Counts calls, so a test can assert that none happened."""

    def __init__(
        self,
        *,
        role: MaterialRole | None = MaterialRole.REFERENCE,
        candidate_id: str | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.role_calls = 0
        self.attribution_calls = 0
        self._role = role
        self._candidate_id = candidate_id
        self._fail = fail

    def classify_role(self, page_image: bytes) -> RoleProposal:
        self.role_calls += 1
        if self._fail is not None:
            raise self._fail
        return RoleProposal(role=self._role, confidence=0.6, descriptor=_descriptor())

    def attribute_answer(
        self, page_image: bytes, candidates: Sequence[AttributionCandidate]
    ) -> AttributionProposal:
        self.attribution_calls += 1
        if self._fail is not None:
            raise self._fail
        return AttributionProposal(
            candidate_id=self._candidate_id, confidence=0.4, descriptor=_descriptor()
        )


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def classifier() -> _RecordingClassifier:
    return _RecordingClassifier()


@pytest.fixture
def client(tmp_path: Path, classifier: _RecordingClassifier) -> Iterator[TestClient]:
    app = create_app(
        api_token=_TOKEN,
        data_root=tmp_path / "app-data",
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        material_classifier_factory=lambda: classifier,
    )
    with TestClient(app) as test_client:
        yield test_client


def _listing(paths: list[str]) -> list[dict[str, object]]:
    return [
        {"relative_path": path, "size_bytes": 1024, "sha256": f"{index:064x}"}
        for index, path in enumerate(paths)
    ]


_ELEVEN_SUBJECTS = [
    path
    for index in range(11)
    for path in (
        f"subject-{index:02d}/01_answers.pdf",
        f"subject-{index:02d}/02_criteria.pdf",
        f"subject-{index:02d}/03_resource.xls",
        f"subject-{index:02d}/04_1_sample.pdf",
        f"subject-{index:02d}/how-to-use.txt",
    )
]


# --------------------------------------------------------------------------- #
# Acceptance criterion 8
# --------------------------------------------------------------------------- #
def test_planning_a_rule_matched_batch_never_calls_the_classifier(
    client: TestClient, classifier: _RecordingClassifier
) -> None:
    """Issue #101 acceptance criterion 8, asserted as the *absence* of a call.

    Planning is pure rule matching over a listing: no bytes are sent, so
    there is nothing a provider could even be shown. The estimate says zero
    calls, and the recording classifier confirms zero happened.
    """
    response = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "batch",
            "files": _listing(_ELEVEN_SUBJECTS),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estimate"]["pending"] == 0
    assert body["estimate"]["not_needed"] == len(_ELEVEN_SUBJECTS)
    assert classifier.role_calls == 0
    assert classifier.attribution_calls == 0


# --------------------------------------------------------------------------- #
# Acceptance criteria 1, 2 and 7
# --------------------------------------------------------------------------- #
def test_the_eleven_subject_batch_plans_as_eleven_tests(client: TestClient) -> None:
    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "batch",
            "files": _listing(_ELEVEN_SUBJECTS),
        },
    ).json()
    assert len(body["groups"]) == 11
    assert all(not group["missing_required_roles_if_new"] for group in body["groups"])


def test_a_single_subject_folder_plans_as_one_test(client: TestClient) -> None:
    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "one-subject",
            "files": _listing(["01_answers.pdf", "02_criteria.pdf"]),
        },
    ).json()
    assert len(body["groups"]) == 1
    assert body["groups"][0]["suggested_name"] == "one-subject"


def test_the_estimate_separates_what_costs_money_from_what_does_not(
    client: TestClient,
) -> None:
    """Acceptance criterion 7: the reviewer sees the call count before
    anything is sent, and it must not count files nothing would be spent on.
    """
    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "batch",
            "files": _listing(["01_answers.pdf", "stray.pdf", "stray.xls"]),
        },
    ).json()
    assert body["estimate"] == {
        "pending": 1,
        "cached": 0,
        "unsupported": 1,
        "not_needed": 1,
    }


def test_an_answers_only_folder_is_planned_without_a_criteria_file(
    client: TestClient,
) -> None:
    """The weekly flow. The group reports what it would be missing *as a new
    test*, and the screen suppresses that once it is bound to an existing
    one -- what actually enforces the requirement is `POST /tests`, which
    cannot be called without the criteria file.
    """
    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "week-2",
            "files": _listing([f"01_answers-{index}.pdf" for index in range(40)]),
        },
    ).json()
    group = body["groups"][0]
    assert group["missing_required_roles_if_new"] == ["grading_criteria"]
    assert {planned["role"] for planned in group["files"]} == {"student_answer"}


def test_an_unknown_template_is_a_404(client: TestClient) -> None:
    response = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={"template_id": "nope", "root_name": "batch", "files": []},
    )
    assert response.status_code == 404


def test_a_path_escaping_the_chosen_folder_is_refused(client: TestClient) -> None:
    response = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "batch",
            "files": [{"relative_path": "../escape.pdf", "size_bytes": 1, "sha256": "0" * 64}],
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Acceptance criterion 4: the template drives the plan
# --------------------------------------------------------------------------- #
def test_the_default_template_is_offered_before_anything_is_saved(
    client: TestClient,
) -> None:
    body = client.get("/intake-templates", headers=_AUTH).json()
    assert [template["id"] for template in body] == ["serial-number-prefix"]


def test_editing_the_template_changes_the_plan(client: TestClient) -> None:
    """Acceptance criterion 4. A school that puts every answer in one folder
    should be able to say so and have a 40-file folder resolve in one rule.
    """
    saved = client.put(
        "/intake-templates",
        headers=_AUTH,
        json={
            "templates": [
                {
                    "id": "by-folder",
                    "name": "フォルダで分ける",
                    "split_child_directories": False,
                    "rules": [
                        {
                            "scope": "folder",
                            "pattern": "answers",
                            "role": "student_answer",
                            "requirement": "required",
                        },
                        {
                            "scope": "folder",
                            "pattern": "criteria",
                            "role": "grading_criteria",
                            "requirement": "required",
                        },
                    ],
                }
            ]
        },
    )
    assert saved.status_code == 200, saved.text

    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "by-folder",
            "root_name": "batch",
            "files": _listing(
                [f"answers/scan-{index}.pdf" for index in range(40)] + ["criteria/rules.pdf"]
            ),
        },
    ).json()
    assert len(body["groups"]) == 1
    assert body["estimate"]["pending"] == 0
    roles = {planned["role"] for planned in body["groups"][0]["files"]}
    assert roles == {"student_answer", "grading_criteria"}


def test_two_templates_may_not_share_an_id(client: TestClient) -> None:
    response = client.put(
        "/intake-templates",
        headers=_AUTH,
        json={
            "templates": [
                {"id": "same", "name": "A", "rules": []},
                {"id": "same", "name": "B", "rules": []},
            ]
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def test_classifying_one_file_returns_a_proposal(
    client: TestClient, classifier: _RecordingClassifier
) -> None:
    response = client.post(
        "/intake/classify",
        headers=_AUTH,
        files={"file": ("stray.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"role": "reference", "confidence": 0.6, "cached": False}
    assert classifier.role_calls == 1


def test_the_same_content_is_not_classified_twice(
    client: TestClient, classifier: _RecordingClassifier
) -> None:
    """A reviewer re-selecting a folder, retrying a failed batch, or being
    handed the same reference material next term must not pay again.
    """
    data = _pdf_bytes()
    first = client.post(
        "/intake/classify", headers=_AUTH, files={"file": ("a.pdf", data, "application/pdf")}
    )
    second = client.post(
        "/intake/classify",
        headers=_AUTH,
        # A different name, the same bytes: the cache is keyed on content.
        files={"file": ("b.pdf", data, "application/pdf")},
    )
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["role"] == "reference"
    assert classifier.role_calls == 1


def test_a_cached_answer_is_reflected_in_the_next_plans_estimate(
    client: TestClient,
) -> None:
    data = _pdf_bytes()
    client.post(
        "/intake/classify", headers=_AUTH, files={"file": ("a.pdf", data, "application/pdf")}
    )
    digest = hashlib.sha256(data).hexdigest()
    body = client.post(
        "/intake/plan",
        headers=_AUTH,
        json={
            "template_id": "serial-number-prefix",
            "root_name": "batch",
            "files": [{"relative_path": "stray.pdf", "size_bytes": len(data), "sha256": digest}],
        },
    ).json()
    assert body["estimate"] == {"pending": 0, "cached": 1, "unsupported": 0, "not_needed": 0}


def test_a_classifier_that_cannot_tell_returns_no_role(tmp_path: Path) -> None:
    """ "Could not tell" is a real answer, and must arrive as one rather than
    as a failure or a guessed default.
    """
    undecided = _RecordingClassifier(role=None)
    app = create_app(
        api_token=_TOKEN,
        data_root=tmp_path / "app-data",
        material_classifier_factory=lambda: undecided,
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/intake/classify",
            headers=_AUTH,
            files={"file": ("stray.pdf", _pdf_bytes(), "application/pdf")},
        )
    assert response.status_code == 200
    assert response.json()["role"] is None


def test_a_host_without_a_classifier_says_so_instead_of_failing_per_file(
    tmp_path: Path,
) -> None:
    """Role rules still work without a provider, and a reviewer assigning
    roles by hand is the same act they perform to confirm a proposal -- so
    this is a reported state, not a broken screen.
    """

    def unavailable() -> MaterialClassifier:
        raise ClassifierUnavailable("no transport configured on this host")

    app = create_app(
        api_token=_TOKEN,
        data_root=tmp_path / "app-data",
        material_classifier_factory=unavailable,
    )
    with TestClient(app) as test_client:
        availability = test_client.get("/intake/classification-availability", headers=_AUTH)
        classify = test_client.post(
            "/intake/classify",
            headers=_AUTH,
            files={"file": ("stray.pdf", _pdf_bytes(), "application/pdf")},
        )
        plan = test_client.post(
            "/intake/plan",
            headers=_AUTH,
            json={
                "template_id": "serial-number-prefix",
                "root_name": "batch",
                "files": _listing(["01_answers.pdf"]),
            },
        )
    assert availability.json() == {
        "available": False,
        "reason": "no transport configured on this host",
    }
    assert classify.status_code == 503
    # Planning still works: rules need no provider at all.
    assert plan.status_code == 200


def test_a_provider_failure_is_a_502_not_a_crash(tmp_path: Path) -> None:
    failing = _RecordingClassifier(fail=ProviderUnavailable("upstream is down"))
    app = create_app(
        api_token=_TOKEN,
        data_root=tmp_path / "app-data",
        material_classifier_factory=lambda: failing,
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/intake/classify",
            headers=_AUTH,
            files={"file": ("stray.pdf", _pdf_bytes(), "application/pdf")},
        )
    assert response.status_code == 502


def test_a_file_that_is_not_a_readable_pdf_is_rejected_before_any_call(
    client: TestClient, classifier: _RecordingClassifier
) -> None:
    response = client.post(
        "/intake/classify",
        headers=_AUTH,
        files={"file": ("stray.pdf", b"not a pdf at all", "application/pdf")},
    )
    assert response.status_code == 400
    assert classifier.role_calls == 0


# --------------------------------------------------------------------------- #
# Attribution
# --------------------------------------------------------------------------- #
def test_attribution_picks_one_of_the_offered_candidates(tmp_path: Path) -> None:
    picking = _RecordingClassifier(candidate_id="test-2")
    app = create_app(
        api_token=_TOKEN,
        data_root=tmp_path / "app-data",
        material_classifier_factory=lambda: picking,
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/intake/attribute",
            headers=_AUTH,
            data={
                "candidate_ids": ["test-1", "test-2"],
                "candidate_labels": ["第1回", "第2回"],
            },
            files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
        )
    assert response.status_code == 200, response.text
    assert response.json()["test_id"] == "test-2"


def test_attribution_with_a_single_candidate_is_refused(
    client: TestClient, classifier: _RecordingClassifier
) -> None:
    """The reviewer has already decided. Asking a provider to choose from a
    list of one spends money to confirm a foregone conclusion -- and that is
    the ordinary case from week two onward, so it must not be reachable by
    accident.
    """
    response = client.post(
        "/intake/attribute",
        headers=_AUTH,
        data={"candidate_ids": ["test-1"], "candidate_labels": ["第1回"]},
        files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 422
    assert classifier.attribution_calls == 0


def test_mismatched_candidate_ids_and_labels_are_refused(client: TestClient) -> None:
    response = client.post(
        "/intake/attribute",
        headers=_AUTH,
        data={"candidate_ids": ["test-1", "test-2"], "candidate_labels": ["第1回"]},
        files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 422


def test_attribution_may_answer_that_it_could_not_tell(client: TestClient) -> None:
    """Expect this often: the observed answer sheets carry a course-name
    field that is printed on some, blank on others and handwritten on the
    rest, and every inspected sheet had blank student name/id fields.
    """
    response = client.post(
        "/intake/attribute",
        headers=_AUTH,
        data={"candidate_ids": ["test-1", "test-2"], "candidate_labels": ["第1回", "第2回"]},
        files={"file": ("answer.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["test_id"] is None


def test_intake_routes_require_the_bearer_token(client: TestClient) -> None:
    assert client.get("/intake-templates").status_code == 401
    assert (
        client.post(
            "/intake/plan",
            json={"template_id": "serial-number-prefix", "root_name": "x", "files": []},
        ).status_code
        == 401
    )
