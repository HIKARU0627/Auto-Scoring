"""Unit tests for `domain.annotation_layout` (Issue #23).

Port of `app/test/pdf_review_geometry_test.dart`'s `resolveAnnotationRect`
coverage to Python -- both sides must agree on where the same annotation
lands (§12.1-12.4), since the review screen and the final PDF export must
place it identically.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from auto_scoring.domain.annotation_layout import (
    annotations_for_attempt,
    derive_mark_areas,
    recognitions_up_to_attempt,
    resolve_annotation_rect,
)
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    BoundingBox,
    GradingSource,
    NormalizedRect,
    Question,
    RecognitionResult,
)

_NOW = datetime(2026, 1, 1)


def _question(**overrides: object) -> Question:
    values: dict[str, object] = {
        "id": "q-1",
        "test_id": "test-1",
        "number": "1",
        "page": 1,
        "points": 5,
    }
    values.update(overrides)
    return Question(**values)  # type: ignore[arg-type]


def _annotation(**overrides: object) -> Annotation:
    values: dict[str, object] = {
        "id": "anno-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "kind": AnnotationKind.COMMENT,
        "comment": "コメント",
        "created_at": _NOW,
    }
    values.update(overrides)
    return Annotation(**values)  # type: ignore[arg-type]


def _recognition(
    *, boxes: tuple[BoundingBox, ...], created_at: datetime = _NOW
) -> RecognitionResult:
    return RecognitionResult(
        id="rec-1",
        submission_id="sub-1",
        question_id="q-1",
        source=GradingSource.AI,
        text="",
        confidence=0.9,
        created_at=created_at,
        boxes=boxes,
    )


def _rect(x: float, y: float, w: float, h: float) -> NormalizedRect:
    return NormalizedRect(x=x, y=y, width=w, height=h)


class TestResolveAnnotationRect:
    def test_an_explicit_rect_is_used_as_is(self) -> None:
        rect = _rect(0.1, 0.2, 0.3, 0.4)
        annotation = _annotation(kind=AnnotationKind.UNDERLINE, rect=rect, anchor_text=None)

        resolved = resolve_annotation_rect(annotation, question=_question(), recognitions=())

        assert resolved == rect

    def test_anchor_text_resolves_against_the_matching_ocr_box_when_answer_area_is_the_full_page(
        self,
    ) -> None:
        box_rect = _rect(0.1, 0.2, 0.3, 0.1)
        annotation = _annotation(kind=AnnotationKind.UNDERLINE, anchor_text="行く", rect=None)
        recognition = _recognition(boxes=(BoundingBox(text="行く", rect=box_rect),))

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved == box_rect

    def test_anchor_text_box_is_mapped_from_crop_space_into_page_space_via_answer_area(
        self,
    ) -> None:
        answer_area = _rect(0.5, 0.5, 0.4, 0.4)
        box_rect = _rect(0.0, 0.0, 0.5, 0.5)  # top-left quarter of the crop
        annotation = _annotation(kind=AnnotationKind.BOX, anchor_text="word", rect=None)
        recognition = _recognition(boxes=(BoundingBox(text="word", rect=box_rect),))

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=answer_area), recognitions=(recognition,)
        )

        assert resolved is not None
        assert resolved.x == pytest.approx(0.5)
        assert resolved.y == pytest.approx(0.5)
        assert resolved.width == pytest.approx(0.2)
        assert resolved.height == pytest.approx(0.2)

    def test_a_zero_area_answer_area_is_treated_as_the_full_page_not_a_zero_size_crop(
        self,
    ) -> None:
        box_rect = _rect(0.1, 0.1, 0.2, 0.2)
        annotation = _annotation(kind=AnnotationKind.BOX, anchor_text="word", rect=None)
        recognition = _recognition(boxes=(BoundingBox(text="word", rect=box_rect),))
        degenerate = _rect(0.5, 0.5, 0.0, 0.3)

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=degenerate), recognitions=(recognition,)
        )

        assert resolved == box_rect

    def test_newest_attempt_wins_when_two_recognitions_report_the_same_anchor_text(
        self,
    ) -> None:
        stale = _recognition(
            boxes=(BoundingBox(text="行く", rect=_rect(0.0, 0.0, 0.1, 0.1)),),
            created_at=_NOW,
        )
        fresh = _recognition(
            boxes=(BoundingBox(text="行く", rect=_rect(0.5, 0.5, 0.1, 0.1)),),
            created_at=_NOW + timedelta(seconds=1),
        )
        annotation = _annotation(kind=AnnotationKind.UNDERLINE, anchor_text="行く", rect=None)

        resolved = resolve_annotation_rect(
            annotation, question=_question(), recognitions=(stale, fresh)
        )

        assert resolved == _rect(0.5, 0.5, 0.1, 0.1)

    @pytest.mark.parametrize(
        "kind",
        [
            AnnotationKind.CIRCLE,
            AnnotationKind.CROSS,
            AnnotationKind.TRIANGLE,
            AnnotationKind.SCORE,
        ],
    )
    def test_a_fixed_position_kind_falls_back_to_score_area_when_unresolved(
        self, kind: AnnotationKind
    ) -> None:
        score_area = _rect(0.8, 0.05, 0.1, 0.05)
        annotation = _annotation(kind=kind, anchor_text=None, rect=None)

        resolved = resolve_annotation_rect(
            annotation, question=_question(score_area=score_area), recognitions=()
        )

        assert resolved == score_area

    def test_a_non_fixed_kind_with_nothing_resolvable_returns_none(self) -> None:
        annotation = _annotation(
            kind=AnnotationKind.COMMENT, anchor_text=None, rect=None, comment="コメント"
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(score_area=_rect(0.8, 0.05, 0.1, 0.05)), recognitions=()
        )

        assert resolved is None


class TestAttemptScoping:
    def test_annotations_for_attempt_keeps_only_the_matching_created_at(self) -> None:
        older = _annotation(id="a1", created_at=_NOW)
        current = _annotation(id="a2", created_at=_NOW + timedelta(seconds=5))

        result = annotations_for_attempt([older, current], _NOW + timedelta(seconds=5))

        assert [a.id for a in result] == ["a2"]

    def test_recognitions_up_to_attempt_excludes_anything_newer(self) -> None:
        ocr = _recognition(boxes=(), created_at=_NOW)
        grading = _recognition(boxes=(), created_at=_NOW + timedelta(seconds=1))
        future = _recognition(boxes=(), created_at=_NOW + timedelta(seconds=10))

        result = recognitions_up_to_attempt([ocr, grading, future], _NOW + timedelta(seconds=1))

        assert result == [ocr, grading]


# --------------------------------------------------------------------------- #
# derive_mark_areas (Issue #120)
# --------------------------------------------------------------------------- #


def test_derived_areas_sit_in_the_band_below_the_answer_box() -> None:
    """The convention: a human's red pen goes under the answer, not over it."""
    answer = NormalizedRect(x=0.1, y=0.2, width=0.8, height=0.3)

    derived = derive_mark_areas(answer)

    assert derived is not None
    score, comment = derived
    for area in (score, comment):
        assert area.y >= answer.y + answer.height, "an area overlapped the student's answer"
        assert area.height > 0
    assert comment.x == answer.x
    assert score.x + score.width == pytest.approx(answer.x + answer.width)
    assert comment.x + comment.width == pytest.approx(score.x), "the two areas overlap"


def test_derived_areas_stay_on_the_page_when_the_answer_box_reaches_the_bottom() -> None:
    """An answer box running to the bottom edge leaves no band under it. Ink
    over the answer is worse than ink beside it, and both beat a PDF with
    nothing on it -- so the answer area itself is used, and never a rect
    that would run off the page (`NormalizedRect` would refuse to build one).
    """
    answer = NormalizedRect(x=0.05, y=0.1, width=0.9, height=0.9)

    derived = derive_mark_areas(answer)

    assert derived is not None
    score, comment = derived
    for area in (score, comment):
        assert area.y + area.height <= 1.0
        assert area.x + area.width <= 1.0
        assert area.height > 0


def test_no_answer_box_means_no_derived_area() -> None:
    """Nothing to derive from: inventing a rect would put the score at a
    guessed spot on someone's answer sheet."""
    assert derive_mark_areas(None) is None
    assert derive_mark_areas(NormalizedRect(x=0.1, y=0.1, width=0.0, height=0.2)) is None
    assert derive_mark_areas(NormalizedRect(x=0.1, y=0.1, width=0.2, height=0.0)) is None
