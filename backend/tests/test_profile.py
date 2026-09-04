"""Unit tests for the Profile domain model's confirmation invariants."""

from __future__ import annotations

import pytest

from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    ProfileStatus,
    Region,
    RegionKind,
)

_SIGNATURE = FormatSignature(pages=(PageFormat(width_pt=595.0, height_pt=842.0),))


def _region(region_id: str, confirmed: bool = False) -> Region:
    return Region(
        region_id=region_id,
        kind=RegionKind.QUESTION,
        page_index=0,
        bbox=NormalizedBBox(x0=0.1, y0=0.1, x1=0.5, y1=0.2),
        label="Q1",
        confirmed=confirmed,
    )


def test_from_candidates_is_always_draft_and_unconfirmed() -> None:
    # A caller passing confirmed=True by mistake must not smuggle a candidate
    # straight to CONFIRMED -- this is the acceptance criterion that
    # candidates are always saved unconfirmed.
    sneaky = _region("q1", confirmed=True)
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [sneaky])
    assert profile.status is ProfileStatus.DRAFT
    assert all(not region.confirmed for region in profile.regions)


def test_confirm_requires_every_region_confirmed() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    with pytest.raises(ValueError, match="not confirmed"):
        profile.confirm([_region("q1", confirmed=False)])


def test_confirm_rejects_empty_region_list() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    with pytest.raises(ValueError, match="no regions"):
        profile.confirm([])


def test_confirm_transitions_to_confirmed_with_reviewed_regions() -> None:
    profile = Profile.from_candidates("p1", "format-a", _SIGNATURE, [_region("q1")])
    confirmed = profile.confirm([_region("q1", confirmed=True)])
    assert confirmed.status is ProfileStatus.CONFIRMED
    assert all(region.confirmed for region in confirmed.regions)
    # confirm() returns a new object; the draft is untouched.
    assert profile.status is ProfileStatus.DRAFT


@pytest.mark.parametrize(
    ("x0", "y0", "x1", "y1"),
    [
        (-0.1, 0.1, 0.5, 0.5),
        (0.1, 0.1, 1.5, 0.5),
        (0.5, 0.1, 0.1, 0.5),  # x0 >= x1
        (0.1, 0.5, 0.5, 0.5),  # y0 >= y1
    ],
)
def test_normalized_bbox_rejects_out_of_range_or_degenerate(
    x0: float, y0: float, x1: float, y1: float
) -> None:
    with pytest.raises(ValueError):
        NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def test_format_signature_matches_within_tolerance_only() -> None:
    a = FormatSignature(pages=(PageFormat(595.0, 842.0),))
    close = FormatSignature(pages=(PageFormat(595.4, 841.6),))
    far = FormatSignature(pages=(PageFormat(600.0, 842.0),))
    wrong_page_count = FormatSignature(pages=(PageFormat(595.0, 842.0), PageFormat(595.0, 842.0)))

    assert a.matches(close, tolerance_pt=1.0)
    assert not a.matches(far, tolerance_pt=1.0)
    assert not a.matches(wrong_page_count, tolerance_pt=1.0)
