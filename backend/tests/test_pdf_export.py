"""Unit tests for `domain.pdf_export` (Issue #23)."""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from datetime import datetime, timedelta

import pytest

from auto_scoring.adapters.pdf.pdfium_pypdf_engine import (
    _LINE_HEIGHT_FACTOR,
    _MIN_FONT_SIZE_PT,
)
from auto_scoring.domain.criteria_extraction import CriteriaDraft, CriteriaQuestion
from auto_scoring.domain.models import (
    Annotation,
    AnnotationKind,
    BoundingBox,
    Export,
    GradeResult,
    GradingSource,
    NormalizedRect,
    Question,
    QuestionReviewVersion,
    RecognitionResult,
    Review,
    ReviewAction,
    Score,
)
from auto_scoring.domain.pdf_engine import AnnotationMark
from auto_scoring.domain.pdf_export import (
    _NOTE_PAGE_LINE_HEIGHT_PT,
    _NOTE_PAGE_MARGIN,
    NoteEntry,
    ReexportDecision,
    ScorePlacementTarget,
    _wrapped_line_count,
    build_export_marks,
    build_note_pages,
    decide_reexport,
    fallback_score_areas,
    note_page_heading,
    review_version_snapshot,
    score_placements,
    unconfirmed_question_ids,
    unplaceable_question_ids,
)
from auto_scoring.domain.profile import NormalizedBBox, Region, RegionKind
from auto_scoring.domain.test_registration import build_questions_and_rubrics

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


def _grade(**overrides: object) -> GradeResult:
    values: dict[str, object] = {
        "id": "grade-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "source": GradingSource.AI,
        "score": Score(awarded=4, maximum=5),
        "confidence": 0.9,
        "created_at": _NOW,
    }
    values.update(overrides)
    return GradeResult(**values)  # type: ignore[arg-type]


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


def _review(**overrides: object) -> Review:
    values: dict[str, object] = {
        "id": "review-1",
        "submission_id": "sub-1",
        "question_id": "q-1",
        "action": ReviewAction.APPROVED,
        "version": 1,
        "ai_grade_result_id": "grade-1",
        "created_at": _NOW,
    }
    values.update(overrides)
    return Review(**values)  # type: ignore[arg-type]


class TestUnconfirmedQuestionIds:
    def test_a_question_with_no_review_history_is_unconfirmed(self) -> None:
        assert unconfirmed_question_ids(["q-1"], {}) == ["q-1"]

    def test_an_approved_question_is_confirmed(self) -> None:
        reviews = {"q-1": [_review(action=ReviewAction.APPROVED)]}
        assert unconfirmed_question_ids(["q-1"], reviews) == []

    def test_a_rejected_question_is_unconfirmed(self) -> None:
        reviews = {
            "q-1": [
                Review(
                    id="r1",
                    submission_id="sub-1",
                    question_id="q-1",
                    action=ReviewAction.REJECTED,
                    version=1,
                    created_at=_NOW,
                )
            ]
        }
        assert unconfirmed_question_ids(["q-1"], reviews) == ["q-1"]

    def test_an_undone_approval_reverts_to_unconfirmed(self) -> None:
        approved = _review(id="r1", version=1)
        undone = Review(
            id="r2",
            submission_id="sub-1",
            question_id="q-1",
            action=ReviewAction.UNDONE,
            version=2,
            undone_review_id="r1",
            created_at=_NOW,
        )
        reviews = {"q-1": [approved, undone]}
        assert unconfirmed_question_ids(["q-1"], reviews) == ["q-1"]

    def test_only_the_unconfirmed_ones_are_named(self) -> None:
        reviews = {"q-1": [_review(id="r1")]}
        assert unconfirmed_question_ids(["q-1", "q-2"], reviews) == ["q-2"]


class TestReviewVersionSnapshot:
    def test_version_is_the_history_length_sorted_by_question_id(self) -> None:
        reviews = {
            "q-2": [_review(id="r1", question_id="q-2")],
            "q-1": [
                _review(id="r2", question_id="q-1", version=1),
                _review(
                    id="r3",
                    question_id="q-1",
                    version=2,
                    action=ReviewAction.MODIFIED,
                    human_grade_result_id="grade-human",
                ),
            ],
        }

        snapshot = review_version_snapshot(["q-1", "q-2"], reviews)

        assert snapshot == (
            QuestionReviewVersion(question_id="q-1", version=2),
            QuestionReviewVersion(question_id="q-2", version=1),
        )


