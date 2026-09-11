"""Resolve an `Annotation` to the page rect it should be drawn at (Issue #23).

Port of `app/lib/core/pdf_review_geometry.dart`'s `resolveAnnotationRect` (Issue
#21/#22, ``docs/pdf-review-overlay.md`` §2.4/§2.8/§2.12) from Dart to this
framework-free domain layer: the review screen and the final PDF export
(Issue #23) must place the same annotation at the same spot, so both sides
implement simplified-design-specification.md §12.1-12.4 the same way. Kept
here rather than shared code (Dart and Python cannot share a module) --
`backend/tests/test_annotation_layout.py` and `app/test/
pdf_review_geometry_test.dart` are expected to agree on the same fixtures.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    BoundingBox,
    NormalizedRect,
    Question,
    RecognitionResult,
)

#: Identity crop (offset 0, scale 1): what a `None`/degenerate `answer_area`
#: effectively is (`_build_answer_image` sends the OCR provider the whole,
#: uncropped page in that case -- see `_effective_answer_area`).
_FULL_PAGE_AREA = NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0)


def annotations_for_attempt(
    annotations: Sequence[Annotation], attempt_created_at: datetime
) -> list[Annotation]:
    """Every annotation sharing ``attempt_created_at`` -- the grading attempt
    currently being exported (mirrors `QuestionReviewState.
    annotationsForDisplayedAttempt`, ``docs/pdf-review-overlay.md`` §2.12):
    annotations are append-only and a re-graded question's history can hold
    several attempts' worth, so only the ones written alongside the
    `GradeResult` actually being exported belong on the page.
    """
    return [a for a in annotations if a.created_at == attempt_created_at]


def recognitions_up_to_attempt(
    recognitions: Sequence[RecognitionResult], attempt_created_at: datetime
) -> list[RecognitionResult]:
    """Every recognition not newer than ``attempt_created_at``, oldest first
    (mirrors `QuestionReviewState.recognitionsForDisplayedAttempt`,
    ``docs/pdf-review-overlay.md`` §2.8): the OCR half of one attempt always
    commits before its grading half, so an exact ``created_at`` match would
    miss it.
    """
    return [r for r in recognitions if r.created_at <= attempt_created_at]


def resolve_annotation_rects(
    annotation: Annotation,
    *,
    question: Question,
    recognitions: Sequence[RecognitionResult],
) -> list[NormalizedRect] | None:
    """Resolve ``annotation`` to the page-normalized rect(s) to draw it at.

    Returns a one-element list for single-rect kinds (including CROSS on the
    anchor's first line only), multiple rects for UNDERLINE/BOX spanning line
    breaks (Issue #256), or ``None`` when nothing may be drawn on the answer
    (§12.4). See ``resolve_annotation_rect`` for the single-rect view.

    ``recognitions`` must already be scoped to the attempt being exported
    (`recognitions_up_to_attempt`).
    """
    if annotation.rect is not None:
        return [annotation.rect]
    if annotation.anchor_text:
        matched = _find_anchor_text_rects(
            annotation.anchor_text,
            recognitions,
            _effective_answer_area(question.answer_area),
            kind=annotation.kind,
        )
        if matched is not None:
            return matched
    return None


def resolve_annotation_rect(
    annotation: Annotation,
    *,
    question: Question,
    recognitions: Sequence[RecognitionResult],
) -> NormalizedRect | None:
    """Resolve ``annotation`` to a single page-normalized rect, per
    simplified-design-specification.md §12.1-12.4.

    Convenience wrapper around `resolve_annotation_rects`: returns the sole
    rect when exactly one was resolved, otherwise ``None`` (including
    multi-rect UNDERLINE/BOX -- callers that must draw every line should use
    `resolve_annotation_rects` instead).

    **There is deliberately no fixed-position fallback** (Issue #141).

    ``recognitions`` must already be scoped to the attempt being exported
    (`recognitions_up_to_attempt`).
    """
    rects = resolve_annotation_rects(annotation, question=question, recognitions=recognitions)
    if rects is None or len(rects) != 1:
        return None
    return rects[0]


def _effective_answer_area(answer_area: NormalizedRect | None) -> NormalizedRect:
    """`answer_area`, or the full-page identity crop for `None`/degenerate
    (non-positive width/height) input -- see `pdf_review_geometry.dart`'s
    identically-named helper for why a zero-area rect must be treated the
    same as `None` rather than composed with as a real crop.
    """
    if answer_area is None or answer_area.width <= 0 or answer_area.height <= 0:
        return _FULL_PAGE_AREA
    return answer_area


#: How much longer than the anchor a matched run of boxes may read, before
#: the match is rejected as too loose to draw a mark from.
#:
#: OCR boxes are whole tokens, so a run containing the anchor almost always
#: carries a little more than the anchor itself (a five-character anchor is
#: found inside a six-character box), and the rect drawn is the run's, not the anchor's.
#: A little slop is the resolution the OCR gives us; a lot of it is Issue #141
#: again in miniature -- a one-character anchor landing on a whole line and a
#: ``×`` stroked across all of it. Twice the anchor plus two characters
#: absorbs token-boundary overshoot at every real length seen in the live run
#: (the widest was a 5-character anchor matched by a 6-character box) while
#: still refusing a box that is mostly not the anchor.
def _run_length_limit(needle: str) -> int:
    return 2 * len(needle) + 2


#: Matches what both `_normalized_for_anchor` and its Dart twin call
#: whitespace. Written as a regex rather than as `str.split()` so the two
#: implementations are comparing the same set of characters: Dart's `RegExp`
#: `\s` and Python's `re` `\s` agree, while `str.split()` also eats a handful
#: of separators Dart would keep.
_WHITESPACE = re.compile(r"\s+")


def _normalized_for_anchor(text: str) -> str:
    """``text`` reduced to what the anchor and the OCR box can be compared on:
    no whitespace, and full-width ASCII folded to ASCII.

    Both halves are mismatches this comparison must not fail on, and both were
    measured in the live run rather than imagined:

    * **Whitespace.** Document AI slices each token's text straight out of
      ``document.text`` (`adapters.ocr.document_ai_provider._segment_text`),
      so the detected line break travels with it: the box reading the word
      酸素 has the text ``"酸素\n"``. Against an exact ``==`` that
      trailing newline alone was enough to leave the annotation unplaced.
    * **Full-width ASCII.** The live run also had a question whose printed
      sub-question labels are full-width Latin letters (U+FF41 and up) while
      the OCR read them back as their ASCII equivalents. A model quoting the
      printed form could never match the read form.

    Deliberately *not* NFKC, which would be the obvious library answer here:
    `pdf_review_geometry.dart` must fold identically (the review screen and
    the export have to agree on where a mark goes -- ``docs/pdf-export.md``
    §2), Dart's core library has no NFKC, and adding a normalization
    dependency to reach one is a bigger commitment than the two rules above,
    which are portable in a few lines. Both rules are idempotent and
    order-independent, so the two implementations cannot drift on them.
    """
    folded = "".join(
        chr(ord(character) - 0xFEE0) if 0xFF01 <= ord(character) <= 0xFF5E else character
        for character in text
    )
    return _WHITESPACE.sub("", folded)


def _find_anchor_text_rects(
    anchor_text: str,
    recognitions: Sequence[RecognitionResult],
    answer_area: NormalizedRect,
    *,
    kind: AnnotationKind | str | None = None,
) -> list[NormalizedRect] | None:
    """The page-normalized rect of the OCR boxes reading ``anchor_text``,
    searching ``recognitions`` newest-first (a stale earlier attempt can
    report the same text at a different position).

    **Matching is per *run of boxes*, not per box** (Issue #141). It used to
    be ``box.text == anchor_text``, and in the live re-verification that
    placed **none of the fourteen** annotations -- not one, across eight
    subjects, with the OCR working. Two reasons, both structural rather than
    bad luck:

    * A Document AI box is one *token*. ``葉緑体で`` is two of them (``葉緑体``,
      ``で``) and a longer phrase is six. Any anchor longer than a
      single token could never equal one box's text.
    * A token's text carries its own trailing break, so even ``酸素`` --
      read perfectly, as one box -- did not equal the anchor ``酸素``.

    So the anchor is looked for inside the text of consecutive boxes, on both
    sides `_normalized_for_anchor`, and the rect is those boxes' union. The
    *shortest* such run wins: a short anchor can be contained in many longer
    ones, and the tightest is the one whose rect most nearly covers the words
    the annotation is actually about.

    What is deliberately **not** done is fuzzy matching (edit distance,
    longest-common-subsequence). It would place several more of the live
    run's annotations, and it would place them by guessing -- which is the
    failure this whole issue is about. An anchor that cannot be found
    verbatim goes to the margin band and says it could not be placed.
    """
    needle = _normalized_for_anchor(anchor_text)
    if not needle:
        return None
    for recognition in reversed(recognitions):
        matched = _shortest_box_run(needle, recognition.boxes, kind=kind)
        if matched is not None:
            return [_crop_relative_to_page(rect, answer_area) for rect in matched]
    return None


def _group_boxes_by_line(boxes: Sequence[BoundingBox]) -> list[list[BoundingBox]]:
    """Split consecutive OCR boxes into line groups in reading order."""
    if not boxes:
        return []
    groups: list[list[BoundingBox]] = [[boxes[0]]]
    for index in range(1, len(boxes)):
        if _is_same_line(boxes[index - 1], boxes[index]):
            groups[-1].append(boxes[index])
        else:
            groups.append([boxes[index]])
    return groups


def _is_same_line(b1: BoundingBox, b2: BoundingBox) -> bool:
    """True if ``b2`` continues on the same line as ``b1`` in reading order.

    A token text containing a line break ends the line. Otherwise, two boxes
    continue the same line if their vertical extent overlaps substantially
    and x advances forward (horizontal text), or their horizontal extent
    overlaps substantially and y advances forward (vertical text).
    """
    if "\n" in b1.text:
        return False
    min_h = min(b1.rect.height, b2.rect.height)
    y_overlap = min(b1.rect.y + b1.rect.height, b2.rect.y + b2.rect.height) - max(
        b1.rect.y, b2.rect.y
    )
    is_horiz = (
        (min_h > 0) and (y_overlap > 0.5 * min_h) and (b2.rect.x >= b1.rect.x - b1.rect.width * 0.1)
    )

    min_w = min(b1.rect.width, b2.rect.width)
    x_overlap = min(b1.rect.x + b1.rect.width, b2.rect.x + b2.rect.width) - max(
        b1.rect.x, b2.rect.x
    )
    is_vert = (
        (min_w > 0)
        and (x_overlap > 0.5 * min_w)
        and (b2.rect.y >= b1.rect.y - b1.rect.height * 0.1)
    )

    return is_horiz or is_vert


def _shortest_box_run(
    needle: str,
    boxes: Sequence[BoundingBox],
    *,
    kind: AnnotationKind | str | None = None,
) -> list[NormalizedRect] | None:
    """The union rect(s) of the fewest consecutive ``boxes`` whose joined,
    normalized text contains ``needle`` -- or ``None`` if no run does.

    When the matched run spans across a line break:
    - Single bounding boxes across line breaks are forbidden (Issue #260).
    - For CROSS (×): one rect from the anchor's first token line only.
    - For UNDERLINE / BOX: one rect per line group (Issue #256).
    - For other kinds: ``None`` (§12.4 evacuate).
    """
    texts = [_normalized_for_anchor(box.text) for box in boxes]
    limit = _run_length_limit(needle)
    best: tuple[int, int] | None = None
    for start in range(len(boxes)):
        joined = ""
        for end in range(start, len(boxes)):
            joined += texts[end]
            # Checked *before* containment: a run that reads far more than
            # the anchor is refused outright rather than accepted for its
            # rect. The rect drawn is the run's, not the anchor's.
            if len(joined) > limit:
                break
            if needle in joined:
                if best is None or end - start < best[1] - best[0]:
                    best = (start, end)
                break
    if best is None:
        return None

    matched_boxes = list(boxes[best[0] : best[1] + 1])
    line_groups = _group_boxes_by_line(matched_boxes)
    if len(line_groups) == 1:
        return [_union([box.rect for box in matched_boxes])]

    is_cross = kind == AnnotationKind.CROSS or (isinstance(kind, str) and kind.lower() == "cross")
    if is_cross:
        return [_union([box.rect for box in line_groups[0]])]

    is_underline_or_box = kind in (AnnotationKind.UNDERLINE, AnnotationKind.BOX) or (
        isinstance(kind, str) and kind.lower() in ("underline", "box")
    )
    if is_underline_or_box:
        return [_union([box.rect for box in group]) for group in line_groups]
    return None


def _union(rects: Sequence[NormalizedRect]) -> NormalizedRect:
    """The smallest rect covering ``rects``.

    A single rect is handed back as-is rather than recomputed: ``x + width -
    x`` is not exactly ``width`` in binary floating point, and one box is by
    far the commonest run, so recomputing would put rounding noise into the
    position of nearly every annotation for nothing.
    """
    if len(rects) == 1:
        return rects[0]
    left = min(rect.x for rect in rects)
    top = min(rect.y for rect in rects)
    right = max(rect.x + rect.width for rect in rects)
    bottom = max(rect.y + rect.height for rect in rects)
    return NormalizedRect(x=left, y=top, width=right - left, height=bottom - top)


def _crop_relative_to_page(rect: NormalizedRect, answer_area: NormalizedRect) -> NormalizedRect:
    """Map ``rect`` -- normalized against the cropped answer image the OCR
    provider actually saw -- into a rect normalized against the whole page,
    by composing it with the crop's own page-normalized ``answer_area``
    (``adapters/image/opencv_preprocessor.crop_normalized_rect``: an
    axis-aligned crop, offset + scale only, no rotation).
    """
    return NormalizedRect(
        x=answer_area.x + rect.x * answer_area.width,
        y=answer_area.y + rect.y * answer_area.height,
        width=rect.width * answer_area.width,
        height=rect.height * answer_area.height,
    )
