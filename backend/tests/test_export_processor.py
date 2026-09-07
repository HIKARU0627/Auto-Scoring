"""Integration tests for `jobs.export_processor.ExportJobProcessor` (Issue #23).

Real SQLite (`session_factory`/`store` fixtures, `tests/conftest.py`) and a
real `PdfiumPypdfEngine` -- these exercise the full generate -> verify ->
atomically-write pipeline, including fault injection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock

from pypdf import PdfReader, PdfWriter
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.job_execution import ProcessingOutcome
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    Export,
    GradingSource,
    Job,
    JobKind,
    JobState,
    NormalizedRect,
    Score,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import PageGeometry
from auto_scoring.jobs.export_processor import ExportJobProcessor, export_id
from tests.support import at, make_grade, make_question, make_review, make_submission, make_test


def _write_source_pdf(path: Path, *, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _seed_reviewed_submission(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    *,
    submission_id: str = "sub-1",
    pages: int = 1,
    original_filename: str = "答案A.pdf",
) -> None:
    """One test, one submission, one confirmed question (page 1) with an
    approved AI grade, a SCORE mark (resolved via `score_area`) and a
    Japanese COMMENT mark (resolved via `comment_area`) -- a minimal but
    fully export-ready fixture.
    """
    source_path = store.submission_source_pdf_path(submission_id)
    _write_source_pdf(source_path, pages=pages)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(
                score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06),
                comment_area=NormalizedRect(x=0.05, y=0.85, width=0.9, height=0.12),
            )
        )
        uow.submissions.add(make_submission(id=submission_id, original_filename=original_filename))
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
        uow.annotations.add(
            Annotation(
                id="anno-comment",
                submission_id=submission_id,
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.COMMENT,
                comment="理由の説明が不足しています。",
                created_at=at(),
            )
        )
        uow.reviews.add(make_review(submission_id=submission_id))
        uow.commit()


def _seed_export_job(
    session_factory: sessionmaker[Session], *, job_id: str = "job-1", submission_id: str = "sub-1"
) -> Job:
    """Persists a RUNNING `Job` (kind=EXPORT) -- ``exports.job_id`` has a real
    foreign key onto ``jobs.id``, so, like the real router (`POST .../export`
    commits the `Job` row before ever enqueuing it), a test must create one
    before `ExportJobProcessor.process` can insert an `Export` referencing it.
    """
    job = Job(
        id=job_id,
        kind=JobKind.EXPORT,
        submission_id=submission_id,
        state=JobState.RUNNING,
        created_at=at(),
        updated_at=at(),
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.jobs.add(job)
        uow.commit()
    return job


class _FailingEngine:
    """Delegates everything except `render_annotations`, which always fails
    -- simulates a PDF generation fault (Issue #23 acceptance: 失敗注入)."""

    def __init__(self, delegate: PdfEngine) -> None:
        self._delegate = delegate

    def page_count(self, source: Path) -> int:
        return self._delegate.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._delegate.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        return self._delegate.page_geometry(source, page_index)

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        return self._delegate.render_page_png(source, page_index, scale=scale)

    def stamp_markers(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError

    def render_annotations(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated rendering failure")


async def test_generates_an_annotated_pdf_and_records_the_export(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export = uow.exports.get(export_id(job))
        assert export is not None
        assert export.submission_id == "sub-1"
        assert export.job_id == "job-1"
        assert [v.question_id for v in export.review_versions] == ["q-1"]
        assert export.review_versions[0].version == 1

    output_path = store.root / export.file_path
    assert output_path.name == "答案A_corrected.pdf"
    reread = PdfReader(str(output_path))
    assert len(reread.pages) == 1
    assert hashlib.sha256(output_path.read_bytes()).hexdigest() == export.file_sha256

    # The source PDF itself is never modified (§35-4).
    assert (
        store.submission_source_pdf_path("sub-1").stat().st_size
        == (store.root / "submissions" / "sub-1" / "source.pdf").stat().st_size
    )


async def test_refuses_when_a_question_has_no_confirmed_review(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    source_path = store.submission_source_pdf_path("sub-1")
    _write_source_pdf(source_path)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(make_question())
        uow.submissions.add(make_submission())
        uow.commit()  # no Review at all for q-1
    job = _seed_export_job(session_factory)

    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert result.error_message is not None and "q-1" in result.error_message
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.exports.list_for_submission("sub-1") == []
    assert not store.exports_dir().exists()


async def test_replaying_the_same_job_is_idempotent(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    first = await processor.process(job)
    second = await processor.process(job)

    assert first.outcome is ProcessingOutcome.SUCCEEDED
    assert second.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert len(uow.exports.list_for_submission("sub-1")) == 1
    assert len(list(store.exports_dir().glob("*.pdf"))) == 1


async def test_two_different_jobs_for_the_same_submission_produce_two_numbered_files(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    job1 = _seed_export_job(session_factory, job_id="job-1")
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    await processor.process(job1)
    first_export = _list_exports(session_factory)[0]
    first_path = store.root / first_export.file_path
    first_bytes = first_path.read_bytes()

    job2 = _seed_export_job(session_factory, job_id="job-2")
    await processor.process(job2)

    exports = _list_exports(session_factory)
    assert len(exports) == 2
    paths = sorted(store.root / export.file_path for export in exports)
    assert paths[0].name == "答案A_corrected.pdf"
    assert paths[1].name == "答案A_corrected_2.pdf"
    # The first successful export's file is completely untouched by the second run.
    assert first_path.read_bytes() == first_bytes


def _list_exports(session_factory: sessionmaker[Session]) -> list[Export]:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        return uow.exports.list_for_submission("sub-1")


async def test_a_generation_failure_leaves_no_export_and_no_file_and_does_not_touch_the_source(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    job = _seed_export_job(session_factory)
    source_path = store.submission_source_pdf_path("sub-1")
    original_bytes = source_path.read_bytes()
    processor = ExportJobProcessor(
        session_factory, store, _FailingEngine(PdfiumPypdfEngine()), Lock()
    )

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert "simulated rendering failure" in (result.error_message or "")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.exports.list_for_submission("sub-1") == []
    assert not store.exports_dir().exists()
    assert source_path.read_bytes() == original_bytes


async def test_a_prior_successful_export_survives_a_later_failed_attempt(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    _seed_reviewed_submission(session_factory, store)
    job1 = _seed_export_job(session_factory, job_id="job-1")
    good_processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    await good_processor.process(job1)
    first_export = _list_exports(session_factory)[0]
    first_path = store.root / first_export.file_path
    first_bytes = first_path.read_bytes()

    job2 = _seed_export_job(session_factory, job_id="job-2")
    failing_processor = ExportJobProcessor(
        session_factory, store, _FailingEngine(PdfiumPypdfEngine()), Lock()
    )
    result = await failing_processor.process(job2)

    assert result.outcome is ProcessingOutcome.FAILED
    assert _list_exports(session_factory) == [first_export]
    assert first_path.read_bytes() == first_bytes


async def test_a_missing_file_after_a_prior_commit_is_regenerated_and_repaired(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P1 review: a crash between `Export`'s DB commit and the file write
    that follows it (`adapters.atomic`'s own documented risk) leaves a
    committed row naming a file that was never written. A later run of the
    same job must notice the file is missing, regenerate it, and repair the
    row in place -- not treat the mere existence of the row as "already
    done" (which would leave `reuse_existing` resolving to a non-existent
    file forever after)."""
    _seed_reviewed_submission(session_factory, store)
    job = _seed_export_job(session_factory)
    stale_export = Export(
        id=export_id(job),
        submission_id="sub-1",
        job_id=job.id,
        file_path="exports/answer_corrected.pdf",
        file_sha256="0" * 64,  # deliberately wrong -- the "lost" file's real hash
        created_at=at(),
        review_versions=(),
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.exports.add(stale_export)
        uow.commit()
    assert not (store.root / stale_export.file_path).exists()

    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    output_path = store.root / stale_export.file_path
    assert output_path.exists()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        exports = uow.exports.list_for_submission("sub-1")
        assert len(exports) == 1  # repaired in place, never a second row
        repaired = exports[0]
        assert repaired.id == stale_export.id
        assert repaired.file_sha256 == hashlib.sha256(output_path.read_bytes()).hexdigest()


async def test_a_job_cancelled_before_publish_does_not_create_an_export(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P2 review: cancelling the coroutine awaiting `to_thread(...)` does not
    stop the underlying thread -- `_generate` keeps running regardless and
    must itself notice, immediately before publishing, that the job's own
    row has since moved to CANCELLED (as `JobQueueService._finalize_cancelled`
    would have written it), and refuse to commit an `Export`/write a file for
    a job the queue no longer considers RUNNING."""
    _seed_reviewed_submission(session_factory, store)
    job = _seed_export_job(session_factory)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        cancelled = uow.jobs.get(job.id)
        assert cancelled is not None
        uow.jobs.save(
            cancelled.transitioned_to(JobState.CANCELLED, updated_at=at()),
            expected_state=JobState.RUNNING,
        )
        uow.commit()

    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.FAILED
    assert "cancelled" in (result.error_message or "")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.exports.list_for_submission("sub-1") == []
    assert not store.exports_dir().exists()


async def test_repair_regenerates_from_the_recorded_snapshot_not_a_later_review_change(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P2 review, round 2: if a reviewer edits/regrades a question between
    an export's original (lost) file and a later repair-retry of the same
    job, the repaired file must still reflect exactly what was true at the
    *recorded* `review_versions` snapshot -- never a newer grade silently
    attributed to that older row's provenance."""
    _seed_reviewed_submission(session_factory, store)  # q-1: grade-1 (4/5), version=1
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    first = await processor.process(job)
    assert first.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        original_export = uow.exports.get(export_id(job))
        assert original_export is not None
    original_path = store.root / original_export.file_path
    original_path.unlink()  # simulate the file being lost after the DB commit

    # The review moves on before the retry: a fresh grade for q-1.
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.grades.add(
            make_grade(id="grade-2", score=Score(awarded=2, maximum=5), created_at=at(10))
        )
        uow.reviews.add(
            make_review(id="review-2", version=2, ai_grade_result_id="grade-2", created_at=at(10))
        )
        uow.commit()

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repaired = uow.exports.get(export_id(job))
        assert repaired is not None
        # Provenance is untouched: still the ORIGINAL snapshot/timestamp,
        # not the review's current (version=2) state.
        assert repaired.review_versions == original_export.review_versions
        assert repaired.created_at == original_export.created_at
        assert len(uow.exports.list_for_submission("sub-1")) == 1  # never a second row

    # Content matches the ORIGINAL grade (4/5), not the newer one (2/5).
    text = PdfReader(str(original_path)).pages[0].extract_text()
    assert "4/5" in text
    assert "2/5" not in text


async def test_a_new_export_never_reuses_a_path_a_lost_export_row_still_reserves(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P1 review, round 3: `LocalFileStore.allocate_export_path`'s own
    ``.exists()`` check can't see a path an `Export` row already names but
    whose file write never landed (the exact "DB commit succeeded, file
    write failed" scenario `_existing_file_is_intact`/
    `_repair_existing_export` exist for). A second, unrelated export
    request must never be handed that same path -- occupying it would let
    a later repair-retry of the original job overwrite the second export's
    file out from under it."""
    _seed_reviewed_submission(session_factory, store)
    job_a = _seed_export_job(session_factory, job_id="job-a")
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    first = await processor.process(job_a)
    assert first.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export_a = uow.exports.get(export_id(job_a))
        assert export_a is not None
    assert export_a.file_path == "exports/答案A_corrected.pdf"
    path_a = store.root / export_a.file_path
    path_a.unlink()  # simulate the file being lost after the DB commit

    # A second, unrelated export request for the same submission (e.g. the
    # review moved on in the meantime -- ACCEPT_NEW_SUPERSEDING) creates a
    # brand new job.
    job_b = _seed_export_job(session_factory, job_id="job-b")
    second = await processor.process(job_b)

    assert second.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export_b = uow.exports.get(export_id(job_b))
        assert export_b is not None
    # Must NOT reuse export_a's still-reserved path.
    assert export_b.file_path == "exports/答案A_corrected_2.pdf"
    path_b = store.root / export_b.file_path
    assert path_b.exists()
    path_b_bytes = path_b.read_bytes()

    # A later repair-retry of the original job A writes only to its OWN
    # path, never touching B's file.
    third = await processor.process(job_a)
    assert third.outcome is ProcessingOutcome.SUCCEEDED
    assert path_a.exists()
    assert path_b.read_bytes() == path_b_bytes  # untouched by A's repair