class TestDecideReexport:
    def test_accepts_a_new_export_when_none_exists_yet(self) -> None:
        snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        assert decide_reexport(None, snapshot) is ReexportDecision.ACCEPT_NEW

    def test_reuses_the_existing_export_when_the_snapshot_is_unchanged(self) -> None:
        snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        previous = Export(
            id="export-1",
            submission_id="sub-1",
            job_id="job-1",
            file_path="exports/a_corrected.pdf",
            file_sha256="0" * 64,
            created_at=_NOW,
            review_versions=snapshot,
        )
        assert decide_reexport(previous, snapshot) is ReexportDecision.REUSE_EXISTING

    def test_supersedes_the_existing_export_once_a_question_s_review_history_advances(
        self,
    ) -> None:
        previous_snapshot = (QuestionReviewVersion(question_id="q-1", version=1),)
        current_snapshot = (QuestionReviewVersion(question_id="q-1", version=2),)
        previous = Export(
            id="export-1",
            submission_id="sub-1",
            job_id="job-1",
            file_path="exports/a_corrected.pdf",
            file_sha256="0" * 64,
            created_at=_NOW,
            review_versions=previous_snapshot,
        )
        assert (
            decide_reexport(previous, current_snapshot) is ReexportDecision.ACCEPT_NEW_SUPERSEDING
        )


