"""Snapping a detected answer box onto the printed ruling (Issue #122).

Two of these tests exist to stop a *fix* rather than a bug.

Issue #122's own text originally recorded the detection error as
"consistently to the right, 3-4% of the page width", from two samples. It is
not: measured over three subjects and two synthetic controls, the same call
errs to the left as often as to the right, is accurate to 0.006 on a sheet
whose columns sit near the model's stereotype, and is out by 0.181 on one
whose columns do not. ``test_snapping_never_moves_a_box_that_already_sits_on
_the_ruling`` and ``test_snapping_moves_boxes_on_both_sides_toward_the_line``
both fail the moment anyone acts on that original description by subtracting
a fixed offset somewhere in this path.

The third one, ``test_a_box_over_the_wrong_column_snaps_onto_the_wrong
_column``, pins a *limitation* of the fix, so it stays a known property
rather than a surprise: snapping repairs a near miss and cannot repair an
invention.
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.answer_area_snapping import (
    SNAP_TOLERANCE,
    PageRuling,
    snap_bbox_to_ruling,
)
from auto_scoring.domain.profile import NormalizedBBox

#: Four narrow vertical columns and the sheet's own left/right borders, at
#: the positions measured on a real vertical-writing answer sheet. Column
#: width is 0.048 -- the measurement that makes this Issue's failure fatal
#: only on vertical sheets (a 0.6-wide horizontal box absorbs the same error).
_COLUMNS = PageRuling(
    vertical=(0.0521, 0.3543, 0.4018, 0.5248, 0.5722, 0.6671, 0.7158, 0.8102, 0.8581, 0.9366),
    horizontal=(0.2500, 0.4800),
)


def _box(x0: float, x1: float, *, y0: float = 0.2500, y1: float = 0.4800) -> NormalizedBBox:
    return NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def test_a_near_miss_snaps_onto_the_column_it_was_naming() -> None:
    # The real measured case: the model reported this column 0.0113 to the
    # left of where the page prints it.
    result = snap_bbox_to_ruling(_box(0.6558, 0.7045), _COLUMNS)

    assert (result.bbox.x0, result.bbox.x1) == (0.6671, 0.7158)
    assert set(result.moved) == {"x0", "x1"}
    assert result.largest_shift == pytest.approx(0.0113, abs=1e-4)


def test_an_invented_position_is_left_alone() -> None:
    """A box in the middle of the page, where the sheet prints no rule at
    all, must come back untouched.

    This is the case snapping cannot help with, and quietly dragging it to
    the nearest line 0.09 away would turn "obviously wrong on the overlay"
    into "plausible and wrong".
    """
    box = _box(0.4400, 0.5000)

    result = snap_bbox_to_ruling(box, _COLUMNS)

    assert result.bbox == box
    assert result.moved == ()
    assert result.largest_shift == 0.0


def test_a_box_over_the_wrong_column_snaps_onto_the_wrong_column() -> None:
    """**A known limitation, pinned on purpose.**

    Nothing here can tell "the model meant this column and missed" from "the
    model meant a different column". A box sitting near the wrong one is
    snapped tidily onto the wrong one, and the result looks exactly as
    confident as a correct one.

    This is why Issue #122's second half -- the blank-crop tripwire
    (`domain.submission_intake.is_nearly_blank_crop`) and showing the
    reviewer the crop -- is not optional garnish on top of this fix.
    """
    # The model placed 問四's box over 問三's column, off by more than half a
    # column width. Every edge is still within tolerance of 問三's rules.
    result = snap_bbox_to_ruling(_box(0.5210, 0.5700), _COLUMNS)

    assert (result.bbox.x0, result.bbox.x1) == (0.5248, 0.5722)
    assert result.moved != ()


def test_snapping_never_moves_a_box_that_already_sits_on_the_ruling() -> None:
    """Fails if a constant offset correction is ever added to this path.

    A box whose edges are already the printed rules is by definition
    correct. Anything that shifts every box by a fixed amount -- the "always
    +0.035 to the right" reading Issue #122 was first written with -- moves
    this one off the column it is already on.
    """
    box = _box(0.6671, 0.7158)

    result = snap_bbox_to_ruling(box, _COLUMNS)

    assert result.bbox == box
    assert result.moved == ()
    assert result.largest_shift == 0.0


def test_snapping_moves_boxes_on_both_sides_toward_the_line() -> None:
    """Fails if a constant offset correction is ever added to this path.

    Two boxes missing the *same* column, one from the left and one from the
    right, must both end up on it -- i.e. be moved in **opposite**
    directions. A fixed offset moves both the same way, so it cannot satisfy
    this and the previous test at once.
    """
    from_left = snap_bbox_to_ruling(_box(0.6600, 0.7100), _COLUMNS)
    from_right = snap_bbox_to_ruling(_box(0.6750, 0.7250), _COLUMNS)

    assert (from_left.bbox.x0, from_left.bbox.x1) == (0.6671, 0.7158)
    assert (from_right.bbox.x0, from_right.bbox.x1) == (0.6671, 0.7158)
    # x0 moved right for one box and left for the other.
    assert from_left.bbox.x0 > 0.6600 and from_right.bbox.x0 < 0.6750


def test_snapping_is_idempotent() -> None:
    """Re-running detection, or re-saving a profile, must not walk a box
    across the page one tolerance at a time."""
    once = snap_bbox_to_ruling(_box(0.6558, 0.7045), _COLUMNS)
    twice = snap_bbox_to_ruling(once.bbox, _COLUMNS)

    assert twice.bbox == once.bbox
    assert twice.moved == ()


def test_an_axis_is_left_alone_when_snapping_would_collapse_the_box() -> None:
    """Both edges within tolerance of the *same* rule must not be pulled onto
    it: that is a zero-width box, which `NormalizedBBox` rejects outright --
    turning a detection that only needed correcting into a failed one."""
    box = _box(0.6650, 0.6700)

    result = snap_bbox_to_ruling(box, _COLUMNS)

    assert result.bbox == box
    assert result.moved == ()


def test_one_edge_snaps_when_only_that_edge_has_a_rule_near_it() -> None:
    """A box whose right edge names a rule and whose left edge names nothing
    keeps the left edge the model gave: half the page's answer is still
    better than none of it."""
    result = snap_bbox_to_ruling(_box(0.4400, 0.5300), _COLUMNS)

    assert result.bbox.x0 == 0.4400
    assert result.bbox.x1 == 0.5248
    assert result.moved == ("x1",)


def test_an_unruled_page_leaves_every_box_untouched() -> None:
    """Answer space that is an open region under a heading has no ruling.
    That is a normal sheet, not a failure, and nothing may be invented for it."""
    box = _box(0.2000, 0.8000)

    result = snap_bbox_to_ruling(box, PageRuling())

    assert result.bbox == box
    assert result.moved == ()


def test_the_tolerance_is_a_real_cutoff() -> None:
    """An edge just inside ``SNAP_TOLERANCE`` snaps; one just outside does
    not. Pins that the tolerance actually bounds how far a box may be moved
    -- without it, "snap to the nearest rule" would drag an invented box
    across the page to whatever line happened to be closest."""
    inside = snap_bbox_to_ruling(_box(0.6671 - SNAP_TOLERANCE * 0.9, 0.7158), _COLUMNS)
    outside = snap_bbox_to_ruling(_box(0.6671 - SNAP_TOLERANCE * 1.1, 0.7158), _COLUMNS)

    assert inside.bbox.x0 == 0.6671
    assert outside.bbox.x0 == pytest.approx(0.6671 - SNAP_TOLERANCE * 1.1)
    assert outside.moved == ()


def test_a_ruling_outside_the_page_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"within 0\.\.1"):
        PageRuling(vertical=(1.5,))


def test_a_negative_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        snap_bbox_to_ruling(_box(0.1, 0.2), _COLUMNS, tolerance=-0.1)
