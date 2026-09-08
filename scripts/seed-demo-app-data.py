#!/usr/bin/env python3
"""Fill an ``app-data/`` root with invented data, so screens have something on them.

Development scaffolding only, and the other half of
``scripts/screenshot-linux-app.sh``: a screen photographed against an empty
database says nothing about density, hierarchy or narrow-width behaviour, and
the state that puts something on every screen cannot be reached by hand
through the UI -- registering a test runs OCR and AI, and a development
machine has no credentials for either (docs/linux-desktop-development.md §4.4).

    uv run --project backend python scripts/seed-demo-app-data.py [--app-data-dir DIR]

**Everything written here is invented**, and deliberately reads as invented:
placeholder test names, placeholder recognized text, placeholder rationales.
The answer PDF is the PoC 3 fixture already in the repository
(``app/test/fixtures/a4-portrait.pdf``). Nothing from a real grading job may
be seeded -- these screens become screenshots, and this repository is public
(AGENTS.md "Security").

Rather than a plausible average, the state is chosen to put every screen's
interesting case on screen at once: a test still being registered next to a
registered one, an answer whose dependency chain is stuck behind a
low-confidence result, an answer with a failed question, and a finished one.

Safety: this script **resets** the root it seeds by deleting every test in it,
which cascades to every answer, grade, annotation and review underneath. So
before it writes anything it walks the schema's ``ON DELETE CASCADE`` edges,
reads every table that cascade reaches, and refuses the whole run unless every
string column of every row's primary key starts with ``demo-`` -- the prefix on
every id this script writes.

The table set is derived from the mapped schema, not listed here. Two versions
of this guard were written by hand and both had holes (Issue #71 review rounds
1 and 2): a hand-kept list goes stale the moment the schema moves, and nothing
fails when it does.

What the check still is, is a prefix on ids rather than a proof of ownership. A
row someone else wrote with a ``demo-`` id would pass it, and a root that passes
is reset in full. It is deliberately blunt in the safe direction: a root the app
has since written to (a review made by hand, a job the queue created) is refused
rather than merged, and the answer is then to seed a fresh directory.

Run it with the sidecar stopped -- the app holds an exclusive lock on this
directory while it runs (docs/linux-desktop-development.md §5.1).
"""

# The seeded strings are Japanese UI text, where the full-width parenthesis is
# the correct one; RUF001 reads every full-width form as a possible typo for its
# ASCII lookalike, which is not what these are.
# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import String, Table, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auto_scoring.adapters.local.profile_store import ProfileStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.sidecar import default_app_data_dir
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.db.migrator import upgrade
from auto_scoring.db.orm import Base, TestRow
from auto_scoring.domain.dependency_graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyGraphStatus,
    DependencyProvision,
)
from auto_scoring.domain.models import (
    ErrorCategory,
    GradeResult,
    GradingSource,
    Job,
    JobKind,
    JobState,
    NormalizedRect,
    Question,
    RecognitionResult,
    Review,
    ReviewAction,
    Rubric,
    RubricCriterion,
    Score,
    Submission,
    SubmissionState,
    Test,
)
from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    ProfileStatus,
    Region,
    RegionKind,
)

#: Prefix every id this script writes starts with, and the whole of the safety
#: check: a row named any other way was not written here, so the root holding it
#: is not this script's to reset.
ID_PREFIX = "demo-"

#: The table the reset deletes from. Everything the guard looks at is derived
#: from it (`cascade_reachable_tables`), so nothing here is a hand-kept list.
RESET_ROOT_TABLE = TestRow.__table__

#: A4 at 72dpi, matching the fixture PDF the submissions point at.
A4_PORTRAIT = PageFormat(width_pt=595.0, height_pt=842.0)

#: Fixed, so a re-run produces the same screens and two screenshots taken a day
#: apart can be compared. Relative dates would make "3日前" drift.
EPOCH = datetime(2026, 9, 1, 9, 0)