class TestBuildExportMarks:
    def test_score_kind_draws_the_confirmed_grade_s_score_not_the_annotation_s_own_comment(
        self,
    ) -> None:
        grade = _grade(score=Score(awarded=3, maximum=5))
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.SCORE,
            comment="stale AI label: 4/5",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(score_area=NormalizedRect(x=0.8, y=0.0, width=0.2, height=0.05)),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        ).marks

        assert len(marks) == 1
        assert marks[0].text == "3/5"

    def test_the_score_is_drawn_even_though_no_annotation_asked_for_it(self) -> None:
        """Issue #120: nothing in this repository ever creates a `SCORE`-kind
        `Annotation` -- only these tests do. The score reached the page only
        if the AI happened to propose one, and in the live run none did, so
        every exported PDF came out with no score on it. The confirmed grade
        is the source of truth for that number (§2.1 of docs/pdf-export.md),
        and it is now what puts the mark there, not a proposal that may never
        arrive.
        """
        score_area = NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05)

        marks = build_export_marks(
            question=_question(score_area=score_area),
            grade=_grade(score=Score(awarded=3, maximum=5)),
            annotations=[],
            recognitions=[],
        ).marks

        assert [(mark.kind, mark.rect, mark.text) for mark in marks] == [
            (AnnotationKind.SCORE, score_area, "3/5")
        ]

    def test_an_ai_proposed_score_annotation_does_not_double_the_score_mark(self) -> None:
        """Both would carry the same text at the same rect, drawn on top of
        each other."""
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.SCORE,
            comment="stale AI label: 4/5",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(score_area=NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05)),
            grade=_grade(score=Score(awarded=3, maximum=5)),
            annotations=[annotation],
            recognitions=[],
        ).marks

        assert [mark.kind for mark in marks] == [AnnotationKind.SCORE]
        assert marks[0].text == "3/5"

    def test_no_score_area_draws_no_score_rather_than_guessing_where_it_goes(self) -> None:
        """`unplaceable_question_ids` is what stops this reaching an export at
        all; if one ever does, the honest outcome is a missing mark, not a
        mark at a guessed spot on someone's answer sheet."""
        marks = build_export_marks(
            question=_question(), grade=_grade(), annotations=[], recognitions=[]
        ).marks

        assert marks == ()

    def test_comment_kind_draws_the_annotation_s_own_comment_text(self) -> None:
        grade = _grade()
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.COMMENT,
            comment="理由の説明が不足しています。",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        ).marks

        assert len(marks) == 1
        assert marks[0].text == "理由の説明が不足しています。"

    def test_falls_back_to_comment_area_when_the_mark_has_no_other_resolvable_position(
        self,
    ) -> None:
        grade = _grade()
        comment_area = NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="コメント",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=comment_area),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        ).marks

        assert marks[0].rect == comment_area

    def test_multiple_notes_get_their_own_slice_of_the_band_instead_of_overlapping(
        self,
    ) -> None:
        """P2 review, round 5: two annotations whose comments both land in the
        same ``comment_area`` must not be drawn on top of one another --
        `PdfEngine.render_annotations` draws each mark independently from its
        rect's own top-left corner. Issue #141 keeps that property by giving
        each note its own slice rather than by merging them into one string:
        a single long comment can no longer push the others out of the band."""
        grade = _grade()
        comment_area = NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)
        first = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="誤字があります。",
            created_at=_NOW,
        )
        second = Annotation(
            id="a2",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="根拠が不足しています。",
            created_at=_NOW,
        )

        marks = build_export_marks(
            question=_question(comment_area=comment_area),
            grade=grade,
            annotations=[first, second],
            recognitions=[],
        ).marks

        notes = [mark for mark in marks if mark.kind is AnnotationKind.COMMENT]
        assert [note.text for note in notes] == ["誤字があります。", "根拠が不足しています。"]
        assert notes[0].rect.y + notes[0].rect.height == pytest.approx(notes[1].rect.y)
        assert notes[0].rect.height == pytest.approx(comment_area.height / 2)

    def test_a_shape_annotation_s_comment_reaches_the_page_as_a_band_note(self) -> None:
        """Issue #141: the live run produced twelve annotations and not one
        character of their comments was drawn. `PdfEngine.render_annotations`
        renders ``text`` only for SCORE/COMMENT marks, so a CROSS carrying an
        explanation had it silently dropped by the engine."""
        grade = _grade()
        box = NormalizedRect(x=0.2, y=0.2, width=0.1, height=0.05)
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.CROSS,
            anchor_text="葉緑体で",
            comment="記述が不完全です。",
            created_at=_NOW,
        )
        recognition = _recognition(boxes=(BoundingBox(text="葉緑体で", rect=box),))

        marks = build_export_marks(
            question=_question(
                answer_area=None,
                comment_area=NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1),
            ),
            grade=grade,
            annotations=[annotation],
            recognitions=[recognition],
        ).marks

        shape = next(mark for mark in marks if mark.kind is AnnotationKind.CROSS)
        note = next(mark for mark in marks if mark.kind is AnnotationKind.COMMENT)
        assert shape.rect == box
        # The engine would throw a shape's text away; carrying one would be a
        # lie about what reaches the page.
        assert shape.text is None
        assert note.text == "× 記述が不完全です。"

    def test_a_placed_comment_annotation_is_written_in_the_band_not_over_the_answer(
        self,
    ) -> None:
        """A COMMENT is prose, not a mark: drawing it at the anchored word's
        own rect put it across the student's writing (Issue #141)."""
        grade = _grade()
        box = NormalizedRect(x=0.2, y=0.2, width=0.1, height=0.05)
        comment_area = NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1)
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.COMMENT,
            anchor_text="行く",
            comment="時制を確認してください。",
            created_at=_NOW,
        )
        recognition = _recognition(boxes=(BoundingBox(text="行く", rect=box),))

        marks = build_export_marks(
            question=_question(answer_area=None, comment_area=comment_area),
            grade=grade,
            annotations=[annotation],
            recognitions=[recognition],
        ).marks

        notes = [mark for mark in marks if mark.kind is AnnotationKind.COMMENT]
        assert [note.rect for note in notes] == [comment_area]

    def test_a_shape_annotation_with_no_comment_contributes_no_band_note(self) -> None:
        grade = _grade()
        box = NormalizedRect(x=0.2, y=0.2, width=0.1, height=0.05)
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.CIRCLE,
            anchor_text="行く",
            created_at=_NOW,
        )
        recognition = _recognition(boxes=(BoundingBox(text="行く", rect=box),))

        marks = build_export_marks(
            question=_question(
                answer_area=None,
                comment_area=NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.1),
            ),
            grade=grade,
            annotations=[annotation],
            recognitions=[recognition],
        ).marks

        assert [mark.kind for mark in marks] == [AnnotationKind.CIRCLE]

    def test_notes_that_do_not_fit_the_band_are_counted_rather_than_dropped(self) -> None:
        """Issue #141 condition: the overflow behaviour is a decision, not an
        accident of whatever the renderer happened to clip. Issue #121 is the
        precedent -- a correct grade thrown away over a long comment, with the
        run still reporting success."""
        grade = _grade()
        # 0.03 tall fits two `_MIN_NOTE_HEIGHT` (0.012) slices, not four.
        comment_area = NormalizedRect(x=0.0, y=0.9, width=1.0, height=0.03)
        annotations = [
            Annotation(
                id=f"a{index}",
                submission_id="sub-1",
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.COMMENT,
                comment=f"コメント{index}",
                created_at=_NOW,
            )
            for index in range(4)
        ]

        marks = build_export_marks(
            question=_question(comment_area=comment_area),
            grade=grade,
            annotations=annotations,
            recognitions=[],
        ).marks

        notes = [mark for mark in marks if mark.kind is AnnotationKind.COMMENT]
        assert [note.text for note in notes] == ["コメント0", "ほか3件は余白に収まらず未表示"]

    def test_a_band_too_short_for_even_one_note_still_reports_every_missing_note(
        self,
    ) -> None:
        grade = _grade()
        comment_area = NormalizedRect(x=0.0, y=0.99, width=1.0, height=0.005)
        annotations = [
            Annotation(
                id=f"a{index}",
                submission_id="sub-1",
                question_id="q-1",
                source=GradingSource.AI,
                kind=AnnotationKind.COMMENT,
                comment=f"コメント{index}",
                created_at=_NOW,
            )
            for index in range(3)
        ]

        marks = build_export_marks(
            question=_question(comment_area=comment_area),
            grade=grade,
            annotations=annotations,
            recognitions=[],
        ).marks

        notes = [mark for mark in marks if mark.kind is AnnotationKind.COMMENT]
        assert [note.text for note in notes] == ["ほか3件は余白に収まらず未表示"]

    def test_a_note_with_no_band_to_go_in_is_handed_back_rather_than_dropped(
        self,
    ) -> None:
        """Issue #161: a question with no ``comment_area`` -- since #161 that
        is every question registered by detection -- draws nothing on the
        answer sheet and hands its notes to the caller for an appended note
        page instead. Before #161 this same case silently returned no marks
        at all, and the comment was lost with the export still reporting
        success (Issue #121's shape).
        """
        grade = _grade()
        annotation = Annotation(
            id="a1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.HUMAN,
            kind=AnnotationKind.COMMENT,
            comment="コメント",
            created_at=_NOW,
        )

        exported = build_export_marks(
            # With an answer box, without a band. That is what every question
            # registered by detection looks like since Issue #161, and it is
            # the combination the assertion below is about: an answer box is
            # a rect something *could* be drawn on, so "nothing was drawn"
            # says something. Against a question with no coordinates at all
            # it would pass no matter what this function did.
            question=_question(
                comment_area=None,
                answer_area=NormalizedRect(x=0.1, y=0.2, width=0.8, height=0.3),
            ),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert exported.marks == (), "nothing may be drawn on the answer sheet"
        assert exported.unplaced_notes == ("コメント",)

    def test_cross_line_underline_draws_per_line_marks_on_answer_sheet(
        self,
    ) -> None:
        """Issue #256: UNDERLINE spanning a line break draws one mark per line on
        the answer sheet; the comment is placed without the unplaced suffix."""
        grade = _grade()
        annotation = Annotation(
            id="a-1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.UNDERLINE,
            anchor_text="春はあけぼ",
            comment="要確認の表現",
            created_at=_NOW,
        )
        recognition = RecognitionResult(
            id="rec-1",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            text="",
            confidence=0.9,
            created_at=_NOW,
            boxes=(
                BoundingBox(
                    text="春", rect=NormalizedRect(x=0.86, y=0.10, width=0.06, height=0.04)
                ),
                BoundingBox(
                    text="は", rect=NormalizedRect(x=0.92, y=0.10, width=0.06, height=0.04)
                ),
                BoundingBox(
                    text="あ", rect=NormalizedRect(x=0.01, y=0.30, width=0.06, height=0.04)
                ),
                BoundingBox(
                    text="け", rect=NormalizedRect(x=0.07, y=0.30, width=0.06, height=0.04)
                ),
                BoundingBox(
                    text="ぼ", rect=NormalizedRect(x=0.13, y=0.30, width=0.06, height=0.04)
                ),
            ),
        )

        exported = build_export_marks(
            question=_question(
                score_area=None,
                comment_area=None,
                answer_area=NormalizedRect(x=0.1, y=0.2, width=0.8, height=0.3),
            ),
            grade=grade,
            annotations=[annotation],
            recognitions=[recognition],
        )

        assert len(exported.marks) == 2
        assert all(mark.kind is AnnotationKind.UNDERLINE for mark in exported.marks)
        assert all(mark.rect.width < 0.95 for mark in exported.marks)
        assert exported.unplaced_notes == ("＿ 要確認の表現",)

    def test_only_annotations_and_recognitions_from_the_grade_s_own_attempt_are_used(
        self,
    ) -> None:
        grade = _grade(created_at=_NOW + timedelta(seconds=10))
        stale_annotation = Annotation(
            id="a-stale",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.UNDERLINE,
            anchor_text="行く",
            created_at=_NOW,
        )
        current_annotation = Annotation(
            id="a-current",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            kind=AnnotationKind.UNDERLINE,
            anchor_text="行く",
            created_at=_NOW + timedelta(seconds=10),
        )
        stale_recognition = RecognitionResult(
            id="rec-stale",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            text="",
            confidence=0.9,
            created_at=_NOW,
            boxes=(
                BoundingBox(text="行く", rect=NormalizedRect(x=0.0, y=0.0, width=0.1, height=0.1)),
            ),
        )
        current_recognition = RecognitionResult(
            id="rec-current",
            submission_id="sub-1",
            question_id="q-1",
            source=GradingSource.AI,
            text="",
            confidence=0.9,
            created_at=_NOW + timedelta(seconds=10),
            boxes=(
                BoundingBox(text="行く", rect=NormalizedRect(x=0.5, y=0.5, width=0.1, height=0.1)),
            ),
        )

        marks = build_export_marks(
            question=_question(),
            grade=grade,
            annotations=[stale_annotation, current_annotation],
            recognitions=[stale_recognition, current_recognition],
        ).marks

        assert len(marks) == 1
        assert marks[0].rect == NormalizedRect(x=0.5, y=0.5, width=0.1, height=0.1)


class TestFallbackScoreAreas:
    """Issue #150: `score_area` の無い設問にも点数を書く場所を与える。"""

    def test_a_question_with_no_score_area_gets_a_margin_slot(self) -> None:
        areas = fallback_score_areas([_question(id="q-1")])

        assert set(areas) == {"q-1"}
        slot = areas["q-1"]
        # 実データ計測で空だと確かめた左余白の帯の中に入っていること
        # (`_FALLBACK_SCORE_STRIP`)。**幅と位置まで見る。** 「何か rect が
        # 返った」だけでは、答案の真ん中に置いても緑になる。
        assert slot.x + slot.width <= 0.035
        assert slot.y >= 0.05
        assert slot.y + slot.height == pytest.approx(0.95)

    def test_a_question_that_has_its_own_score_area_gets_no_slot(self) -> None:
        placeable = _question(score_area=NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05))

        assert fallback_score_areas([placeable]) == {}

    def test_two_questions_on_one_page_get_slots_that_do_not_overlap(self) -> None:
        """スライスを配り分けているか。同じ矩形を2つに渡すと、エンジンは両方を
        その左上から描くので重なって両方読めなくなる (Issue #141 の P2 review
        が注釈で踏んだのと同じ失敗)。"""
        areas = fallback_score_areas([_question(id="q-1"), _question(id="q-2")])

        first, second = areas["q-1"], areas["q-2"]
        assert first.y + first.height <= second.y

    def test_slots_are_allocated_per_page(self) -> None:
        """ページごとに帯を持つ。ページをまたいで詰めると、2ページ目の設問が
        1ページ目の帯の下の方に置かれ、**別のページの余白に書かれる。**"""
        areas = fallback_score_areas([_question(id="q-1", page=1), _question(id="q-2", page=2)])

        assert areas["q-1"] == areas["q-2"]


