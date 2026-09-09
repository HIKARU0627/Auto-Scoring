"""Integration tests for `jobs.export_processor.ExportJobProcessor` (Issue #23).

Real SQLite (`session_factory`/`store` fixtures, `tests/conftest.py`) and a
real `PdfiumPypdfEngine` -- these exercise the full generate -> verify ->
atomically-write pipeline, including fault injection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock

import pytest
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
    ReviewAction,
    Score,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import PageGeometry
from auto_scoring.jobs.export_processor import ExportJobProcessor, export_id
from tests.font_support import install_font_covering
from tests.pdf_content import drawn_text
from tests.support import at, make_grade, make_question, make_review, make_submission, make_test

#: The comment every export-ready fixture below stamps on the page. Named
#: because `japanese_font` has to hand the exact text to
#: `install_font_covering` -- the whole point being that the font is checked
#: for the glyphs this module actually draws, not assumed.
_FIXTURE_COMMENT = "理由の説明が不足しています。"


@pytest.fixture
def japanese_font(monkeypatch: pytest.MonkeyPatch) -> None:
    """Requested by every test whose export draws `_FIXTURE_COMMENT`, i.e.
    every one that seeds a reviewed submission and then actually renders it
    (tests/font_support.py). The score drawn alongside it is deliberately
    *not* required here: none of these assert on it, and demanding Latin
    glyphs too would skip them on machines whose only Japanese face has
    none."""
    install_font_covering(monkeypatch, _FIXTURE_COMMENT)


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
                comment=_FIXTURE_COMMENT,
                created_at=at(),
            )
        )
        uow.reviews.add(make_review(submission_id=submission_id))
        uow.commit()


def _seed_second_reviewed_submission_for_the_same_test(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    *,
    submission_id: str,
    original_filename: str,
) -> None:
    """A second, independent export-ready submission for the *same* `Test`
    row (`test-1`/`q-1`, already inserted by an earlier
    `_seed_reviewed_submission` call in the same test) -- unlike that
    helper, this does not re-add `Test`/`Question` (their ids are fixed and
    would collide) and gives every submission-scoped row (`GradeResult`,
    `Annotation`, `Review`) an id namespaced by ``submission_id`` so two
    calls in the same test never collide with each other either."""
    source_path = store.submission_source_pdf_path(submission_id)
    _write_source_pdf(source_path)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.submissions.add(
            make_submission(
                id=submission_id,
                original_filename=original_filename,
                source_pdf_path=f"submissions/{submission_id}/source.pdf",
                # `(test_id, source_pdf_sha256)` is unique -- `make_submission`'s
                # default sha256 would collide with the first submission's.
                source_pdf_sha256="1" * 64,
            )
        )
        uow.grades.add(make_grade(id=f"grade-{submission_id}", submission_id=submission_id))
        uow.annotations.add(
            Annotation(
                id=f"anno-score-{submission_id}",
                submission_id=submission_id,
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.SCORE,
                created_at=at(),
            )
        )
        uow.annotations.add(
            Annotation(
                id=f"anno-comment-{submission_id}",
                submission_id=submission_id,
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.COMMENT,
                comment=_FIXTURE_COMMENT,
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


@pytest.mark.usefixtures("japanese_font")
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


async def test_a_question_with_no_score_area_has_its_score_written_in_the_margin(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #150 本体の受入。**回答欄が検出できなかった設問がある答案でも
    出力でき、その設問の点数が紙に乗ること。**

    実機再検証 #4 では、この形の答案 (7教科中4教科) が 409 で拒まれて1枚も
    出力できなかった。ここで見るのは「ファイルが出来た」ではなく
    `tests.pdf_content.drawn_text` が読み出す**実際に置かれた文字**である
    (Issue #141 の教訓: インクの有無は「どの字か」を答えない)。

    余白帯は幅がページの3%しかないので、文字は帯の中で**縦に折り返して積まれる**
    (`_draw_text` の `_wrap_text`)。読める向きなので折り返し自体は問題ないが、
    **切り詰め (`_ELLIPSIS`) が起きていないこと**は見る。点数が "問2 4…" に
    なって出るのは、出ないのと同じくらい悪い。したがって改行を落として
    突き合わせる。
    """
    # 場所のある設問 (q-1) と無い設問 (q-2) を1ページに混ぜる。片方だけの
    # 答案では「余白帯に落ちた」のか「元から全部落ちた」のか区別できない。
    _write_source_pdf(store.submission_source_pdf_path("sub-1"))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(
                id="q-1",
                number="問1",
                score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06),
            )
        )
        uow.questions.add(make_question(id="q-2", number="問2", score_area=None))
        uow.submissions.add(make_submission())
        for question_id, grade_id in (("q-1", "grade-1"), ("q-2", "grade-2")):
            uow.grades.add(make_grade(id=grade_id, question_id=question_id))
            uow.reviews.add(
                make_review(
                    id=f"review-{question_id}",
                    question_id=question_id,
                    ai_grade_result_id=grade_id,
                )
            )
        uow.commit()
    install_font_covering(monkeypatch, "問1 問2 4/5")
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export = uow.exports.get(export_id(job))
        assert export is not None
    placed = "".join(drawn_text(store.root / export.file_path).split())
    # 肯定形が先: 通常の経路 (`score_area` のある設問) が生きていることを言って
    # から、余白帯の行を見る。前者が死ぬと後者だけでは気づけない。
    assert placed.count("4/5") == 2
    assert "4/5問2" in placed
    assert "…" not in placed


