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
       OCR bounding boxes (§12.3), newest attempt first, and mapped from
       crop-relative into page-relative space through ``question.
       answer_area`` (§12.3, ``_crop_relative_to_page``).
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


def _find_anchor_text_rect(
    anchor_text: str, recognitions: Sequence[RecognitionResult], answer_area: NormalizedRect
) -> NormalizedRect | None:
    """The page-normalized rect of the most recent OCR box whose text exactly
    matches ``anchor_text``, searching ``recognitions`` newest-first (a stale
    earlier attempt can report the same text at a different position).
    """
    for recognition in reversed(recognitions):
        for box in recognition.boxes:
            if box.text == anchor_text:
                return _crop_relative_to_page(box, answer_area)
    return None


def _crop_relative_to_page(box: BoundingBox, answer_area: NormalizedRect) -> NormalizedRect:
    """Map ``box`` -- normalized against the cropped answer image the OCR
    provider actually saw -- into a rect normalized against the whole page,
    by composing it with the crop's own page-normalized ``answer_area``
    (``adapters/image/opencv_preprocessor.crop_normalized_rect``: an
    axis-aligned crop, offset + scale only, no rotation).
    """
    rect = box.rect
    return NormalizedRect(
        x=answer_area.x + rect.x * answer_area.width,
        y=answer_area.y + rect.y * answer_area.height,
        width=rect.width * answer_area.width,
        height=rect.height * answer_area.height,
    )


#: Share of the derived band's width given to the score, at its right end --
#: the rest is the comment's. See `derive_mark_areas`.
_DERIVED_SCORE_WIDTH_SHARE = 0.2

#: A derived band shorter than this (page-normalized) has no room for legible
#: text, so `derive_mark_areas` falls back onto the answer area itself rather
#: than producing a sliver nothing can be read in.
_MIN_DERIVED_BAND_HEIGHT = 0.02


def derive_mark_areas(
    answer_area: NormalizedRect | None,
) -> tuple[NormalizedRect, NormalizedRect] | None:
    """``(score_area, comment_area)`` derived from where a question's answer
    box is, or ``None`` when there is no box to derive from (Issue #120).

    `Question.score_area`/`comment_area` used to come only from a `SCORE` /
    `ANNOTATION_AREA` region, which a human placed on the profile screen.
    Issue #103 took that screen away on purpose -- the 配点 must have exactly
    one input -- and the registration path built by Issues #101/#103/#105
    produces neither region. So every question registered through it had
    ``None`` for both, `build_export_marks` had nowhere to draw, and the
    export ran to success while writing nothing at all: a 添削済み PDF byte
    for byte the same as the answer sheet it came from.

    Deriving is what closes that without reopening #103's decision: nothing
    is added to any screen, and a hand-placed region still wins
    (`domain.test_registration.build_questions_and_rubrics` only falls back
    to this). It is deliberately not a detection either -- the real material
    does print a 得点欄 on some subjects (observed during Issue #105), but
    not demonstrably on all of them, so a rule that needs one cannot be the
    floor. Detecting it later fills `Question.score_area` in with something
    better and changes nothing here or downstream.

    **The convention.** The band directly *below* the answer box, as tall as
    the box or as much of the page as is left, whichever is less: that is
    where a human's red pen goes, and it does not cover what the student
    wrote. The score takes the right `_DERIVED_SCORE_WIDTH_SHARE` of it and
    the comment the rest, so the two never overlap -- `PdfEngine.
    render_annotations` draws every mark from its own rect and would
    otherwise stack them illegibly on top of one another. A box that reaches
    the bottom of the page leaves no band, and there the answer area itself
    is used: ink over the answer is worse than ink beside it, and both are
    better than a PDF with nothing on it.
    """
    if answer_area is None or answer_area.width <= 0 or answer_area.height <= 0:
        return None
    band = _band_below(answer_area)
    score_width = band.width * _DERIVED_SCORE_WIDTH_SHARE
    comment = NormalizedRect(x=band.x, y=band.y, width=band.width - score_width, height=band.height)
    score = NormalizedRect(
        x=band.x + comment.width, y=band.y, width=score_width, height=band.height
    )
    return score, comment


def _band_below(answer_area: NormalizedRect) -> NormalizedRect:
    """The strip under ``answer_area``, or ``answer_area`` itself when the
    page has no usable room left below it."""
    top = answer_area.y + answer_area.height
    height = min(answer_area.height, 1.0 - top)
    if height < _MIN_DERIVED_BAND_HEIGHT:
        return answer_area
    return NormalizedRect(x=answer_area.x, y=top, width=answer_area.width, height=height)
