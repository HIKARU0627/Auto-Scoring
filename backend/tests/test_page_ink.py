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

from auto_scoring.adapters.image.ink import (
    ink_coverage,
    measure_page_boxes,
    measure_page_ruling,
)

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


class TestMeasuredBoxes:
    """`measure_page_boxes` (Issue #164).

    The reason this exists next to `measure_page_ruling` rather than instead
    of it: a rule is a long line, a box is a closed loop, and the real sheets
    have answer spaces that only one of the two can see. Issue #164 measured
    both against the five real subjects with five or more questions -- the
    numbers below are the shapes those sheets actually print, redrawn
    synthetically.
    """

    def _draw_box(
        self,
        image: np.ndarray,
        *,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        width: int = 3,
    ) -> None:
        _draw_horizontal(image, y0, x0=x0, x1=x1, width=width)
        _draw_horizontal(image, y1, x0=x0, x1=x1, width=width)
        _draw_vertical(image, x0, y0=y0, y1=y1, width=width)
        _draw_vertical(image, x1, y0=y0, y1=y1, width=width)

    def test_a_drawn_box_is_reported_at_its_printed_position(self) -> None:
        image = _blank_page()
        self._draw_box(image, x0=0.20, y0=0.30, x1=0.60, y1=0.40)

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 1
        assert boxes[0].x0 == pytest.approx(0.20, abs=0.01)
        assert boxes[0].x1 == pytest.approx(0.60, abs=0.01)
        assert boxes[0].y0 == pytest.approx(0.30, abs=0.01)
        assert boxes[0].y1 == pytest.approx(0.40, abs=0.01)

    def test_short_sided_boxes_are_found_where_the_ruling_measure_sees_nothing(self) -> None:
        """The failure that made Issue #164's first half necessary.

        One measured subject stacks five sub-item boxes (a-e) in a column
        0.046 wide. None of their sides is long enough to be a *rule*, so the
        list Issue #122 hands the model has no entry for any of them and it
        invents their edges -- it returned five boxes spaced exactly 0.047
        apart, the same stereotype #122 found in x. As boxes they are plain.
        """
        image = _blank_page()
        for index in range(5):
            top = 0.27 + index * 0.08
            self._draw_box(image, x0=0.798, y0=top, x1=0.844, y1=top + 0.08)

        ruling = measure_page_ruling(_encode(image))
        boxes = measure_page_boxes(_encode(image))

        assert ruling.horizontal == ()
        assert len(boxes) == 1
        assert boxes[0].y0 == pytest.approx(0.27, abs=0.01)
        assert boxes[0].y1 == pytest.approx(0.67, abs=0.01)

    def test_the_smallest_real_answer_box_is_still_found(self) -> None:
        """0.031 x 0.022 of the page -- the size one measured subject prints
        for a one-word answer, and the box `_BOX_SIDE_RUN` exists to reach.

        At `measure_page_ruling`'s own run length this box disappears
        entirely, and with it the difference between the two functions: on
        the real sheets, raising the threshold that far loses 4 of the 16
        candidates on one subject and 1 of 5 on another.
        """
        image = _blank_page()
        self._draw_box(image, x0=0.092, y0=0.250, x1=0.123, y1=0.272)

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 1
        assert boxes[0].x1 == pytest.approx(0.123, abs=0.01)

    def test_the_printed_rule_between_two_cells_does_not_split_them(self) -> None:
        """The rule itself is not part of either cell, so two stacked cells
        come out of the contour pass with the rule's own width of blank
        between them. Bridging less than that turns one answer space into
        two, and then the reviewer is offered half of it."""
        image = _blank_page()
        self._draw_box(image, x0=0.30, y0=0.30, x1=0.60, y1=0.40, width=5)
        self._draw_box(image, x0=0.30, y0=0.40, x1=0.60, y1=0.50, width=5)

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 1
        assert boxes[0].y1 == pytest.approx(0.50, abs=0.01)

    def test_touching_cells_are_one_box(self) -> None:
        """A 原稿用紙 grid is one place to write, not 90 of them.

        Reported separately, one measured subject's two grids would have
        offered the reviewer 186 candidates and asked the model to list 90
        indexes for one question.
        """
        image = _blank_page()
        for row in range(5):
            for column in range(20):
                self._draw_box(
                    image,
                    x0=0.14 + column * 0.035,
                    y0=0.28 + row * 0.034,
                    x1=0.14 + (column + 1) * 0.035,
                    y1=0.28 + (row + 1) * 0.034,
                    width=2,
                )

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 1
        assert boxes[0].x0 == pytest.approx(0.14, abs=0.02)
        assert boxes[0].x1 == pytest.approx(0.84, abs=0.02)

    def test_boxes_separated_by_blank_paper_stay_separate(self) -> None:
        """The other half of the same decision. One measured subject prints
        問一's three columns and 問二's two boxes on one page with a gap
        between the groups; merging them would hand each question the other's
        answer."""
        image = _blank_page()
        for x0 in (0.525, 0.668, 0.810):
            self._draw_box(image, x0=x0, y0=0.25, x1=x0 + 0.048, y1=0.48)
        self._draw_box(image, x0=0.354, y0=0.25, x1=0.402, y1=0.36)

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 4

    def test_a_frame_around_other_boxes_is_not_offered(self) -> None:
        """Every measured sheet draws one border around the whole answer
        area, and the header block around its own rows. Offered as
        candidates, they let the model answer "the whole page" -- which is
        exactly the crop intake already flags as unusable."""
        image = _blank_page()
        self._draw_box(image, x0=0.05, y0=0.22, x1=0.95, y1=0.95, width=4)
        self._draw_box(image, x0=0.20, y0=0.30, x1=0.60, y1=0.40)

        boxes = measure_page_boxes(_encode(image))

        assert len(boxes) == 1
        assert boxes[0].x1 == pytest.approx(0.60, abs=0.01)

    def test_a_page_with_no_printed_box_reports_none(self) -> None:
        """Not a failure: one measured subject's answer space is an open
        region under 「考え方・計算過程」 with no border anywhere, and the prompt
        keeps a way to describe one (`DetectedAnswerAreaOutput.bbox`)."""
        image = _blank_page()
        _draw_horizontal(image, 0.30, x0=0.10, x1=0.90)

        assert measure_page_boxes(_encode(image)) == ()
