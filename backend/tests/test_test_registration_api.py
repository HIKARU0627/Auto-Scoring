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

import threading
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api import test_registration_router
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.models import Question, Rubric
from auto_scoring.domain.pdf_intake import IntakeLimits
from auto_scoring.domain.test_registration import (
    build_questions_and_rubrics as _real_build_questions_and_rubrics,
)
from tests.support import make_test

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


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    db_url = sqlite_url(data_root / "database.sqlite")
    return build_session_factory(create_sqlite_engine(db_url))


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
    def test_requires_auth(self, client: TestClient, data_root: Path) -> None:
        """Rejected by SubmissionUploadGateMiddleware at the ASGI boundary,
        before FastAPI ever spools the two-PDF multipart body (Issue #16
        review) -- see test_submission_upload_gate.py for the unit-level
        proof this happens before the body is read.
        """
        response = client.post(
            "/tests",
            data={"name": "国語"},
            files={
                "model_answer": ("model-answer.pdf", _pdf_bytes(), "application/pdf"),
                "manual": ("manual.pdf", _pdf_bytes(), "application/pdf"),
            },
        )
        assert response.status_code == 401

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert uow.tests.list_all() == []

    def test_list_test_registrations_includes_drafts_and_ready_tests(
        self, client: TestClient
    ) -> None:
        """Issue #16 review: `GET /tests` (answer intake) only lists `ready`
        tests, so a `draft` test needs a different way to be found again
        (e.g. after leaving TestSettingsPage or restarting the app).
        """
        test_id = _register_test(client)

        response = client.get("/test-registrations", headers=_auth())
        assert response.status_code == 200
        statuses = {entry["id"]: entry["status"] for entry in response.json()}
        assert statuses == {test_id: "draft"}

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

    def test_does_not_413_when_two_within_limit_pdfs_exceed_one_files_worth(
        self, client: TestClient
    ) -> None:
        """`POST /tests` carries two independently size-limited PDFs in one
        multipart body. The ASGI-level `MaxBodySizeMiddleware` must be sized
        for *two* files, not one -- each file here is within the 5 MiB
        fixture limit on its own, but their combined body exceeds a
        single-file budget (5 MiB + overhead), which would previously 413
        before either file's own validation ever ran.

        The padding after `%PDF-` isn't a well-formed PDF, so this still
        fails validation (400) once the body is actually read; what this
        test pins down is that it must not fail at the ASGI layer with 413.
        """
        each_file_size = 3 * 1024 * 1024
        padded = b"%PDF-1.7\n" + b"0" * (each_file_size - 20)
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "サイズ確認"},
            files={
                "model_answer": ("model-answer.pdf", padded, "application/pdf"),
                "manual": ("manual.pdf", padded, "application/pdf"),
            },
        )
        assert response.status_code != 413


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

    def test_confirm_rejects_a_blank_question_label(self, client: TestClient) -> None:
        """A blank/whitespace-only QUESTION label passes Region/Profile
        validation (`label` is just a plain `str`) but fails once
        `Question(number=...)` itself validates it -- that raises the
        broader `DomainError`, not the narrower `TestRegistrationError`,
        and must still become a 422, not an unhandled 500 (Issue #16
        review).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = [
            _region(region_id="question-blank", kind="question", label="   ", text="問1"),
            _region(
                region_id="score-blank",
                kind="score",
                label="   ",
                text="5点",
                bbox=(0.6, 0.1, 0.7, 0.2),
            ),
        ]
        client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions})
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

    def test_update_requires_the_regions_field(self, client: TestClient) -> None:
        """A malformed body omitting `regions` entirely must fail validation
        (422), not silently wipe every region the way a `default_factory`
        empty list would (Issue #16 review).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        response = client.put(f"/tests/{test_id}/profile", headers=_auth(), json={})
        assert response.status_code == 422

        # The prior regions must survive the rejected request untouched.
        profile = client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert len(profile.json()["regions"]) == 3

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

    def test_confirm_recovers_from_a_profile_file_write_failure(
        self, client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If `profile.json` fails to write after Question/Rubric rows have
        already committed (disk full, permissions, ...), a retried confirm
        must succeed without duplicating those rows (Issue #16 review: a
        naive re-add would hit a UNIQUE constraint and the registration
        would be stuck unable to ever complete).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        real_write_atomic = LocalFileStore.write_atomic

        def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
            if path.name == "profile.json":
                raise OSError("simulated disk-full failure")
            return real_write_atomic(self, path, data)

        monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)
        with pytest.raises(OSError):
            client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert len(uow.questions.list_for_test(test_id)) == 1

        monkeypatch.setattr(LocalFileStore, "write_atomic", real_write_atomic)
        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "confirmed"

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert len(uow.questions.list_for_test(test_id)) == 1

    def test_confirm_reconciles_a_changed_region_set_on_retry(
        self, client: TestClient, data_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retry must not just skip ids that already exist -- it must end
        up with *exactly* the question set the confirmed profile describes.
        If the reviewer edited the (still-draft) profile between the failed
        attempt and the retry (here: dropped question 2 entirely), the stale
        row from the first attempt must not survive (Issue #16 review: a
        `ready` test would otherwise be graded against a question the
        confirmed profile no longer has).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        two_questions = _minimal_regions(label="1") + _minimal_regions(label="2")
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": two_questions},
        )

        real_write_atomic = LocalFileStore.write_atomic

        def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
            if path.name == "profile.json":
                raise OSError("simulated disk-full failure")
            return real_write_atomic(self, path, data)

        monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)
        with pytest.raises(OSError):
            client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert {q.number for q in uow.questions.list_for_test(test_id)} == {"1", "2"}

        # The profile is still draft (the file write never succeeded) --
        # drop question 2 before retrying.
        monkeypatch.setattr(LocalFileStore, "write_atomic", real_write_atomic)
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(label="1")},
        )
        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert response.status_code == 200, response.text

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert {q.number for q in uow.questions.list_for_test(test_id)} == {"1"}

    def test_confirm_and_analyze_are_serialized_for_the_same_test(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`/profile/analyze` and `/profile/confirm` both read the on-disk
        profile, transform it, and overwrite it in full -- neither rereads
        or compare-and-sets against the file right before its own write. An
        `/analyze` that read the profile as DRAFT before a concurrent
        `/confirm` committed its Questions and saved the CONFIRMED file
        would otherwise silently clobber that file with its own stale DRAFT
        result once it finally finishes (Issue #16 review round 3).

        Simulate the overlap: block `/confirm` mid-flight (after it has
        already loaded the DRAFT profile, before it writes anything), start
        `/confirm` a concurrent `/analyze` while it is blocked, and check
        `/analyze` is blocked behind it rather than running concurrently.
        Serialized, `/analyze` only proceeds once `/confirm` has fully
        finished -- so it re-reads a profile that is now CONFIRMED and is
        rejected (409), instead of racing ahead against stale state and
        overwriting the confirmed file afterward.
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        confirm_started = threading.Event()
        release_confirm = threading.Event()

        def slow_build(*args: Any, **kwargs: Any) -> tuple[list[Question], list[Rubric]]:
            confirm_started.set()
            assert release_confirm.wait(timeout=5)
            return _real_build_questions_and_rubrics(*args, **kwargs)

        monkeypatch.setattr(test_registration_router, "build_questions_and_rubrics", slow_build)

        confirm_responses: list[int] = []

        def _run_confirm() -> None:
            response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
            confirm_responses.append(response.status_code)

        confirm_thread = threading.Thread(target=_run_confirm)
        confirm_thread.start()
        assert confirm_started.wait(timeout=5)

        analyze_responses: list[int] = []

        def _run_analyze() -> None:
            response = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
            analyze_responses.append(response.status_code)

        analyze_thread = threading.Thread(target=_run_analyze)
        analyze_thread.start()
        # `/analyze` must not be able to observe or act on the profile
        # while `/confirm` is still mid-flight -- give it every chance to
        # race ahead before proving it didn't.
        analyze_thread.join(timeout=0.5)
        assert analyze_responses == []

        release_confirm.set()
        confirm_thread.join(timeout=5)
        analyze_thread.join(timeout=5)

        assert confirm_responses == [200]
        # Serialized behind the now-confirmed profile, not a stale 200 that
        # would go on to overwrite it with a fresh DRAFT.
        assert analyze_responses == [409]

        profile = client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert profile.json()["status"] == "confirmed"


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

    def test_rejects_completion_when_the_confirmed_graph_no_longer_matches_the_questions(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`get_latest_confirmed(...) is not None` alone is not enough: a
        confirmed graph is immutable, but a profile-confirm retry (Issue #16
        review) can still replace the test's Questions afterward, leaving a
        graph whose `question_ids` no longer describes the test yet still
        reads CONFIRMED. `complete_registration` must reuse
        `can_start_submission_processing`'s stricter check the same way
        Issue #26's submission pipeline does, not just check for *any*
        confirmed graph (Issue #16 review round 3).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        two_questions = _minimal_regions(label="1") + _minimal_regions(label="2")
        client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": two_questions})

        real_write_atomic = LocalFileStore.write_atomic

        def failing_write_atomic(self: LocalFileStore, path: Path, data: bytes) -> Path:
            if path.name == "profile.json":
                raise OSError("simulated disk-full failure")
            return real_write_atomic(self, path, data)

        monkeypatch.setattr(LocalFileStore, "write_atomic", failing_write_atomic)
        with pytest.raises(OSError):
            client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        monkeypatch.setattr(LocalFileStore, "write_atomic", real_write_atomic)

        # The DB commit from the failed attempt above already created both
        # questions -- confirm a dependency graph over that (still-current)
        # set before the retry below changes it.
        self._confirm_dependency_graph(client, test_id)

        # Retry confirm with question 2 dropped: the profile file never
        # reached CONFIRMED (the write above failed), so this is allowed --
        # and reconciles the Questions down to just "1", stranding the
        # dependency graph confirmed a moment ago.
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(label="1")},
        )
        confirm = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth())
        assert confirm.status_code == 200, confirm.text

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 409
        assert "設問依存関係" in response.json()["detail"]

    def test_cannot_complete_registration_twice(self, client: TestClient) -> None:
        test_id = _register_test(client)
        self._confirm_profile(client, test_id)
        self._confirm_dependency_graph(client, test_id)
        client.post(f"/tests/{test_id}/complete-registration", headers=_auth())

        response = client.post(f"/tests/{test_id}/complete-registration", headers=_auth())
        assert response.status_code == 409


def test_starting_the_app_repairs_a_draft_test_left_incomplete_by_a_prior_crash(
    data_root: Path,
) -> None:
    """`create_app()` runs a startup repair sweep (api/app.py) for exactly
    the case a caught `FinalizationError` can't cover: a `Test` row
    committed successfully in a *previous* process, one of whose two PDFs
    never actually reached disk before that process died. Unlike a
    `Submission`, a `Test` has no `error` state to move into -- the only
    usable recovery is removing the row outright (Issue #16 review round
    4). Simulate the crash by deleting a PDF after a normal successful
    registration, then create a fresh app instance against the same
    data_root (as a restart would) and confirm the sweep removes the
    now-unusable draft before the app ever serves a request.
    """
    first_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    first_client = TestClient(first_app)
    test_id = _register_test(first_client)

    LocalFileStore(data_root).test_manual_pdf_path(test_id).unlink()

    restarted_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    restarted_client = TestClient(restarted_app)

    fetched = restarted_client.get(f"/tests/{test_id}", headers=_auth())
    assert fetched.status_code == 404

    listed = restarted_client.get("/test-registrations", headers=_auth())
    assert listed.json() == []


def test_starting_the_app_leaves_a_pre_migration_test_alone(data_root: Path) -> None:
    """Migration 0008 backfills `status='draft'` onto every pre-existing
    `Test` row -- none of which were ever registered through
    `register_test`, so none of them have the two PDFs this Issue's
    registration flow writes. The repair sweep must never treat "no PDFs on
    disk" alone as "an interrupted registration" for such a row: an earlier
    version of this sweep did exactly that and deleted every pre-existing
    test -- cascading to its Questions and Submissions -- on the first
    startup after upgrading a production database past that migration
    (Issue #16 review round 5, data loss).
    """
    # Runs migrations (via create_app) without ever calling register_test --
    # the DB then holds exactly what upgrading a pre-0008 database would
    # look like: a `Test` row with no registration marker and no PDFs.
    create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.tests.add(make_test(id="legacy-test", name="移行前のテスト"))
        uow.commit()

    restarted_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    fetched = TestClient(restarted_app).get("/tests/legacy-test", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "draft"


def test_starting_the_app_leaves_a_healthy_draft_test_alone(data_root: Path) -> None:
    """The repair sweep must not touch a `DRAFT` test whose PDFs are simply
    still waiting for review -- only one whose files are actually missing.
    """
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    test_id = _register_test(TestClient(app))

    restarted_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    fetched = TestClient(restarted_app).get(f"/tests/{test_id}", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "draft"
