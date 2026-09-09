"""Unit tests for `domain.pdf_export` (Issue #23)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

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
from auto_scoring.domain.pdf_export import (
    ReexportDecision,
    build_export_marks,
    decide_reexport,
    fallback_score_areas,
    review_version_snapshot,
    unconfirmed_question_ids,
    unplaceable_question_ids,
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
        )

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
        )

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
        )

        assert [mark.kind for mark in marks] == [AnnotationKind.SCORE]
        assert marks[0].text == "3/5"

    def test_no_score_area_draws_no_score_rather_than_guessing_where_it_goes(self) -> None:
        """`unplaceable_question_ids` is what stops this reaching an export at
        all; if one ever does, the honest outcome is a missing mark, not a
        mark at a guessed spot on someone's answer sheet."""
        marks = build_export_marks(
            question=_question(), grade=_grade(), annotations=[], recognitions=[]
        )

        assert marks == []

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
        )

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
        )

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
        )

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
        )

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
        )

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
        )

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
        )

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
        )

        notes = [mark for mark in marks if mark.kind is AnnotationKind.COMMENT]
        assert [note.text for note in notes] == ["ほか3件は余白に収まらず未表示"]

    def test_a_mark_with_no_resolvable_position_at_all_is_skipped_not_crashed_on(
        self,
    ) -> None:
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

        marks = build_export_marks(
            question=_question(comment_area=None),
            grade=grade,
            annotations=[annotation],
            recognitions=[],
        )

        assert marks == []

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
        )

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
