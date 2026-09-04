"""PoC 3 (issue #12) repro command: regenerate the coordinate-diff report.

    uv run python poc/issue_12_pdf_coordinates/report.py

Builds a fixture PDF per orientation / rotation / page size / CropBox, stamps a
mark at a set of known normalized points with the adopted transform
(:mod:`auto_scoring.domain.pdf_geometry` via
:class:`auto_scoring.adapters.pdf.PdfiumPypdfEngine`), rasterizes the result with
pdfium, reads each mark back, and writes:

* ``docs/poc-3-pdf-coordinates/samples/<fixture>.pdf``  -- stamped PDF
* ``docs/poc-3-pdf-coordinates/samples/<fixture>.png``  -- preview raster
* ``docs/poc-3-pdf-coordinates/coordinate-diff-report.md`` -- expected vs measured

Exits non-zero if any point lands outside the tolerance asserted by
``backend/tests/test_pdf_engine_roundtrip.py``. Deterministic: re-running
reproduces byte-identical numbers.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops
from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, RectangleObject

from auto_scoring.adapters.pdf import PdfiumPypdfEngine
from auto_scoring.domain.pdf_geometry import (
    NormalizedPoint,
    normalized_to_user_space,
)

_TOLERANCE = 4e-3
_RENDER_SCALE = 2.0
_A4_W, _A4_H = 595.0, 842.0
_LETTER_W, _LETTER_H = 612.0, 792.0

_OUT_DIR = Path(__file__).resolve().parents[3] / "docs" / "poc-3-pdf-coordinates"
_SAMPLES_DIR = _OUT_DIR / "samples"


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


FIXTURES = [
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
]

TEST_POINTS = [
    NormalizedPoint(0.12, 0.15),
    NormalizedPoint(0.50, 0.50),
    NormalizedPoint(0.90, 0.25),
    NormalizedPoint(0.25, 0.88),
    NormalizedPoint(0.82, 0.80),
]


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
    with path.open("wb") as handle:
        writer.write(handle)


def measure_red_centroid(png_bytes: bytes) -> NormalizedPoint:
    with Image.open(BytesIO(png_bytes)) as image:
        rgb = image.convert("RGB")
    red, green, _ = rgb.split()
    redness = ImageChops.subtract(red, green).point(lambda v: 255 if v > 80 else 0)
    box = redness.getbbox()
    if box is None:
        raise SystemExit("stamped mark not found in the rendered page")
    left, top, right, bottom = box
    width, height = rgb.size
    return NormalizedPoint((left + right) / 2 / width, (top + bottom) / 2 / height)


def main() -> int:
    engine = PdfiumPypdfEngine()
    _SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[str] = []
    worst = 0.0
    for fixture in FIXTURES:
        source = _SAMPLES_DIR / f"{fixture.name}.source.pdf"
        stamped = _SAMPLES_DIR / f"{fixture.name}.pdf"
        write_fixture(fixture, source)

        # All points on one page: the human-inspectable sample artifact.
        engine.stamp_markers(source, stamped, {0: list(TEST_POINTS)})
        (_SAMPLES_DIR / f"{fixture.name}.png").write_bytes(
            engine.render_page_png(stamped, 0, scale=_RENDER_SCALE)
        )

        # One point at a time on a clean page: the measurement.
        geometry = engine.page_geometry(source, 0)
        for point in TEST_POINTS:
            probe = _SAMPLES_DIR / f"{fixture.name}.probe.pdf"
            engine.stamp_markers(source, probe, {0: [point]})
            measured = measure_red_centroid(engine.render_page_png(probe, 0, scale=_RENDER_SCALE))
            probe.unlink()
            user = normalized_to_user_space(point, geometry)
            error = max(abs(measured.x - point.x), abs(measured.y - point.y))
            worst = max(worst, error)
            rows.append(
                f"| {fixture.name} | {fixture.media_box_label} "
                f"| {fixture.rotation} | {fixture.crop_label} "
                f"| ({point.x:.2f}, {point.y:.2f}) "
                f"| ({user.x:.2f}, {user.y:.2f}) "
                f"| ({measured.x:.4f}, {measured.y:.4f}) | {error:.4f} |"
            )
        source.unlink()

    verdict = "PASS" if worst <= _TOLERANCE else "FAIL"
    columns = [
        "fixture",
        "MediaBox",
        "/Rotate",
        "CropBox",
        "normalized (x, y)",
        "expected user-space (x, y) pt",
        "measured normalized (x, y)",
        "abs error",
    ]
    report = _OUT_DIR / "coordinate-diff-report.md"
    report.write_text(
        "\n".join(
            [
                "# PoC 3 coordinate-diff report (generated)",
                "",
                "Regenerate with:",
                "",
                "```",
                "uv run python poc/issue_12_pdf_coordinates/report.py",
                "```",
                "",
                f"- render scale: {_RENDER_SCALE} px/pt",
                f"- tolerance: {_TOLERANCE} normalized ({_TOLERANCE * _A4_H:.2f} pt on A4 height)",
                f"- worst error: {worst:.4f} normalized -> **{verdict}**",
                "",
                "Expected user-space point = adopted transform output; measured = "
                "bounding-box centre of the mark read back from the pdfium raster.",
                "",
                "| " + " | ".join(columns) + " |",
                "| " + " | ".join("---" for _ in columns) + " |",
                *rows,
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {report.relative_to(_OUT_DIR.parent.parent)}")
    print(f"worst error {worst:.4f} normalized ({verdict}, tolerance {_TOLERANCE})")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
