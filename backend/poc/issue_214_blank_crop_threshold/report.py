"""Issue #214 probe: ink coverage vs crop area on live-run #6 crops.

Two modes:

``--self-test``
    Synthetic only. Confirms that ``ink_coverage`` is the ink-pixel *fraction*
    (already area-normalised) and that the same ink pattern in a smaller crop
    yields a higher ratio. Runs anywhere, needs no data.

``--data DIR``
    Re-measures every PNG listed in ``DIR/out/ink.txt`` against
    ``DIR/out/crops/`` using the product's ``ink_coverage``.  Prints counts,
    the sorted distribution, area-coverage regression, and threshold splits.
    The real answer sheets are copyrighted material kept outside this
    repository; only ratios and pixel dimensions are printed.

Full plan, expectation, result and decision:
``docs/answer-intake-and-preprocessing.md`` §4.1 (Issue #214).
"""

from __future__ import annotations

import argparse
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from auto_scoring.adapters.image.ink import _INK_LEVEL, ink_coverage
from auto_scoring.domain.submission_intake import NEARLY_BLANK_INK_COVERAGE, is_nearly_blank_crop

_TABLE_ROW = re.compile(r"^\|[^|]+\|[^|]+\|[^|]+\|")


@dataclass(frozen=True)
class CropMeasurement:
    subject: str
    question: str
    reported_ink: float
    measured_ink: float
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        help="live-run tree with out/ink.txt and out/crops/*.png",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="calibrate on synthetic crops (no real data)",
    )
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        _report_self_test()
    if arguments.data is not None:
        _report_data(arguments.data)
    if not arguments.self_test and arguments.data is None:
        parser.error("nothing to do: pass --self-test, --data DIR, or both")
    return 0


def _report_self_test() -> None:
    """Synthetic checks that do not need licensed material."""
    line = 3
    small = np.full((100, 200), 255, dtype=np.uint8)
    small[50 : 50 + line, :] = 0
    small_cov = ink_coverage(_encode(small))

    # Same line thickness, 4x area in each dimension → 16x fewer ink pixels per area.
    large = np.full((400, 800), 255, dtype=np.uint8)
    large[200 : 200 + line, :] = 0
    large_cov = ink_coverage(_encode(large))

    assert small_cov > large_cov, "same ruling in a smaller crop must read higher"
    assert math.isclose(small_cov / large_cov, 4.0, rel_tol=0.02)

    # Fraction-of-pixels definition.
    ink_pixels = int((small <= _INK_LEVEL).sum())
    assert math.isclose(ink_pixels / small.size, small_cov, rel_tol=1e-9)

    print("self-test: ink_coverage is area-normalised (ink-pixel fraction)")
    print(f"self-test: small crop coverage={small_cov:.6f} large={large_cov:.6f}")


def _report_data(data_root: Path) -> None:
    ink_txt = data_root / "out" / "ink.txt"
    crops_dir = data_root / "out" / "crops"
    rows = _load_measurements(ink_txt, crops_dir)
    rows.sort(key=lambda row: row.measured_ink)

    print(f"crops measured: {len(rows)}")
    mismatches = [r for r in rows if abs(r.measured_ink - r.reported_ink) > 1e-6]
    print(f"ink.txt mismatches: {len(mismatches)}")

    areas = np.array([row.area for row in rows], dtype=float)
    inks = np.array([row.measured_ink for row in rows], dtype=float)
    log_slope, log_r = _log_log_regression(areas, inks)
    lin_slope, lin_intercept, lin_r = _linear_regression(areas, inks)

    print(f"log(area) vs log(ink): slope={log_slope:.4f} r={log_r:.4f}")
    print(f"ink vs area: slope={lin_slope:.2e} intercept={lin_intercept:.4f} r={lin_r:.4f}")

    below = sum(1 for row in rows if is_nearly_blank_crop(row.measured_ink))
    print(f"below NEARLY_BLANK_INK_COVERAGE ({NEARLY_BLANK_INK_COVERAGE}): {below}/{len(rows)}")

    print("distribution (measured_ink, area_px, width x height):")
    for row in rows:
        print(
            f"  {row.measured_ink:.6f}  {row.area:7d}  "
            f"{row.width:4d}x{row.height:4d}  {row.subject}/{row.question}"
        )

    if len(rows) >= 2:
        smallest = rows[0]
        second = rows[1]
        ratio = second.measured_ink / smallest.measured_ink
        thresh_ratio = smallest.measured_ink / NEARLY_BLANK_INK_COVERAGE
        print(
            f"smallest ink={smallest.measured_ink:.6f} "
            f"({thresh_ratio:.2f}x threshold); "
            f"next={second.measured_ink:.6f} ({ratio:.2f}x smallest)"
        )
        would_catch = 1
        would_pass = len(rows) - 1
        print(
            f"threshold in ({smallest.measured_ink:.6f}, {second.measured_ink:.6f}) "
            f"would stop {would_catch}/{len(rows)} and pass {would_pass}/{len(rows)} "
            "on this run only"
        )


def _load_measurements(ink_txt: Path, crops_dir: Path) -> list[CropMeasurement]:
    if not ink_txt.is_file():
        raise FileNotFoundError(ink_txt)
    if not crops_dir.is_dir():
        raise FileNotFoundError(crops_dir)

    rows: list[CropMeasurement] = []
    for line in ink_txt.read_text().splitlines():
        if not _TABLE_ROW.match(line) or "---" in line or "教科" in line:
            continue
        parts = [part.strip() for part in line.split("|")[1:-1]]
        if len(parts) < 3:
            continue
        subject, question, ink_str = parts[0], parts[1], parts[2]
        crop_path = crops_dir / f"{subject}_{question}.png"
        if not crop_path.is_file():
            raise FileNotFoundError(crop_path)
        png = crop_path.read_bytes()
        measured = ink_coverage(png)
        image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"could not decode {crop_path}")
        height, width = int(image.shape[0]), int(image.shape[1])
        rows.append(
            CropMeasurement(
                subject=subject,
                question=question,
                reported_ink=float(ink_str),
                measured_ink=measured,
                width=width,
                height=height,
            )
        )
    return rows


def _encode(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode synthetic image")
    return bytes(encoded.tobytes())


def _log_log_regression(areas: np.ndarray, inks: np.ndarray) -> tuple[float, float]:
    log_a = np.log(areas)
    log_i = np.log(inks + 1e-12)
    slope, _ = np.polyfit(log_a, log_i, 1)
    r = float(np.corrcoef(log_a, log_i)[0, 1])
    return float(slope), r


def _linear_regression(areas: np.ndarray, inks: np.ndarray) -> tuple[float, float, float]:
    slope, intercept = np.polyfit(areas, inks, 1)
    r = float(np.corrcoef(areas, inks)[0, 1])
    return float(slope), float(intercept), r


if __name__ == "__main__":
    raise SystemExit(main())