class TestUnplaceableQuestionIds:
    """Issue #120 acceptance 3: 書く場所が決まらないときに、黙って空の PDF を
    出さないこと。出力前に分かること.

    Issue #150 で意味が狭まった。`score_area` が無いだけでは拒まない (余白帯に
    書く)。**帯にも収まらないときだけ**拒む。"""

    def test_a_question_with_no_score_area_is_no_longer_refused(self) -> None:
        """#150 の本体。実機再検証 #4 で7教科中4教科が出力できなかったのは、
        回答欄が検出できなかった設問が1つでもあると、**全問確定済みでも**答案
        まるごと拒まれていたからである。"""
        placeable = _question(
            id="q-1", score_area=NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05)
        )
        no_area = _question(id="q-2")

        assert unplaceable_question_ids([placeable, no_area]) == []

    def test_a_question_that_can_be_written_on_is_not_named(self) -> None:
        assert (
            unplaceable_question_ids(
                [_question(score_area=NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05))]
            )
            == []
        )

    def test_questions_beyond_the_strip_s_capacity_are_still_named(self) -> None:
        """拒否経路が生きていることを**肯定形で**先に言う。ここが死ぬと、読めない
        大きさの点数を描いて成功を返す方に倒れ、しかもテストは緑のままになる。

        `_FALLBACK_SCORE_STRIP` は高さ 0.90、1件あたり最低
        `_MIN_FALLBACK_SCORE_HEIGHT` (0.048) なので容量は18件。19件目から溢れる。
        """
        crowded = [_question(id=f"q-{index}") for index in range(19)]

        named = unplaceable_question_ids(crowded)

        assert len(fallback_score_areas(crowded)) == 18
        assert named == ["q-18"]


