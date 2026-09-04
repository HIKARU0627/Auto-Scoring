"""Unit tests for PoC 1 metrics, plus an end-to-end aggregation from fixtures.

The end-to-end test proves the acceptance criterion "human ground-truth labels
-> metrics" and "regenerate a secret-free aggregate" without any credentials or
real student data (Issue #13).
"""

import json
from pathlib import Path

import pytest

from auto_scoring.domain.ocr import BoundingBox, OcrResult
from auto_scoring.domain.ocr_metrics import (
    OcrGroundTruth,
    bounding_box_center_error,
    character_error_rate,
    evaluate_sample,
    keyword_match_rate,
    summarize_by_quality,
    to_markdown_table,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "ocr"


def test_character_error_rate_basic_cases() -> None:
    assert character_error_rate("abc", "abc") == 0.0
    assert character_error_rate("abc", "abd") == pytest.approx(1.0 / 3.0)
    assert character_error_rate("", "") == 0.0
    assert character_error_rate("", "x") == 1.0
    assert character_error_rate("abc", "") == 1.0


def test_keyword_match_rate() -> None:
    hypothesis = "根から水を吸引する"
    assert keyword_match_rate(["根", "水", "吸収"], hypothesis) == pytest.approx(2.0 / 3.0)
    assert keyword_match_rate([], "anything") == 1.0
    assert keyword_match_rate(["光合成"], "光合成による反応") == 1.0


def test_bounding_box_center_error() -> None:
    a = BoundingBox(x=0.2, y=0.5, width=0.1, height=0.1)
    b = BoundingBox(x=0.3, y=0.5, width=0.1, height=0.1)
    assert bounding_box_center_error(a, b) == pytest.approx(0.1)


def _load_samples() -> list[tuple[OcrGroundTruth, OcrResult]]:
    samples: list[tuple[OcrGroundTruth, OcrResult]] = []
    for path in sorted(_FIXTURES.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        samples.append(
            (
                OcrGroundTruth.from_mapping(raw["ground_truth"]),
                OcrResult.from_mapping(raw["ocr_result"]),
            )
        )
    return samples


def test_end_to_end_aggregate_from_fixtures() -> None:
    metrics = [evaluate_sample(truth, result) for truth, result in _load_samples()]
    summaries = {summary.bucket: summary for summary in summarize_by_quality(metrics)}

    assert set(summaries) == {"clean", "messy", "normal"}

    clean = summaries["clean"]
    assert clean.mean_character_error_rate == 0.0
    assert clean.mean_keyword_match_rate == 1.0
    assert clean.mean_bounding_box_iou == pytest.approx(1.0)
    assert clean.mean_bounding_box_center_error == pytest.approx(0.0)

    normal = summaries["normal"]
    assert normal.mean_character_error_rate == pytest.approx(1.0 / 12.0)
    assert normal.mean_bounding_box_center_error is None

    messy = summaries["messy"]
    assert messy.samples == 2
    assert messy.mean_character_error_rate == pytest.approx(0.5625)
    assert messy.failure_rate == pytest.approx(0.5)
    assert messy.low_confidence_rate == pytest.approx(0.5)
    assert messy.mean_bounding_box_center_error == pytest.approx(0.05)
    assert messy.mean_bounding_box_iou == pytest.approx(0.5)


def test_markdown_table_renders_header_and_rows() -> None:
    metrics = [evaluate_sample(truth, result) for truth, result in _load_samples()]
    table = to_markdown_table(summarize_by_quality(metrics))
    assert table.startswith("| 手書き品質 |")
    assert "| clean |" in table
    assert "| messy |" in table
    assert len(table.splitlines()) == 5  # header + divider + 3 buckets
