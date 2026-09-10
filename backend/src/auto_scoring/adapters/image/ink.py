"""Measuring the ink on a rendered page: where the long printed rules run,
where the printed boxes are, and how much ink a crop has at all (Issue #122,
Issue #164).

Both answers come from the *same* raster the answer-area crop is taken from
(``PdfEngine.render_page_png`` at ``adapters.submission_intake.RENDER_SCALE``)
and share one definition of "ink", which is the reason they live in one
module rather than two.

Neither function reads or reports anything about *what* is written -- only
positions and a coverage ratio. The pages are a cram school's copyrighted
material (AGENTS.md "Security"), and nothing here may end up describing them.
"""

from __future__ import annotations

import cv2
import numpy as np

from auto_scoring.domain.answer_area_snapping import PageRuling
from auto_scoring.domain.profile import NormalizedBBox

#: Grayscale level at or below which a pixel counts as ink.
#:
#: These are scans, not synthetic pages: 200 (of 255) keeps a faint printed
#: rule while leaving paper texture out. Measured on three real answer
#: sheets, a region of blank paper comes out at a coverage of 0.000015 or
#: less at this level, against 0.050-0.121 for a region a student wrote in --
#: four orders of magnitude apart, which is what makes
#: `domain.submission_intake.NEARLY_BLANK_INK_COVERAGE` safe to set.
_INK_LEVEL = 200

#: How long an unbroken run of ink must be, as a fraction of the page
#: dimension it runs along, before the morphological opening keeps it. Below
#: this, handwriting strokes and the vertical strokes of printed characters
#: survive and are reported as ruling.
_MIN_RUN = 0.035

#: How much of the page dimension a rule must span in total to be reported.
#: A rule bounding one answer column runs a fraction of the page, not all of
#: it, so this is well under half.
_MIN_SPAN = 0.10

#: Columns/rows this close together are one rule, not two -- a rule is a few
#: pixels wide at any useful render scale, and an antialiased edge widens it.
_MERGE_GAP = 0.003


def measure_page_ruling(png_bytes: bytes) -> PageRuling:
    """The normalized positions of the long printed rules on one page raster.

    A rule is reported at the *midpoint* of the run of columns (or rows) it
    covers, so a 3-pixel-wide printed line yields one position rather than
    three. Returns empty tuples for a page with no ruling at all, which is a
    normal sheet, not a failure -- see `PageRuling`.
    """
    image = _decode(png_bytes)
    height, width = int(image.shape[0]), int(image.shape[1])
    ink = (image <= _INK_LEVEL).astype(np.uint8)
    return PageRuling(
        vertical=_lines(ink, axis=0, along=height, across=width),
        horizontal=_lines(ink, axis=1, along=width, across=height),
    )


#: How long a run of ink must be, as a fraction of the page dimension it
#: runs along, to count as one side of a printed box. Well under
#: :data:`_MIN_RUN`: a box side is short (one マス of a 原稿用紙 grid is
#: ~0.02 of the page) where a *rule* -- what `measure_page_ruling` looks for
#: -- runs across a whole answer column. This is the number that makes the
#: two functions see different things on the same page.
_BOX_SIDE_RUN = 0.012

#: Smallest area a cell may have, as a fraction of the page. Below this it is
#: a gap between two strokes of a printed character, not a place to write.
_MIN_CELL_AREA = 0.0004

#: How far apart two cells may be and still be reported as one box, as a
#: fraction of the shorter page dimension. A 原稿用紙 grid's cells touch, and
#: an answer's sub-items (a / b / c) are stacked with a hairline between
#: them; two *different* questions' boxes are separated by much more.
_CELL_JOIN = 0.006


def measure_page_boxes(png_bytes: bytes) -> tuple[NormalizedBBox, ...]:
    """The printed boxes on one page raster, in reading order (top, then left).

    **Why this exists, when `measure_page_ruling` already measures the page.**
    Issue #122 handed the model the printed *rules* and asked it to copy the
    values. Issue #164 measured what that produces on the real sheets and
    found two failures the rules cannot fix:

    * a box whose sides are too short to be rules is not in the list at all,
      so the model invents its edges -- on one subject it returned five
      evenly-spaced boxes 0.047 apart for a column whose real sub-boxes it
      could see perfectly well;
    * where the list *is* complete the model still picks the wrong pair of
      values, because nothing in a list of numbers says which pair bounds a
      box. On one subject the chosen pair bounded the blank paper between two
      answer columns.

    A box is a closed loop of printed sides, so it can be measured directly
    rather than reconstructed from the sides. That turns "estimate a
    rectangle" into the same multiple-choice question the question number
    already is (Issue #101, Issue #105) -- see
    `adapters.answer_area_detection._prompt`.

    Only *leaf* boxes are kept: a box that contains another one is a frame
    around it (the page border, a table's outer rule), and returning it would
    offer the reviewer's whole page as one candidate. Leaves that touch are
    then reported as one box, because a 原稿用紙 grid's 90 cells are one place
    to write, not 90 of them.

    Reports nothing at all for a page whose answer space has no printed
    border -- an open region under a 「考え方・計算過程」 heading is a real,
    measured case, and the prompt keeps a way to describe one.
    """
    image = _decode(png_bytes)
    height, width = int(image.shape[0]), int(image.shape[1])
    ink = (image <= _INK_LEVEL).astype(np.uint8)
    horizontal = _keep_runs(ink, (max(3, int(width * _BOX_SIDE_RUN)), 1))
    vertical = _keep_runs(ink, (1, max(3, int(height * _BOX_SIDE_RUN))))
    sides = cv2.dilate(horizontal | vertical, np.ones((3, 3), np.uint8), iterations=1)
    return _join(_leaf_cells(sides, width=width, height=height), width=width, height=height)


