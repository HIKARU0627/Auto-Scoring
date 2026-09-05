"""API-level tests for test registration (Issue #16): register a test's two
PDFs, review/edit its profile, confirm it, and gate `complete-registration`
on both the profile and the dependency graph (Issue #26) being confirmed.

Automatic candidate detection (`POST /profile/analyze`) is exercised at the
unit level against real PDF text (`test_profile_candidate_generation.py`);
here the registration fixtures use plain text-free PDFs and drive the
review/confirm flow through `PUT /profile` -- exactly the manual-fallback
path a format automatic detection cannot handle (docs/poc-4-multi-layout-profiles.md
"自動検出困難な形式と手動fallback") -- so these tests don't need to embed
Japanese text into a hand-built PDF (which would require a full CID font).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from auto_scoring.api.app import create_app
from auto_scoring.domain.pdf_intake import IntakeLimits

_TOKEN = "test-registration-token"


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _encrypted_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt(user_password="secret")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(data_root: Path) -> TestClient:
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


def _register_test(client: TestClient, *, name: str = "国語 第1回") -> str:
    response = client.post(
        "/tests",
        headers=_auth(),
        data={"name": name, "subject": "国語"},
        files={
            "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
            "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


def _region(
    *,
    region_id: str,
    kind: str,
    label: str,
    page_index: int = 0,
    text: str | None = None,
    bbox: tuple[float, float, float, float] = (0.1, 0.1, 0.5, 0.2),
) -> dict[str, object]:
    x0, y0, x1, y1 = bbox
    return {
        "region_id": region_id,
        "kind": kind,
        "page_index": page_index,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "label": label,
        "confirmed": False,
        "text": text,
    }


def _minimal_regions(*, label: str = "1", score_text: str = "5点") -> list[dict[str, object]]:
    return [
        _region(region_id=f"question-{label}", kind="question", label=label, text=f"問{label}"),
        _region(
            region_id=f"answer-{label}",
            kind="answer_area",
            label=label,
            bbox=(0.1, 0.3, 0.5, 0.5),
        ),
        _region(
            region_id=f"score-{label}",
            kind="score",
            label=label,
            text=score_text,
            bbox=(0.6, 0.1, 0.7, 0.2),
        ),
    ]


class TestCreateTest:
    def test_registers_a_draft_test(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = client.get(f"/tests/{test_id}", headers=_auth())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "draft"
        assert body["name"] == "国語 第1回"

    def test_rejects_a_non_pdf_file(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "不正PDF"},
            files={
                "model_answer": ("model-answer.pdf", b"not a pdf", "application/pdf"),
                "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert response.status_code == 400

    def test_rejects_an_encrypted_pdf(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "暗号化PDF"},
            files={
                "model_answer": (
                    "model-answer.pdf",
                    _encrypted_pdf_bytes(),
                    "application/pdf",
                ),
                "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert response.status_code == 400

    def test_rejects_an_empty_name(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "   "},
            files={
                "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
                "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert response.status_code == 422


class TestProfileReviewAndConfirm:
    def test_analyze_then_update_then_confirm_creates_questions(self, client: TestClient) -> None:
        test_id = _register_test(client)

        analyze = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        assert analyze.status_code == 200
        assert analyze.json()["status"] == "draft"
        # The registration PDFs carry no text, so nothing is auto-detected --
        # exactly the "requires manual fallback" case (poc-4 docs).
        assert analyze.json()["regions"] == []

        updated = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "draft"
        assert len(updated.json()["regions"]) == 3

        confirmed = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["status"] == "confirmed"
        assert all(region["confirmed"] for region in confirmed.json()["regions"])

    def test_confirm_rejects_an_invalid_score(self, client: TestClient) -> None:
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(score_text="配点未定")},
        )
        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert response.status_code == 422

    def test_confirm_rejects_a_duplicate_question_number(self, client: TestClient) -> None:
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = _minimal_regions()
        regions.append(
            _region(region_id="question-1-dup", kind="question", label="1", text="重複問1")
        )
        client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions})
        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert response.status_code == 422

    def test_update_rejects_out_of_range_coordinates(self, client: TestClient) -> None:
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = _minimal_regions()
        regions[0]["bbox"] = {"x0": -0.1, "y0": 0.1, "x1": 0.5, "y1": 0.2}
        response = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        )
        assert response.status_code == 422

    def test_cannot_edit_or_reanalyze_after_confirming(self, client: TestClient) -> None:
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())

        reanalyze = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        assert reanalyze.status_code == 409

        reedit = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        assert reedit.status_code == 409

        reconfirm = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert reconfirm.status_code == 409

    def test_profile_survives_a_process_restart(self, client: TestClient, data_root: Path) -> None:
        """Simulates a restart: a brand-new `create_app`/session against the
        same `data_root` must see the same profile a prior process saved
        (Issue #16 acceptance: "保存後の再起動で修正内容が復元される").
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        restarted_app = create_app(api_token=_TOKEN, data_root=data_root)
        restarted_client = TestClient(restarted_app)
        response = restarted_client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert response.status_code == 200
        assert len(response.json()["regions"]) == 3


class TestCompleteRegistration:
    def _confirm_profile(self, client: TestClient, test_id: str) -> None:
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert response.status_code == 200, response.text

    def _confirm_dependency_graph(self, client: TestClient, test_id: str) -> None:
        analyze = client.post(
            f"/tests/{test_id}/dependency-graph/analyze",
            headers=_auth(),
            json={"overrides": []},
        )
        assert analyze.status_code == 200, analyze.text
        version = analyze.json()["version"]
        confirm = client.post(
            f"/tests/{test_id}/dependency-graph/confirm",
            headers=_auth(),
            json={"version": version, "edges": []},
        )
        assert confirm.status_code == 200, confirm.text

    def test_rejects_completion_before_the_dependency_graph_is_confirmed(
        self, client: TestClient
    ) -> None:
        test_id = _register_test(client)
        self._confirm_profile(client, test_id)

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 409
        assert "設問依存関係" in response.json()["detail"]

    def test_rejects_completion_before_the_profile_is_confirmed(self, client: TestClient) -> None:
        # A dependency graph can't even be analyzed yet -- Question rows
        # only exist once the profile is confirmed
        # (domain.test_registration.build_questions_and_rubrics) -- so an
        # unconfirmed profile is, on its own, enough to block completion.
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 409
        assert "プロファイル" in response.json()["detail"]

    def test_succeeds_once_both_are_confirmed(self, client: TestClient) -> None:
        test_id = _register_test(client)
        self._confirm_profile(client, test_id)
        self._confirm_dependency_graph(client, test_id)

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["test"]["status"] == "ready"
        assert body["profile_confirmed"] is True
        assert body["dependency_graph_confirmed"] is True

        # answer processing depends on a *ready* test in later Issues, but
        # the dependency graph itself is already the enforcement point
        # (domain.dependency_graph.can_start_submission_processing) -- this
        # just checks the test-level status the settings screen shows.
        get_test = client.get(f"/tests/{test_id}", headers=_auth())
        assert get_test.json()["status"] == "ready"

    def test_cannot_complete_registration_twice(self, client: TestClient) -> None:
        test_id = _register_test(client)
        self._confirm_profile(client, test_id)
        self._confirm_dependency_graph(client, test_id)
        client.post(f"/tests/{test_id}/complete-registration", headers=_auth())

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 409