def at(minutes: float = 0) -> datetime:
    return EPOCH + timedelta(minutes=minutes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-data-dir",
        type=Path,
        default=default_app_data_dir(),
        help=(
            "app-data/ root to seed. Defaults to the one the sidecar picks for "
            "itself when the app launches it, which is the one the screenshot "
            "script's app will read."
        ),
    )
    parser.add_argument(
        "--source-pdf",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "app/test/fixtures/a4-portrait.pdf",
        help="PDF stored as every seeded answer's source. Must be a single A4 portrait page.",
    )
    args = parser.parse_args(argv)

    root: Path = args.app_data_dir
    files = LocalFileStore(root)
    database_url = sqlite_url(files.database_path())

    # A root with no database yet holds nothing to protect, so it is created
    # outright. An existing one is *read before it is migrated*: `upgrade()`
    # writes to the database, and nothing may write to a root that is about to
    # turn out to hold real data.
    empty_root = not files.database_path().exists()
    if empty_root:
        upgrade(database_url)

    engine = create_sqlite_engine(database_url)
    unit_of_work = SqlAlchemyUnitOfWork(build_session_factory(engine))

    with unit_of_work as uow:
        try:
            foreign = foreign_row_counts(uow.session)
        except SQLAlchemyError:
            # A database this script cannot read is one it cannot vouch for
            # either -- an older schema, or something else entirely.
            print(
                f"{root} has a database this script cannot read; refusing to touch it.",
                file=sys.stderr,
            )
            return 1
        if foreign:
            print(
                f"{root} holds rows this script did not write "
                f"({', '.join(f'{table}: {count}' for table, count in foreign.items())}); "
                "refusing to touch it, because seeding first deletes every test in the "
                "root and everything that cascades from it. Point --app-data-dir at a "
                "directory of its own.",
                file=sys.stderr,
            )
            return 1

    if not empty_root:
        upgrade(database_url)

    with unit_of_work as uow:
        # Every table hangs off `tests` with ON DELETE CASCADE, so this is the
        # whole reset: re-running must not double the rows on screen.
        for test in uow.tests.list_all():
            uow.tests.delete(test.id)
        uow.commit()

        _seed(uow, files, source_pdf=args.source_pdf)
        uow.commit()

    print(f"seeded {root}")
    return 0


def cascade_reachable_tables(root: Table = RESET_ROOT_TABLE) -> list[Table]:
    """Every table a deleted row of [root] takes with it, [root] included.

    Read out of the mapped schema rather than listed by hand. The list form was
    wrong twice: first it named only `tests`, then it named twelve tables and
    argued `dependency_edges` away on a foreign key that does not exist
    (Issue #71 review rounds 1 and 2). A list has to be re-derived by a human
    every time the schema moves, and nothing fails when they forget; this walks
    the same `ON DELETE CASCADE` edges SQLite will walk.
    """
    reached = {root}
    frontier = [root]
    while frontier:
        target = frontier.pop()
        for table in Base.metadata.tables.values():
            if table in reached:
                continue
            if any(
                constraint.referred_table is target and constraint.ondelete == "CASCADE"
                for constraint in table.foreign_key_constraints
            ):
                reached.add(table)
                frontier.append(table)
    return sorted(reached, key=lambda table: table.name)


def foreign_row_counts(session: Session) -> dict[str, int]:
    """How many rows each cascaded table holds that this script did not write.

    Empty when the root is this script's to reset.

    A row counts as this script's when **every string column of its primary
    key** starts with [ID_PREFIX]. The primary key is the right thing to read
    because it is what identifies the row -- for a link table like
    `dependency_edges` that means the graph *and both endpoints*, which is
    exactly where the second hole was: those endpoints are plain strings, not
    foreign keys into `questions`, so checking `questions` never covered them.

    A table whose key carries no string at all cannot be judged this way, so
    every row in it counts as foreign: an unknown is refused, not waved through.

    Ids are counted, never printed. An id from a real ``app-data/`` is real
    data, and this output ends up in terminals and CI logs (AGENTS.md
    "Security").
    """
    counts: dict[str, int] = {}
    for table in cascade_reachable_tables():
        columns = [
            column for column in table.primary_key.columns if isinstance(column.type, String)
        ]
        if not columns:
            total = len(session.execute(select(table)).all())
            if total:
                counts[table.name] = total
            continue
        foreign = sum(
            1
            for key in session.execute(select(*columns))
            if any(not str(value).startswith(ID_PREFIX) for value in key)
        )
        if foreign:
            counts[table.name] = foreign
    return counts


