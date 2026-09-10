"""Issue #130 probe: how far does the printed ruling move between two separate
scans of the same answer form, and is that enough to miss an answer column?

Two modes, because a measurement of real scans is worth nothing without a
measurement of the ruler:

``--self-test``
    Synthetic only. Builds a ruled page, transforms it by a *known* rotation,
    scale and translation, and reports how far this probe's estimate lands from
    the truth. That error is the noise floor every real number below is read
    against. Runs anywhere, needs no data.

``--data DIR``
    Every directory under ``DIR`` holding two or more PDFs matching
    ``--pattern`` is one group of scans of the same form. Pages with the same
    index are compared pairwise.

The real data is a cram school's copyrighted material and is not in this
repository; its location is an argument, never a default (AGENTS.md
"Security"). The output carries positions and counts only -- no page image, no
text, and not even the directory names, which are replaced by stable labels.

Full plan, expectation, result and decision:
``docs/poc-5-scan-to-scan-drift.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from drift import PageScan, PairDrift, measure_page, measure_pair

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine

#: The scale intake renders answer pages at
#: (`adapters.submission_intake.RENDER_SCALE`). The probe measures the same
#: raster the crop would be taken from, not a sharper one.
RENDER_SCALE = 2.0

#: The width of one answer column on the real vertical-writing forms, measured
#: in Issue #122. The question this probe exists to answer is how the drift
#: compares with it.
ANSWER_COLUMN_WIDTH = 0.048


@dataclass(frozen=True)
class PagePair:
    group: str
    page: int
    left: int
    right: int
    drift: PairDrift


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="directory tree of same-form scan groups")
    parser.add_argument(
        "--pattern", default="04*.pdf", help="which PDFs in a directory are the same form"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="calibrate against known transforms"
    )
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        _report_self_test()
    if arguments.data is not None:
        _report_data(arguments.data, arguments.pattern)
    if not arguments.self_test and arguments.data is None:
        parser.error("nothing to do: pass --self-test, --data DIR, or both")
    return 0


# --------------------------------------------------------------------------
# Calibration: what this probe's own error is.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Case:
    """One known transform to recover, and how hard the page is made to read.

    ``occlude`` hides two thirds of the answer-column rules on the second page
    and draws four long strokes that are not rules -- the shape a student's
    handwriting makes of a form. Without a case like it, a fit is only ever
    tested on two pages carrying identical rule sets, which is the one
    situation the real data never provides.
    """

    label: str
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    shift_x: float = 0.0
    shift_y: float = 0.0
    occlude: bool = False


#: Chosen to bracket what the real scans turned out to show, plus an identity
#: case -- a probe that reported drift on two copies of one page would make
#: every other row meaningless.
_CALIBRATION_CASES = (
    _Case("identity"),
    _Case("rotation only", rotation=0.30),
    _Case("rotation only", rotation=-0.60),
    _Case("translation only", shift_x=0.010, shift_y=0.040),
    _Case("scale only", scale_x=1.004, scale_y=0.996),
    _Case("all three", rotation=0.45, scale_x=1.003, scale_y=0.998, shift_x=-0.008, shift_y=0.025),
    _Case(
        "all three, ruling hidden",
        rotation=0.45,
        scale_x=1.003,
        scale_y=0.998,
        shift_x=-0.008,
        shift_y=0.025,
        occlude=True,
    ),
)


def _report_self_test() -> None:
    print("## Calibration (synthetic, known transform)\n")
    print(
        "| case | rotation deg | scale x | scale y | shift x | shift y "
        "| err rotation deg | err scale x | err scale y | err shift x | err shift y |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    worst = {"rotation": 0.0, "scale": 0.0, "translation": 0.0}
    for case in _CALIBRATION_CASES:
        page = _synthetic_form()
        moved = _apply(page, case)
        if case.occlude:
            moved = _occlude(moved)
        drift = measure_pair(measure_page(_png(page)), measure_page(_png(moved)))
        truth = (
            f"| {case.label} | {case.rotation:+.2f} | {case.scale_x:.4f} | {case.scale_y:.4f} "
            f"| {case.shift_x:+.3f} | {case.shift_y:+.3f} "
        )
        if drift.x.fit is None or drift.y.fit is None:
            print(f"{truth}| not measurable | | | | |")
            continue
        errors = (
            drift.rotation_degrees - case.rotation,
            drift.x.fit.scale - case.scale_x,
            drift.y.fit.scale - case.scale_y,
            _centre(drift.x.fit.scale, drift.x.fit.shift) - _centre(case.scale_x, case.shift_x),
            _centre(drift.y.fit.scale, drift.y.fit.shift) - _centre(case.scale_y, case.shift_y),
        )
        worst["rotation"] = max(worst["rotation"], abs(errors[0]))
        worst["scale"] = max(worst["scale"], abs(errors[1]), abs(errors[2]))
        worst["translation"] = max(worst["translation"], abs(errors[3]), abs(errors[4]))
        print(
            f"{truth}| {errors[0]:+.3f} | {errors[1]:+.5f} | {errors[2]:+.5f} "
            f"| {errors[3]:+.5f} | {errors[4]:+.5f} |"
        )
    print(
        f"\nNoise floor over {len(_CALIBRATION_CASES)} cases: "
        f"rotation {worst['rotation']:.3f} deg, scale {worst['scale']:.5f}, "
        f"translation {worst['translation']:.5f} page units."
    )
    _report_different_forms()


def _report_different_forms() -> None:
    """Two *different* forms must come back unmeasurable, not as a large drift.

    This is the assertion that keeps the "could not compare" count in the real
    run honest: without it, a probe that quietly fitted anything to anything
    would report the same numbers and no row would ever be excluded.
    """
    other = _synthetic_form()
    other[:] = 255
    for y in (0.32, 0.44, 0.56, 0.68, 0.80):
        cv2.line(other, (int(0.1 * 1191), int(y * 1684)), (int(0.9 * 1191), int(y * 1684)), 0, 3)
    drift = measure_pair(measure_page(_png(_synthetic_form())), measure_page(_png(other)))
    verdict = (
        "MEASURED -- the guard is not working" if drift.measured else "not measurable (correct)"
    )
    print(f"\nA page ruled a different way, compared with the form above: {verdict}.\n")


def _centre(scale: float, shift: float) -> float:
    return scale * 0.5 + shift - 0.5


def _occlude(page: np.ndarray) -> np.ndarray:
    """Paint out most of the answer-column rules and add long strokes that are
    not rules, the way an answered sheet does."""
    height, width = page.shape
    covered = page.copy()
    cv2.rectangle(
        covered,
        (int(0.10 * width), int(0.30 * height)),
        (int(0.40 * width), int(0.88 * height)),
        255,
        -1,
    )
    for x in (0.44, 0.58, 0.72, 0.86):
        cv2.line(
            covered,
            (int(x * width), int(0.34 * height)),
            (int((x + 0.004) * width), int(0.62 * height)),
            60,
            2,
        )
    return covered


def _synthetic_form(width: int = 1191, height: int = 1684) -> np.ndarray:
    """A blank page ruled like the real forms: a header table, a footer rule,
    and answer columns at *unequal* spacing so a fit that assumed a regular
    pitch could not pass by accident."""
    page = np.full((height, width), 255, dtype=np.uint8)
    for y in (0.085, 0.118, 0.150, 0.183, 0.215, 0.945):
        cv2.line(
            page, (int(0.06 * width), int(y * height)), (int(0.94 * width), int(y * height)), 0, 3
        )
    for x in (0.06, 0.28, 0.52, 0.94):
        cv2.line(
            page, (int(x * width), int(0.085 * height)), (int(x * width), int(0.215 * height)), 0, 3
        )
    left = 0.10
    for gap in (0.075, 0.048, 0.075, 0.061, 0.075, 0.052, 0.075):
        cv2.line(
            page,
            (int(left * width), int(0.30 * height)),
            (int(left * width), int(0.88 * height)),
            0,
            3,
        )
        left += gap
    cv2.line(
        page, (int(left * width), int(0.30 * height)), (int(left * width), int(0.88 * height)), 0, 3
    )
    cv2.line(
        page, (int(0.10 * width), int(0.30 * height)), (int(left * width), int(0.30 * height)), 0, 3
    )
    cv2.line(
        page, (int(0.10 * width), int(0.88 * height)), (int(left * width), int(0.88 * height)), 0, 3
    )
    return page


def _apply(page: np.ndarray, case: _Case) -> np.ndarray:
    height, width = page.shape
    stretch = np.array(
        [
            [case.scale_x, 0.0, case.shift_x * width],
            [0.0, case.scale_y, case.shift_y * height],
            [0.0, 0.0, 1.0],
        ]
    )
    centre = (width / 2.0, height / 2.0)
    turn = np.vstack([cv2.getRotationMatrix2D(centre, case.rotation, 1.0), [0, 0, 1]])
    combined = (turn @ stretch)[:2]
    return cv2.warpAffine(page, combined, (width, height), flags=cv2.INTER_LINEAR, borderValue=255)


def _png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode synthetic page")
    return bytes(buffer.tobytes())


# --------------------------------------------------------------------------
# Real data.
# --------------------------------------------------------------------------


def _report_data(root: Path, pattern: str) -> None:
    started = time.monotonic()
    groups, duplicates = _groups(root, pattern)
    if not groups:
        raise SystemExit(f"no directory under {root} holds two or more files matching {pattern!r}")
    engine = PdfiumPypdfEngine()
    pairs: list[PagePair] = []
    unmatched: list[tuple[str, int]] = []
    reasons: dict[str, int] = {}
    documents = 0
    print("## Corpus\n")
    print("| group | documents | pages per document | pages compared |")
    print("| --- | ---: | ---: | ---: |")
    for label, files in groups:
        documents += len(files)
        scans = [_scan_document(engine, path) for path in files]
        common = min(len(scan) for scan in scans)
        print(f"| {label} | {len(files)} | {'/'.join(str(len(s)) for s in scans)} | {common} |")
        for page in range(common):
            for left, right in _combinations(len(scans)):
                drift = measure_pair(scans[left][page], scans[right][page])
                for axis in (drift.x, drift.y):
                    if axis.reason is not None:
                        reasons[axis.reason] = reasons.get(axis.reason, 0) + 1
                if drift.measured:
                    pairs.append(PagePair(label, page, left, right, drift))
                else:
                    unmatched.append((label, page))
    _print_denominator(groups, documents, pairs, unmatched, duplicates, reasons)
    _print_pairs(pairs)
    _print_summary(pairs)
    print(f"\nElapsed: {time.monotonic() - started:.0f} s.")


def _combinations(count: int) -> Iterator[tuple[int, int]]:
    for left in range(count):
        for right in range(left + 1, count):
            yield left, right


def _print_denominator(
    groups: Sequence[tuple[str, list[Path]]],
    documents: int,
    pairs: Sequence[PagePair],
    unmatched: Sequence[tuple[str, int]],
    duplicates: int,
    reasons: dict[str, int],
) -> None:
    """What was actually measured, counted from the files rather than assumed.

    Split by axis on purpose: a form ruled for horizontal writing carries
    almost no rules running down the page, so "27 pairs measured" would hide
    that the x figures rest on a much smaller number than the y ones.
    """
    measured_x = sum(1 for pair in pairs if pair.drift.x.fit is not None)
    measured_y = sum(1 for pair in pairs if pair.drift.y.fit is not None)
    print(
        f"\n{documents} documents in {len(groups)} groups of the same form, "
        f"covering {len({(p.group, p.page) for p in pairs})} distinct pages. "
        f"{duplicates} further group(s) held byte-identical copies of files already "
        f"counted and were dropped, so no page is counted twice.\n"
    )
    print(f"- {len(pairs)} page pairs yielded at least one measurable axis.")
    pinned = sum(
        1
        for pair in pairs
        for axis in (pair.drift.x, pair.drift.y)
        if axis.fit is not None and not axis.fit.scale_measured
    )
    print(
        f"- x (across the page) is determined on {measured_x} of them, y (down it) on {measured_y}."
    )
    print(
        f"- {pinned} of those axes asked for more stretch than two scans of one sheet can "
        f"produce and were refitted with the scale pinned at 1; their translation and "
        f"residual still count, their scale does not."
    )
    print(f"- {len(unmatched)} page pairs matched on neither axis.")
    print("\nWhy the axes that were not measured were not measured:\n")
    print("| reason | axes |")
    print("| --- | ---: |")
    for reason, count in sorted(reasons.items(), key=lambda item: -item[1]):
        print(f"| {reason} | {count} |")
    print()


def _groups(root: Path, pattern: str) -> tuple[list[tuple[str, list[Path]]], int]:
    """Directories holding two or more matching PDFs, labelled ``G01``,
    ``G02`` ... in path order, with duplicate groups removed.

    The label, not the directory name, is what gets printed: the names carry
    the school's subject and material titles, and only numbers may leave this
    probe. Sorting makes the labels the same on every run.

    Groups whose files are byte-for-byte the ones of an earlier group are
    dropped. The real corpus contains such a pair -- one subject's samples are
    literally the same PDFs as another's -- and counting both would double
    every number they contribute while looking like independent evidence.
    """
    found: list[list[Path]] = []
    seen: set[frozenset[str]] = set()
    duplicates = 0
    for directory in sorted({path.parent for path in root.rglob(pattern)}):
        files = sorted(directory.glob(pattern))
        if len(files) < 2:
            continue
        fingerprint = frozenset(_digest(path) for path in files)
        if fingerprint in seen:
            duplicates += 1
            continue
        seen.add(fingerprint)
        found.append(files)
    return [(f"G{index:02d}", files) for index, files in enumerate(found, start=1)], duplicates


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scan_document(engine: PdfiumPypdfEngine, path: Path) -> list[PageScan]:
    return [
        measure_page(engine.render_page_png(path, index, scale=RENDER_SCALE))
        for index in range(engine.page_count(path))
    ]


def _print_pairs(pairs: Sequence[PagePair]) -> None:
    print("## Per page pair\n")
    print(
        "| group | page | pair | rotation deg | axis | rules | scale "
        "| from rotation | from scale | from translation | residual | total |"
    )
    print("| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in pairs:
        for name, axis in (("x", item.drift.x), ("y", item.drift.y)):
            rules = f"{axis.available[0]},{axis.available[1]}"
            head = (
                f"| {item.group} | {item.page + 1} | {item.left + 1}-{item.right + 1} "
                f"| {item.drift.rotation_degrees:+.2f} | {name} "
            )
            if axis.fit is None:
                print(
                    f"{head}| {rules} | -- | {axis.from_rotation:.4f} "
                    f"| -- | -- | -- | not measurable |"
                )
                continue
            scale = f"{axis.fit.scale:.4f}" if axis.fit.scale_measured else "pinned"
            share = f"{axis.from_scale:.4f}" if axis.from_scale is not None else "--"
            print(
                f"{head}| {axis.fit.matched}/{rules} | {scale} "
                f"| {axis.from_rotation:.4f} | {share} "
                f"| {axis.from_translation:.4f} | {axis.fit.max_residual:.4f} "
                f"| {axis.total:.4f} |"
            )
    print()


def _print_summary(pairs: Sequence[PagePair]) -> None:
    if not pairs:
        return
    print("## Summary\n")
    print(
        f"Page-normalized displacements, against the {ANSWER_COLUMN_WIDTH} answer-column "
        f"width Issue #122 measured.\n"
    )
    print("| quantity | n | median | 90th pct | max | max / 0.048 |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name, values in _summary_rows(pairs):
        array = np.abs(np.asarray(values, dtype=float))
        ratio = "--" if name.endswith("(deg)") else f"{array.max() / ANSWER_COLUMN_WIDTH:.2f}"
        print(
            f"| {name} | {len(array)} | {np.median(array):.4f} | "
            f"{np.percentile(array, 90):.4f} | {array.max():.4f} | {ratio} |"
        )
    print()


def _summary_rows(pairs: Sequence[PagePair]) -> Iterator[tuple[str, list[float]]]:
    yield "rotation (deg)", [pair.drift.rotation_degrees for pair in pairs]
    for axis in ("x", "y"):
        measured = [getattr(pair.drift, axis) for pair in pairs]
        yield f"from rotation, {axis}", [item.from_rotation for item in measured]
        fitted = [item for item in measured if item.fit is not None]
        if not fitted:
            continue
        measurable = [item for item in fitted if item.from_scale is not None]
        if measurable:
            yield f"from scale, {axis}", [_float(item.from_scale) for item in measurable]
        yield f"from translation, {axis}", [_float(item.from_translation) for item in fitted]
        yield (
            f"unexplained residual, {axis}",
            [_float(item.fit.max_residual) for item in fitted if item.fit],
        )
        yield f"total, {axis}", [_float(item.total) for item in fitted]


def _float(value: float | None) -> float:
    if value is None:
        raise ValueError("summary asked for a value the fit does not have")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
