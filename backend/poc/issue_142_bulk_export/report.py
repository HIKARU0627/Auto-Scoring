"""Issue #142 probe -- how long a 40-sheet bulk PDF export actually takes.

Usage (run from ``backend/``)::

    uv run python poc/issue_142_bulk_export/report.py [--sheets 40]
        [--questions 5] [--pages 2] [--scan-dpi 150] [--out FILE]

**This measures, it does not decide.** The decision it feeds is
`docs/pdf-export.md` section 12.3 -- whether a bulk export goes on the existing
job queue or runs synchronously in the request. The criterion stated in the
Issue is "40枚規模で UI が固まらないこと", and the number that answers it is how
long the whole run takes end to end, split into the two halves that behave
differently:

* **sidecar** -- queue + render, which happens off the HTTP request either way.
* **app** -- fetching each produced PDF over loopback and writing it into the
  folder the reviewer picked, which is what `core/bulk_export.dart` does and
  the only part that could ever block the Flutter isolate.

Everything is synthetic. The answer sheets are generated grey-noise images at
``--scan-dpi``, sized like a real scan rather than like a blank page, because a
blank one-page PDF measures the queue and nothing else. **No real student
answers, no credentials, nothing persisted outside a temp directory**
(`AGENTS.md` "Security": 実データはリポジトリ外).

It stays honest about what it is not: a Linux CI box is not the Windows laptop
this app ships to, and generated noise is not a scan of handwriting. Read the
output as an order of magnitude and a shape, never as a promise.

Removal-or-promotion condition: delete this probe once the same number can be
read off a real run (`docs/mvp-acceptance.md`); until then it is the only
evidence behind section 12.3's choice, so it stays runnable.
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
from fastapi.testclient import TestClient
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

# Run from `backend/`. `poc/` is not packaged (poc/README.md), so importing
# the test helpers here costs the shipped wheel nothing -- and reusing them
# means the probe seeds exactly what the tests seed, rather than growing a
# second, silently diverging copy.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.font_support import _FALLBACK_FONTS, _covers
from tests.support import (
    at,
    make_grade,
    make_question,
    make_review,
    make_submission,
    make_test,
)

import auto_scoring.db.orm  # noqa: F401  (registers tables on Base.metadata)
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.base import Base
from auto_scoring.db.engine import (
    build_session_factory,
    create_sqlite_engine,
    sqlite_url,
)
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    GradingSource,
    NormalizedRect,
)
from auto_scoring.jobs.export_processor import ExportJobProcessor

import auto_scoring.adapters.pdf.pdfium_pypdf_engine as engine_module  # isort: skip

_TOKEN = "bulk-export-probe-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

#: A4 at 72pt/inch.
_PAGE_WIDTH_PT = 595.0
_PAGE_HEIGHT_PT = 842.0


@dataclass(frozen=True)
class Timings:
    sheets: int
    source_bytes: int
    request_seconds: float
    render_seconds: float
    transfer_seconds: float
    output_bytes: int

    @property
    def total_seconds(self) -> float:
        return self.request_seconds + self.render_seconds + self.transfer_seconds

    @property
    def per_sheet_seconds(self) -> float:
        return self.total_seconds / self.sheets if self.sheets else 0.0


def _scan_like_pdf(pages: int, dpi: int, rng: np.random.Generator) -> bytes:
    """A PDF the size and shape of a scanned answer sheet.

    Grey noise at ``dpi``, JPEG-compressed by reportlab -- incompressible
    enough that the file lands in the same order of magnitude as a real scan,
    which is what makes the transfer half of the measurement mean anything.
    """
    width_px = int(_PAGE_WIDTH_PT / 72 * dpi)
    height_px = int(_PAGE_HEIGHT_PT / 72 * dpi)
    buffer = io.BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=(_PAGE_WIDTH_PT, _PAGE_HEIGHT_PT))
    for _ in range(pages):
        # Mostly-white paper with speckle, the way a scan of handwriting
        # compresses -- not uniform noise, which would be worst-case.
        noise = rng.integers(200, 256, size=(height_px, width_px), dtype=np.uint8)
        canvas.drawImage(
            ImageReader(_as_png(noise)),
            0,
            0,
            width=_PAGE_WIDTH_PT,
            height=_PAGE_HEIGHT_PT,
        )
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _as_png(grey: np.ndarray) -> io.BytesIO:
    import cv2

    ok, encoded = cv2.imencode(".png", grey)
    if not ok:  # pragma: no cover -- cv2 only fails on a bad extension
        raise RuntimeError("could not encode the synthetic scan")
    return io.BytesIO(encoded.tobytes())


def _seed(
    session_factory: object,
    store: LocalFileStore,
    *,
    sheets: int,
    questions: int,
    pages: int,
    dpi: int,
) -> int:
    rng = np.random.default_rng(142)
    total_source_bytes = 0
    with SqlAlchemyUnitOfWork(session_factory) as uow:  # type: ignore[arg-type]
        uow.tests.add(make_test())
        for index in range(questions):
            uow.questions.add(
                make_question(
                    id=f"q-{index:02d}",
                    number=f"問{index:02d}",
                    page=1,
                    score_area=NormalizedRect(
                        x=0.80, y=0.02 + index * 0.07, width=0.16, height=0.05
                    ),
                )
            )
        uow.commit()

    for sheet in range(sheets):
        submission_id = f"sub-{sheet:03d}"
        data = _scan_like_pdf(pages, dpi, rng)
        total_source_bytes += len(data)
        path = store.submission_source_pdf_path(submission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        with SqlAlchemyUnitOfWork(session_factory) as uow:  # type: ignore[arg-type]
            uow.submissions.add(
                make_submission(
                    id=submission_id,
                    source_pdf_path=f"submissions/{submission_id}/source.pdf",
                    source_pdf_sha256=f"{sheet:064d}",
                    page_count=pages,
                    original_filename=f"{submission_id}.pdf",
                )
            )
            for index in range(questions):
                question_id = f"q-{index:02d}"
                grade_id = f"grade-{submission_id}-{index:02d}"
                uow.grades.add(
                    make_grade(id=grade_id, submission_id=submission_id, question_id=question_id)
                )
                uow.annotations.add(
                    Annotation(
                        id=f"anno-{submission_id}-{index:02d}",
                        submission_id=submission_id,
                        question_id=question_id,
                        source=GradingSource.AI,
                        kind=AnnotationKind.SCORE,
                        created_at=at(),
                    )
                )
                uow.reviews.add(
                    make_review(
                        id=f"review-{submission_id}-{index:02d}",
                        submission_id=submission_id,
                        question_id=question_id,
                        ai_grade_result_id=grade_id,
                    )
                )
            uow.commit()
    return total_source_bytes


def _install_export_font() -> None:
    """Let the export draw its score text on a machine that is not Windows.

    Production only looks for the Windows-shipped Japanese fonts on purpose
    (`docs/pdf-export.md` "日本語フォントの解決"), so this appends a fallback
    exactly the way `tests/font_support.py` does -- **after** the production
    candidates, so a real Windows run never reaches it. A probe that cannot
    render is a probe that measures nothing, so it stops rather than
    reporting a number for a run that failed.
    """
    original = engine_module._JAPANESE_FONT_CANDIDATES
    if any(candidate.exists() for candidate in original):
        return
    required = "0123456789/問"
    fallback = next(
        (path for path in _FALLBACK_FONTS if path.exists() and _covers(path, required)),
        None,
    )
    if fallback is None:
        raise SystemExit(
            f"no installed TrueType font covers {required!r}; the export cannot draw on "
            "this machine (docs/mvp-acceptance.md section 4)"
        )
    engine_module._JAPANESE_FONT_CANDIDATES = (*original, fallback)


def measure(*, sheets: int, questions: int, pages: int, dpi: int) -> Timings:
    _install_export_font()
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        engine = create_sqlite_engine(sqlite_url(root / "database.sqlite"))
        Base.metadata.create_all(engine)
        session_factory = build_session_factory(engine)
        store = LocalFileStore(root / "app-data")
        source_bytes = _seed(
            session_factory, store, sheets=sheets, questions=questions, pages=pages, dpi=dpi
        )

        processor = ExportJobProcessor(session_factory, store, PdfiumPypdfEngine(), Lock())
        app = create_app(
            api_token=_TOKEN,
            session_factory=session_factory,
            data_root=store.root,
            job_processor=processor,
        )
        with TestClient(app) as client:
            started = time.monotonic()
            response = client.post("/tests/test-1/export", headers=_AUTH)
            response.raise_for_status()
            items = response.json()["items"]
            requested = time.monotonic()

            job_ids = [item["job_id"] for item in items if item["job_id"]]
            refused = [item for item in items if item["status"] == "refused"]
            if refused:
                raise SystemExit(f"the probe seeded sheets the sidecar refuses: {refused[:3]}")
            _wait_until_settled(client, job_ids)
            rendered = time.monotonic()

            output_bytes = 0
            for item in items:
                exports = client.get(
                    f"/submissions/{item['submission_id']}/exports", headers=_AUTH
                ).json()
                export = exports[-1]
                pdf = client.get(f"/exports/{export['id']}/file", headers=_AUTH)
                pdf.raise_for_status()
                output_bytes += len(pdf.content)
                (root / "picked-folder").mkdir(exist_ok=True)
                (root / "picked-folder" / Path(export["file_path"]).name).write_bytes(pdf.content)
            transferred = time.monotonic()

        engine.dispose()
        return Timings(
            sheets=sheets,
            source_bytes=source_bytes,
            request_seconds=requested - started,
            render_seconds=rendered - requested,
            transfer_seconds=transferred - rendered,
            output_bytes=output_bytes,
        )


def _wait_until_settled(client: TestClient, job_ids: list[str], *, timeout: float = 900.0) -> None:
    deadline = time.monotonic() + timeout
    remaining = list(job_ids)
    while remaining:
        still: list[str] = []
        for job_id in remaining:
            body = client.get(f"/jobs/{job_id}", headers=_AUTH).json()
            if body["state"] in {"succeeded", "failed", "cancelled"}:
                if body["state"] != "succeeded":
                    raise SystemExit(f"job {job_id} ended {body['state']}: {body['last_error']}")
                continue
            still.append(job_id)
        remaining = still
        if remaining and time.monotonic() > deadline:
            raise SystemExit(f"{len(remaining)} jobs never settled")
        if remaining:
            time.sleep(0.05)


def _render(timings: Timings, *, questions: int, pages: int, dpi: int) -> str:
    mib = 1024 * 1024
    return "\n".join(
        [
            "# Issue #142 -- 一括PDF出力の所要時間 (合成データ)",
            "",
            f"- 答案 {timings.sheets} 枚 / 設問 {questions} 問 / {pages} ページ / {dpi}dpi 相当",
            f"- 入力合計 {timings.source_bytes / mib:.1f} MiB "
            f"(1枚あたり {timings.source_bytes / timings.sheets / mib:.2f} MiB)",
            f"- 出力合計 {timings.output_bytes / mib:.1f} MiB",
            "",
            "| 区間 | 秒 |",
            "| --- | --- |",
            f"| `POST /tests/{{id}}/export` の応答まで | {timings.request_seconds:.2f} |",
            f"| キュー + 描画が全件終わるまで | {timings.render_seconds:.2f} |",
            f"| 取得してフォルダへ書き出すまで | {timings.transfer_seconds:.2f} |",
            f"| **合計** | **{timings.total_seconds:.2f}** |",
            "",
            f"1枚あたり {timings.per_sheet_seconds:.2f} 秒。",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", type=int, default=40)
    parser.add_argument("--questions", type=int, default=5)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--scan-dpi", type=int, default=150)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    timings = measure(
        sheets=args.sheets, questions=args.questions, pages=args.pages, dpi=args.scan_dpi
    )
    report = _render(timings, questions=args.questions, pages=args.pages, dpi=args.scan_dpi)
    if args.out is None:
        print(report)
    else:
        args.out.write_text(report + "\n", encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
