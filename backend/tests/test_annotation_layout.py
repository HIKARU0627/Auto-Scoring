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

    def test_a_box_matches_despite_the_line_break_ocr_leaves_on_its_text(self) -> None:
        """Issue #141: Document AI slices a token's text straight out of the
        page text, so the detected break travels with it. Against the old
        ``box.text == anchor_text`` that trailing newline alone was enough to
        leave a perfectly-read word unplaced -- and in the live run none of
        the fourteen annotations was placed at all."""
        box_rect = _rect(0.1, 0.2, 0.3, 0.1)
        annotation = _annotation(kind=AnnotationKind.CROSS, anchor_text="酸素", rect=None)
        recognition = _recognition(boxes=(BoundingBox(text="酸素\n", rect=box_rect),))

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved == box_rect

    def test_an_anchor_spanning_several_boxes_resolves_to_their_union(self) -> None:
        """An OCR box is one *token*: ``葉緑体で`` arrives as ``葉緑体`` + ``で``, so
        no single box could ever equal an anchor of more than one token."""
        annotation = _annotation(kind=AnnotationKind.CROSS, anchor_text="葉緑体で", rect=None)
        recognition = _recognition(
            boxes=(
                BoundingBox(text="葉緑体", rect=_rect(0.10, 0.20, 0.08, 0.04)),
                BoundingBox(text="で", rect=_rect(0.18, 0.21, 0.04, 0.03)),
            )
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved is not None
        assert resolved.x == pytest.approx(0.10)
        assert resolved.y == pytest.approx(0.20)
        assert resolved.width == pytest.approx(0.12)
        assert resolved.height == pytest.approx(0.04)

    def test_a_full_width_anchor_matches_the_ascii_the_ocr_read(self) -> None:
        box_rect = _rect(0.4, 0.1, 0.05, 0.03)
        annotation = _annotation(kind=AnnotationKind.CIRCLE, anchor_text="\uff41", rect=None)
        recognition = _recognition(boxes=(BoundingBox(text="a\n", rect=box_rect),))

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved == box_rect

    def test_the_shortest_run_containing_the_anchor_wins(self) -> None:
        """A short anchor is contained in many longer runs; the tightest one
        is the only one whose rect is about the words the mark is for."""
        annotation = _annotation(kind=AnnotationKind.CROSS, anchor_text="酸素", rect=None)
        recognition = _recognition(
            boxes=(
                BoundingBox(text="酸", rect=_rect(0.10, 0.20, 0.02, 0.03)),
                BoundingBox(text="素", rect=_rect(0.12, 0.20, 0.02, 0.03)),
                BoundingBox(text="酸素", rect=_rect(0.50, 0.20, 0.04, 0.03)),
            )
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved == _rect(0.50, 0.20, 0.04, 0.03)

    def test_a_run_that_reads_far_more_than_the_anchor_is_refused(self) -> None:
        """The rect drawn is the run's, not the anchor's. Letting a
        one-character anchor match a whole line would put a ``×`` across all
        of it -- Issue #141's own symptom, in miniature."""
        annotation = _annotation(kind=AnnotationKind.CROSS, anchor_text="の", rect=None)
        recognition = _recognition(
            boxes=(BoundingBox(text="光合成は葉緑体で行われる", rect=_rect(0.1, 0.2, 0.8, 0.04)),)
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved is None

    def test_boxes_that_are_not_consecutive_do_not_match(self) -> None:
        """The live run had a model join two different sub-answers into one
        anchor. They are not adjacent on the page, so there is no run
        covering both, and nothing may be drawn from them."""
        annotation = _annotation(kind=AnnotationKind.CROSS, anchor_text="水デンプン", rect=None)
        recognition = _recognition(
            boxes=(
                BoundingBox(text="水\n", rect=_rect(0.10, 0.20, 0.04, 0.03)),
                BoundingBox(text="b\n", rect=_rect(0.10, 0.30, 0.04, 0.03)),
                BoundingBox(text="デンプン", rect=_rect(0.10, 0.40, 0.08, 0.03)),
            )
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(answer_area=None), recognitions=(recognition,)
        )

        assert resolved is None

    @pytest.mark.parametrize(
        "kind",
        [
            AnnotationKind.CIRCLE,
            AnnotationKind.CROSS,
            AnnotationKind.TRIANGLE,
            AnnotationKind.SCORE,
        ],
    )
    def test_no_kind_falls_back_to_score_area_when_its_anchor_matched_nothing(
        self, kind: AnnotationKind
    ) -> None:
        """Issue #141: a ``×`` whose anchor matched nothing used to be drawn at
        ``score_area``. Since Issue #120 that area is a band as tall as the
        answer box, so the live run's output carried a red cross over a
        quarter of the page -- reading as the whole answer struck out, for an
        error in one term of one formula. The position is unknown; nothing on
        the answer may claim otherwise (§12.4)."""
        score_area = _rect(0.8, 0.05, 0.1, 0.05)
        annotation = _annotation(kind=kind, anchor_text="答案に無い語", rect=None)
        recognition = _recognition(
            boxes=(BoundingBox(text="別の語", rect=_rect(0.1, 0.1, 0.1, 0.1)),)
        )

        resolved = resolve_annotation_rect(
            annotation, question=_question(score_area=score_area), recognitions=(recognition,)
        )

        assert resolved is None

    def test_an_explicit_rect_still_places_a_fixed_position_kind(self) -> None:
        """Dropping the fallback must not stop a mark whose position *is*
        known from being drawn: a reviewer who placed a ○ by hand
        (`review/edit`) supplies a rect, and it is used as-is."""
        rect = _rect(0.2, 0.3, 0.1, 0.05)
        annotation = _annotation(kind=AnnotationKind.CIRCLE, rect=rect, anchor_text=None)

        resolved = resolve_annotation_rect(
            annotation,
            question=_question(score_area=_rect(0.8, 0.05, 0.1, 0.05)),
            recognitions=(),
        )

        assert resolved == rect

    def test_an_annotation_with_nothing_resolvable_returns_none(self) -> None:
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
