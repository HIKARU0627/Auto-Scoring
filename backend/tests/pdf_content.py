"""Reading back what an export actually *drew*, from the PDF content stream.

`tests.pdf_ink` measures red pixels on a rasterized page and answers "is
there ink inside this rect". That is the right question for a shape's
position, and the wrong one for two things Issue #141 turned on:

* **Text.** Ink says a glyph was painted; it cannot say *which* glyph, so a
  comment drawn as ``notdef`` boxes, or the wrong comment entirely, still
  reads as ink. The live run's symptom was precisely "the shapes are there
  and the words are not".
* **Absence.** "No ink inside this rect" is the kind of negative assertion
  that goes vacuous the moment the code that draws anything at all breaks --
  the whole page comes out blank and every such test still passes.

So this module counts drawing *operations* instead: how many paths were
stroked and where, and what text was placed. A test that says "one stroke,
inside the anchored word's box, and no other" fails both when the stroke
moves and when it disappears.

Issue #141's own diagnosis was made this way: the exported PDF held exactly
three operations -- two score strings and one stroked cross the size of the
whole score band -- which is what identified the bug before a line was
changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import ContentStream

#: Path-painting operators that put a visible stroke or fill on the page.
#: ``n`` is deliberately absent: it ends a path without painting it (it is
#: what follows the ``W`` clip reportlab emits), and counting it would report
#: marks nobody can see.
_PAINTING_OPERATORS = frozenset({b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"})


@dataclass(frozen=True)
class DrawnPath:
    """One painted path's bounding box, in PDF user-space points."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def _apply(
    matrix: tuple[float, float, float, float, float, float], x: float, y: float
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def _multiply(
    inner: tuple[float, float, float, float, float, float],
    outer: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a1, b1, c1, d1, e1, f1 = inner
    a2, b2, c2, d2, e2, f2 = outer
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def drawn_paths(source: Path, page_index: int = 0) -> list[DrawnPath]:
    """Every painted path on ``page_index``, as user-space bounding boxes.

    The graphics state is tracked through ``q``/``Q``/``cm`` so a mark drawn
    inside reportlab's rotate-and-translate block (`_draw_mark_in_place`) is
    reported where it lands on the page, not where its local coordinates say.
    """
    reader = PdfReader(str(source))
    page = reader.pages[page_index]
    contents = page.get_contents()
    if contents is None:
        return []
    stack: list[tuple[float, float, float, float, float, float]] = []
    ctm: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    points: list[tuple[float, float]] = []
    paths: list[DrawnPath] = []
    for operands, operator in ContentStream(contents, reader).operations:
        if operator == b"q":
            stack.append(ctm)
        elif operator == b"Q":
            ctm = stack.pop() if stack else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        elif operator == b"cm":
            ctm = _multiply(tuple(float(value) for value in operands), ctm)  # type: ignore[arg-type]
        elif operator in (b"m", b"l"):
            points.append(_apply(ctm, float(operands[0]), float(operands[1])))
        elif operator in (b"c", b"v", b"y"):
            values = [float(value) for value in operands]
            points.extend(
                _apply(ctm, values[index], values[index + 1]) for index in range(0, len(values), 2)
            )
        elif operator == b"re":
            x, y, width, height = (float(value) for value in operands)
            points.extend(
                _apply(ctm, corner_x, corner_y)
                for corner_x, corner_y in (
                    (x, y),
                    (x + width, y),
                    (x + width, y + height),
                    (x, y + height),
                )
            )
        elif operator in _PAINTING_OPERATORS:
            if points:
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                paths.append(DrawnPath(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys)))
            points = []
        elif operator == b"n":
            points = []
    return paths


def drawn_text(source: Path, page_index: int | None = None) -> str:
    """Every character the export placed -- on ``page_index``, or across all
    pages when it is ``None``.

    Uses the font's ToUnicode map (`PdfReader`'s own extraction), so a comment
    that came out as ``notdef`` boxes, or as the wrong string, is visible as
    such rather than as "there is ink here".

    The per-page form is what Issue #161 needs on both sides of one
    assertion: the note text has to be on the appended note page *and* not
    on the answer sheet, and "no text anywhere" would satisfy only the
    second half while looking like a pass.
    """
    reader = PdfReader(str(source))
    pages = reader.pages if page_index is None else [reader.pages[page_index]]
    return "\n".join(page.extract_text() for page in pages)


def drawn_font_sizes(source: Path, page_index: int) -> list[float]:
    """The point size each string on ``page_index`` was actually drawn at,
    in the order they were drawn.

    Read from the content stream's own ``Tf`` operands rather than inferred
    from the mark rects, because the size a rect asks for and the size
    `adapters.pdf.pdfium_pypdf_engine._draw_text` settles on are different
    things: that function shrinks a point at a time until the wrapped lines
    fit and stops at a 6pt floor. "The note is legible" is a claim about the
    second number, so this reports the second number.

    `_draw_mark_in_place` only ever translates and rotates the canvas (never
    scales), so the ``Tf`` operand is the size on the paper.
    """
    reader = PdfReader(str(source))
    contents = reader.pages[page_index].get_contents()
    if contents is None:
        return []
    sizes: list[float] = []
    current = 0.0
    for operands, operator in ContentStream(contents, reader).operations:
        if operator == b"Tf":
            current = float(operands[1])
        elif operator in (b"Tj", b"TJ", b"'", b'"'):
            sizes.append(current)
    return sizes
