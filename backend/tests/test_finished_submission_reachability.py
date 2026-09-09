"""承認を終えた答案が、まだ取り出せることの回帰テスト (Issue #137, 親 #3).

Issue #112 で全問承認した答案は ``REVIEWED`` になり、ホーム画面の「レビューを
続ける」候補から外れる。**消えること自体は意図した動き**で、残りの作業だけを
見せるためのものである。ところが #137 の実機再検証では、そこから先へ行けなく
なっていた -- 答案がホームから消え、開き直す画面が無く、取り込み直しは重複と
して弾かれ、PDF出力ボタンはレビュー画面にしか無い。このアプリの成果物は採点済み
PDFなので、これは**完了操作を行うと成果物に到達できなくなる**という事故である。

画面の導線そのものは ``app/`` 側で直す。**このモジュールが押さえるのはその下**、
サイドカーが承認済みの答案を閉じ込めていないことである。

- 一覧に残る (``GET /tests/{id}/submissions``)
- 開き直して直せる (``POST .../review/undo`` -- `REVIEWED` はレビュー操作が
  効く状態である)
- 出力を起動できる (``POST /submissions/{id}/export``) -- **出力PDFの中身は
  見ていない**。何を見て何を見ていないかは
  `test_a_finished_submission_still_exports_to_a_pdf_file` に書いてある。

3つをまたいで1か所に置いてあるのは、**どれか1つが塞がれば画面をいくら直しても
行き止まりに戻る**からである。そして3つはそれぞれ別のルータにあるので、
どのルータのテストも単独ではこの性質を守れない。

どのテストも、答案を**すでに終わった状態で** seed する。同じプロセスの中で
承認して ``REVIEWED`` に到達させるのではない -- #137 の利用者はアプリを閉じて
翌日戻ってきた人であり、再現したいのは「終わった答案を後から開く」経路である。
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
    SubmissionState,
)
from auto_scoring.jobs.export_processor import ExportJobProcessor
from tests.font_support import install_font_covering
from tests.support import at, make_grade, make_question, make_review, make_submission, make_test

_TOKEN = "finished-submission-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def client(session_factory: sessionmaker[Session], store: LocalFileStore) -> Iterator[TestClient]:
    """The real app with a real export processor behind it.

    The export half of this module runs a job to completion rather than
    stopping at the 202, because "出力できる" is the claim being pinned and a
    queued job is not yet a PDF. `test_export_api.py` builds its client the
    same way.
    """
    processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
    app = create_app(
        api_token=_TOKEN,
        session_factory=session_factory,
        data_root=store.root,
        job_processor=processor,
    )
    with TestClient(app) as test_client:
        yield test_client


def _write_source_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _seed_finished_submission(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    *,
    submission_id: str = "sub-1",
) -> None:
    """1問だけの答案を、**全問承認を終えた状態**で置く。

    ``state=REVIEWED`` と承認済みの `Review` を両方書くのが要点で、片方だけでは
    #137 の場面にならない -- 状態だけなら出力の可否 (`domain.pdf_export` は
    レビュー履歴のほうを見る) が変わらず、履歴だけなら一覧での見え方が変わらない。
    """
    _write_source_pdf(store.submission_source_pdf_path(submission_id))
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.questions.add(
            make_question(score_area=NormalizedRect(x=0.8, y=0.0, width=0.18, height=0.06))
        )
        uow.submissions.add(
            make_submission(
                id=submission_id,
                original_filename="答案A.pdf",
                state=SubmissionState.REVIEWED,
            )
        )
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


def test_a_tests_submission_list_keeps_the_ones_already_finished(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """終わった答案は ``GET /tests/{id}/submissions`` から消えない。

    ホームが確認済みを「レビューを続ける」候補から外すのは画面側の判断で
    (`app/lib/features/home/home_dashboard.dart` の ``_resumableBuckets``)、
    **一覧APIまで一緒に絞り込んではならない**。絞り込んだ瞬間、答案一覧を持つ
    画面をどれだけ足しても確認済みには到達できなくなる。

    ``EXPORTED`` も同じ理由で残す。一度出力した答案をもう一度出力したい
    (出力先を消した、採点を直した) というのは普通に起きることで、そのときにも
    一覧が唯一の入口である。
    """
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        for index, (submission_id, state) in enumerate(
            [
                ("sub-open", SubmissionState.AI_PROCESSED),
                ("sub-done", SubmissionState.REVIEWED),
                ("sub-exported", SubmissionState.EXPORTED),
            ]
        ):
            uow.submissions.add(
                make_submission(
                    id=submission_id,
                    source_pdf_path=f"submissions/{submission_id}/source.pdf",
                    source_pdf_sha256=str(index) * 64,
                    state=state,
                )
            )
        uow.commit()

    response = client.get("/tests/test-1/submissions", headers=_AUTH)

    assert response.status_code == 200, response.text
    # **先に一覧が引けていることを言う。** 「確認済みが消えていない」を
    # 「確認済みが入っている」で書くのはそのためで、`sub-done not in ...` の形に
    # すると一覧が空でも通ってしまう (docs/quality-gates.md「全 green は
    # 「画面で動く」を意味しない」)。
    assert {row["id"]: row["state"] for row in response.json()} == {
        "sub-open": "ai_processed",
        "sub-done": "reviewed",
        "sub-exported": "exported",
    }


def test_a_finished_submission_can_still_be_reopened_and_corrected(
    client: TestClient, session_factory: sessionmaker[Session], store: LocalFileStore
) -> None:
    """``REVIEWED`` の答案は、開き直して採点を直せる。

    `adapters.review_actions._REVIEWABLE_SUBMISSION_STATES` に ``REVIEWED`` が
    入っていることが、これを成り立たせている。外すと Undo は通るのに答案は
    ``REVIEWED`` のまま残り -- 未確定の設問を抱えたまま「確認済み」を名乗る --
    画面は片付いたものとして数え、出力は 409 で拒む、という食い違いになる。

    直したあと承認し直すところまで見るのは、**戻れるだけでは足りない**から
    である。開いて直して、また完了に戻せて初めて「開き直せる」と言える。
    """
    _seed_finished_submission(session_factory, store)

    # 終わった答案として実際に開けることを先に確かめる。添削レビュー画面が最初に
    # 引くのがこの2本で、ここが空なら以下の遷移は何も意味しない。
    opened = client.get("/submissions/sub-1", headers=_AUTH)
    assert opened.status_code == 200, opened.text
    assert opened.json()["state"] == "reviewed"
    reviews = client.get("/submissions/sub-1/questions/q-1/reviews", headers=_AUTH)
    assert reviews.status_code == 200
    assert [row["action"] for row in reviews.json()] == ["approved"]

    undone = client.post(
        "/submissions/sub-1/questions/q-1/review/undo",
        headers=_AUTH,
        json={"expected_version": 1},
    )
    assert undone.status_code == 201, undone.text
    # 取込がきれいに済んだ答案なので、戻り先は ``AI_PROCESSED`` -- 要確認の旗を
    # 立て直さない (Issue #112 受入5)。
    assert undone.json()["submission_state"] == "ai_processed"

    reapproved = client.post(
        "/submissions/sub-1/questions/q-1/review/approve",
        headers=_AUTH,
        json={"expected_version": 2},
    )
    assert reapproved.status_code == 201, reapproved.text
    assert reapproved.json()["submission_state"] == "reviewed"


def test_a_finished_submission_still_exports_to_a_pdf_file(
    client: TestClient,
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``REVIEWED`` の答案から、採点済みPDFが実際に出る。

    #137 の成果物そのもの。検証時は開発用ルート (``AUTO_SCORING_INITIAL_ROUTE``)
    でレビュー画面を直接開いて出力しており、**利用者にその手段は無かった**。
    出力を起動する画面は ``app/`` 側で足すが、その起動先がここで詰まっていない
    ことは、画面と独立に押さえておく価値がある。

    ``POST /export`` は答案の状態を見ない (`domain.pdf_export` はレビュー履歴の
    ほうを見る) -- つまりこれは「見るようにしてはいけない」ことの記録でもある。
    完了した答案を「もう終わったもの」として弾く条件を足すと、成果物が二度と
    取り出せなくなる。

    **このテストは出力PDFの中身を1ピクセルも見ていない。** 見ているのは
    「経路が開いているか」だけである -- 202 が返り、ジョブが `succeeded` に達し、
    `Export` 行がそのジョブを指し、その `file_path` にファイルが在る。
    **入力の答案用紙をそのまま複製しただけのファイルでも、このテストは緑になる。**

    これが空言でないのは、実際に起きたからである (Issue #120): 出力は 202 を返し、
    ジョブは成功し、答案用紙とバイト単位で同一のPDFが出た。そのとき最も近くに
    いたテストは ``output != source`` を2つの `Path` で比べており、ファイル名が
    違えば常に真だった (`tests/pdf_ink.py` の docstring)。**存在とサイズは
    中身の証拠にならない。**

    ここで中身まで見ないのは、担当が別だからである。描かれた内容は
    `tests/pdf_ink.py` の赤インク測定で見るもので、`test_export_processor.py`・
    `test_pdf_annotation_rendering.py`・`test_e2e_acceptance.py` がその担当。
    このモジュールの主張は #137 の「承認を終えた答案から出力を起動できるか」に
    閉じており、描画が壊れたときにここが赤くなるのは筋が違う
    (実際 Issue #141 の時点で、点数は描かれるが注釈は1文字も描かれていない)。

    したがって、**このテストが緑であることを「出力PDFの中身が正しい」根拠に
    使わないこと。** 言えるのは「確認済みの答案でも出力が拒まれず、ファイルが
    1つ出来上がるところまでは進む」だけである。

    ただし床は 0 ではない。202 を返す前に `unconfirmed_question_ids` と
    `unplaceable_question_ids` (Issue #120) が「確定していない設問」「描き場所の
    無い設問」を弾くので、少なくとも**描くべきものと描く場所がある状態**で
    ジョブが起票されたことは言える。そこから先、実際に紙へ乗ったかは見ていない。

    後者の床は Issue #150 で下がった。`score_area` の無い設問は左余白帯へ退避
    するようになり (`domain.pdf_export.fallback_score_areas`)、`unplaceable_
    question_ids` が弾くのは**帯にも収まらない設問だけ**になった。したがって
    ここで言える「描く場所がある」は、以前より弱い主張である。

    **「せめて出力が入力と違うことくらい見よう」は効かない。採らなかった理由を
    残しておく。** `pdf_ink.py` が記録している `Path` 比較ほど露骨ではないので、
    次に読む人が良かれと思って足しうるが、バイト比較も同じだけ空虚である:

        source            : 431 bytes
        blank export      : 488 bytes   # marks を空にして出力したもの
        blank == source ? : False

    `PdfiumPypdfEngine.render_annotations` は常に
    ``PdfWriter().append(PdfReader(source))`` で**PDFを構造ごと書き直す**ので、
    ``/Producer`` が付きオブジェクトが再直列化され、**1本も線を引かなくても
    バイトは変わる**。したがって ``output_bytes != source_bytes`` は恒真で、
    ``output_path != source_path`` と同じく「常に緑のアサーション」になる。

    ついでに測れたこと: 出力は決定的である (同じ入力から2回出して同一バイト、
    ``/CreationDate`` も ``/ID`` も埋まっていない)。つまりゴールデンファイルとの
    比較なら成立するが、それはもう描画の検証であって、上に書いたとおり担当が違う。
    **中身を見たいなら `pdf_ink.py` の赤インク測定を使うこと。**
    """
    # 出力するスコアは ``"4/5"`` (`domain.pdf_export._score_text`) -- 必要な
    # グリフはラテン文字だけで、日本語フォントは要らない。
    install_font_covering(monkeypatch, "0123456789/")
    _seed_finished_submission(session_factory, store)

    requested = client.post("/submissions/sub-1/export", headers=_AUTH)

    assert requested.status_code == 202, requested.text
    job_id = requested.json()["job_id"]
    assert job_id is not None
    assert _wait_until_job_state(client, job_id, "succeeded")["kind"] == "export"

    exports = client.get("/submissions/sub-1/exports", headers=_AUTH)
    assert exports.status_code == 200
    files = exports.json()
    assert [row["job_id"] for row in files] == [job_id]
    assert (store.root / files[0]["file_path"]).exists()
