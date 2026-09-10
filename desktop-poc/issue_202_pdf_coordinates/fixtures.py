"""Synthetic PDF fixtures shared by PoC 6 (issue #202).

Same matrix as PoC 3 — see ``docs/poc-3-pdf-coordinates.md`` fixture table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

from auto_scoring.domain.pdf_geometry import NormalizedPoint

_TOLERANCE = 4e-3
_A4_W, _A4_H = 595.0, 842.0
_LETTER_W, _LETTER_H = 612.0, 792.0


@dataclass(frozen=True)
class Fixture:
    name: str
    media_width: float
    media_height: float
    rotation: int = 0
    crop: tuple[float, float, float, float] | None = None
    media_offset: tuple[float, float] = (0.0, 0.0)

    @property
    def media_box_label(self) -> str:
        left, bottom = self.media_offset
        return str([left, bottom, left + self.media_width, bottom + self.media_height])

    @property
    def crop_label(self) -> str:
        return "full page" if self.crop is None else str(list(self.crop))


FIXTURES: tuple[Fixture, ...] = (
    Fixture("a4-portrait", _A4_W, _A4_H),
    Fixture("a4-rotate-90", _A4_W, _A4_H, rotation=90),
    Fixture("a4-rotate-180", _A4_W, _A4_H, rotation=180),
    Fixture("a4-rotate-270", _A4_W, _A4_H, rotation=270),
    Fixture("a4-landscape", _A4_H, _A4_W),
    Fixture("letter-portrait", _LETTER_W, _LETTER_H),
    Fixture("a4-mediabox-offset", _A4_W, _A4_H, media_offset=(100.0, 200.0)),
    Fixture("a4-cropbox-inset", _A4_W, _A4_H, crop=(30.0, 40.0, 565.0, 800.0)),
    Fixture(
        "a4-cropbox-inset-rotate-90",
        _A4_W,
        _A4_H,
        rotation=90,
        crop=(30.0, 40.0, 565.0, 800.0),
    ),
)

TEST_POINTS: tuple[NormalizedPoint, ...] = (
    NormalizedPoint(0.12, 0.15),
    NormalizedPoint(0.50, 0.50),
    NormalizedPoint(0.90, 0.25),
    NormalizedPoint(0.25, 0.88),
    NormalizedPoint(0.82, 0.80),
)


def write_fixture(fixture: Fixture, path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=fixture.media_width, height=fixture.media_height)
    media_left, media_bottom = fixture.media_offset
    page.mediabox = RectangleObject(
        [
            media_left,
            media_bottom,
            media_left + fixture.media_width,
            media_bottom + fixture.media_height,
        ]
    )
    if fixture.rotation:
        page[NameObject("/Rotate")] = NumberObject(fixture.rotation)
    if fixture.crop is not None:
        page[NameObject("/CropBox")] = RectangleObject(list(fixture.crop))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