def _seed(uow: SqlAlchemyUnitOfWork, files: LocalFileStore, *, source_pdf: Path) -> None:
    _seed_graded_test(uow, files, source_pdf=source_pdf)
    _seed_half_registered_test(uow)


def _seed_graded_test(
    uow: SqlAlchemyUnitOfWork, files: LocalFileStore, *, source_pdf: Path
) -> None:
    """A registered test with three answers at three different stages.

    The dependency structure is the one docs/dependency-dag-progress-view.md
    §5 explains: 問1/問2/問4 run in parallel, 問3 waits on both 問1 and 問2,
    問5 waits on 問3 and 問1. It is here so the progress diagram has something
    to say -- a chain that is stopped, and the reason it is stopped.
    """
    test_id = f"{ID_PREFIX}kokugo"
    uow.tests.add(
        Test(
            id=test_id,
            name="国語 第1回 記述（デモ）",
            subject="国語",
            created_at=at(),
        )
    )

    # `<test id>:<question number>`, the shape
    # `domain/test_registration.build_questions_and_rubrics` gives a real
    # registration: テスト設定画面 prints these ids as they are, so an invented
    # shape would make that screen look better than it is.
    question_ids = [f"{test_id}:{index}" for index in range(1, 6)]
    for index, question_id in enumerate(question_ids, start=1):
        uow.questions.add(
            Question(
                id=question_id,
                test_id=test_id,
                number=str(index),
                page=1,
                points=5 if index < 5 else 10,
                # Stacked down the page, so the review overlay has a plausible
                # place to point at for each question.
                answer_area=NormalizedRect(
                    x=0.1, y=0.1 + 0.15 * (index - 1), width=0.8, height=0.12
                ),
            )
        )
        uow.rubrics.add(
            Rubric(
                id=f"{question_id}:rubric",
                question_id=question_id,
                criteria=(
                    RubricCriterion(
                        id=f"{question_id}:rubric:c1",
                        description="主旨をとらえている",
                        max_points=3,
                        position=0,
                    ),
                    RubricCriterion(
                        id=f"{question_id}:rubric:c2",
                        description="文末表現が適切",
                        max_points=2,
                        position=1,
                    ),
                ),
            )
        )

    uow.dependency_graphs.save(
        DependencyGraph(
            id=f"{test_id}:v1",
            test_id=test_id,
            version=1,
            question_ids=frozenset(question_ids),
            edges=(
                _edge(question_ids[0], question_ids[2], "問1の答えを前提にしている"),
                _edge(question_ids[1], question_ids[2], "問2の判断を引き継ぐ"),
                _edge(question_ids[2], question_ids[4], "問3の結論をまとめさせる"),
                _edge(question_ids[0], question_ids[4], "問1の答えも使う"),
            ),
            unresolved=(),
            status=DependencyGraphStatus.CONFIRMED,
            created_at=at(1),
            confirmed_at=at(2),
        )
    )
    _save_profile(files, test_id=test_id, question_ids=question_ids)
    uow.tests.mark_ready(test_id)

    # 1件目: 人が今開いている答案。問2 が低Confidenceのまま止まっており、その先の
    # 問3・問5 が動けない -- 依存グラフを見せる意味が一番はっきり出る状態。
    _seed_submission(
        uow,
        files,
        source_pdf=source_pdf,
        submission_id=f"{ID_PREFIX}sub-a",
        test_id=test_id,
        student_label="答案A（デモ）",
        state=SubmissionState.NEEDS_REVIEW,
        created_at=at(10),
        question_ids=question_ids,
        job_states={
            question_ids[0]: (JobState.SUCCEEDED, True),
            question_ids[1]: (JobState.SUCCEEDED, False),
            question_ids[2]: (JobState.BLOCKED, None),
            question_ids[3]: (JobState.SUCCEEDED, True),
            question_ids[4]: (JobState.BLOCKED, None),
        },
        approved={question_ids[0]},
    )

    # 2件目: AI採点が1問だけ落ちた答案。失敗の見せ方と、失敗が下流を止めたままに
    # する様子が出る。
    #
    # `queued` や `running` は置けない。サイドカーは起動と同時にキューを回すので、
    # 終端でないジョブは数秒で終端へ動いてしまう -- 撮れるのは「そのあと」の画面で
    # あって、置いたはずの状態ではない。実行中ノードの動きはそもそも静止画に写らず、
    # `app/test/dependency_dag_panel_test.dart` が代わりに検査している
    # (docs/dependency-dag-progress-view.md §5.2)。
    _seed_submission(
        uow,
        files,
        source_pdf=source_pdf,
        submission_id=f"{ID_PREFIX}sub-b",
        test_id=test_id,
        student_label="答案B（デモ）",
        state=SubmissionState.AI_PROCESSED,
        created_at=at(12),
        question_ids=question_ids,
        job_states={
            question_ids[0]: (JobState.SUCCEEDED, True),
            question_ids[1]: (JobState.FAILED, None),
            question_ids[2]: (JobState.BLOCKED, None),
            question_ids[3]: (JobState.SUCCEEDED, True),
            question_ids[4]: (JobState.BLOCKED, None),
        },
        approved=set(),
    )

    # 3件目: 片付いた答案。「終わったものが積み上がる」側を1件だけ置く。
    _seed_submission(
        uow,
        files,
        source_pdf=source_pdf,
        submission_id=f"{ID_PREFIX}sub-c",
        test_id=test_id,
        student_label="答案C（デモ）",
        state=SubmissionState.REVIEWED,
        created_at=at(14),
        question_ids=question_ids,
        job_states={question_id: (JobState.SUCCEEDED, True) for question_id in question_ids},
        approved=set(question_ids),
    )


