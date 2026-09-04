"""API-level tests for the answer-intake endpoints (Issue #17)."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.models import NormalizedRect
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from auto_scoring.domain.pdf_intake import IntakeLimits
from tests.support import make_question, make_test

_TOKEN = "submissions-test-token"


def _pdf_bytes(*, pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=300, height=400)
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


def _seed_test(data_root: Path, *, with_answer_area: bool = True) -> None:
    factory = _session_factory(data_root)
    with SqlAlchemyUnitOfWork(factory) as uow:
        uow.tests.add(make_test(id="test-1", name="国語", subject=None))
        uow.questions.add(
            make_question(
                id="q-1",
                page=1,
                answer_area=(
                    NormalizedRect(x=0.1, y=0.1, width=0.5, height=0.2)
                    if with_answer_area
                    else None
                ),
            )
        )
        uow.commit()


def test_list_tests_requires_auth(client: TestClient) -> None:
    response = client.get("/tests")
    assert response.status_code == 401


def test_list_tests_returns_seeded_test(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    response = client.get("/tests", headers=_auth())
    assert response.status_code == 200
    assert response.json() == [{"id": "test-1", "name": "国語", "subject": None}]


def test_create_submission_happy_path(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("student-a.pdf", _pdf_bytes(), "application/pdf")},
        data={"student_label": "student-a"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["test_id"] == "test-1"
    assert body["state"] == "ai_processed"
    assert body["page_count"] == 1
    assert body["student_label"] == "student-a"
    assert body["review_reason"] is None
    assert body["is_retry"] is False

    listed = client.get("/tests/test-1/submissions", headers=_auth())
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]

    fetched = client.get(f"/submissions/{body['id']}", headers=_auth())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_create_submission_rejects_non_pdf_extension(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("student-a.txt", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 400


def test_create_submission_rejects_encrypted_pdf(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.encrypt(user_password="secret")
    buffer = BytesIO()
    writer.write(buffer)

    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("student-a.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert response.status_code == 400


def test_create_submission_rejects_oversize_page_count(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("student-a.pdf", _pdf_bytes(pages=6), "application/pdf")},
    )
    assert response.status_code == 400


def test_create_submission_rejects_oversize_file_before_materializing(
    client: TestClient, data_root: Path
) -> None:
    """The 5 MiB fixture limit is enforced while streaming the upload in
    chunks, not after buffering the whole (6 MiB) body into one `bytes`.
    """
    _seed_test(data_root)
    oversized = b"%PDF-1.7\n" + b"0" * (6 * 1024 * 1024)
    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("big.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 413

    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        assert uow.submissions.list_for_test("test-1") == []


def test_create_submission_tolerates_multipart_overhead_near_the_limit(
    client: TestClient, data_root: Path
) -> None:
    """A file part sized just *under* max_size_bytes must not be rejected by
    the ASGI body-size middleware just because multipart framing (boundary,
    part headers, the student_label field) pushes the *total* request body a
    little past max_size_bytes -- only the file part itself is subject to
    that limit (api/app.py::_read_upload_within_limit).

    The padding after `%PDF-` isn't a well-formed PDF, so the request still
    fails once it reaches PDF parsing (a 400, exercised elsewhere); what this
    test pins down is that it must not fail at the ASGI layer with 413, which
    would mean the middleware's own limit didn't get the overhead margin
    api/app.py adds on top of IntakeLimits.max_size_bytes.
    """
    _seed_test(data_root)
    limit = 5 * 1024 * 1024
    file_bytes = b"%PDF-1.7\n" + b"0" * (limit - 200)
    assert len(file_bytes) < limit

    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("student-a.pdf", file_bytes, "application/pdf")},
        data={"student_label": "student-a"},
    )
    assert response.status_code != 413


def test_create_submission_rejects_unknown_test(client: TestClient) -> None:
    response = client.post(
        "/tests/does-not-exist/submissions",
        headers=_auth(),
        files={"file": ("student-a.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 404


def test_create_submission_rejects_duplicate(client: TestClient, data_root: Path) -> None:
    _seed_test(data_root)
    data = _pdf_bytes()
    first = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("a.pdf", data, "application/pdf")},
    )
    assert first.status_code == 201

    second = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("a-again.pdf", data, "application/pdf")},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["existing_submission_id"] == first.json()["id"]


def test_create_submission_missing_answer_area_lands_in_needs_review(
    client: TestClient, data_root: Path
) -> None:
    _seed_test(data_root, with_answer_area=False)
    response = client.post(
        "/tests/test-1/submissions",
        headers=_auth(),
        files={"file": ("a.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "needs_review"
    assert body["review_reason"] == "answer_area_undefined:q-1"


def test_get_submission_404_for_unknown_id(client: TestClient) -> None:
    response = client.get("/submissions/does-not-exist", headers=_auth())
    assert response.status_code == 404


class _SlowPdfEngine:
    """Delegates to a real ``PdfEngine`` but sleeps before every page render --
    standing in for a submission whose rasterization genuinely takes a while.
    """

    def __init__(self, delegate: PdfEngine, *, delay_seconds: float) -> None:
        self._delegate = delegate
        self._delay_seconds = delay_seconds

    def page_count(self, source: Path) -> int:
        return self._delegate.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._delegate.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        return self._delegate.page_geometry(source, page_index)

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        time.sleep(self._delay_seconds)
        return self._delegate.render_page_png(source, page_index, scale=scale)

    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        self._delegate.stamp_markers(source, destination, markers, mark_size_pt=mark_size_pt)


def test_healthz_stays_responsive_while_an_intake_is_running(data_root: Path) -> None:
    """Regression test: intake used to run inline in the async handler,
    synchronously rasterizing every page -- for a submission that takes
    minutes to render, that blocked the whole (single-worker) event loop, so
    even an unrelated /healthz request would stall until intake finished.
    api/app.py now offloads the intake pipeline to a worker thread
    (``asyncio.to_thread``); this pins that behaviour against a real shared
    event loop (``with TestClient(...) as client`` -- without the ``with``,
    Starlette's TestClient gives each request its own throwaway event loop,
    which would pass this test even without the fix).
    """
    app = create_app(
        api_token=_TOKEN,
        data_root=data_root,
        intake_limits=IntakeLimits(max_size_bytes=5 * 1024 * 1024, max_pages=5),
        pdf_engine=_SlowPdfEngine(PdfiumPypdfEngine(), delay_seconds=1.0),
    )
    _seed_test(data_root)

    with TestClient(app) as client:
        intake_done = threading.Event()

        def _run_intake() -> None:
            client.post(
                "/tests/test-1/submissions",
                headers=_auth(),
                files={"file": ("student-a.pdf", _pdf_bytes(), "application/pdf")},
            )
            intake_done.set()

        intake_thread = threading.Thread(target=_run_intake)
        intake_thread.start()
        time.sleep(0.2)  # let the slow render actually start
        assert not intake_done.is_set()

        start = time.monotonic()
        response = client.get("/healthz")
        elapsed = time.monotonic() - start

        assert response.status_code == 200
        # Far under the 1s render delay: the event loop answered this while
        # intake was still running on its worker thread, not after it.
        assert elapsed < 0.5
        intake_thread.join(timeout=5)
        assert intake_done.is_set()
