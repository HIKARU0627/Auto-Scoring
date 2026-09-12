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

import shutil
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
from auto_scoring.api import test_artifact_lock, test_registration_router
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.models import Question, Rubric, SubmissionState
from auto_scoring.domain.pdf_intake import IntakeLimits
from auto_scoring.domain.test_registration import (
    build_questions_and_rubrics as _real_build_questions_and_rubrics,
)
from tests.support import make_grade, make_review, make_submission, make_test

_TOKEN = "test-registration-token"

#: Liveness guard for a wait on an *observable state transition* inside the
#: system under test (a request reaching a particular point), not a budget
#: the state is expected to reach on an idle machine. It expires only if the
#: transition never happens at all -- a genuine failure, not runner slowness
#: -- so it is deliberately far above any observed time. See Issue #439 and
#: `docs/test-timing.md`.
_STATE_CHANGE_TIMEOUT_SECONDS = 30.0


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
    """Register with the required criteria PDF plus a reference PDF.

    The reference is what the profile tests below need: automatic candidate
    generation takes its page geometry from a model-answer-shaped document,
    and Issue #101 made that optional -- so a test registered without one
    gets a 409 from `/profile/analyze` telling the reviewer to draw the
    regions by hand (`test_analyze_without_a_reference_pdf_says_so`).
    """
    response = client.post(
        "/tests",
        headers=_auth(),
        data={"name": name, "subject": "国語", "material_roles": ["reference"]},
        files=[
            ("criteria", ("02_criteria.pdf", _pdf_bytes(), "application/pdf")),
            ("materials", ("reference.pdf", _pdf_bytes(), "application/pdf")),
        ],
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


def _confirm(client: TestClient, test_id: str) -> Any:
    """`POST /profile/confirm`, pinned to the profile's current revision.

    Exercises the normal reviewer flow (fetch, then confirm what was
    fetched) -- tests of the revision check itself pass an explicit,
    deliberately stale `revision` instead of using this helper.
    """
    revision = client.get(f"/tests/{test_id}/profile", headers=_auth()).json()["revision"]
    return client.post(
        f"/tests/{test_id}/profile/confirm",
        headers=_auth(),
        json={"revision": revision},
    )


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


class _ContentionSignallingLock:
    """A ``threading.Lock`` stand-in that sets an event when a second
    acquirer finds the lock already held.

    `test_confirm_and_analyze_are_serialized_for_the_same_test` needs to show
    that `/analyze` is *parked* behind `/confirm`, not merely that no answer
    happened to arrive within a fixed window. A fixed `join(timeout=0.5)` +
    "the response list is still empty" is a measurement of the runner's
    speed: on a busy machine `/analyze` may simply not have been dispatched
    yet, which is not the property under test (Issue #439). Waiting for this
    event instead waits on a state the system under test reaches -- the
    analyze request contending for the per-test lock -- and if the lock is
    removed (the mutation this guards against) it is never set.
    """

    def __init__(self, inner: threading.Lock, contended: threading.Event) -> None:
        self._inner = inner
        self._contended = contended

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if self._inner.locked():
            self._contended.set()
        return self._inner.acquire(blocking, timeout)

    def release(self) -> None:
        self._inner.release()

    def __enter__(self) -> _ContentionSignallingLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


class TestCreateTest:
    def test_requires_auth(self, client: TestClient, data_root: Path) -> None:
        """Rejected by SubmissionUploadGateMiddleware at the ASGI boundary,
        before FastAPI ever spools the multipart body (Issue #16
        review) -- see test_submission_upload_gate.py for the unit-level
        proof this happens before the body is read.
        """
        response = client.post(
            "/tests",
            data={"name": "国語"},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
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
            files={"criteria": ("02_criteria.pdf", b"not a pdf", "application/pdf")},
        )
        assert response.status_code == 400

    def test_rejects_an_encrypted_pdf(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "暗号化PDF"},
            files={"criteria": ("02_criteria.pdf", _encrypted_pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 400

    def test_rejects_an_empty_name(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "   "},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 422

    def test_rejects_a_name_over_the_length_limit(self, client: TestClient) -> None:
        """An authenticated caller could otherwise pack most of the
        request's own size limit into `name`, stored verbatim and returned
        on every test-registration list response (Issue #16 review round
        8).
        """
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "国" * 201},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 422

    def test_rejects_a_subject_over_the_length_limit(self, client: TestClient) -> None:
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "国語", "subject": "国" * 201},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 422

    def test_does_not_413_when_two_within_limit_pdfs_exceed_one_files_worth(
        self, client: TestClient
    ) -> None:
        """`POST /tests` can carry several independently size-limited files in one
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
            data={"name": "サイズ確認", "material_roles": ["reference"]},
            files=[
                ("criteria", ("02_criteria.pdf", padded, "application/pdf")),
                ("materials", ("reference.pdf", padded, "application/pdf")),
            ],
            # `material_roles` pairs positionally with `materials`.
        )
        assert response.status_code != 413


class TestMaterials:
    """Issue #101: what was registered, under which role, and undoing it."""

    def test_a_test_registers_without_a_model_answer(self, client: TestClient) -> None:
        """Acceptance criterion 3. `criteria` is the only required file."""
        response = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "模範解答なし"},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
        )
        assert response.status_code == 201, response.text
        materials = client.get(f"/tests/{response.json()['id']}/materials", headers=_auth()).json()
        assert [material["role"] for material in materials] == ["grading_criteria"]

    def test_materials_report_the_reviewers_own_file_name(self, client: TestClient) -> None:
        """ "Which of my files became the 採点基準?" has to stay answerable
        after import, so the name the reviewer chose the file by is kept.
        """
        test_id = _register_test(client)
        materials = client.get(f"/tests/{test_id}/materials", headers=_auth()).json()
        by_role = {material["role"]: material for material in materials}
        assert by_role["grading_criteria"]["original_filename"] == "02_criteria.pdf"
        assert by_role["reference"]["original_filename"] == "reference.pdf"

    def test_materials_can_be_attached_later(self, client: TestClient) -> None:
        """The weekly flow needs this: a 添削資料 that turns up after the test
        was registered must be attachable without re-registering it.
        """
        test_id = _register_test(client)
        response = client.post(
            f"/tests/{test_id}/materials",
            headers=_auth(),
            data={"material_roles": ["annotation_sample"]},
            files=[("materials", ("04_1_sample.pdf", _pdf_bytes(), "application/pdf"))],
        )
        assert response.status_code == 201, response.text
        roles = [
            material["role"]
            for material in client.get(f"/tests/{test_id}/materials", headers=_auth()).json()
        ]
        assert sorted(roles) == ["annotation_sample", "grading_criteria", "reference"]

    def test_mismatched_material_and_role_counts_are_refused(self, client: TestClient) -> None:
        """The two lists pair positionally; a mismatch would shift every role
        by one and attach files under roles nobody chose.
        """
        test_id = _register_test(client)
        response = client.post(
            f"/tests/{test_id}/materials",
            headers=_auth(),
            data={"material_roles": ["annotation_sample", "reference"]},
            files=[("materials", ("04_1_sample.pdf", _pdf_bytes(), "application/pdf"))],
        )
        assert response.status_code == 422

    def test_an_unknown_role_is_refused(self, client: TestClient) -> None:
        test_id = _register_test(client)
        response = client.post(
            f"/tests/{test_id}/materials",
            headers=_auth(),
            data={"material_roles": ["not-a-role"]},
            files=[("materials", ("x.pdf", _pdf_bytes(), "application/pdf"))],
        )
        assert response.status_code == 422

    def test_a_test_can_be_deleted(self, client: TestClient) -> None:
        """Importing into the wrong test is an ordinary mistake. Without a
        route for the delete that already existed, the only remedy would be
        editing `app-data/` by hand.
        """
        test_id = _register_test(client)
        assert client.delete(f"/tests/{test_id}", headers=_auth()).status_code == 204
        assert client.get(f"/tests/{test_id}", headers=_auth()).status_code == 404

    def test_deleting_a_test_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        assert client.delete("/tests/nope", headers=_auth()).status_code == 404

    def test_analyze_without_a_reference_pdf_says_what_to_do_instead(
        self, client: TestClient
    ) -> None:
        """Automatic candidate generation reads the page layout from a
        model-answer-shaped PDF, which Issue #101 made optional -- so most
        tests now have none.

        It must say so, not fall back to the criteria PDF's own geometry: a
        profile bound to a page layout no submission has would crop every
        later answer from the wrong coordinates, silently.
        """
        created = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "参考資料なし"},
            files={"criteria": ("02_criteria.pdf", _pdf_bytes(), "application/pdf")},
        )
        test_id = created.json()["id"]
        response = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        assert response.status_code == 409
        assert "手動" in response.json()["detail"]


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

        confirmed = _confirm(client, test_id)
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
        response = _confirm(client, test_id)
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
        response = _confirm(client, test_id)
        assert response.status_code == 422

    def test_confirm_rejects_a_duplicate_question_number(self, client: TestClient) -> None:
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = _minimal_regions()
        regions.append(
            _region(region_id="question-1-dup", kind="question", label="1", text="重複問1")
        )
        client.put(f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions})
        response = _confirm(client, test_id)
        assert response.status_code == 422

    def test_confirm_supports_question_spanning_two_pages(self, client: TestClient) -> None:
        """Issue #108: a question whose answer area spans 2 pages confirms successfully."""
        created = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "2ページ参考", "subject": "国語", "material_roles": ["reference"]},
            files=[
                ("criteria", ("02_criteria.pdf", _pdf_bytes(pages=2), "application/pdf")),
                ("materials", ("reference.pdf", _pdf_bytes(pages=2), "application/pdf")),
            ],
        )
        assert created.status_code == 201
        test_id = created.json()["id"]
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = _minimal_regions()
        regions.append(
            _region(
                region_id="answer-1-p2",
                kind="answer_area",
                label="1",
                page_index=1,
                bbox=(0.1, 0.5, 0.5, 0.7),
            )
        )
        put_res = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        )
        assert put_res.status_code == 200, put_res.text
        response = _confirm(client, test_id)
        assert response.status_code == 200, response.text

    def test_confirm_cross_page_region_error_for_three_pages(self, client: TestClient) -> None:
        """Issue #108: CrossPageRegionError 422 explains that answer areas
        may span at most 2 pages.
        """
        created = client.post(
            "/tests",
            headers=_auth(),
            data={"name": "3ページ参考", "subject": "国語", "material_roles": ["reference"]},
            files=[
                ("criteria", ("02_criteria.pdf", _pdf_bytes(pages=3), "application/pdf")),
                ("materials", ("reference.pdf", _pdf_bytes(pages=3), "application/pdf")),
            ],
        )
        assert created.status_code == 201
        test_id = created.json()["id"]
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        regions = _minimal_regions()
        regions.append(
            _region(
                region_id="answer-1-p2",
                kind="answer_area",
                label="1",
                page_index=1,
                bbox=(0.1, 0.5, 0.5, 0.7),
            )
        )
        regions.append(
            _region(
                region_id="answer-1-p3",
                kind="answer_area",
                label="1",
                page_index=2,
                bbox=(0.1, 0.5, 0.5, 0.7),
            )
        )
        put_res = client.put(
            f"/tests/{test_id}/profile", headers=_auth(), json={"regions": regions}
        )
        assert put_res.status_code == 200, put_res.text
        response = _confirm(client, test_id)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "3ページ以上にまたがっているか" in detail
        assert "最大2ページ" in detail

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
        _confirm(client, test_id)

        reanalyze = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        assert reanalyze.status_code == 409

        reedit = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        assert reedit.status_code == 409

        reconfirm = _confirm(client, test_id)
        assert reconfirm.status_code == 409

    def test_profile_survives_a_process_restart(self, client: TestClient, data_root: Path) -> None:
        """Simulates a restart: a brand-new `create_app`/session against the
        same `data_root` must see the same profile a prior process saved
        (Issue #16 acceptance: "保存後の再起動で修正内容が復元される").

        The `client` fixture's own app is never entered as a lifespan
        context, so its data-root lock is still held at this point --
        re-entering the same app via `with TestClient(client.app)` runs
        that lifespan (start then stop) and releases it before the second
        `create_app` below reuses the same data_root, matching a real
        restart instead of raising `DataRootLockedError` (review round 10,
        P1).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        with TestClient(client.app):
            pass

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
            _confirm(client, test_id)

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert len(uow.questions.list_for_test(test_id)) == 1

        monkeypatch.setattr(LocalFileStore, "write_atomic", real_write_atomic)
        response = _confirm(client, test_id)
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
            _confirm(client, test_id)

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
        response = _confirm(client, test_id)
        assert response.status_code == 200, response.text

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            assert {q.number for q in uow.questions.list_for_test(test_id)} == {"1"}

    def test_confirm_is_refused_once_a_reviewed_answer_exists(
        self, client: TestClient, data_root: Path
    ) -> None:
        """Issue #112: 完了した答案が、設問の作り直しで孤児にならないこと。

        `ensure_questions_can_be_rebuilt` (Issue #103) guards both rebuild
        paths. The other one -- `POST /criteria/confirm` -- is pinned by
        `test_criteria_api.py::test_confirming_refuses_once_answers_exist_and_destroys_nothing`;
        this path had no test at all (`make_submission` did not appear in this
        file), so the guard here rested on nobody exercising it.

        Why Issue #112 cares: 設問 ids are deterministic
        (``f"{test_id}:{number}"``, `domain.test_registration`) and
        ``reviews.question_id`` is ``ON DELETE CASCADE``. So a rebuild deletes
        every `Review` and re-inserts questions under the same ids, while
        nothing recomputes the submission's own state. A submission left at
        ``REVIEWED`` would then be counted as 確認済み on ホーム画面 with **zero**
        human confirmations behind it -- 「黙って古い完了が残る」.

        The guard is what makes that unreachable, so it is what this pins:
        the refusal, and that the completion is still intact afterwards.
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(label="1")},
        )

        # A submission that a person has finished reviewing: the exact thing a
        # rebuild would silently orphan.
        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            uow.questions.add(
                Question(id=f"{test_id}:1", test_id=test_id, number="1", page=1, points=5)
            )
            uow.submissions.add(
                make_submission(id="sub-1", test_id=test_id, state=SubmissionState.REVIEWED)
            )
            # An `approved` Review must name the AI grade it approved
            # (`Review.__post_init__`), so the grade comes first.
            uow.grades.add(
                make_grade(id="grade-1", submission_id="sub-1", question_id=f"{test_id}:1")
            )
            uow.reviews.add(
                make_review(
                    id="rev-1",
                    submission_id="sub-1",
                    question_id=f"{test_id}:1",
                    ai_grade_result_id="grade-1",
                )
            )
            uow.commit()

        response = _confirm(client, test_id)

        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        # Names the way forward, not only the refusal.
        assert "新しいテストとして登録し直して" in detail

        with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
            submission = uow.submissions.get("sub-1")
            assert submission is not None
            assert submission.state is SubmissionState.REVIEWED
            # The review history the completion stands on is still there.
            assert len(uow.reviews.history("sub-1", f"{test_id}:1")) == 1

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

        confirm_in_build = threading.Event()
        release_confirm = threading.Event()

        def slow_build(*args: Any, **kwargs: Any) -> tuple[list[Question], list[Rubric]]:
            # Runs while `/confirm` holds the per-test lock. Park here until
            # the test has observed `/analyze` contend for that lock, so the
            # overlap is real rather than hoped for.
            confirm_in_build.set()
            release_confirm.wait()
            return _real_build_questions_and_rubrics(*args, **kwargs)

        monkeypatch.setattr(test_registration_router, "build_questions_and_rubrics", slow_build)

        # Observe `/analyze` reaching the per-test lock and finding it taken
        # -- a state, not a 0.5s window (Issue #439).
        analyze_reached_the_lock = threading.Event()
        real_for_test = test_artifact_lock.TestArtifactLocks.for_test

        def for_test_with_contention(
            locks: test_artifact_lock.TestArtifactLocks, target: str
        ) -> Any:
            lock = real_for_test(locks, target)
            if target != test_id:
                return lock
            return _ContentionSignallingLock(lock, analyze_reached_the_lock)

        monkeypatch.setattr(
            test_artifact_lock.TestArtifactLocks,
            "for_test",
            for_test_with_contention,
        )

        confirm_responses: list[int] = []

        def _run_confirm() -> None:
            response = _confirm(client, test_id)
            confirm_responses.append(response.status_code)

        analyze_responses: list[int] = []

        def _run_analyze() -> None:
            response = client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
            analyze_responses.append(response.status_code)

        confirm_thread = threading.Thread(target=_run_confirm)
        analyze_thread = threading.Thread(target=_run_analyze)
        try:
            confirm_thread.start()
            # Start `/analyze` only once `/confirm` is demonstrably inside the
            # build (and so holds the lock), otherwise the two could simply
            # run in the opposite order and prove nothing.
            assert confirm_in_build.wait(timeout=_STATE_CHANGE_TIMEOUT_SECONDS), (
                "/confirm never reached the build while holding the lock"
            )
            analyze_thread.start()
            assert analyze_reached_the_lock.wait(timeout=_STATE_CHANGE_TIMEOUT_SECONDS), (
                "/analyze never contended for the per-test lock"
            )
            # Guaranteed by the contention signal: `/analyze` is parked on
            # the lock `/confirm` holds, so it cannot have answered yet.
            assert analyze_responses == []
        finally:
            # Always release, even if the wait above timed out, so a failed
            # test cannot leave `/confirm` parked forever.
            release_confirm.set()

        # Cleanup only: a deadline on either join would measure the runner,
        # not the serialization this test exists to prove (Issue #439).
        confirm_thread.join()
        analyze_thread.join()

        assert confirm_responses == [200]
        # Serialized behind the now-confirmed profile, not a stale 200 that
        # would go on to overwrite it with a fresh DRAFT.
        assert analyze_responses == [409]

        profile = client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert profile.json()["status"] == "confirmed"

    def test_confirm_rejects_a_stale_revision(self, client: TestClient) -> None:
        """Two clients reviewing the same test: client A fetches/saves the
        profile (capturing its revision), then before A calls confirm,
        client B's own `PUT /profile` replaces the region set. A's confirm
        must not silently approve B's regions under A's attestation --
        confirming is "I reviewed *this* region set", not "whatever is on
        disk when the request happens to run" (Issue #16 review round 8,
        docs/test-registration.md's human-review contract).
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        a_saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(label="1")},
        )
        assert a_saved.status_code == 200, a_saved.text
        stale_revision = a_saved.json()["revision"]

        b_saved = client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions(label="2")},
        )
        assert b_saved.status_code == 200, b_saved.text
        assert b_saved.json()["revision"] != stale_revision

        response = client.post(
            f"/tests/{test_id}/profile/confirm",
            headers=_auth(),
            json={"revision": stale_revision},
        )
        assert response.status_code == 409
        assert "revision" in response.json()["detail"]

        # B's regions must still be there, still draft -- A's stale confirm
        # attempt must not have touched anything.
        profile = client.get(f"/tests/{test_id}/profile", headers=_auth())
        assert profile.json()["status"] == "draft"
        assert [r["label"] for r in profile.json()["regions"]] == ["2", "2", "2"]

    def test_confirm_requires_the_revision_field(self, client: TestClient) -> None:
        """A malformed body omitting `revision` entirely must fail request
        validation (422), not be treated as some default revision.
        """
        test_id = _register_test(client)
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )

        response = client.post(f"/tests/{test_id}/profile/confirm", headers=_auth(), json={})
        assert response.status_code == 422


class TestCompleteRegistration:
    def _confirm_profile(self, client: TestClient, test_id: str) -> None:
        client.post(f"/tests/{test_id}/profile/analyze", headers=_auth())
        client.put(
            f"/tests/{test_id}/profile",
            headers=_auth(),
            json={"regions": _minimal_regions()},
        )
        response = _confirm(client, test_id)
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
            _confirm(client, test_id)
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
        confirm = _confirm(client, test_id)
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
    committed successfully in a *previous* process, whose grading-criteria
    file never actually reached disk before that process died. Unlike a
    `Submission`, a `Test` has no `error` state to move into -- the only
    usable recovery is removing the row outright (Issue #16 review round
    4). Simulate the crash by deleting the criteria file after a normal
    successful registration, then create a fresh app instance against the same
    data_root (as a restart would) and confirm the sweep removes the
    now-unusable draft before the app ever serves a request.

    The first app's usage is wrapped in ``with TestClient(...) as
    first_client`` so its lifespan runs and releases the data-root lock on
    exit -- otherwise building the second `create_app` below, against the
    same data_root a real restart would reuse, would raise
    `DataRootLockedError` instead of simulating one (review round 10, P1:
    the lock is held for `create_app`'s whole data-root initialization).
    """
    first_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    with TestClient(first_app) as first_client:
        test_id = _register_test(first_client)

    # Everything the registration wrote except its marker -- the marker is
    # what tells the sweep this row went through `register_test` at all, and
    # a crash between the DB commit and the file writes leaves exactly this.
    shutil.rmtree(LocalFileStore(data_root).test_dir(test_id) / "materials")

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
    """Migration 0011 backfills `status='draft'` onto every pre-existing
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
    # the DB then holds exactly what upgrading a pre-0011 database would
    # look like: a `Test` row with no registration marker and no PDFs.
    #
    # Wrapped in `with TestClient(...)` (not a bare `create_app(...)` call)
    # so its lifespan runs and releases the data-root lock immediately --
    # otherwise the second `create_app` below, against the same data_root,
    # would raise `DataRootLockedError` (review round 10, P1: `create_app`
    # acquires that lock unconditionally, even before any TestClient exists).
    with TestClient(
        create_app(
            api_token=_TOKEN,
            data_root=data_root,
            intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        )
    ):
        pass
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

    The first app's usage is wrapped in `with TestClient(...)` so its
    lifespan runs and releases the data-root lock on exit -- otherwise the
    second `create_app` below, against the same data_root, would raise
    `DataRootLockedError` (review round 10, P1).
    """
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    with TestClient(app) as client:
        test_id = _register_test(client)

    restarted_app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
    )
    fetched = TestClient(restarted_app).get(f"/tests/{test_id}", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "draft"
