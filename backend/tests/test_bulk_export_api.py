"""HTTP integration tests for the test-wide bulk export (Issue #142, parent #3).

Same style as `test_export_api.py`: `TestClient` + real SQLite with the
app's lifespan started, so `jobs.queue.JobQueueService`'s background worker
really runs the real `ExportJobProcessor` against a real `PdfiumPypdfEngine`.
A bulk export that only *claims* to have queued 40 jobs is exactly the thing
this endpoint exists to stop being possible, so nothing here is faked.

The property under test throughout is **一括で出すことが、1枚の巻き添えで
止まらない**: one unconfirmed sheet, or one sheet whose render fails, must
cost the reviewer that sheet and nothing else.
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
from auto_scoring.domain.pdf_export import ExportRefusalReason
from auto_scoring.jobs.export_processor import ExportJobProcessor
from tests.font_support import install_font_covering
from tests.support import at, make_grade, make_question, make_review, make_submission, make_test

_TOKEN = "bulk-export-test-token"
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
    """The glyphs an export here needs are the score's own (``"4/5"``) --
    Latin, not Japanese. Same reasoning as `test_export_api.py`'s fixture."""
    install_font_covering(monkeypatch, "0123456789/")


def _write_source_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _seed_test_with_one_question(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06))
        )
        uow.commit()


def _seed_submission(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    *,
    submission_id: str,
    confirmed: bool = True,
    with_source_pdf: bool = True,
) -> None:
    """One answer sheet of the seeded test.

    ``confirmed=False`` leaves it with no `Review`, which is the
    `ExportRefusalReason.UNCONFIRMED_QUESTIONS` refusal. ``with_source_pdf=
    False`` leaves the row pointing at a file that is not on disk, which is
    how a *job* (rather than the gate) is made to fail here -- the failure
    happens inside the real processor, not in a stubbed one.
    """
    if with_source_pdf:
        _write_source_pdf(store.submission_source_pdf_path(submission_id))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.submissions.add(
            make_submission(
                id=submission_id,
                source_pdf_path=f"submissions/{submission_id}/source.pdf",
                # Distinct per submission: `(test_id, source_pdf_sha256)` is
                # unique, which is how re-uploading the same answer sheet is
                # caught (`domain.submission_intake.decide_reintake`).
                source_pdf_sha256=submission_id.encode().hex().ljust(64, "0")[:64],
                original_filename=f"{submission_id}.pdf",
            )
        )
        if not confirmed:
            uow.commit()
            return
        uow.grades.add(make_grade(id=f"grade-{submission_id}", submission_id=submission_id))
        uow.annotations.add(
            Annotation(
                id=f"anno-{submission_id}",
                submission_id=submission_id,
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.SCORE,
                created_at=at(),
            )
        )
        uow.reviews.add(
            make_review(
                id=f"review-{submission_id}",
                submission_id=submission_id,
                ai_grade_result_id=f"grade-{submission_id}",
            )
        )
        uow.commit()


def _wait_until_settled(
    client: TestClient, job_ids: list[str], *, timeout: float = 30.0
) -> dict[str, dict[str, Any]]:
    """Poll every job until none is still queued/running; return them by id."""
    deadline = time.monotonic() + timeout
    while True:
        bodies: dict[str, dict[str, Any]] = {}
        for job_id in job_ids:
            response = client.get(f"/jobs/{job_id}", headers=_AUTH)
            assert response.status_code == 200, response.text
            bodies[job_id] = response.json()
        if all(body["state"] in {"succeeded", "failed", "cancelled"} for body in bodies.values()):
            return bodies
        if time.monotonic() > deadline:
            raise AssertionError(f"jobs never settled: {bodies}")
        time.sleep(0.01)


def _items_by_submission(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["submission_id"]: item for item in body["items"]}


def test_bulk_export_of_an_unknown_test_returns_404(client: TestClient) -> None:
    response = client.post("/tests/does-not-exist/export", headers=_AUTH)
    assert response.status_code == 404


