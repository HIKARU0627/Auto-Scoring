"""API-level tests for the answer-intake endpoints (Issue #17)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.models import NormalizedRect
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