class TestScorePlacements:
    """Issue #406: the review screen draws the score where the *export* draws
    it. `score_placements` is the one judgment both consult, so the screen
    never has to re-derive it (and cannot say "here" when the export refuses).

    The three cases are asserted against the two functions the export itself
    uses, so a change to either one that this composition does not follow is a
    red test rather than a screen that disagrees with the paper.
    """

    def test_a_question_with_its_own_score_area_is_placed_on_it(self) -> None:
        area = NormalizedRect(x=0.8, y=0.6, width=0.2, height=0.05)

        placements = score_placements([_question(id="q-1", score_area=area)])

        assert placements["q-1"].target is ScorePlacementTarget.OWN
        assert placements["q-1"].rect == area

    def test_a_question_without_an_area_is_placed_in_the_margin_strip(self) -> None:
        question = _question(id="q-1")

        placements = score_placements([question])

        assert placements["q-1"].target is ScorePlacementTarget.MARGIN
        # The very slot the export's own allocation returns, not a copy of it.
        assert placements["q-1"].rect == fallback_score_areas([question])["q-1"]

    def test_a_question_the_export_refuses_is_placed_nowhere(self) -> None:
        crowded = [_question(id=f"q-{index}") for index in range(19)]

        placements = score_placements(crowded)

        refused = unplaceable_question_ids(crowded)
        assert refused == ["q-18"]
        assert placements["q-18"].target is ScorePlacementTarget.NONE
        assert placements["q-18"].rect is None
        # Every question the export *would* draw keeps a destination: the
        # screen must not lose the other 18 to the one it refuses.
        assert all(
            placements[question.id].target is ScorePlacementTarget.MARGIN
            for question in crowded
            if question.id != "q-18"
        )

    def test_two_margin_questions_get_their_own_slots(self) -> None:
        """The screen draws from the same slots the export does, so the
        no-two-on-one-rect rule has to survive this composition too."""
        placements = score_placements([_question(id="q-1"), _question(id="q-2")])

        first = placements["q-1"].rect
        second = placements["q-2"].rect
        assert first is not None and second is not None
        assert first.y + first.height <= second.y