def _keep_runs(ink: np.ndarray, kernel_size: tuple[int, int]) -> np.ndarray:
    return cv2.morphologyEx(
        ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel_size)
    )


def _leaf_cells(sides: np.ndarray, *, width: int, height: int) -> list[tuple[int, int, int, int]]:
    """Pixel rectangles of every enclosed area that encloses nothing itself.

    ``RETR_CCOMP`` gives two levels: an outer contour of the printed strokes
    and, as its children, the holes they enclose. The holes are the boxes.
    """
    contours, hierarchy = cv2.findContours(sides, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    cells: list[tuple[int, int, int, int]] = []
    for contour, info in zip(contours, hierarchy[0], strict=True):
        if info[3] < 0:  # an outer contour, not a hole
            continue
        x, y, cell_width, cell_height = cv2.boundingRect(contour)
        if cell_width * cell_height < _MIN_CELL_AREA * width * height:
            continue
        cells.append((x, y, x + cell_width, y + cell_height))
    return [cell for cell in cells if not _contains_another(cell, cells)]


def _contains_another(
    cell: tuple[int, int, int, int], cells: list[tuple[int, int, int, int]]
) -> bool:
    x0, y0, x1, y1 = cell
    area = (x1 - x0) * (y1 - y0)
    return any(
        x0 <= other[0]
        and y0 <= other[1]
        and x1 >= other[2]
        and y1 >= other[3]
        and (other[2] - other[0]) * (other[3] - other[1]) < area
        for other in cells
    )


def _join(
    cells: list[tuple[int, int, int, int]], *, width: int, height: int
) -> tuple[NormalizedBBox, ...]:
    """One box per group of cells that touch, normalized.

    Done by painting the cells solid and growing them by ``_CELL_JOIN``
    rather than by comparing edges pairwise: a scan is never quite square,
    and two rows of a grid that a pairwise test rejects for a two-pixel
    misalignment are plainly one grid to a human.
    """
    if not cells:
        return ()
    filled = np.zeros((height, width), np.uint8)
    for x0, y0, x1, y1 in cells:
        cv2.rectangle(filled, (x0, y0), (x1, y1), 255, -1)
    span = max(3, int(_CELL_JOIN * min(width, height)))
    grown = cv2.dilate(filled, np.ones((span, span), np.uint8), iterations=1)
    count, _, stats, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    boxes: list[NormalizedBBox] = []
    for index in range(1, count):
        x, y, blob_width, blob_height, _ = stats[index]
        # Undo the growth, so the reported box is the printed one.
        x, y = x + span // 2, y + span // 2
        blob_width, blob_height = blob_width - span, blob_height - span
        if blob_width <= 0 or blob_height <= 0:
            continue
        boxes.append(
            NormalizedBBox(
                x0=x / width,
                y0=y / height,
                x1=(x + blob_width) / width,
                y1=(y + blob_height) / height,
            )
        )
    return tuple(sorted(boxes, key=lambda box: (box.y0, box.x0)))


def ink_coverage(png_bytes: bytes) -> float:
    """The fraction of ``png_bytes`` that is ink, ``0.0``-``1.0``.

    Used by intake to tell a crop that landed on the answer from one that
    landed on the margin (`domain.submission_intake.is_nearly_blank_crop`).
    """
    image = _decode(png_bytes)
    return float((image <= _INK_LEVEL).mean())


def _decode(png_bytes: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("could not decode page image")
    return image


def _lines(ink: np.ndarray, *, axis: int, along: int, across: int) -> tuple[float, ...]:
    """Positions (normalized against ``across``) of the rules running along
    ``axis``.

    ``axis=0`` sums down columns and so finds *vertical* rules; ``axis=1``
    finds horizontal ones. The morphological opening before the sum is what
    separates a rule from a column of unrelated ink that happens to line up:
    only runs at least ``_MIN_RUN`` of ``along`` long survive it.
    """
    run = max(3, int(_MIN_RUN * along))
    kernel_size = (1, run) if axis == 0 else (run, 1)
    kept = _keep_runs(ink, kernel_size)
    totals = kept.sum(axis=axis)
    hits = np.nonzero(totals > _MIN_SPAN * along)[0]
    if hits.size == 0:
        return ()
    gap = max(1, int(_MERGE_GAP * across))
    positions: list[float] = []
    start = previous = int(hits[0])
    for index in hits[1:]:
        current = int(index)
        if current - previous > gap:
            positions.append((start + previous) / 2.0 / across)
            start = current
        previous = current
    positions.append((start + previous) / 2.0 / across)
    return tuple(positions)
