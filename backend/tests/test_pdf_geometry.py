"""Regression tests for the PoC 3 coordinate contract (pure, no PDF library)."""

import pytest

from auto_scoring.domain.pdf_geometry import (
    NormalizedPoint,
    PageGeometry,
    UserSpacePoint,
    normalized_to_user_space,
    user_space_to_normalized,
)

_A4_W, _A4_H = 595.0, 842.0

_GEOMETRIES = [
    PageGeometry(_A4_W, _A4_H),
    PageGeometry(_A4_W, _A4_H, rotation=90),
    PageGeometry(_A4_W, _A4_H, rotation=180),
    PageGeometry(_A4_W, _A4_H, rotation=270),
    PageGeometry(_A4_H, _A4_W),  # landscape
    PageGeometry(535.0, 760.0, crop_offset_x=30.0, crop_offset_y=40.0),
    PageGeometry(535.0, 760.0, crop_offset_x=30.0, crop_offset_y=40.0, rotation=90),
    PageGeometry(_A4_W, _A4_H, rotation=-90),  # normalizes to 270
]

_POINTS = [
    NormalizedPoint(0.0, 0.0),
    NormalizedPoint(1.0, 1.0),
    NormalizedPoint(0.5, 0.5),
    NormalizedPoint(0.12, 0.15),
    NormalizedPoint(0.9, 0.25),
    NormalizedPoint(0.25, 0.88),
]


@pytest.mark.parametrize("geometry", _GEOMETRIES)
@pytest.mark.parametrize("point", _POINTS)
def test_round_trip_is_identity(geometry: PageGeometry, point: NormalizedPoint) -> None:
    restored = user_space_to_normalized(normalized_to_user_space(point, geometry), geometry)
    assert restored.x == pytest.approx(point.x, abs=1e-9)
    assert restored.y == pytest.approx(point.y, abs=1e-9)


def test_no_rotation_flips_only_the_y_axis() -> None:
    geometry = PageGeometry(_A4_W, _A4_H)
    top_left = normalized_to_user_space(NormalizedPoint(0.0, 0.0), geometry)
    assert (top_left.x, top_left.y) == pytest.approx((0.0, _A4_H))
    bottom_right = normalized_to_user_space(NormalizedPoint(1.0, 1.0), geometry)
    assert (bottom_right.x, bottom_right.y) == pytest.approx((_A4_W, 0.0))


def test_quarter_turn_swaps_displayed_dimensions() -> None:
    geometry = PageGeometry(_A4_W, _A4_H, rotation=90)
    assert geometry.displayed_width == _A4_H
    assert geometry.displayed_height == _A4_W


def test_rotation_90_maps_display_top_left_to_crop_lower_left() -> None:
    geometry = PageGeometry(_A4_W, _A4_H, rotation=90)
    point = normalized_to_user_space(NormalizedPoint(0.0, 0.0), geometry)
    assert (point.x, point.y) == pytest.approx((0.0, 0.0))


def test_rotation_270_maps_display_top_left_to_crop_upper_right() -> None:
    geometry = PageGeometry(_A4_W, _A4_H, rotation=270)
    point = normalized_to_user_space(NormalizedPoint(0.0, 0.0), geometry)
    assert (point.x, point.y) == pytest.approx((_A4_W, _A4_H))


def test_crop_offset_shifts_the_user_space_point() -> None:
    plain = PageGeometry(535.0, 760.0)
    inset = PageGeometry(535.0, 760.0, crop_offset_x=30.0, crop_offset_y=40.0)
    centre = NormalizedPoint(0.5, 0.5)
    a = normalized_to_user_space(centre, plain)
    b = normalized_to_user_space(centre, inset)
    assert (b.x - a.x, b.y - a.y) == pytest.approx((30.0, 40.0))


def test_user_space_to_normalized_matches_known_values() -> None:
    geometry = PageGeometry(_A4_W, _A4_H)
    middle = user_space_to_normalized(UserSpacePoint(_A4_W / 2, _A4_H / 2), geometry)
    assert (middle.x, middle.y) == pytest.approx((0.5, 0.5))


def test_rejects_non_positive_crop() -> None:
    with pytest.raises(ValueError, match="positive"):
        PageGeometry(0.0, 100.0)


def test_rejects_rotation_that_is_not_a_quarter_turn() -> None:
    with pytest.raises(ValueError, match="multiple of 90"):
        PageGeometry(100.0, 100.0, rotation=45)