class TestTheScoreNeverLandsOnTheAnswer:
    """Issue #159: 得点欄が生徒の筆跡の上に印字される。

    実機再検証 #5 の計測 —— 回答欄を持つ16設問のうち **14件**で、#120 が導出した
    「回答欄の真下の帯」が元答案のインクの上に載っていた（白紙は 0.0015%、最悪の
    設問は 16.5%）。うち **6件**は**次の設問の回答欄の中**に入っていた。
    「回答欄の真下」が空なのは紙がそこに何も置いていないときだけで、複数設問の
    ある紙はそこに次の設問を置く。**縦書き固有ではなかった。**

    ここは登録経路（`build_questions_and_rubrics`）から出力時の解決
    （`fallback_score_areas`）まで通して測る。`Question` を手で組み立てて
    `score_area=None` を置いたのでは、**製品が到達しない状態をフィクスチャで
    作ってテストが自分に同意する**だけになる（`test_e2e_intake_to_export` が
    同じ罠を明記している）。
    """

    @staticmethod
    def _questions(*boxes: NormalizedBBox) -> list[Question]:
        """`boxes` を回答欄に持つ設問群を、実際の登録経路で作る。

        #101 → #103 → #105 の経路が確定するのは設問と回答欄だけで、
        `SCORE`/`ANNOTATION_AREA` region は出てこない。
        """
        regions: list[Region] = []
        for index, box in enumerate(boxes):
            label = str(index + 1)
            regions.append(
                Region(
                    region_id=f"question-{label}",
                    kind=RegionKind.QUESTION,
                    page_index=0,
                    bbox=box,
                    label=label,
                    confirmed=True,
                    text=f"問{label}",
                )
            )
            regions.append(
                Region(
                    region_id=f"answer_area-{label}",
                    kind=RegionKind.ANSWER_AREA,
                    page_index=0,
                    bbox=box,
                    label=label,
                    confirmed=True,
                )
            )
        draft = CriteriaDraft(
            test_id="test-1",
            questions=tuple(
                CriteriaQuestion(number=str(index + 1), points=5) for index in range(len(boxes))
            ),
        )
        questions, _ = build_questions_and_rubrics("test-1", regions, criteria=draft)
        return questions

    @staticmethod
    def _score_rect(question: Question, questions: list[Question]) -> NormalizedRect:
        """その設問の点数が**実際に描かれる**矩形。

        自前の `score_area` があればそれ、無ければ出力時に割り当てられる余白
        スロット（`build_export_marks` が使う順序と同じ）。**どちらを通ったかを
        問わない**のは、#159 が言っているのが「点数がどこに落ちるか」であって
        「どの関数が返したか」ではないからである。片方だけを見るテストは、
        導出が復活したときに「スロットが無い」と落ちて、**重なっていること自体は
        一度も評価しない。**
        """
        if question.score_area is not None:
            return question.score_area
        slot = fallback_score_areas(questions).get(question.id)
        assert slot is not None, f"{question.id} は点数を書く場所が無い"
        return slot

    def test_the_score_never_overlaps_any_answer_box_on_its_page(self) -> None:
        """6/16 が次の設問の回答欄に入っていた件。**縦に積んだ回答欄**という、
        実機で最も多かった形で測る。直す前は1問目の点数が2問目の回答欄に
        丸ごと入る。"""
        stacked = self._questions(
            NormalizedBBox(x0=0.08, y0=0.20, x1=0.92, y1=0.45),
            NormalizedBBox(x0=0.08, y0=0.45, x1=0.92, y1=0.70),
            NormalizedBBox(x0=0.08, y0=0.70, x1=0.92, y1=0.95),
        )
        answer_boxes = [question.answer_area for question in stacked]
        assert all(box is not None for box in answer_boxes), "回答欄が確定していない"

        for question in stacked:
            score = self._score_rect(question, stacked)
            for index, box in enumerate(answer_boxes):
                assert box is not None
                assert _overlap(score, box) == 0.0, (
                    f"{question.id} の点数が設問{index + 1}の回答欄に重なっている"
                )

    def test_the_score_of_a_vertical_answer_column_goes_to_the_margin(self) -> None:
        """縦書きの回答欄（縦に長く横に狭い一列）。#159 が報告した形。

        一列しかないので**矩形どうしは交差しない** —— 実機で重なっていたのは
        「真下の帯」が同じマス目の続き、つまり紙のインクだったからで、それは
        domain からは見えない。ここで固定できるのは「点数の位置が回答欄の形から
        導かれていないこと」の方である: 実測で空だと確かめた左余白帯の中に入る。
        """
        (question,) = self._questions(NormalizedBBox(x0=0.797, y0=0.222, x1=0.843, y1=0.457))
        score = self._score_rect(question, [question])

        assert question.answer_area is not None
        assert score.x + score.width <= 0.035, "点数が左余白帯の外にある"
        assert score.x + score.width <= question.answer_area.x, "点数が回答欄より右にある"

    def test_the_score_never_breaks_the_minimum_font_size(self) -> None:
        """Issue #133: 縦書きで導出された得点欄が最小フォントサイズを下回る。

        実機の該当設問は `score_area.width = 0.0031`（A4縦で約1.8pt）で、6pt の
        全角1文字すら幅に入らない。`_draw_text` はフォントを下限で止めるので、
        点数は1行1文字に潰れる。

        余白帯のスロットは幅も高さも固定なので、**回答欄の形に関係なく**下限を
        割らない。#159 の変更で自動的にそうなるが、「たまたま」ではないことを
        ここで固定する —— `_MIN_FONT_SIZE_PT` を上げれば、このテストが先に落ちる。
        """
        (question,) = self._questions(
            # #133 を起こす形: 幅がページの1.6%しかない縦一列。
            NormalizedBBox(x0=0.638, y0=0.236, x1=0.654, y1=0.960)
        )
        score = self._score_rect(question, [question])

        # このプロジェクトが扱う最小のページ = A4横の短辺 (595pt)。
        # 正規化された幅・高さはそこで最も小さい実寸になる。
        shortest_page_pt = 595.0
        assert score.width * shortest_page_pt >= _MIN_FONT_SIZE_PT, "全角1文字が幅に入らない"
        assert score.height * shortest_page_pt >= _MIN_FONT_SIZE_PT * _LINE_HEIGHT_FACTOR, (
            "1行が高さに入らない"
        )


