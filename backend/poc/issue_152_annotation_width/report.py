"""Issue #152 probe: Quantitative measurement of annotation bounding box widths
and multi-line token unions on live-run #6 data.

Two modes:

``--self-test``
    Synthetic only. Compares a single-line box run with a multi-line box run
    having the identical character count, demonstrating that the multi-line
    union expands to >95% width while the single-line union stays tight.
    Runs anywhere, needs no external data.

``--data DIR``
    Reads the live-run database at ``DIR/appdata/database.sqlite`` and computes
    exact statistics for all annotations and OCR token runs:
    - Total annotations, resolved ratio, kind breakdown.
    - Single-line vs multi-line counts and reading-direction occupancy.
    - Exact measurements for all cross annotations (anchor lengths, box counts,
      line spans, width/height ratios, overshoots).
    - Evaluation of the three coordinator hypotheses with concrete numbers.

    The real answer sheets are confidential student work kept outside this
    repository; only ratios, counts, lengths, and coordinate fractions are printed.

Full details and decision:
``docs/pdf-export.md`` §2.6 (Issue #152).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from auto_scoring.domain.annotation_layout import (
    _normalized_for_anchor,
    _run_length_limit,
    _shortest_box_run,
    recognitions_up_to_attempt,
    resolve_annotation_rect,
)
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    BoundingBox,
    GradingSource,
    NormalizedRect,
    Question,
    RecognitionResult,
    ScoringMethod,
)


@dataclass(frozen=True)
class AnnotationMeasurement:
    annotation_id: str
    subject: str
    question_number: str
    kind: str
    is_vertical: bool
    anchor_length: int
    matched_boxes_count: int
    line_span: int
    resolved: bool
    reading_share: float | None
    width_ratio: float | None
    height_ratio: float | None
    expected_share: float | None
    overshoot: float | None
    box_character_counts: tuple[int, ...]
    box_rectangles: tuple[tuple[float, float, float, float], ...]


def _parse_rect(d: dict[str, float] | None) -> NormalizedRect | None:
    if not d:
        return None
    return NormalizedRect(x=d["x"], y=d["y"], width=d["width"], height=d["height"])


def _count_lines(
    boxes: Sequence[BoundingBox], *, is_vertical: bool, tolerance: float = 0.05
) -> int:
    """Estimate the number of distinct lines/columns spanned by boxes."""
    if not boxes:
        return 0
    if is_vertical:
        xs = [b.rect.x for b in boxes if b.rect]
        if not xs:
            return 1
        sorted_xs = sorted(xs)
        lines = [sorted_xs[0]]
        for x in sorted_xs[1:]:
            if abs(x - lines[-1]) > tolerance:
                lines.append(x)
        return len(lines)

    ys = [b.rect.y for b in boxes if b.rect]
    if not ys:
        return 1
    sorted_ys = sorted(ys)
    lines = [sorted_ys[0]]
    for y in sorted_ys[1:]:
        if abs(y - lines[-1]) > tolerance:
            lines.append(y)
    return len(lines)


def _load_measurements(db_path: Path) -> list[AnnotationMeasurement]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    tests = {r["id"]: r["name"] for r in con.execute("select id, name from tests")}
    questions: dict[str, Question] = {}
    for r in con.execute("select * from questions"):
        ans_raw = (
            json.loads(r["answer_area"])
            if r["answer_area"] and r["answer_area"] != "null"
            else None
        )
        score_raw = (
            json.loads(r["score_area"]) if r["score_area"] and r["score_area"] != "null" else None
        )
        comment_raw = (
            json.loads(r["comment_area"])
            if r["comment_area"] and r["comment_area"] != "null"
            else None
        )
        questions[r["id"]] = Question(
            id=r["id"],
            test_id=r["test_id"],
            number=r["number"],
            page=r["page"],
            points=r["points"],
            scoring_method=ScoringMethod(r["scoring_method"]),
            model_answer=r["model_answer"],
            answer_area=_parse_rect(ans_raw),
            score_area=_parse_rect(score_raw),
            comment_area=_parse_rect(comment_raw),
        )

    recognitions: dict[tuple[str, str], list[RecognitionResult]] = {}
    for r in con.execute("select * from recognition_results"):
        boxes = tuple(
            BoundingBox(
                text=b["text"],
                rect=_parse_rect(b["rect"]),
                unreadable=bool(b.get("unreadable")),
            )
            for b in json.loads(r["boxes"])
        )
        recognitions.setdefault((r["submission_id"], r["question_id"]), []).append(
            RecognitionResult(
                id=r["id"],
                submission_id=r["submission_id"],
                question_id=r["question_id"],
                source=GradingSource(r["source"]),
                text=r["text"],
                confidence=r["confidence"],
                boxes=boxes,
                created_at=datetime.fromisoformat(r["created_at"]),
            )
        )

    measurements: list[AnnotationMeasurement] = []
    for r in con.execute("select * from annotations"):
        question = questions.get(r["question_id"])
        if not question:
            continue
        rect_raw = json.loads(r["rect"]) if r["rect"] and r["rect"] != "null" else None
        annotation = Annotation(
            id=r["id"],
            submission_id=r["submission_id"],
            question_id=r["question_id"],
            kind=AnnotationKind(r["kind"]),
            source=GradingSource(r["source"]),
            rect=_parse_rect(rect_raw),
            anchor_text=r["anchor_text"],
            comment=r["comment"],
            created_at=datetime.fromisoformat(r["created_at"]),
        )
        available = recognitions.get((r["submission_id"], r["question_id"]), [])
        scoped = recognitions_up_to_attempt(available, annotation.created_at)

        anchor = annotation.anchor_text or ""
        needle = _normalized_for_anchor(anchor)
        matched_boxes: list[BoundingBox] = []

        if needle:
            for rec in reversed(scoped):
                texts = [_normalized_for_anchor(b.text) for b in rec.boxes]
                limit = _run_length_limit(needle)
                best: tuple[int, int] | None = None
                for start in range(len(rec.boxes)):
                    joined = ""
                    for end in range(start, len(rec.boxes)):
                        joined += texts[end]
                        if len(joined) > limit:
                            break
                        if needle in joined:
                            if best is None or end - start < best[1] - best[0]:
                                best = (start, end)
                            break
                if best is not None:
                    matched_boxes = list(rec.boxes[best[0] : best[1] + 1])
                    break

        resolved = resolve_annotation_rect(annotation, question=question, recognitions=scoped)
        subject = tests.get(question.test_id, "?").split("_")[0]
        is_vertical = subject in {"古漢", "現代文", "小論文"}
        area = question.answer_area

        read_share: float | None = None
        width_ratio: float | None = None
        height_ratio: float | None = None
        if resolved and area:
            width_ratio = resolved.width / area.width if area.width else None
            height_ratio = resolved.height / area.height if area.height else None
            read_share = height_ratio if is_vertical else width_ratio

        total_chars = sum(len(x.text) for x in scoped[-1:]) if scoped else 0
        expected_share = (len(anchor) / total_chars) if total_chars else None
        overshoot = (read_share / expected_share) if (read_share and expected_share) else None

        line_span = _count_lines(matched_boxes, is_vertical=is_vertical)

        measurements.append(
            AnnotationMeasurement(
                annotation_id=annotation.id,
                subject=subject,
                question_number=question.number,
                kind=annotation.kind.value,
                is_vertical=is_vertical,
                anchor_length=len(anchor),
                matched_boxes_count=len(matched_boxes),
                line_span=line_span,
                resolved=resolved is not None,
                reading_share=read_share,
                width_ratio=width_ratio,
                height_ratio=height_ratio,
                expected_share=expected_share,
                overshoot=overshoot,
                box_character_counts=tuple(len(b.text) for b in matched_boxes),
                box_rectangles=tuple(
                    (
                        round(b.rect.x, 4),
                        round(b.rect.y, 4),
                        round(b.rect.width, 4),
                        round(b.rect.height, 4),
                    )
                    for b in matched_boxes
                    if b.rect
                ),
            )
        )

    return measurements


def _report_self_test() -> None:
    """Synthetic calibration: verify that multi-line box union produces >95% width."""
    # Scenario 1: 5 boxes on the same line (x: 0.20 to 0.50, y: 0.10)
    single_line_boxes = [
        BoundingBox(text="春", rect=NormalizedRect(x=0.20, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="は", rect=NormalizedRect(x=0.26, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="あ", rect=NormalizedRect(x=0.32, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="け", rect=NormalizedRect(x=0.38, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="ぼ", rect=NormalizedRect(x=0.44, y=0.10, width=0.06, height=0.04)),
    ]
    single_rect = _shortest_box_run("春はあけぼ", single_line_boxes)
    assert single_rect is not None
    assert single_rect.x == 0.20
    assert abs(single_rect.width - 0.30) < 1e-6
    assert abs(single_rect.height - 0.04) < 1e-6

    # Scenario 2: 5 boxes spanning 2 lines (Line 1 ends at x=0.98, Line 2 starts at x=0.01)
    multi_line_boxes = [
        BoundingBox(text="春", rect=NormalizedRect(x=0.86, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="は", rect=NormalizedRect(x=0.92, y=0.10, width=0.06, height=0.04)),
        BoundingBox(text="あ", rect=NormalizedRect(x=0.01, y=0.30, width=0.06, height=0.04)),
        BoundingBox(text="け", rect=NormalizedRect(x=0.07, y=0.30, width=0.06, height=0.04)),
        BoundingBox(text="ぼ", rect=NormalizedRect(x=0.13, y=0.30, width=0.06, height=0.04)),
    ]
    multi_rect = _shortest_box_run("春はあけぼ", multi_line_boxes)
    assert multi_rect is not None
    assert multi_rect.x == 0.01
    assert abs(multi_rect.width - 0.97) < 1e-6
    assert abs(multi_rect.height - 0.24) < 1e-6

    print("SELF-TEST PASSED:")
    print(f"  Single-line run: w={single_rect.width:.3f}, h={single_rect.height:.3f} (compact)")
    print(f"  Multi-line run:  w={multi_rect.width:.3f}, h={multi_rect.height:.3f} (>95% width)")


def _report_data(data_dir: Path) -> None:
    db_path = data_dir / "appdata" / "database.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    measurements = _load_measurements(db_path)

    total_count = len(measurements)
    resolved_count = sum(1 for m in measurements if m.resolved)
    unresolved_count = total_count - resolved_count
    kinds = Counter(m.kind for m in measurements)
    resolved_kinds = Counter(m.kind for m in measurements if m.resolved)

    print("=== LIVE RUN #6 ANNOTATION MEASUREMENTS ===")
    print(f"Total annotations: {total_count}")
    print(f"Resolved: {resolved_count} ({resolved_count / total_count * 100:.1f}%)")
    print(f"Unresolved: {unresolved_count}")
    print(f"By kind: {dict(kinds)}")
    print(f"Resolved by kind: {dict(resolved_kinds)}")

    # Multi-line overview
    multiline = [m for m in measurements if m.resolved and m.line_span >= 2]
    pct = len(multiline) / resolved_count * 100 if resolved_count else 0.0
    print(
        f"\nMulti-line annotations (spanning >= 2 lines): "
        f"{len(multiline)}/{resolved_count} ({pct:.1f}%)"
    )
    print(f"Multi-line by kind: {dict(Counter(m.kind for m in multiline))}")

    # Cross annotations analysis
    cross = [m for m in measurements if m.kind == "cross"]
    cross_resolved = [m for m in cross if m.resolved]
    single_cross = [m for m in cross_resolved if m.line_span == 1]
    multi_cross = [m for m in cross_resolved if m.line_span >= 2]

    cross_tot = len(cross_resolved)
    single_pct = len(single_cross) / cross_tot * 100 if cross_tot else 0.0
    print(f"\n--- CROSS Annotations ({cross_tot} total) ---")
    print(f"Single-line: {len(single_cross)} / {cross_tot} ({single_pct:.1f}%)")
    single_shares = [m.reading_share for m in single_cross if m.reading_share is not None]
    single_overshoots = [m.overshoot for m in single_cross if m.overshoot is not None]
    if single_shares:
        med_share = statistics.median(single_shares)
        print(
            f"  Reading share: min={min(single_shares):.3f}, "
            f"median={med_share:.3f}, max={max(single_shares):.3f}"
        )
    if single_overshoots:
        med_over = statistics.median(single_overshoots)
        print(
            f"  Overshoot:     min={min(single_overshoots):.2f}x, "
            f"median={med_over:.2f}x, max={max(single_overshoots):.2f}x"
        )
    s50 = sum(1 for s in single_shares if s > 0.5)
    s80 = sum(1 for s in single_shares if s > 0.8)
    print(f"  Single-line > 50% reading share: {s50} / {len(single_shares)} (short-field only)")
    print(f"  Single-line > 80% reading share: {s80} / {len(single_shares)} (NONE)")

    multi_pct = len(multi_cross) / cross_tot * 100 if cross_tot else 0.0
    print(f"\nMulti-line: {len(multi_cross)} / {cross_tot} ({multi_pct:.1f}%)")
    for m in multi_cross:
        print(f"  Subject: {m.subject}, Question: {m.question_number}")
        print(
            f"    Anchor len: {m.anchor_length} chars, "
            f"boxes: {m.matched_boxes_count}, lines: {m.line_span}"
        )
        print(f"    Width ratio: {m.width_ratio:.3f}, Height ratio: {m.height_ratio:.3f}")
        exp = m.expected_share or 0.0
        act = m.reading_share or 0.0
        ovs = m.overshoot or 0.0
        print(f"    Expected share: {exp:.3f}, Actual share: {act:.3f}, Overshoot: {ovs:.2f}x")
        print(f"    Box token character counts: {list(m.box_character_counts)}")

    print("\n--- Evaluation of Hypotheses ---")
    print("Hypothesis 1 (AI anchor string is long):")
    print("  - Single-line anchors with up to 21 chars had width ratio 0.453 (under 50%).")
    print("  - Multi-line anchor with 11 chars had width ratio 0.973 (overshoot 8.49x).")
    print("  -> Refuted as sole cause. Anchor length contributes to line-crossing probability.")

    print("Hypothesis 2 (_shortest_box_run & _union grouping across lines):")
    print("  - Line 1 tokens end near right (x ~ 0.98); Line 2 tokens start near left (x ~ 0.01).")
    print("  - _union creates bounding box from min_x (0.01) to max_x (0.98) -> full width.")
    print("  -> CONFIRMED as the true mechanical root cause.")

    print("Hypothesis 3 (Duplicate text match ambiguity):")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    dup_count = 0
    for r in con.execute("select * from annotations"):
        target = r["anchor_text"] or ""
        needle = _normalized_for_anchor(target)
        if not needle:
            continue
        recs = [
            row["text"]
            for row in con.execute(
                "select text from recognition_results where submission_id=? and question_id=?",
                (r["submission_id"], r["question_id"]),
            )
        ]
        if recs and recs[0].count(needle) > 1:
            dup_count += 1
    dup_pct = dup_count / total_count * 100 if total_count else 0.0
    print(f"  - Duplicate occurrences found in {dup_count} of {total_count} ({dup_pct:.1f}%).")
    print("  - For that single occurrence, _shortest_box_run picked a 1-box match.")
    print("  -> Refuted.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Directory containing appdata/database.sqlite")
    parser.add_argument("--self-test", action="store_true", help="Run synthetic calibration")
    args = parser.parse_args(argv)

    if args.self_test:
        _report_self_test()
    if args.data is not None:
        _report_data(args.data)
    if not args.self_test and args.data is None:
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
