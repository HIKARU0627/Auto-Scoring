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
    AnnotationKind,
    BoundingBox,
    NormalizedRect,
    Question,
    RecognitionResult,
)

#: Annotation kinds placed at a question's fixed "Annotation配置領域" (§12.2)
#: rather than at a specific word/phrase -- mirrors `pdf_review_geometry.dart`'s
#: `fixedPositionAnnotationKinds`.
FIXED_POSITION_KINDS = frozenset(
    {AnnotationKind.CIRCLE, AnnotationKind.CROSS, AnnotationKind.TRIANGLE, AnnotationKind.SCORE}
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
    3. Otherwise, a fixed-position kind (`FIXED_POSITION_KINDS`) falls back to
       ``question.score_area`` (§12.2).
    4. Anything still unresolved returns ``None`` -- the caller falls back to
       ``question.comment_area`` (§12.4).

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
    if annotation.kind in FIXED_POSITION_KINDS:
        return question.score_area
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