def _overlap(first: NormalizedRect, second: NormalizedRect) -> float:
    """2つの矩形が重なっている面積（正規化）。"""
    width = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
    height = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
    return max(0.0, width) * max(0.0, height)


# --------------------------------------------------------------------------- #
# build_note_pages (Issue #161)
# --------------------------------------------------------------------------- #

#: A4 portrait, the commonest of the real answer sheets.
_A4_WIDTH_PT = 595.0
_A4_HEIGHT_PT = 842.0

_HEADING = note_page_heading(test_name="日本史添削", submission_id="sub-1")


def _note_pages(
    entries: Sequence[NoteEntry],
    *,
    width: float = _A4_WIDTH_PT,
    height: float = _A4_HEIGHT_PT,
) -> list[tuple[AnnotationMark, ...]]:
    return build_note_pages(entries, heading=_HEADING, page_width_pt=width, page_height_pt=height)


def _entry(text: str, *, page: int = 1, number: str = "問1") -> NoteEntry:
    return NoteEntry(page=page, question_number=number, text=text)


def _rects_intersect(first: NormalizedRect, second: NormalizedRect) -> bool:
    """Whether two page-normalized rects share any area at all.

    Touching edges are not an intersection: `_note_page_marks` stacks each
    line's rect directly onto the previous one's bottom edge, which is
    exactly right and must not read as an overlap.
    """
    return (
        first.x < second.x + second.width
        and second.x < first.x + first.width
        and first.y < second.y + second.height
        and second.y < first.y + first.height
    )


