"""Issue #25 probe -- how queue throughput varies with the concurrency cap.

Usage::

    uv run python poc/issue_25_queue_throughput/report.py [--answers N]
        [--latency SECONDS] [--concurrency 1,2,3,4] [--out FILE]

**This measures, it does not decide.** The parallel-AI-processing count is
decision E in `docs/business-rules-and-evaluation-data.md` section 3, and it
belongs to the project owner. Its stated inputs are the chosen model's and OCR
service's rate limits, the real per-answer processing time, and the throughput
and error rate at each concurrency -- and the first three of those cannot exist
until decisions A and B are made and Issue #35 measures a real provider on real
answers. What this probe supplies is the fourth kind of input, and only the
part that is knowable now: how the queue itself scales once you *assume* a
per-call provider latency. Read the output as "given a provider that takes L
seconds per call, the queue delivers this much throughput at this cap" -- never
as a recommended cap.

For the same reason the error rate it prints is always 0.00: the providers here
are deterministic stand-ins with no network, no quota and no rate limiter, so
there is nothing for them to fail at. A meaningful error rate needs a real
provider under real load, which is Issue #35's job.

Everything is synthetic. No real student answers, no credentials, nothing
persisted outside a temp directory.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Run from `backend/`. The probe drives the same app, through the same
# endpoints, as `tests/test_e2e_acceptance.py`, so it reuses that module's
# fixture helpers rather than growing a second, silently diverging copy of
# "register a test, upload an answer, wait for its jobs". `poc/` is not
# packaged (see poc/README.md), so importing from `tests/` here costs the
# shipped wheel nothing.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.test_e2e_acceptance import (
    QUESTIONS,
    ScriptedAIProvider,
    ScriptedOCRProvider,
    register_ready_test,
    start_jobs,
    upload_answer,
    wait_until_settled,
)

from auto_scoring.domain.ai_provider import GradingRequest, GradingResponse
from auto_scoring.domain.ocr import OcrResult

DEFAULT_ANSWERS = 12
DEFAULT_LATENCY_SECONDS = 0.05
DEFAULT_CONCURRENCIES = (1, 2, 3, 4)


class _SlowOCRProvider(ScriptedOCRProvider):
    """The scripted provider plus a fixed per-call latency.

    A real OCR call spends its time waiting on a network round trip, which is
    what makes a concurrency cap matter at all; a stand-in that returns
    instantly would measure only this process's own bookkeeping. The call
    happens on a worker thread (`asyncio.to_thread`), so a plain `sleep` here
    occupies a slot exactly as a real call would.
    """

    def __init__(self, latency_seconds: float) -> None:
        super().__init__()
        self._latency_seconds = latency_seconds

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        time.sleep(self._latency_seconds)
        return super().recognize(image, language=language)


class _SlowAIProvider(ScriptedAIProvider):
    """`_SlowOCRProvider`'s counterpart for the grading half."""

    def __init__(self, latency_seconds: float) -> None:
        super().__init__()
        self._latency_seconds = latency_seconds

    def grade(self, request: GradingRequest) -> GradingResponse:
        time.sleep(self._latency_seconds)
        return super().grade(request)


@dataclass(frozen=True, kw_only=True)
class Measurement:
    concurrency: int
    answers: int
    questions_per_answer: int
    intake_seconds: float
    queue_seconds: float
    per_answer_seconds: float
    answers_per_minute: float
    failed_jobs: int

    @property
    def error_rate(self) -> float:
        total = self.answers * self.questions_per_answer
        return self.failed_jobs / total if total else 0.0


def measure(*, concurrency: int, answers: int, latency_seconds: float) -> Measurement:
    # Imported here, not at module scope: importing `create_app` pulls in the
    # whole FastAPI/SQLAlchemy stack, and `--help` should not pay for it.
    from tests.test_e2e_acceptance import build_app_client

    ocr = _SlowOCRProvider(latency_seconds)
    ai = _SlowAIProvider(latency_seconds)
    with tempfile.TemporaryDirectory(prefix="auto-scoring-poc25-") as scratch:
        data_root = Path(scratch) / "app-data"
        client = build_app_client(data_root, ocr, ai, max_concurrency=concurrency)
        with client:
            test_id = register_ready_test(client)

            started = time.monotonic()
            submissions = [
                upload_answer(client, test_id, marker=f"poc25-{index:03d}")
                for index in range(answers)
            ]
            intake_seconds = time.monotonic() - started

            started = time.monotonic()
            for submission_id in submissions:
                start_jobs(client, submission_id)
            failed = 0
            for submission_id in submissions:
                for job in wait_until_settled(client, submission_id, timeout=300.0):
                    failed += job["state"] != "succeeded"
            queue_seconds = time.monotonic() - started

    return Measurement(
        concurrency=concurrency,
        answers=answers,
        questions_per_answer=len(QUESTIONS),
        intake_seconds=intake_seconds,
        queue_seconds=queue_seconds,
        per_answer_seconds=queue_seconds / answers,
        answers_per_minute=answers / queue_seconds * 60.0,
        failed_jobs=failed,
    )


def render(measurements: list[Measurement], *, latency_seconds: float) -> str:
    lines = [
        "| 並列度 | 答案件数 | 設問/答案 | 取込 合計(s) | キュー処理 合計(s) "
        "| 1答案あたり(s) | スループット(答案/分) | エラー率 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in measurements:
        lines.append(
            f"| {row.concurrency} | {row.answers} | {row.questions_per_answer} "
            f"| {row.intake_seconds:.2f} | {row.queue_seconds:.2f} "
            f"| {row.per_answer_seconds:.3f} | {row.answers_per_minute:.1f} "
            f"| {row.error_rate:.2f} |"
        )
    baseline = next((m for m in measurements if m.concurrency == 1), None)
    if baseline is not None and len(measurements) > 1:
        speedups = ", ".join(
            f"並列{m.concurrency}: {baseline.queue_seconds / m.queue_seconds:.2f}倍"
            for m in measurements
            if m.concurrency != 1
        )
        lines.append("")
        lines.append(f"並列1を基準とした短縮率: {speedups}")
    lines.append("")
    lines.append(
        f"擬似provider遅延: 1呼び出しあたり {latency_seconds:.3f} s "
        f"(OCR・AIそれぞれ)。1設問 = OCR 1回 + AI 1回。"
    )
    lines.append(
        "エラー率は常に 0.00 -- 決定論的な擬似providerには失敗する要因が無い。"
        "意味のあるエラー率は実providerでの実測 (Issue #35) を要する。"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=int, default=DEFAULT_ANSWERS)
    parser.add_argument("--latency", type=float, default=DEFAULT_LATENCY_SECONDS)
    parser.add_argument(
        "--concurrency",
        default=",".join(str(value) for value in DEFAULT_CONCURRENCIES),
        help="comma-separated caps to measure",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    concurrencies = [int(value) for value in args.concurrency.split(",") if value.strip()]
    measurements = [
        measure(concurrency=value, answers=args.answers, latency_seconds=args.latency)
        for value in concurrencies
    ]
    report = render(measurements, latency_seconds=args.latency)
    if args.out is not None:
        args.out.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