async def test_a_long_question_number_never_eats_the_margin_score(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """余白帯の行が長すぎて切り詰められるとき、**消えるのは番号であって点数では
    ないこと。**

    `_draw_text` は入り切らない行を省略記号で打ち切るので、**行の末尾にあるものが
    食われる。** 帯の幅はページの3%（A4で約18pt）しかなく、`Question.number` は
    `test_registration._MAX_QUESTION_NUMBER_BYTES`（40バイト）まで許される。
    番号を先に置くと、40文字のASCII番号は9行に折り返して点数を枠外へ押し出し、
    **確定した点数が消えたまま出力は成功を返す**（Issue #121 と同じ形）。

    ここでは1ページに18件（帯の容量ぴったり、つまり1件あたりの高さが最小になる条件）を
    並べ、そのうち1件に上限いっぱいの番号を与える。容量を1件でも増やせば 409 に
    なるので、これが「切り詰めが実際に起こりうる最小の高さ」である。
    """
    long_number = "Q" + "1234567890" * 3 + "123456789"  # 40 bytes, the limit
    assert len(long_number.encode()) == 40
    _write_source_pdf(store.submission_source_pdf_path("sub-1"))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.submissions.add(make_submission())
        for index in range(18):
            question_id = f"q-{index:02d}"
            uow.questions.add(
                make_question(
                    id=question_id,
                    number=long_number if index == 0 else f"問{index:02d}",
                    score_area=None,
                )
            )
            uow.grades.add(make_grade(id=f"grade-{index:02d}", question_id=question_id))
            uow.reviews.add(
                make_review(
                    id=f"review-{index:02d}",
                    question_id=question_id,
                    ai_grade_result_id=f"grade-{index:02d}",
                )
            )
        uow.commit()
    install_font_covering(monkeypatch, "問0123456789/Q")
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export = uow.exports.get(export_id(job))
        assert export is not None
    placed = "".join(drawn_text(store.root / export.file_path).split())
    # 肯定形が先: 18件ぶんの点数がすべて紙に乗っていること。ここが死ぬと下の
    # 「切り詰めは番号側に起きた」は、何も描かれていなくても真になる。
    assert placed.count("4/5") == 18
    # そして切り詰めは実際に起きている（起きない条件で測っても意味がない）。
    assert "…" in placed
    # それでも消えたのは番号の末尾で、点数ではない。
    assert long_number not in placed
    assert "4/5Q1234" in placed


async def test_exports_a_question_a_person_graded_after_ai_failed(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #118, and the reason this test exists at all: a question the AI
    never graded has no AI `GradeResult` and no AI annotations, so *every*
    downstream consumer of "the confirmed grade" has to work from the human
    row alone.

    Export is the one that fails silently -- it does not raise, it just
    draws a page with nothing on it (Issue #120: dropping the SCORE region
    from the screen broke PDF output without a single failing test). So the
    assertion here is not "it succeeded" but "the score is on the page".
    """
    # Latin glyphs, not `japanese_font`'s Japanese ones: the whole assertion
    # here is that the *score* reaches the page, so the font has to be able
    # to draw one (tests/font_support.py -- coverage differs per face).
    install_font_covering(monkeypatch, "3/5")
    source_path = store.submission_source_pdf_path("sub-1")
    _write_source_pdf(source_path)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(
                score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06),
                comment_area=NormalizedRect(x=0.05, y=0.85, width=0.9, height=0.12),
            )
        )
        uow.submissions.add(make_submission())
        # No AI grade and no AI annotation: the grading job failed
        # permanently, so Issue #97 wrote neither.
        uow.grades.add(
            make_grade(
                id="grade-human",
                source=GradingSource.HUMAN,
                score=Score(awarded=3, maximum=5),
            )
        )
        uow.annotations.add(
            Annotation(
                id="anno-score",
                submission_id="sub-1",
                question_id="q-1",
                source=GradingSource.HUMAN,
                kind=AnnotationKind.SCORE,
                created_at=at(),
            )
        )
        uow.reviews.add(
            make_review(
                action=ReviewAction.MODIFIED,
                ai_grade_result_id=None,
                human_grade_result_id="grade-human",
            )
        )
        uow.commit()
    job = _seed_export_job(session_factory)
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    result = await processor.process(job)

    assert result.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export = uow.exports.get(export_id(job))
    assert export is not None
    output_path = store.root / export.file_path
    assert "3/5" in _extracted_text(output_path)


def _extracted_text(path: Path) -> str:
    return "".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


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


@pytest.mark.usefixtures("japanese_font")
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


@pytest.mark.usefixtures("japanese_font")
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


@pytest.mark.usefixtures("japanese_font")
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


@pytest.mark.usefixtures("japanese_font")
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


@pytest.mark.usefixtures("japanese_font")
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
    session_factory: sessionmaker[Session], store: LocalFileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 review, round 2: if a reviewer edits/regrades a question between
    an export's original (lost) file and a later repair-retry of the same
    job, the repaired file must still reflect exactly what was true at the
    *recorded* `review_versions` snapshot -- never a newer grade silently
    attributed to that older row's provenance."""
    # Unlike its siblings this one reads the drawn score back out of the PDF,
    # so the font has to carry the digits as well as the comment -- see
    # `japanese_font`, whose weaker requirement would not do here.
    install_font_covering(monkeypatch, _FIXTURE_COMMENT + "4/5" + "2/5")
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


@pytest.mark.usefixtures("japanese_font")
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


@pytest.mark.usefixtures("japanese_font")
async def test_a_new_export_for_a_different_submission_does_not_reuse_a_path_reserved_by_another(
    session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """P1 review, round 4: R3's fix (the test above) only reserved paths
    recorded by `Export` rows for the *same* submission
    (`ExportRepository.list_for_submission`) -- but export filenames are
    derived from the source file's stem alone, with no submission id in the
    path (`LocalFileStore.allocate_export_path`). Two different submissions
    that happen to share an original filename share the same export-path
    namespace, so a path submission A's Export row already claims (even one
    whose file write never landed) must stay reserved when a wholly
    different submission B is exported too -- not only when A itself is
    re-exported."""
    _seed_reviewed_submission(
        session_factory, store, submission_id="sub-1", original_filename="答案A.pdf"
    )
    job_a = _seed_export_job(session_factory, job_id="job-a", submission_id="sub-1")
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())

    first = await processor.process(job_a)
    assert first.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export_a = uow.exports.get(export_id(job_a))
        assert export_a is not None
    assert export_a.file_path == "exports/答案A_corrected.pdf"
    (store.root / export_a.file_path).unlink()  # simulate the file being lost after the DB commit

    # A second, DIFFERENT submission (its own Test/Question/Review/Grade)
    # that just happens to share the same original filename.
    _seed_second_reviewed_submission_for_the_same_test(
        session_factory, store, submission_id="sub-2", original_filename="答案A.pdf"
    )
    job_b = _seed_export_job(session_factory, job_id="job-b", submission_id="sub-2")
    second = await processor.process(job_b)

    assert second.outcome is ProcessingOutcome.SUCCEEDED
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        export_b = uow.exports.get(export_id(job_b))
        assert export_b is not None
    # Must NOT reuse export_a's still-reserved path, even though export_a
    # belongs to an entirely different submission.
    assert export_b.file_path == "exports/答案A_corrected_2.pdf"
    path_b = store.root / export_b.file_path
    assert path_b.exists()
