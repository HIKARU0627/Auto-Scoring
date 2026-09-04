"""Coordinate contract between the app's ``0..1`` space and PDF user space.

Adopted from PoC 3 (GitHub issue #12). See ``docs/poc-3-pdf-coordinates.md``.

The app and the test profile store annotation positions as **normalized points**
with a *top-left* origin over the page *as displayed* by pdfium (``pdfrx`` on the
Flutter side). A :class:`~auto_scoring.domain.pdf_engine.PdfEngine` that writes
annotations needs **PDF user space**: a *bottom-left* origin, measured in points,
*before* the page ``/Rotate`` is applied.

This module is the only piece of PoC 3 promoted into the app. It is pure Python
(no PDF library) so it can live in the framework-free domain layer and be covered
by a fast regression test.

The transform is parameterized by :class:`PageGeometry`, which carries exactly
what pdfium needs to lay out a page: the crop box (``CropBox`` clipped to
``MediaBox``) and the page rotation. Rendering DPI / zoom deliberately does *not*
appear -- normalization divides it out, which is the property PoC 3 verified.
"""

from __future__ import annotations

from dataclasses import dataclass

_QUARTER_TURNS = (90, 270)


@dataclass(frozen=True)
class PageGeometry:
    """Layout of one rendered PDF page, in user-space points.

    ``crop_offset_x`` / ``crop_offset_y`` are the lower-left corner of the crop
    box in absolute user space; they are non-zero when ``CropBox`` insets
    ``MediaBox``. ``rotation`` is the page ``/Rotate`` value (clockwise degrees).
    """

    crop_width: float
    crop_height: float
    crop_offset_x: float = 0.0
    crop_offset_y: float = 0.0
    rotation: int = 0

    def __post_init__(self) -> None:
        if self.crop_width <= 0.0 or self.crop_height <= 0.0:
            raise ValueError("crop dimensions must be positive")
        if self.rotation % 90 != 0:
            raise ValueError("rotation must be a multiple of 90 degrees")

    @property
    def normalized_rotation(self) -> int:
        """Rotation reduced to one of ``0``, ``90``, ``180``, ``270``."""
        return self.rotation % 360

    @property
    def displayed_width(self) -> float:
        """Page width as pdfium displays it (crop dims swap on a quarter turn)."""
        if self.normalized_rotation in _QUARTER_TURNS:
            return self.crop_height
        return self.crop_width

    @property
    def displayed_height(self) -> float:
        """Page height as pdfium displays it."""
        if self.normalized_rotation in _QUARTER_TURNS:
            return self.crop_width
        return self.crop_height


@dataclass(frozen=True)
class NormalizedPoint:
    """A point in ``[0, 1]`` with a top-left origin over the displayed page."""

    x: float
    y: float


@dataclass(frozen=True)
class UserSpacePoint:
    """A point in PDF user space: bottom-left origin, points, pre-rotation."""

    x: float
    y: float


def normalized_to_user_space(point: NormalizedPoint, geometry: PageGeometry) -> UserSpacePoint:
    """Convert a displayed-space normalized point to a PDF user-space point."""
    displayed_x = point.x * geometry.displayed_width
    displayed_y = point.y * geometry.displayed_height
    crop_x, crop_y = _unrotate(displayed_x, displayed_y, geometry)
    return UserSpacePoint(
        x=crop_x + geometry.crop_offset_x,
        y=(geometry.crop_height - crop_y) + geometry.crop_offset_y,
    )


def user_space_to_normalized(point: UserSpacePoint, geometry: PageGeometry) -> NormalizedPoint:
    """Inverse of :func:`normalized_to_user_space`."""
    crop_x = point.x - geometry.crop_offset_x
    crop_y = geometry.crop_height - (point.y - geometry.crop_offset_y)
    displayed_x, displayed_y = _rotate(crop_x, crop_y, geometry)
    return NormalizedPoint(
        x=displayed_x / geometry.displayed_width,
        y=displayed_y / geometry.displayed_height,
    )


def _unrotate(
    displayed_x: float, displayed_y: float, geometry: PageGeometry
) -> tuple[float, float]:
    """Displayed top-left coords -> crop-local top-left coords (undo ``/Rotate``)."""
    width, height = geometry.crop_width, geometry.crop_height
    rotation = geometry.normalized_rotation
    if rotation == 0:
        return displayed_x, displayed_y
    if rotation == 90:
        return displayed_y, height - displayed_x
    if rotation == 180:
        return width - displayed_x, height - displayed_y
    return width - displayed_y, displayed_x  # 270


def _rotate(crop_x: float, crop_y: float, geometry: PageGeometry) -> tuple[float, float]:
    """Crop-local top-left coords -> displayed top-left coords (apply ``/Rotate``)."""
    width, height = geometry.crop_width, geometry.crop_height
    rotation = geometry.normalized_rotation
    if rotation == 0:
        return crop_x, crop_y
    if rotation == 90:
        return height - crop_y, crop_x
    if rotation == 180:
        return width - crop_x, height - crop_y
    return crop_y, width - crop_x  # 270
