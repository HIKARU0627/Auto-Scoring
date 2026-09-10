"""PoC 1 metrics -- computed from human ground-truth labels.

Pure functions and plain dataclasses. The harness
(``backend/poc/run_ocr_eval.py``) feeds recorded provider output and human
labels in; nothing here reaches a provider or the network. Aggregates are
secret-free by construction: only counts and averaged scores leave this module
(Issue #13 verification).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any

from auto_scoring.domain.ocr import BoundingBox, ConfidenceBand, OcrResult

_COLUMNS = (
    "手書き品質",
    "件数",
    "平均CER",
    "重要語一致率",
    "BBox中心誤差",
    "BBox IoU",
    "読めなかった語の割合",
    "失敗率",
)


def _levenshtein(source: str, target: str) -> int:
    if source == target:
        return 0
    if not source:
        return len(target)
    if not target:
        return len(source)
    previous = list(range(len(target) + 1))
    for i, source_char in enumerate(source, start=1):
        current = [i]
        for j, target_char in enumerate(target, start=1):
            substitution = previous[j - 1] + int(source_char != target_char)
            current.append(min(previous[j] + 1, current[j - 1] + 1, substitution))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance divided by reference length. 0.0 is a perfect read.

    An empty reference scores 0.0 when the hypothesis is empty too, else 1.0.
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return _levenshtein(reference, hypothesis) / len(reference)


def keyword_match_rate(keywords: Sequence[str], hypothesis: str) -> float:
    """Fraction of keywords that appear verbatim in ``hypothesis`` (1.0 if none)."""
    if not keywords:
        return 1.0
    return sum(1 for keyword in keywords if keyword and keyword in hypothesis) / len(keywords)


def bounding_box_center_error(expected: BoundingBox, actual: BoundingBox) -> float:
    """Euclidean distance between box centres, in normalised page units."""
    expected_x, expected_y = expected.center
    actual_x, actual_y = actual.center
    return math.hypot(expected_x - actual_x, expected_y - actual_y)


def _box_alignment(
    expected: Sequence[BoundingBox], actual: Sequence[BoundingBox]
) -> tuple[float, float] | None:
    """Mean centre error and mean IoU, matching each expected box to its best actual box."""
    if not expected or not actual:
        return None
    matches = [
        (
            box,
            max(
                actual,
                key=lambda candidate: (
                    box.iou(candidate),
                    -bounding_box_center_error(box, candidate),
                ),
            ),
        )
        for box in expected
    ]
    errors = [bounding_box_center_error(box, best) for box, best in matches]
    ious = [box.iou(best) for box, best in matches]
    return fmean(errors), fmean(ious)


@dataclass(frozen=True)
class OcrGroundTruth:
    """Human label for one question-region sample (business rules section 6.3).

    Holds no student-identifying data: ``sample_id`` is an opaque id.
    """

    sample_id: str
    reference_text: str
    keywords: tuple[str, ...]
    handwriting_quality: str  # "clean" | "normal" | "messy"
    layout_type: str
    expected_boxes: tuple[BoundingBox, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> OcrGroundTruth:
        return cls(
            sample_id=str(data["sample_id"]),
            reference_text=str(data["reference_text"]),
            keywords=tuple(str(keyword) for keyword in data.get("keywords", ())),
            handwriting_quality=str(data["handwriting_quality"]),
            layout_type=str(data["layout_type"]),
            expected_boxes=tuple(
                BoundingBox.from_mapping(box) for box in data.get("expected_boxes", ())
            ),
        )


@dataclass(frozen=True)
class SampleMetrics:
    """Per-sample metrics for one recorded OCR run against its human label."""

    sample_id: str
    handwriting_quality: str
    layout_type: str
    character_error_rate: float
    keyword_match_rate: float
    bounding_box_center_error: float | None
    bounding_box_iou: float | None
    #: Share of this sample's tokens the provider put in the LOW band.
    #:
    #: A *rate*, not "did any token come back LOW" (`OcrResult.
    #: has_low_confidence`), which is what this used to report. Any sample
    #: with more spans has more chances to contain one low span, so that
    #: boolean rose with the length of the answer rather than with how badly
    #: it was read -- the same defect Issue #158 removed from the usable gate
    #: (docs/ocr-recognition-pipeline.md §9). ``0.0`` when the sample has no
    #: tokens at all; ``failed`` is what says that.
    #:
    #: Reported by band, not by `RecognitionSettings.confidence_threshold`:
    #: this is a PoC report, and nothing branches on it. The threshold stays
    #: the single place a *decision* reads (business rules §3.1 (C)).
    unreadable_token_rate: float
    failed: bool


@dataclass(frozen=True)
class BucketSummary:
    """Averaged metrics for every sample in one handwriting-quality bucket."""

    bucket: str
    samples: int
    mean_character_error_rate: float
    mean_keyword_match_rate: float
    mean_bounding_box_center_error: float | None
    mean_bounding_box_iou: float | None
    mean_unreadable_token_rate: float
    failure_rate: float


def _unreadable_token_rate(result: OcrResult) -> float:
    if not result.tokens:
        return 0.0
    low = sum(1 for token in result.tokens if token.band is ConfidenceBand.LOW)
    return low / len(result.tokens)


def evaluate_sample(truth: OcrGroundTruth, result: OcrResult) -> SampleMetrics:
    """Score one recorded OCR ``result`` against its human ``truth`` label."""
    alignment = _box_alignment(
        truth.expected_boxes, [token.bounding_box for token in result.tokens]
    )
    return SampleMetrics(
        sample_id=truth.sample_id,
        handwriting_quality=truth.handwriting_quality,
        layout_type=truth.layout_type,
        character_error_rate=character_error_rate(truth.reference_text, result.text),
        keyword_match_rate=keyword_match_rate(truth.keywords, result.text),
        bounding_box_center_error=None if alignment is None else alignment[0],
        bounding_box_iou=None if alignment is None else alignment[1],
        unreadable_token_rate=_unreadable_token_rate(result),
        failed=not result.text and not result.tokens,
    )


def _mean_or_none(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def summarize_by_quality(samples: Iterable[SampleMetrics]) -> list[BucketSummary]:
    """Group per-sample metrics by handwriting quality and average each bucket."""
    by_bucket: dict[str, list[SampleMetrics]] = {}
    for sample in samples:
        by_bucket.setdefault(sample.handwriting_quality, []).append(sample)

    summaries: list[BucketSummary] = []
    for bucket in sorted(by_bucket):
        group = by_bucket[bucket]
        errors = [
            s.bounding_box_center_error for s in group if s.bounding_box_center_error is not None
        ]
        ious = [s.bounding_box_iou for s in group if s.bounding_box_iou is not None]
        summaries.append(
            BucketSummary(
                bucket=bucket,
                samples=len(group),
                mean_character_error_rate=fmean(s.character_error_rate for s in group),
                mean_keyword_match_rate=fmean(s.keyword_match_rate for s in group),
                mean_bounding_box_center_error=_mean_or_none(errors),
                mean_bounding_box_iou=_mean_or_none(ious),
                mean_unreadable_token_rate=fmean(s.unreadable_token_rate for s in group),
                failure_rate=fmean(float(s.failed) for s in group),
            )
        )
    return summaries


def _fmt(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def to_markdown_table(summaries: Sequence[BucketSummary]) -> str:
    """Render bucket summaries as a Markdown table (the docs "結果表")."""
    rows = [
        "| " + " | ".join(_COLUMNS) + " |",
        "| " + " | ".join(["---"] * len(_COLUMNS)) + " |",
    ]
    for summary in summaries:
        rows.append(
            "| "
            + " | ".join(
                (
                    summary.bucket,
                    str(summary.samples),
                    _fmt(summary.mean_character_error_rate),
                    _fmt(summary.mean_keyword_match_rate),
                    _fmt(summary.mean_bounding_box_center_error),
                    _fmt(summary.mean_bounding_box_iou),
                    _fmt(summary.mean_unreadable_token_rate),
                    _fmt(summary.failure_rate),
                )
            )
            + " |"
        )
    return "\n".join(rows)