def _seed_half_registered_test(uow: SqlAlchemyUnitOfWork) -> None:
    """A test whose registration was started and never finished.

    ホーム画面's「次の一手」picks this up, and テスト設定画面 has an un-analyzed
    profile to show -- both of which vanish if every seeded test is complete.
    """
    test_id = f"{ID_PREFIX}rika"
    uow.tests.add(
        Test(
            id=test_id,
            name="理科 第2回（デモ）",
            subject="理科",
            created_at=at(60),
        )
    )
    for index in range(1, 4):
        uow.questions.add(
            Question(
                id=f"{test_id}:{index}",
                test_id=test_id,
                number=str(index),
                page=1,
                points=5,
            )
        )


def _seed_submission(
    uow: SqlAlchemyUnitOfWork,
    files: LocalFileStore,
    *,
    source_pdf: Path,
    submission_id: str,
    test_id: str,
    student_label: str,
    state: SubmissionState,
    created_at: datetime,
    question_ids: list[str],
    job_states: dict[str, tuple[JobState, bool | None]],
    approved: set[str],
) -> None:
    stored = files.submission_source_pdf_path(submission_id)
    stored.parent.mkdir(parents=True, exist_ok=True)
    # One fixture, three answers, and intake refuses to take the same content
    # into a test twice (`submissions.test_id, source_pdf_sha256` is unique).
    # A trailing PDF comment is ignored by every reader and is enough to make
    # each copy its own document.
    stored.write_bytes(source_pdf.read_bytes() + f"\n% {submission_id}\n".encode())
    # The page preview intake would have written. Without it the sidecar's
    # startup sweep reads a submission past intake with a file missing as an
    # interrupted intake and moves it to `error`
    # (`adapters/submission_intake.py`), which is not the state being seeded.
    preview = files.submission_page_image_path(submission_id, 1)
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(PdfiumPypdfEngine().render_page_png(stored, 0, scale=1.0))

    uow.submissions.add(
        Submission(
            id=submission_id,
            test_id=test_id,
            source_pdf_path=f"submissions/{submission_id}/source.pdf",
            source_pdf_sha256=hashlib.sha256(stored.read_bytes()).hexdigest(),
            page_count=1,
            state=state,
            student_label=student_label,
            original_filename="demo-answer.pdf",
            created_at=created_at,
        )
    )

    for index, question_id in enumerate(question_ids, start=1):
        job_state, usable = job_states[question_id]
        uow.jobs.add(
            Job(
                id=f"{submission_id}-job-{index}",
                kind=JobKind.GRADING,
                submission_id=submission_id,
                question_id=question_id,
                state=job_state,
                usable=usable,
                # The one the diagram draws the "waiting on" label from. Only
                # meaningful while blocked.
                blocked_on_question_id=(
                    question_ids[1] if question_id == question_ids[2] else question_ids[2]
                )
                if job_state is JobState.BLOCKED
                else None,
                # A failure a reviewer can act on, phrased the way the
                # grading processor phrases a provider outage.
                attempts=3 if job_state is JobState.FAILED else 0,
                last_error="AIプロバイダに接続できませんでした（デモ）"
                if job_state is JobState.FAILED
                else None,
                error_code=ErrorCategory.SERVER_ERROR if job_state is JobState.FAILED else None,
                dependency_graph_version=1,
                created_at=created_at + timedelta(seconds=index),
                updated_at=created_at + timedelta(minutes=1, seconds=index),
            )
        )
        if job_state is not JobState.SUCCEEDED:
            continue

        # Low-confidence results are what make a `SUCCEEDED` job unusable, so
        # the two have to agree: a reviewer looking at 74% next to 「要確認」
        # can see why the chain stopped.
        confidence = 0.94 if usable else 0.74
        uow.recognitions.add(
            RecognitionResult(
                id=f"{submission_id}-rec-{index}",
                submission_id=submission_id,
                question_id=question_id,
                source=GradingSource.AI,
                text=f"（デモ）問{index} の答案として読み取った文字列がここに入ります。",
                confidence=confidence,
                created_at=created_at + timedelta(minutes=1, seconds=index),
            )
        )
        grade_id = f"{submission_id}-grade-{index}"
        uow.grades.add(
            GradeResult(
                id=grade_id,
                submission_id=submission_id,
                question_id=question_id,
                source=GradingSource.AI,
                score=Score(awarded=4 if usable else 2, maximum=5),
                confidence=confidence,
                rationale="（デモ）採点根拠の文がここに入ります。",
                created_at=created_at + timedelta(minutes=2, seconds=index),
            )
        )
        if question_id in approved:
            uow.reviews.add(
                Review(
                    id=f"{submission_id}-review-{index}",
                    submission_id=submission_id,
                    question_id=question_id,
                    action=ReviewAction.APPROVED,
                    ai_grade_result_id=grade_id,
                    version=1,
                    created_at=created_at + timedelta(minutes=3, seconds=index),
                )
            )


def _edge(from_question_id: str, to_question_id: str, rationale: str) -> DependencyEdge:
    return DependencyEdge(
        from_question_id=from_question_id,
        to_question_id=to_question_id,
        provides=(DependencyProvision.RECOGNIZED_TEXT,),
        rationale=rationale,
    )


def _save_profile(files: LocalFileStore, *, test_id: str, question_ids: list[str]) -> None:
    """A confirmed profile, so テスト設定画面 shows a registered test as registered."""
    regions = []
    for index, question_id in enumerate(question_ids):
        top = 0.1 + 0.15 * index
        regions.append(
            Region(
                region_id=f"{question_id}:answer-area",
                kind=RegionKind.ANSWER_AREA,
                page_index=0,
                bbox=NormalizedBBox(x0=0.1, y0=top, x1=0.9, y1=top + 0.12),
                # The question number alone: テスト設定画面 renders this as
                # 「設問<label>」.
                label=str(index + 1),
                confirmed=True,
            )
        )
    ProfileStore(files.root).save(
        Profile(
            profile_id=f"{test_id}-profile",
            format_id=test_id,
            signature=FormatSignature(pages=(A4_PORTRAIT,)),
            regions=tuple(regions),
            status=ProfileStatus.CONFIRMED,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
