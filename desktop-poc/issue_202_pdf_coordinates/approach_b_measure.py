"""Approach B: pypdfium2 bitmap display (same engine as PoC 3 sidecar adapter)."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from auto_scoring.adapters.pdf import PdfiumPypdfEngine

from fixtures import FIXTURES, TEST_POINTS, write_fixture
from measure_common import RENDER_SCALE, TOLERANCE, max_error, measure_red_centroid

_PAGE_COUNT_BENCH = 40
_BENCH_SCALES = (1.0, 2.0, 3.5)


@dataclass(frozen=True)
class RoundTripRow:
    fixture: str
    point_x: float
    point_y: float
    measured_x: float
    measured_y: float
    error: float


@dataclass(frozen=True)
class ApproachBResult:
    round_trip_rows: tuple[RoundTripRow, ...]
    worst_error: float
    render_ms_by_scale: dict[float, float]
    forty_page_png_bytes: int
    forty_page_render_ms: float


def measure_round_trip(samples_dir: Path) -> tuple[tuple[RoundTripRow, ...], float]:
    engine = PdfiumPypdfEngine()
    rows: list[RoundTripRow] = []
    worst = 0.0
    for fixture in FIXTURES:
        source = samples_dir / f"{fixture.name}.pdf"
        write_fixture(fixture, source)
        for point in TEST_POINTS:
            stamped = samples_dir / f"{fixture.name}.probe.pdf"
            engine.stamp_markers(source, stamped, {0: [point]})
            measured = measure_red_centroid(
                engine.render_page_png(stamped, 0, scale=RENDER_SCALE)
            )
            error = max_error(point, measured)
            worst = max(worst, error)
            rows.append(
                RoundTripRow(
                    fixture=fixture.name,
                    point_x=point.x,
                    point_y=point.y,
                    measured_x=measured.x,
                    measured_y=measured.y,
                    error=error,
                )
            )
            stamped.unlink()
    return tuple(rows), worst


def measure_performance(samples_dir: Path) -> tuple[dict[float, float], int, float]:
    engine = PdfiumPypdfEngine()
    source = samples_dir / "bench-a4-portrait.pdf"
    write_fixture(FIXTURES[0], source)

    render_ms_by_scale: dict[float, float] = {}
    for scale in _BENCH_SCALES:
        runs = []
        for _ in range(5):
            start = time.perf_counter()
            engine.render_page_png(source, 0, scale=scale)
            runs.append((time.perf_counter() - start) * 1000.0)
        render_ms_by_scale[scale] = statistics.median(runs)

    forty_dir = samples_dir / "forty-pages"
    forty_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    start = time.perf_counter()
    for index in range(_PAGE_COUNT_BENCH):
        page_path = forty_dir / f"page-{index:02d}.pdf"
        write_fixture(FIXTURES[0], page_path)
        png = engine.render_page_png(page_path, 0, scale=RENDER_SCALE)
        total_bytes += len(png)
    forty_page_ms = (time.perf_counter() - start) * 1000.0
    return render_ms_by_scale, total_bytes, forty_page_ms


def run(samples_dir: Path) -> ApproachBResult:
    samples_dir.mkdir(parents=True, exist_ok=True)
    rows, worst = measure_round_trip(samples_dir)
    render_ms, forty_bytes, forty_ms = measure_performance(samples_dir)
    return ApproachBResult(
        round_trip_rows=rows,
        worst_error=worst,
        render_ms_by_scale=render_ms,
        forty_page_png_bytes=forty_bytes,
        forty_page_render_ms=forty_ms,
    )


def verdict(worst_error: float) -> str:
    return "PASS" if worst_error <= TOLERANCE else "FAIL"
