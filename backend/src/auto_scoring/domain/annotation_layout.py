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


def resolve_annotation_rect(
    annotation: Annotation,
    *,
    question: Question,
    recognitions: Sequence[RecognitionResult],
) -> NormalizedRect | None:
    """Resolve ``annotation`` to the page-normalized rect to draw it at, per
    simplified-design-specification.md §12.1-12.4:

    1. An explicit ``rect`` is used as-is.
    2. Otherwise, an ``anchor_text`` is looked up against ``recognitions``'
       OCR bounding boxes (§12.3, `_find_anchor_text_rect`), newest attempt
       first, and mapped from crop-relative into page-relative space through
       ``question.answer_area`` (§12.3, ``_crop_relative_to_page``).
    3. Anything still unresolved returns ``None`` -- **nothing is drawn on
       the answer**, and the caller says so in the question's comment area
       instead (§12.4).

    **There is deliberately no fixed-position fallback** (Issue #141). Until
    then a CIRCLE/CROSS/TRIANGLE/SCORE whose anchor matched nothing was drawn
    at ``question.score_area``, on the grounds that §12.2 places
    question-level symbols there. Two different things were being conflated:
    "the AI meant a mark about the whole question" and "we could not find the
    words the AI meant". In the live re-verification every one of the
    fourteen annotations took this path, and since Issue #120 derives
    ``score_area`` as a band the height of the answer box, the result was a
    red ``×`` cutting across a quarter of the page -- on top of the score,
    and reading as though the whole answer had been struck out over an error
    in one term of one formula. §12.4 already said what to do instead
    ("無理に本文付近へ配置しない"): a position nobody knows is not a position.

    ``recognitions`` must already be scoped to the attempt being exported
    (`recognitions_up_to_attempt`).
    """
    if annotation.rect is not None:
        return annotation.rect
    if annotation.anchor_text:
        matched = _find_anchor_text_rect(
            annotation.anchor_text, recognitions, _effective_answer_area(question.answer_area)
        )
        if matched is not None:
            return matched
    return None


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


def _find_anchor_text_rect(
    anchor_text: str, recognitions: Sequence[RecognitionResult], answer_area: NormalizedRect
) -> NormalizedRect | None:
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
        matched = _shortest_box_run(needle, recognition.boxes)
        if matched is not None:
            return _crop_relative_to_page(matched, answer_area)
    return None


def _shortest_box_run(needle: str, boxes: Sequence[BoundingBox]) -> NormalizedRect | None:
    """The union rect of the fewest consecutive ``boxes`` whose joined,
    normalized text contains ``needle`` -- or ``None`` if no run does."""
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
    return _union([box.rect for box in boxes[best[0] : best[1] + 1]])


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


#: A derived band shorter than this (page-normalized) has no room for legible
#: text, so `derive_comment_area` falls back onto the answer area itself
#: rather than producing a sliver nothing can be read in.
_MIN_DERIVED_BAND_HEIGHT = 0.02


def derive_comment_area(answer_area: NormalizedRect | None) -> NormalizedRect | None:
    """The margin band a question's *comment* is written in, derived from
    where its answer box is -- or ``None`` when there is no box to derive
    from (Issue #120).

    `Question.comment_area` used to come only from an ``ANNOTATION_AREA``
    region, which a human placed on the profile screen. Issue #103 took that
    screen away on purpose -- the 配点 must have exactly one input -- and the
    registration path built by Issues #101/#103/#105 produces no such region.
    So every question registered through it had ``None``, `build_export_marks`
    had nowhere to draw, and the export ran to success while writing nothing
    at all: a 添削済み PDF byte for byte the same as the answer sheet it came
    from.

    **The convention.** The band directly *below* the answer box, as tall as
    the box or as much of the page as is left, whichever is less: that is
    where a human's red pen goes. A box that reaches the bottom of the page
    leaves no band, and there the answer area itself is used.

    **This used to derive the score's position too, and no longer does**
    (Issue #159). It returned ``(score_area, comment_area)``, the band split
    with the score taking its right 20%. The rule reads as though it keeps
    ink off the student's writing, and the live re-verification measured that
    it does not: of the sixteen questions that had an answer box, **fourteen
    had a derived band sitting on inked page content**, and **six had one
    falling inside the *next* question's answer box** -- one of them
    completely. Blank paper measures 0.0015% ink coverage at the same
    threshold; the worst derived score band measured 16.5%, more ink than the
    answer box it belonged to.

    The reason is that "below the answer box" is only empty when the sheet
    puts nothing there, and a sheet with several questions on it puts the
    next question there. Issue #159 was filed as a vertical-writing bug --
    a narrow column's band running down into more of the same grid -- and
    the measurement showed the rule breaking on horizontally-written
    subjects as well; vertical writing is only where it is most visible.

    So the score no longer has a position derived from geometry at all. It
    goes to the page's left margin strip (`domain.pdf_export.
    fallback_score_areas`), the one place on these sheets that was *measured*
    empty rather than assumed to be. `domain.test_registration.
    build_questions_and_rubrics` therefore leaves `Question.score_area`
    ``None`` unless a human placed a ``SCORE`` region, and every derived
    question's score is resolved at export time like Issue #150's.

    The comment keeps the band, whole rather than four fifths of it, and
    keeps the defect: a comment band is on inked content just as often (the
    same live measurement put the worst at 19.1%). Fixing that is not the
    same change -- a score is three to five characters and fits the 3%-wide
    strip, a comment is prose and would be ellipsis-truncated there -- so it
    is tracked separately and deliberately left alone here.
    """
    if answer_area is None or answer_area.width <= 0 or answer_area.height <= 0:
        return None
    return _band_below(answer_area)


def _band_below(answer_area: NormalizedRect) -> NormalizedRect:
    """The strip under ``answer_area``, or ``answer_area`` itself when the
    page has no usable room left below it."""
    top = answer_area.y + answer_area.height
    height = min(answer_area.height, 1.0 - top)
    if height < _MIN_DERIVED_BAND_HEIGHT:
        return answer_area
    return NormalizedRect(x=answer_area.x, y=top, width=answer_area.width, height=height)