def test_bulk_export_of_a_test_with_no_submissions_returns_an_empty_list(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """**Zero targets is a normal answer, not an error.** The screen has to
    be able to say "対象が0件です" *before* the reviewer picks an output
    folder, and it can only do that if asking is cheap and succeeds."""
    _seed_test_with_one_question(session_factory)

    response = client.post("/tests/test-1/export", headers=_AUTH)

    assert response.status_code == 200, response.text
    assert response.json() == {"test_id": "test-1", "items": []}


@pytest.mark.usefixtures("score_font")
def test_bulk_export_queues_every_submission_and_writes_one_file_each(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """添削は生徒ごとに返すものなので束ねない (Issue #142): three answer
    sheets produce three separate files, named by the existing single-export
    rule (`LocalFileStore.allocate_export_path`)."""
    _seed_test_with_one_question(session_factory)
    for submission_id in ("sub-1", "sub-2", "sub-3"):
        _seed_submission(session_factory, store, submission_id=submission_id)

    response = client.post("/tests/test-1/export", headers=_AUTH)

    assert response.status_code == 200, response.text
    items = _items_by_submission(response.json())
    assert len(items) == 3
    assert {item["status"] for item in items.values()} == {"queued"}
    _wait_until_settled(client, [item["job_id"] for item in items.values()])

    written: set[str] = set()
    for submission_id in ("sub-1", "sub-2", "sub-3"):
        exports = client.get(f"/submissions/{submission_id}/exports", headers=_AUTH).json()
        assert len(exports) == 1, submission_id
        path = store.root / exports[0]["file_path"]
        assert path.exists()
        written.add(path.name)
    assert written == {"sub-1_corrected.pdf", "sub-2_corrected.pdf", "sub-3_corrected.pdf"}


@pytest.mark.usefixtures("score_font")
def test_a_refused_submission_does_not_stop_the_rest_and_is_listed_with_its_reason(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """The single-submission endpoint answers this case with a 409 and
    nothing else. **A bulk run must not**: one unconfirmed sheet in the
    middle of 40 would otherwise cost the reviewer the other 39. The refused
    one comes back as a row naming its reason and its questions."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")
    _seed_submission(session_factory, store, submission_id="sub-2", confirmed=False)
    _seed_submission(session_factory, store, submission_id="sub-3")

    response = client.post("/tests/test-1/export", headers=_AUTH)

    assert response.status_code == 200, response.text
    items = _items_by_submission(response.json())
    assert items["sub-2"]["status"] == "refused"
    assert items["sub-2"]["refusal_code"] == ExportRefusalReason.UNCONFIRMED_QUESTIONS.value
    assert items["sub-2"]["refusal_question_ids"] == ["q-1"]
    assert items["sub-2"]["job_id"] is None

    # The other two were not merely reported as queued -- they really ran.
    assert items["sub-1"]["status"] == "queued"
    assert items["sub-3"]["status"] == "queued"
    settled = _wait_until_settled(client, [items["sub-1"]["job_id"], items["sub-3"]["job_id"]])
    assert {body["state"] for body in settled.values()} == {"succeeded"}
    for submission_id in ("sub-1", "sub-3"):
        assert len(client.get(f"/submissions/{submission_id}/exports", headers=_AUTH).json()) == 1
    assert client.get("/submissions/sub-2/exports", headers=_AUTH).json() == []


@pytest.mark.usefixtures("score_font")
def test_a_job_that_fails_mid_run_does_not_stop_the_rest(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """The other half of "途中で止めない": a sheet that passes the gate and
    then fails while rendering. `sub-2`'s source PDF is not on disk, so the
    real `ExportJobProcessor` fails on it -- and the two either side of it
    still produce their files."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")
    _seed_submission(session_factory, store, submission_id="sub-2", with_source_pdf=False)
    _seed_submission(session_factory, store, submission_id="sub-3")

    response = client.post("/tests/test-1/export", headers=_AUTH)

    items = _items_by_submission(response.json())
    assert {item["status"] for item in items.values()} == {"queued"}
    settled = _wait_until_settled(client, [item["job_id"] for item in items.values()])

    assert settled[items["sub-2"]["job_id"]]["state"] == "failed"
    assert settled[items["sub-2"]["job_id"]]["last_error"]
    assert settled[items["sub-1"]["job_id"]]["state"] == "succeeded"
    assert settled[items["sub-3"]["job_id"]]["state"] == "succeeded"
    for submission_id in ("sub-1", "sub-3"):
        assert len(client.get(f"/submissions/{submission_id}/exports", headers=_AUTH).json()) == 1


@pytest.mark.usefixtures("score_font")
def test_a_second_run_re_exports_only_the_submissions_it_is_asked_for(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """「失敗分だけを再実行できること」(Issue #142). The screen already holds
    the failed rows, so re-running them is the same call with a shorter
    list -- there is no server-side "bulk run" to resume."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")
    _seed_submission(session_factory, store, submission_id="sub-2", with_source_pdf=False)
    first = _items_by_submission(client.post("/tests/test-1/export", headers=_AUTH).json())
    _wait_until_settled(client, [item["job_id"] for item in first.values()])
    _write_source_pdf(store.submission_source_pdf_path("sub-2"))

    response = client.post(
        "/tests/test-1/export", headers=_AUTH, json={"submission_ids": ["sub-2"]}
    )

    assert response.status_code == 200, response.text
    items = _items_by_submission(response.json())
    assert list(items) == ["sub-2"]
    assert items["sub-2"]["status"] == "queued"
    settled = _wait_until_settled(client, [items["sub-2"]["job_id"]])
    assert settled[items["sub-2"]["job_id"]]["state"] == "succeeded"
    # sub-1 was not asked for, so it was not re-run: still its one file.
    assert len(client.get("/submissions/sub-1/exports", headers=_AUTH).json()) == 1


def test_submission_ids_that_are_not_in_this_test_are_refused(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """Silently dropping them would look like a successful run over a
    shorter list, and the caller would never learn that what it asked for is
    not going to happen."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")

    response = client.post(
        "/tests/test-1/export", headers=_AUTH, json={"submission_ids": ["sub-1", "not-here"]}
    )

    assert response.status_code == 400
    assert response.json()["detail"]["submission_ids"] == ["not-here"]
    assert client.get("/submissions/sub-1/exports", headers=_AUTH).json() == []


@pytest.mark.usefixtures("score_font")
def test_an_already_exported_submission_comes_back_as_reused_rather_than_re_rendered(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """`decide_reexport` is the *same* decision the single endpoint makes.
    A reviewer who re-runs a whole test after fixing one sheet must not get
    39 byte-for-byte duplicate files."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")
    first = _items_by_submission(client.post("/tests/test-1/export", headers=_AUTH).json())
    _wait_until_settled(client, [first["sub-1"]["job_id"]])

    second = _items_by_submission(client.post("/tests/test-1/export", headers=_AUTH).json())

    assert second["sub-1"]["status"] == "reused"
    assert second["sub-1"]["job_id"] is None
    assert second["sub-1"]["export"]["file_path"].endswith("sub-1_corrected.pdf")
    assert len(client.get("/submissions/sub-1/exports", headers=_AUTH).json()) == 1


@pytest.mark.usefixtures("score_font")
def test_the_exported_file_can_be_fetched_as_pdf_bytes(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """The app writes each sheet into the folder the reviewer picked, and
    it deliberately does not know where ``app-data/`` is -- so it needs the
    bytes, not a path (`api.export_router.get_export_file`)."""
    _seed_test_with_one_question(session_factory)
    _seed_submission(session_factory, store, submission_id="sub-1")
    items = _items_by_submission(client.post("/tests/test-1/export", headers=_AUTH).json())
    _wait_until_settled(client, [items["sub-1"]["job_id"]])
    export = client.get("/submissions/sub-1/exports", headers=_AUTH).json()[0]

    response = client.get(f"/exports/{export['id']}/file", headers=_AUTH)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == (store.root / export["file_path"]).read_bytes()
    assert response.content.startswith(b"%PDF")


def test_fetching_an_unknown_export_file_returns_404(client: TestClient) -> None:
    assert client.get("/exports/does-not-exist/file", headers=_AUTH).status_code == 404
