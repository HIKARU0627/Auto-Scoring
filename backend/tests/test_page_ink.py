"""Measuring the printed ruling and the ink on a page raster (Issue #122).

Everything here runs on synthetic images with known geometry. The real
answer sheets these numbers were taken from are a cram school's copyrighted
material and never enter the repository (AGENTS.md "Security"), so the
measurements they produced are quoted in the assertions' reasoning instead.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from auto_scoring.adapters.image.ink import ink_coverage, measure_page_ruling

#: Same shape as a real answer sheet rendered at ``RENDER_SCALE`` -- the
#: run-length and span thresholds are fractions of the page, so a page of a
#: different size would exercise different pixel counts for the same content.
_WIDTH, _HEIGHT = 1191, 1685


def _blank_page() -> np.ndarray:
    return np.full((_HEIGHT, _WIDTH), 255, dtype=np.uint8)


def _encode(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return bytes(encoded.tobytes())


def _draw_vertical(image: np.ndarray, x: float, *, y0: float, y1: float, width: int = 3) -> None:
    column = int(x * _WIDTH)
    image[int(y0 * _HEIGHT) : int(y1 * _HEIGHT), column : column + width] = 0


def _draw_horizontal(image: np.ndarray, y: float, *, x0: float, x1: float, width: int = 3) -> None:
    row = int(y * _HEIGHT)
    image[row : row + width, int(x0 * _WIDTH) : int(x1 * _WIDTH)] = 0


def test_vertical_rules_are_reported_at_their_measured_positions() -> None:
    """The four narrow columns of a vertical-writing sheet, at the spacing
    measured on real material (0.048 wide)."""
    image = _blank_page()
    for x in (0.3543, 0.4018, 0.6671, 0.7158):
        _draw_vertical(image, x, y0=0.25, y1=0.48)

    ruling = measure_page_ruling(_encode(image))

    assert ruling.vertical == pytest.approx((0.3543, 0.4018, 0.6671, 0.7158), abs=2e-3)
    assert ruling.horizontal == ()


def test_horizontal_rules_are_reported_at_their_measured_positions() -> None:
    image = _blank_page()
    for y in (0.2209, 0.3567, 0.4866):
        _draw_horizontal(image, y, x0=0.10, x1=0.90)

    ruling = measure_page_ruling(_encode(image))

    assert ruling.horizontal == pytest.approx((0.2209, 0.3567, 0.4866), abs=2e-3)
    assert ruling.vertical == ()


def test_one_printed_line_is_one_position_not_one_per_pixel_column() -> None:
    """A rule is several pixels wide at any useful render scale, and
    antialiasing widens it further. Reporting each of those columns would
    give `domain.answer_area_snapping` a cluster of near-identical
    candidates and a snap that lands on whichever edge came first."""
    image = _blank_page()
    _draw_vertical(image, 0.5, y0=0.20, y1=0.80, width=9)

    ruling = measure_page_ruling(_encode(image))

    assert len(ruling.vertical) == 1
    assert ruling.vertical[0] == pytest.approx(0.5, abs=5e-3)


def test_handwriting_is_not_reported_as_ruling() -> None:
    """The whole method rests on this. A vertical stroke of a handwritten
    character is ink in a column too; if short strokes counted, every
    answered column would offer a dozen false rules to snap onto -- and
    snapping would then move boxes onto the student's own pen marks."""
    image = _blank_page()
    for index in range(12):
        _draw_vertical(image, 0.30 + index * 0.005, y0=0.30, y1=0.32)

    assert measure_page_ruling(_encode(image)).vertical == ()


def test_a_page_with_no_ruling_reports_none() -> None:
    """Answer space that is an open region under a heading is a normal
    sheet. Nothing may be invented for it."""
    ruling = measure_page_ruling(_encode(_blank_page()))

    assert ruling.vertical == ()
    assert ruling.horizontal == ()


def test_ink_coverage_of_blank_paper_is_zero() -> None:
    assert ink_coverage(_encode(_blank_page())) == 0.0


def test_ink_coverage_counts_the_inked_fraction() -> None:
    image = _blank_page()
    image[: _HEIGHT // 4, :] = 0

    assert ink_coverage(_encode(image)) == pytest.approx(0.25, abs=1e-3)


def test_ink_coverage_ignores_light_paper_texture() -> None:
    """Scans are not pure white. The threshold has to leave paper out, or a
    crop of blank paper would never look blank -- which is the whole signal
    `domain.submission_intake.is_nearly_blank_crop` depends on."""
    image = np.full((_HEIGHT, _WIDTH), 235, dtype=np.uint8)

    assert ink_coverage(_encode(image)) == 0.0


def test_undecodable_bytes_are_rejected_rather_than_measured() -> None:
    for measure in (ink_coverage, measure_page_ruling):
        with pytest.raises(ValueError, match="could not decode page image"):
            measure(b"not a png")