class TestBuildNotePages:
    def test_an_answer_with_no_notes_gets_no_note_page(self) -> None:
        """Every export appending a near-empty sheet would cost one sheet of
        paper per submission for nothing -- forty answers, forty sheets."""
        assert _note_pages([]) == []

    def test_every_note_page_names_the_test_and_the_answer_it_belongs_to(self) -> None:
        """A note page is a physically separate sheet. Staples come out and
        printers collate wrongly, so each sheet has to be identifiable on its
        own -- not only the first one.
        """
        pages = _note_pages([_entry("コメント" * 20) for _ in range(200)])

        assert len(pages) > 1, "the fixture was meant to overflow onto a second page"
        for page in pages:
            assert page[0].text == _HEADING

    def test_the_heading_carries_no_personal_data(self) -> None:
        """The answer sheet may print a student's name; this sheet does not
        reprint it, and never names the uploaded file (free text a user can
        type anything into). Only the test name and the opaque submission id
        (`AGENTS.md` "Security").
        """
        heading = note_page_heading(test_name="現代文添削", submission_id="abc123")

        assert "現代文添削" in heading
        assert "abc123" in heading

    def test_a_note_line_names_the_page_and_question_it_is_about(self) -> None:
        """The cost of moving the notes off the answer is that the shape and
        the sentence about it are no longer side by side. This is what pays
        it back: the reference leads every line.
        """
        (page,) = _note_pages([_entry("説明が不足しています。", page=2, number="問3")])

        (line,) = [mark for mark in page if mark.text != _HEADING]
        assert line.text == "第2頁 問3 説明が不足しています。"
        assert line.text.startswith("第2頁 問3"), "the reference must lead, not trail"

    def test_notes_that_do_not_fit_one_page_start_another_rather_than_being_cut(self) -> None:
        """Issue #121 threw a confirmed grade away over a long comment and
        reported success. The same shape is available here -- keep the notes
        that fit, drop the rest, hand back a plausible-looking page -- so
        this fixes the count: every note is on some page, whole.
        """
        entries = [_entry(f"コメント{index:03d}" + "あ" * 40) for index in range(120)]

        pages = _note_pages(entries)

        assert len(pages) > 1
        drawn = [mark.text for page in pages for mark in page if mark.text != _HEADING]
        for entry in entries:
            assert f"第1頁 問1 {entry.text}" in drawn

    def test_every_note_gets_room_for_its_own_longest_possible_wrap(self) -> None:
        """The promise that nothing is ellipsis-truncated rests entirely on
        each rect being at least as tall as the note's worst-case wrap
        (`_chars_per_line`). Checked here in points, against the same 12pt
        line box `adapters.pdf.pdfium_pypdf_engine._draw_text` is handed.
        """
        entries = [_entry("あ" * length) for length in (1, 40, 119)]

        (page,) = _note_pages(entries)

        usable_width_pt = _A4_WIDTH_PT * (1.0 - 2.0 * _NOTE_PAGE_MARGIN)
        for mark in page:
            needed = _wrapped_line_count(mark.text or "", usable_width_pt)
            room_pt = mark.rect.height * _A4_HEIGHT_PT
            assert room_pt >= needed * _NOTE_PAGE_LINE_HEIGHT_PT

    def test_no_two_marks_on_a_note_page_overlap(self) -> None:
        """Marks are drawn independently from their own top-left corner, so
        two rects that intersect are two blocks of prose printed over each
        other -- both illegible, export still reporting success (the same
        failure `_stacked_rects` exists to prevent on the answer sheet).
        """
        (page,) = _note_pages([_entry("あ" * length) for length in (10, 80, 119, 5)])

        for first, second in itertools.combinations(page, 2):
            assert not _rects_intersect(first.rect, second.rect), (
                f"{first.text!r} and {second.text!r} were drawn on top of each other"
            )

    def test_every_mark_stays_inside_the_page(self) -> None:
        """A rect running past the bottom edge is a note nobody will ever
        read, and it is silent -- the export still succeeds.
        """
        pages = _note_pages([_entry("あ" * 100) for _ in range(300)])

        for page in pages:
            for mark in page:
                assert mark.rect.y >= 0.0
                assert mark.rect.y + mark.rect.height <= 1.0
                assert mark.rect.x + mark.rect.width <= 1.0

    def test_a_landscape_answer_gets_landscape_notes(self) -> None:
        """The wider sheet wraps the same note into fewer lines. Sizing from
        the answer rather than a fixed A4 is what keeps the printed result
        one uniform stack of paper.
        """
        entry = _entry("あ" * 119)

        (portrait,) = _note_pages([entry])
        (landscape,) = _note_pages([entry], width=_A4_HEIGHT_PT, height=_A4_WIDTH_PT)

        assert landscape[-1].rect.height * _A4_WIDTH_PT < portrait[-1].rect.height * _A4_HEIGHT_PT

    def test_a_note_too_long_for_a_whole_page_is_split_across_pages_not_cut(self) -> None:
        """Unreachable on a real answer sheet (`models.MAX_COMMENT_CHARS`
        caps a note at four A4 lines against about sixty per page), but the
        alternative if it ever happens is the engine's ellipsis eating the
        end of a sentence with nothing to say it did.
        """
        pages = _note_pages([_entry("あ" * 400)], width=200.0, height=200.0)

        assert len(pages) > 1
        rebuilt = "".join(
            mark.text or "" for page in pages for mark in page if mark.text != _HEADING
        )
        assert rebuilt == "第1頁 問1 " + "あ" * 400
