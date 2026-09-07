"""HTTP integration tests for `api.export_router` (Issue #23, parent #3).

Exercises the endpoints end to end through `TestClient` + real SQLite, with
the app's lifespan actually started (``with TestClient(app) as client:``) so
`jobs.queue.JobQueueService`'s background worker really runs the real
`ExportJobProcessor` against a real `PdfiumPypdfEngine` -- the same "run to
completion through the real queue" style `test_jobs_api.py` uses.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from threading import Lock
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    GradingSource,
    NormalizedRect,
)
from auto_scoring.jobs.export_processor import ExportJobProcessor
from tests.font_support import install_font_covering
from tests.support import at, make_grade, make_question, make_review, make_submission, make_test

_TOKEN = "export-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def client(session_factory: sessionmaker[Session], store: LocalFileStore) -> Iterator[TestClient]:
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    app = create_app(
        api_token=_TOKEN,
        session_factory=session_factory,
        data_root=store.root,
        job_processor=processor,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def score_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requested by every test that runs an export to completion here.

    Unlike `test_export_processor.py`'s `japanese_font`, the fixtures here
    seed a SCORE mark and no comment, so the glyphs the export needs are the
    score's own (`domain/pdf_export._score_text` -> ``"4/5"``) -- Latin,
    not Japanese (tests/font_support.py).
    """
    install_font_covering(monkeypatch, "0123456789/")


def _write_source_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _seed_reviewed_submission(
    session_factory: sessionmaker[Session], store: LocalFileStore, *, submission_id: str = "sub-1"
) -> None:
    _write_source_pdf(store.submission_source_pdf_path(submission_id))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06))
        )
        uow.submissions.add(make_submission(id=submission_id, original_filename="答案A.pdf"))
        uow.grades.add(make_grade())
        uow.annotations.add(
            Annotation(
                id="anno-score",
                submission_id=submission_id,
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.SCORE,
                created_at=at(),
            )
        )
        uow.reviews.add(make_review(submission_id=submission_id))
        uow.commit()


def _wait_until_job_state(
    client: TestClient, job_id: str, state: str, *, timeout: float = 10.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/jobs/{job_id}", headers=_AUTH)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        if body["state"] == state:
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"job {job_id} never reached {state!r}, last body: {body}")
        time.sleep(0.01)


def test_export_of_a_submission_with_no_test_returns_404(client: TestClient) -> None:
    response = client.post("/submissions/does-not-exist/export", headers=_AUTH)
    assert response.status_code == 404


def test_export_refuses_and_names_unconfirmed_questions(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _write_source_pdf(store.submission_source_pdf_path("sub-1"))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.commit()  # no Review at all -> q-1 is unconfirmed

    response = client.post("/submissions/sub-1/export", headers=_AUTH)

    assert response.status_code == 409
    assert response.json()["detail"]["question_ids"] == ["q-1"]


@pytest.mark.usefixtures("score_font")
def test_export_queues_a_job_and_completes_through_the_real_queue(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)

    response = client.post("/submissions/sub-1/export", headers=_AUTH)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["decision"] == "accept_new"
    job_id = body["job_id"]
    assert job_id is not None

    job_body = _wait_until_job_state(client, job_id, "succeeded")
    assert job_body["kind"] == "export"

    listing = client.get("/submissions/sub-1/exports", headers=_AUTH)
    assert listing.status_code == 200
    exports = listing.json()
    assert len(exports) == 1
    assert exports[0]["job_id"] == job_id
    output_path = store.root / exports[0]["file_path"]
    assert output_path.exists()
    assert output_path.name == "答案A_corrected.pdf"


@pytest.mark.usefixtures("score_font")
def test_reexporting_unchanged_review_state_reuses_the_existing_export(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    first = client.post("/submissions/sub-1/export", headers=_AUTH).json()
    _wait_until_job_state(client, first["job_id"], "succeeded")

    second = client.post("/submissions/sub-1/export", headers=_AUTH)

    assert second.status_code == 200
    body = second.json()
    assert body["decision"] == "reuse_existing"
    assert body["job_id"] is None
    assert body["export"]["id"] is not None

    listing = client.get("/submissions/sub-1/exports", headers=_AUTH)
    assert len(listing.json()) == 1


@pytest.mark.usefixtures("score_font")
def test_reexporting_when_the_previous_export_s_file_has_gone_missing_queues_a_fresh_one(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P1 review, round 2: `decide_reexport` alone (unchanged review state)
    would say `reuse_existing`, but if the previously recorded export's file
    is missing (e.g. it was deleted, or a crash between its DB commit and
    the file write that follows it), the endpoint must not claim success
    against a file that isn't there -- it must queue a fresh export
    instead."""
    _seed_reviewed_submission(session_factory, store)
    first = client.post("/submissions/sub-1/export", headers=_AUTH).json()
    _wait_until_job_state(client, first["job_id"], "succeeded")
    first_listing = client.get("/submissions/sub-1/exports", headers=_AUTH).json()
    assert len(first_listing) == 1
    (store.root / first_listing[0]["file_path"]).unlink()

    second = client.post("/submissions/sub-1/export", headers=_AUTH)

    assert second.status_code == 202, second.text
    body = second.json()
    assert body["decision"] == "accept_new_superseding"
    assert body["job_id"] is not None

    _wait_until_job_state(client, body["job_id"], "succeeded")
    listing = client.get("/submissions/sub-1/exports", headers=_AUTH).json()
    assert len(listing) == 2
    new_export = next(e for e in listing if e["job_id"] == body["job_id"])
    assert (store.root / new_export["file_path"]).exists()
