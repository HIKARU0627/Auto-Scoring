"""PoC 1 harness -- aggregate OCR metrics from recorded runs + human labels.

Usage::

    uv run python poc/run_ocr_eval.py [--dataset DIR] [--out FILE]

Every ``*.json`` under ``DIR`` is one sample (see
``tests/fixtures/ocr/README.md`` for the shape)::

    {"ground_truth": { ... }, "ocr_result": { ... recorded provider output ... }}

``DIR`` defaults to the committed synthetic fixtures, so the command runs with
no credentials and no dataset and reproduces a secret-free aggregate table
(Issue #13 verification). Point ``--dataset`` at the licensed evaluation set for
real numbers; ``docs/poc-1-japanese-handwriting-ocr.md`` has the credentials
setup and the live-provider path.

Only counts and averaged scores are printed. Provider request/response bodies
are never read or logged here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from auto_scoring.domain.ocr import OcrResult
from auto_scoring.domain.ocr_metrics import (
    OcrGroundTruth,
    evaluate_sample,
    summarize_by_quality,
    to_markdown_table,
)

_DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ocr"


def _load_samples(dataset: Path) -> list[tuple[OcrGroundTruth, OcrResult]]:
    files = sorted(dataset.glob("*.json"))
    if not files:
        raise SystemExit("no *.json samples found in dataset")
    samples: list[tuple[OcrGroundTruth, OcrResult]] = []
    for path in files:
        raw = json.loads(path.read_text(encoding="utf-8"))
        samples.append(
            (
                OcrGroundTruth.from_mapping(raw["ground_truth"]),
                OcrResult.from_mapping(raw["ocr_result"]),
            )
        )
    return samples


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # keep the JP table readable on Windows

    parser = argparse.ArgumentParser(description="PoC 1 OCR metric aggregator")
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    samples = _load_samples(args.dataset)
    metrics = [evaluate_sample(truth, result) for truth, result in samples]
    table = to_markdown_table(summarize_by_quality(metrics))
    report = f"# PoC 1 OCR aggregate\n\nsamples: {len(metrics)}\n\n{table}\n"

    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
