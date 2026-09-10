"""Answer-area detection: what a provider is allowed to say, and what happens
to what it says (Issue #105).

Every fixture here is synthetic. The real material this feature was measured
against is a cram school's copyrighted answer sheets, and none of it -- not a
page, not a crop, not a question number, not a subject name -- appears in this
repository (AGENTS.md "Security", Issue #105 acceptance 9).
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pydantic import ValidationError

from auto_scoring.domain.answer_area_detection import (
    MAX_NOTE_CHARS,
    SNAPPED_NOTE_PREFIX,
    UNASSIGNED_QUESTION_LABEL,
    AnswerAreaDetectionError,
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    UnassignedAnswerAreaError,
    ensure_answer_areas_confirmable,
    missing_question_numbers,
    reading_order_conflicts,
    parse_answer_area_detection,
    regions_from_detection,
    unassigned_answer_area_ids,
)
from auto_scoring.domain.answer_area_snapping import PageRuling
from auto_scoring.domain.profile import NormalizedBBox, Region, RegionKind

_NUMBERS = ("Q1", "Q2", "Q3")


def _area(
    *,
    page: int = 1,
    number: str = "Q1",
    bbox: tuple[float, float, float, float] = (0.1, 0.2, 0.6, 0.4),
    note: str | None = None,
) -> dict[str, object]:
    x0, y0, x1, y1 = bbox
    return {
        "page": page,
        "question_number": number,
        "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        "note": note,
    }


def _parse(areas: list[dict[str, object]], *, page_count: int = 2) -> AnswerAreaDetectionOutput:
    return parse_answer_area_detection(
        json.dumps({"areas": areas}), question_numbers=_NUMBERS, page_count=page_count
    )


def _parse_with_boxes(
    areas: list[dict[str, object]],
    *,
    absent: list[str] | None = None,
    page_count: int = 1,
) -> AnswerAreaDetectionOutput:
    """Parse against the one page of measured boxes `_MEASURED` describes."""
    return parse_answer_area_detection(
        json.dumps({"areas": areas, "questions_not_on_these_pages": absent or []}),
        question_numbers=_NUMBERS,
        page_count=page_count,
        boxes_per_page=[len(_MEASURED[0])],
    )


class TestParsing:
    def test_accepts_a_well_formed_response(self) -> None:
        output = _parse([_area(), _area(page=2, number="Q2")])
        assert [area.question_number for area in output.areas] == ["Q1", "Q2"]

    def test_accepts_an_empty_area_list(self) -> None:
        """ "Ran, and found nothing" is a valid answer.

        The prompt tells the model to report nothing rather than guess, so
        rejecting an empty list here would push it back towards guessing --
        and the caller already surfaces the result as every question being
        undetected.
        """
        assert _parse([]).areas == []

    def test_rejects_a_question_number_outside_the_candidate_set(self) -> None:
        """The core of Issue #105 acceptance 3: attribution is a choice from
        this test's confirmed questions, never free text. A number nobody
        offered attaches the box to an allocation that does not exist, and
        `build_questions_and_rubrics` would then ignore the region without a
        word.
        """
        with pytest.raises(ValidationError):
            _parse([_area(number="Q9")])

    def test_accepts_the_unassigned_sentinel(self) -> None:
        output = _parse([_area(number=UNASSIGNED_QUESTION_LABEL, note="どの設問か判断できない")])
        assert output.areas[0].question_number == UNASSIGNED_QUESTION_LABEL

    def test_rejects_a_page_beyond_the_document(self) -> None:
        with pytest.raises(ValidationError):
            _parse([_area(page=3)], page_count=2)

    def test_rejects_a_page_below_one(self) -> None:
        with pytest.raises(ValidationError):
            _parse([_area(page=0)])

    @pytest.mark.parametrize(
        "bbox",
        [
            (-0.1, 0.2, 0.6, 0.4),
            (0.1, 0.2, 1.4, 0.4),
            (0.6, 0.2, 0.6, 0.4),  # zero width
            (0.1, 0.4, 0.6, 0.2),  # inverted
        ],
    )
    def test_rejects_an_unusable_box(self, bbox: tuple[float, float, float, float]) -> None:
        """A degenerate or off-page box must fail here, while it is still a
        `ValidationError` the adapters convert into `SchemaViolation`.

        `NormalizedBBox` would raise `ValueError` for the same input, which is
        outside the detector port's exception contract and would surface as an
        unhandled 500 instead of "the provider's answer was malformed".
        """
        with pytest.raises(ValidationError):
            _parse([_area(bbox=bbox)])

    def test_rejects_an_over_long_note(self) -> None:
        with pytest.raises(ValidationError):
            _parse([_area(note="あ" * (MAX_NOTE_CHARS + 1))])

    def test_rejects_an_unknown_field(self) -> None:
        area = _area()
        area["confidence"] = 0.9
        with pytest.raises(ValidationError):
            _parse([area])

    def test_rejects_a_non_object_body(self) -> None:
        with pytest.raises(ValidationError):
            parse_answer_area_detection("[]", question_numbers=_NUMBERS, page_count=1)


class TestRegionsFromDetection:
    def test_builds_one_region_per_area(self) -> None:
        regions = regions_from_detection(_parse([_area(), _area(page=2, number="Q2")]))
        assert [(r.kind, r.label, r.page_index) for r in regions] == [
            (RegionKind.ANSWER_AREA, "Q1", 0),
            (RegionKind.ANSWER_AREA, "Q2", 1),
        ]

    def test_merges_several_boxes_of_one_question_on_one_page(self) -> None:
        """Measured: one subject's answer sheet gives a single question five
        separate small boxes, one per sub-item. ``Question.answer_area`` is one
        rectangle, so the crop sent for grading is one image either way --
        merging here makes what is stored match what is sent.
        """
        regions = regions_from_detection(
            _parse(
                [
                    _area(bbox=(0.1, 0.1, 0.2, 0.2)),
                    _area(bbox=(0.5, 0.6, 0.7, 0.8)),
                ]
            )
        )
        assert len(regions) == 1
        assert regions[0].bbox == NormalizedBBox(x0=0.1, y0=0.1, x1=0.7, y1=0.8)

    def test_a_merge_says_so_in_the_region_note(self) -> None:
        """Never silently: a single rectangle standing for several the model
        reported is something the reviewer has to be able to see.
        """
        regions = regions_from_detection(
            _parse([_area(bbox=(0.1, 0.1, 0.2, 0.2)), _area(bbox=(0.5, 0.6, 0.7, 0.8))])
        )
        assert regions[0].text is not None
        assert "2" in regions[0].text

    def test_a_single_box_carries_no_merge_note(self) -> None:
        regions = regions_from_detection(_parse([_area()]))
        assert regions[0].text is None

    def test_keeps_the_model_note(self) -> None:
        regions = regions_from_detection(
            _parse([_area(number=UNASSIGNED_QUESTION_LABEL, note="設問番号が読めない")])
        )
        assert regions[0].text == "設問番号が読めない"

    def test_does_not_merge_two_boxes_the_model_could_not_attribute(self) -> None:
        """`UNASSIGNED_QUESTION_LABEL` means "I could not say", not "the same
        question". Merging two of them assumes the very thing the model just
        said it could not establish, swallows whatever lies between two
        different questions, and cannot be undone: assigning the merged
        rectangle to a question later cannot recover which part was whose.

        Fixing the old `answer_regions[0]` bug by replacing "drop the rest"
        with "blend the rest" loses the same information.
        """
        regions = regions_from_detection(
            _parse(
                [
                    _area(number=UNASSIGNED_QUESTION_LABEL, bbox=(0.1, 0.1, 0.2, 0.2)),
                    _area(number=UNASSIGNED_QUESTION_LABEL, bbox=(0.5, 0.6, 0.7, 0.8)),
                ]
            )
        )
        assert len(regions) == 2
        assert {(r.bbox.x0, r.bbox.y0) for r in regions} == {(0.1, 0.1), (0.5, 0.6)}
        assert all(r.text is None for r in regions)

    def test_each_unassigned_box_can_be_confirmed_or_deleted_on_its_own(self) -> None:
        """The point of keeping them separate: the confirm gate is a per-box
        decision, not one yes/no over a merged blob.
        """
        regions = regions_from_detection(
            _parse(
                [
                    _area(number=UNASSIGNED_QUESTION_LABEL, bbox=(0.1, 0.1, 0.2, 0.2)),
                    _area(number=UNASSIGNED_QUESTION_LABEL, bbox=(0.5, 0.6, 0.7, 0.8)),
                ]
            )
        )
        assert len(unassigned_answer_area_ids(regions)) == 2
        resolved = (regions[0], replace(regions[1], label="Q2"))
        assert len(unassigned_answer_area_ids(resolved)) == 1

    def test_does_not_merge_one_question_across_pages(self) -> None:
        """Measured: one subject prints a question's first half on one page and
        its continuation on the next.

        Two pages are two coordinate spaces and ``Question.page`` is a single
        page, so a union would be meaningless. Both regions are kept, and
        `build_questions_and_rubrics` refuses them at confirm time with
        `CrossPageRegionError` -- which is the honest outcome: this app cannot
        represent a multi-page question yet, and says so rather than dropping
        half a student's answer.
        """
        regions = regions_from_detection(_parse([_area(page=1), _area(page=2)]))
        assert [r.page_index for r in regions] == [0, 1]
        assert {r.label for r in regions} == {"Q1"}

    def test_region_ids_are_unique(self) -> None:
        regions = regions_from_detection(
            _parse([_area(), _area(number="Q2"), _area(page=2, number="Q3")])
        )
        assert len({r.region_id for r in regions}) == len(regions)

    def test_replaces_only_answer_areas_and_keeps_the_reviewers_own_regions(self) -> None:
        """Re-running detection after a provider failure is normal, and must
        not throw away a 問題文 or 添削記号領域 the reviewer drew by hand.
        """
        kept = Region(
            region_id="manual-question",
            kind=RegionKind.QUESTION,
            page_index=0,
            bbox=NormalizedBBox(x0=0.0, y0=0.0, x1=0.5, y1=0.1),
            label="Q1",
        )
        stale = Region(
            region_id="answer-area-old",
            kind=RegionKind.ANSWER_AREA,
            page_index=0,
            bbox=NormalizedBBox(x0=0.0, y0=0.9, x1=0.5, y1=1.0),
            label="Q1",
        )
        regions = regions_from_detection(_parse([_area()]), existing_regions=(kept, stale))
        assert kept in regions
        assert stale not in regions
        assert sum(1 for r in regions if r.kind is RegionKind.ANSWER_AREA) == 1

    def test_every_region_is_unconfirmed(self) -> None:
        """The AI's proposal is never the final word (Issue #105 acceptance 2).
        `Profile.from_candidates` enforces this too; stated here so the
        detection path cannot quietly start producing confirmed regions.
        """
        regions = regions_from_detection(_parse([_area(), _area(number="Q2")]))
        assert all(not region.confirmed for region in regions)


class TestVisibleGaps:
    def test_undetected_lists_questions_with_no_box(self) -> None:
        regions = regions_from_detection(_parse([_area(number="Q2")]))
        assert missing_question_numbers(regions, _NUMBERS)[0] == ("Q1", "Q3")

    def test_undetected_follows_an_edit_rather_than_a_stored_value(self) -> None:
        """The one moment this matters is right after the reviewer draws the
        missing box, so it is derived on every read rather than stored.
        """
        regions = regions_from_detection(_parse([_area(number="Q2")]))
        drawn = (
            *regions,
            Region(
                region_id="manual-0",
                kind=RegionKind.ANSWER_AREA,
                page_index=0,
                bbox=NormalizedBBox(x0=0.1, y0=0.5, x1=0.4, y1=0.6),
                label="Q1",
            ),
        )
        assert missing_question_numbers(drawn, _NUMBERS)[0] == ("Q3",)

    def test_an_unassigned_box_does_not_cover_a_question(self) -> None:
        regions = regions_from_detection(_parse([_area(number=UNASSIGNED_QUESTION_LABEL)]))
        assert missing_question_numbers(regions, _NUMBERS)[0] == _NUMBERS

    def test_unassigned_ids_name_the_boxes_that_block_a_confirm(self) -> None:
        regions = regions_from_detection(
            _parse([_area(), _area(page=2, number=UNASSIGNED_QUESTION_LABEL)])
        )
        assert len(unassigned_answer_area_ids(regions)) == 1

    def test_confirm_is_blocked_while_a_box_has_no_question(self) -> None:
        """`build_questions_and_rubrics` ignores a region whose label matches
        no question. Without this check the model would have found a box,
        nobody would have assigned it, and it would disappear in silence.
        """
        regions = regions_from_detection(_parse([_area(number=UNASSIGNED_QUESTION_LABEL)]))
        with pytest.raises(UnassignedAnswerAreaError):
            ensure_answer_areas_confirmable(regions)

    def test_confirm_is_not_blocked_by_an_undetected_question(self) -> None:
        """Deliberately different from Issue #103's unknown 配点, which does
        block: an unknown score is confirmed into a silently wrong
        ``Question.points`` that nobody sees, while a question with no answer
        area is sent to grading as the whole page and marked
        ``no_answer_area_defined`` -- it fails loudly, on the review screen.
        Stop what goes wrong quietly; let through what goes wrong loudly.
        """
        regions = regions_from_detection(_parse([_area(number="Q2")]))
        assert missing_question_numbers(regions, _NUMBERS)[0]
        ensure_answer_areas_confirmable(regions)


class TestSnappingIntoRegions:
    """`regions_from_detection` moves each reported box onto the printed
    ruling before merging (Issue #122). The snapping rule itself is covered
    by ``test_answer_area_snapping.py``; these check the wiring."""

    #: Two narrow columns, at the positions measured on a real sheet.
    _RULING = PageRuling(vertical=(0.6671, 0.7158, 0.8102, 0.8581))

    def test_a_box_is_snapped_onto_the_ruling(self) -> None:
        regions = regions_from_detection(
            _parse([_area(bbox=(0.6558, 0.25, 0.7045, 0.48))]),
            page_rulings=(self._RULING,),
        )
        assert regions[0].bbox.x0 == 0.6671
        assert regions[0].bbox.x1 == 0.7158

    def test_snapping_says_so_in_the_region_note(self) -> None:
        """The rectangle on the overlay is then not the one the model
        reported, and the reviewer is about to confirm it."""
        regions = regions_from_detection(
            _parse([_area(bbox=(0.6558, 0.25, 0.7045, 0.48))]),
            page_rulings=(self._RULING,),
        )
        assert regions[0].text is not None
        assert SNAPPED_NOTE_PREFIX in regions[0].text

    def test_boxes_are_snapped_before_they_are_merged_not_after(self) -> None:
        """A union of two stereotyped rectangles is not a rectangle the page
        has anywhere, so snapping the union would pick a rule near an edge
        that was never real. Here two boxes each land on their own column and
        the merged region spans both -- which snapping afterwards could not
        produce, because the union's own edges are already on rules.
        """
        regions = regions_from_detection(
            _parse(
                [
                    _area(bbox=(0.6558, 0.25, 0.7045, 0.48)),
                    _area(bbox=(0.8210, 0.25, 0.8690, 0.48)),
                ]
            ),
            page_rulings=(self._RULING,),
        )
        assert len(regions) == 1
        assert (regions[0].bbox.x0, regions[0].bbox.x1) == (0.6671, 0.8581)

    def test_a_page_with_no_measured_ruling_keeps_the_model_coordinates(self) -> None:
        """Callers that measured nothing -- and pages that have no ruling --
        must not have coordinates invented for them."""
        regions = regions_from_detection(_parse([_area(bbox=(0.6558, 0.25, 0.7045, 0.48))]))
        assert regions[0].bbox.x0 == 0.6558
        assert regions[0].text is None

    def test_each_page_is_snapped_to_its_own_ruling(self) -> None:
        """Two pages of one sheet can be ruled differently; using page 1's
        lines on page 2 would move boxes onto lines that page does not have."""
        regions = regions_from_detection(
            _parse([_area(page=2, number="Q2", bbox=(0.1050, 0.25, 0.2050, 0.48))]),
            page_rulings=(self._RULING, PageRuling(vertical=(0.1000, 0.2000))),
        )
        assert (regions[0].bbox.x0, regions[0].bbox.x1) == (0.1000, 0.2000)


class TestRequest:
    def test_rejects_an_empty_question_set(self) -> None:
        """A multiple-choice question with no choices is not one. The caller
        answers 409 rather than falling back to free text.
        """
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(page_images=(b"png",), question_numbers=())

    def test_rejects_no_pages(self) -> None:
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(page_images=(), question_numbers=_NUMBERS)

    def test_rejects_an_empty_page_image(self) -> None:
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(page_images=(b"png", b""), question_numbers=_NUMBERS)

    def test_rejects_a_ruling_that_does_not_cover_every_page(self) -> None:
        """One entry per page, or the measured lines of one page would be
        attached to the image of another (Issue #122)."""
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(
                page_images=(b"png", b"png"),
                question_numbers=_NUMBERS,
                page_rulings=(PageRuling(vertical=(0.5,)),),
            )

    def test_rejects_a_question_number_equal_to_the_sentinel(self) -> None:
        """Otherwise "the model could not decide" and "the model chose this
        question" would be the same value.
        """
        with pytest.raises(AnswerAreaDetectionError):
            AnswerAreaDetectionRequest(
                page_images=(b"png",), question_numbers=(UNASSIGNED_QUESTION_LABEL,)
            )


def _chosen(
    *,
    page: int = 1,
    number: str = "Q1",
    indexes: list[int] | None = None,
    note: str | None = None,
) -> dict[str, object]:
    """One area that *chooses* measured boxes rather than describing one."""
    return {
        "page": page,
        "question_number": number,
        "box_indexes": indexes if indexes is not None else [0],
        "bbox": None,
        "note": note,
    }


_MEASURED = (
    (
        NormalizedBBox(x0=0.810, y0=0.252, x1=0.859, y1=0.480),
        NormalizedBBox(x0=0.668, y0=0.252, x1=0.716, y1=0.480),
        NormalizedBBox(x0=0.525, y0=0.252, x1=0.573, y1=0.480),
    ),
)


class TestChoosingAMeasuredBox:
    """Issue #164's first half: the model picks a measured box instead of
    describing a rectangle.

    Measured on the five real subjects with five or more questions: asked for
    coordinates it put one subject's box on the blank paper between two
    answer columns (graded 0, approved), clipped another's crops to the first
    of two answer rows, and returned five sub-boxes spaced exactly 0.047
    apart for a column whose sub-boxes it could see. Given the same page's
    measured boxes to choose from, the two worst subjects went from 0 of 2
    correctly attributed questions to 2 of 2, stable over three runs.
    """

    def test_a_chosen_box_becomes_the_region_verbatim(self) -> None:
        output = _parse_with_boxes([_chosen(indexes=[0])])

        regions = regions_from_detection(output, page_boxes=_MEASURED)

        assert regions[0].bbox == _MEASURED[0][0]

    def test_several_chosen_boxes_are_unioned_into_one_region(self) -> None:
        """One measured subject gives 問一 three separate columns; the region
        that gets cropped and sent for grading is a single rectangle."""
        output = _parse_with_boxes([_chosen(indexes=[0, 1, 2])])

        regions = regions_from_detection(output, page_boxes=_MEASURED)

        assert len(regions) == 1
        assert regions[0].bbox.x0 == pytest.approx(0.525)
        assert regions[0].bbox.x1 == pytest.approx(0.859)

    def test_a_chosen_box_is_never_reported_as_moved(self) -> None:
        """Snapping's note tells the reviewer the rectangle on screen is not
        the one the model reported. A chosen box *is* the printed box, so
        saying it moved would be false -- and would train the reviewer to
        ignore the note in the case where it is true."""
        output = _parse_with_boxes([_chosen(indexes=[0])])

        regions = regions_from_detection(
            output,
            page_boxes=_MEASURED,
            page_rulings=(PageRuling(vertical=(0.5, 0.9), horizontal=(0.1, 0.9)),),
        )

        assert regions[0].text is None or SNAPPED_NOTE_PREFIX not in regions[0].text

    def test_a_described_rectangle_is_still_snapped_onto_the_ruling(self) -> None:
        """Issue #122's repair, unchanged, for the one case that still needs
        it: an answer space with no printed border anywhere."""
        output = _parse_with_boxes([_area(bbox=(0.1013, 0.2, 0.6, 0.4))])

        regions = regions_from_detection(
            output,
            page_boxes=_MEASURED,
            page_rulings=(PageRuling(vertical=(0.1000,), horizontal=()),),
        )

        assert regions[0].bbox.x0 == pytest.approx(0.1000)

    def test_an_area_that_gives_both_a_choice_and_a_rectangle_is_rejected(self) -> None:
        """Two answers to "where is it" is not more information than one; it
        is a response nobody can act on, and picking either silently would
        make the other one unfalsifiable."""
        area = _chosen(indexes=[0])
        area["bbox"] = {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4}

        with pytest.raises(ValidationError):
            _parse_with_boxes([area])

    def test_an_area_that_gives_neither_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _parse_with_boxes([_chosen(indexes=[])])

    def test_a_box_index_that_was_not_offered_is_rejected(self) -> None:
        """An index is positional. Resolved against a shorter list it is an
        `IndexError` on a good day and another page's rectangle on a bad one,
        and there is no reading of "box 7" that is safe when six were
        offered."""
        with pytest.raises(ValidationError):
            _parse_with_boxes([_chosen(indexes=[7])])


class TestQuestionsNotOnThesePages:
    """Issue #164's second half.

    Measured over the real material: the registered answer sheet is one page
    of a longer one (page 1 of 9, 1 of 2, 2 of 4, 2 of 5, 1 of 5) while the
    採点基準 the question list comes from covers the whole assignment. 26 of
    that run's 37 questions had no answer space on the registered page
    because the paper has none, and counting them as detection failures is
    what produced this Issue's "27% detection rate".
    """

    def test_the_reported_absences_are_kept(self) -> None:
        output = _parse_with_boxes([_chosen()], absent=["Q2", "Q3"])

        assert output.questions_not_on_these_pages == ["Q2", "Q3"]

    def test_a_question_outside_the_candidate_set_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _parse_with_boxes([_chosen()], absent=["Q9"])

    def test_the_unassigned_sentinel_cannot_be_reported_absent(self) -> None:
        """The sentinel says "I found a box and could not attribute it",
        which is a statement about a box. There is no box here."""
        with pytest.raises(ValidationError):
            _parse_with_boxes([_chosen()], absent=[UNASSIGNED_QUESTION_LABEL])

    def test_a_question_both_located_and_reported_absent_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _parse_with_boxes([_chosen(number="Q2")], absent=["Q2"])

    def test_a_question_in_neither_list_is_accepted_and_reads_as_undetected(self) -> None:
        """Rejecting the whole response would cost the reviewer every box it
        did find, to punish an omission. "The model did not say" is the
        conservative half of the split."""
        output = _parse_with_boxes([_chosen(number="Q1")], absent=["Q2"])
        regions = regions_from_detection(output, page_boxes=_MEASURED)

        undetected, absent = missing_question_numbers(
            regions, _NUMBERS, output.questions_not_on_these_pages
        )

        assert undetected == ("Q3",)
        assert absent == ("Q2",)


class TestMissingQuestionsAreSplitByCause:
    """The distinction is the point: a question the model missed needs a box
    drawn, and a question that is not on the sheet needs the 採点基準 or the
    registered sheet fixed. Telling the reviewer to do the first when the
    second is true is how this Issue's reporter came to measure the wrong
    denominator."""

    def _region(self, label: str) -> Region:
        return Region(
            region_id=f"answer-area-{label}",
            kind=RegionKind.ANSWER_AREA,
            page_index=0,
            bbox=NormalizedBBox(x0=0.1, y0=0.2, x1=0.6, y1=0.4),
            label=label,
        )

    def test_a_question_with_a_region_is_in_neither_list(self) -> None:
        undetected, absent = missing_question_numbers([self._region("Q1")], _NUMBERS, ["Q2", "Q3"])

        assert "Q1" not in undetected and "Q1" not in absent

    def test_a_reported_absence_the_reviewer_drew_anyway_leaves_both_lists(self) -> None:
        """Derived on every read against the current region set, so nothing
        has to be un-stored when the reviewer -- who can see the page, and is
        not obliged to believe the model -- draws the box themselves."""
        undetected, absent = missing_question_numbers([self._region("Q2")], _NUMBERS, ["Q2"])

        assert absent == ()
        assert undetected == ("Q1", "Q3")

    def test_without_a_detection_run_every_missing_question_is_undetected(self) -> None:
        """A profile whose boxes were all drawn by hand has nothing stored,
        and must not read as "the paper has no answer space for any of
        these"."""
        undetected, absent = missing_question_numbers([], _NUMBERS)

        assert undetected == _NUMBERS
        assert absent == ()


class TestReadingOrderConflicts:
    """The one detection failure that looks like success (Issue #171).

    Measured on the real material: on a vertical, right-to-left sheet the
    model puts both boxes exactly on the printed columns and then attributes
    each to the *other* question -- every run, three for three. Nothing else
    notices, because every question has a box: the screen says every question
    has an answer area, and the two answers are graded against each other's
    rubric. One real run produced 0/10 and 0/20 that way, both at high
    confidence, both approved by a person.

    The geometry below is the measured position of each subject's answer
    areas, normalized, taken from the eight registered answer sheets.
    """

    def _regions(self, *placed: tuple[str, float, float, float, float]) -> list[Region]:
        return [
            Region(
                region_id=f"answer-area-{index}",
                kind=RegionKind.ANSWER_AREA,
                page_index=0,
                bbox=NormalizedBBox(x0=x0, y0=y0, x1=x1, y1=y1),
                label=label,
            )
            for index, (label, x0, y0, x1, y1) in enumerate(placed)
        ]

    def test_a_vertical_sheet_read_right_to_left_is_quiet_when_correct(self) -> None:
        """問一's column is the one further right on a right-to-left sheet."""
        regions = self._regions(
            ("問一", 0.798, 0.270, 0.843, 0.671),
            ("問二", 0.639, 0.270, 0.703, 0.720),
        )

        assert reading_order_conflicts(regions, ("問一", "問二", "問三")) == ()

    def test_the_measured_swap_is_named(self) -> None:
        """The same two columns, attributed the other way round -- which is
        what the real detector returns for this subject."""
        regions = self._regions(
            ("問一", 0.639, 0.270, 0.703, 0.720),
            ("問二", 0.798, 0.270, 0.843, 0.671),
        )

        assert reading_order_conflicts(regions, ("問一", "問二", "問三")) == (("問一", "問二"),)

    def test_a_horizontal_sheet_reads_top_to_bottom(self) -> None:
        regions = self._regions(
            ("問6", 0.181, 0.357, 0.840, 0.493),
            ("問7", 0.178, 0.509, 0.837, 0.602),
        )

        assert reading_order_conflicts(regions, ("問5", "問6", "問7")) == ()

    def test_a_horizontal_sheet_swapped_is_named(self) -> None:
        regions = self._regions(
            ("問6", 0.178, 0.509, 0.837, 0.602),
            ("問7", 0.181, 0.357, 0.840, 0.493),
        )

        assert reading_order_conflicts(regions, ("問5", "問6", "問7")) == (("問6", "問7"),)

    def test_questions_that_are_not_adjacent_in_the_list_still_compare(self) -> None:
        """One measured subject has only its 3rd and 4th questions on the
        registered page. Their *relative* order is what this checks; the gap
        between their numbers says nothing."""
        regions = self._regions(
            ("設問Ａ (3)", 0.136, 0.278, 0.830, 0.446),
            ("設問Ｂ (1)", 0.139, 0.620, 0.832, 0.787),
        )
        numbers = ("設問Ａ (1)", "設問Ａ (2)", "設問Ａ (3)", "設問Ｂ (1)", "設問Ｂ (2)")

        assert reading_order_conflicts(regions, numbers) == ()

    def test_one_answer_area_on_a_page_has_no_order_to_contradict(self) -> None:
        """True by construction rather than by a guard -- there is no pair to
        compare. Kept as a statement of the behaviour, not as a claim that
        some branch enforces it."""
        regions = self._regions(("問1", 0.016, 0.244, 0.962, 0.463))

        assert reading_order_conflicts(regions, ("問1", "問2")) == ()

    def test_pages_are_checked_apart(self) -> None:
        """A question order spanning two pages says nothing about where on
        either page the boxes sit.

        Laid out so that pooling the pages would *invent* a conflict: 問二 is
        near the top of page 2 and 問一 near the bottom of page 1, which read
        as one page is the wrong way round and read as two pages is nothing
        at all.
        """
        regions = self._regions(("問一", 0.1, 0.6, 0.9, 0.8))
        regions.append(
            Region(
                region_id="answer-area-1",
                kind=RegionKind.ANSWER_AREA,
                page_index=1,
                bbox=NormalizedBBox(x0=0.1, y0=0.2, x1=0.9, y1=0.4),
                label="問二",
            )
        )

        assert reading_order_conflicts(regions, ("問一", "問二")) == ()

    def test_a_region_naming_no_confirmed_question_is_ignored(self) -> None:
        """An unassigned box has no number, so it has no place in the order.
        It blocks the confirm on its own account
        (`ensure_answer_areas_confirmable`)."""
        regions = self._regions(
            (UNASSIGNED_QUESTION_LABEL, 0.798, 0.270, 0.843, 0.671),
            ("問一", 0.639, 0.270, 0.703, 0.720),
        )

        assert reading_order_conflicts(regions, ("問一", "問二")) == ()

    def test_writing_direction_comes_from_the_shape_of_the_answer_areas(self) -> None:
        """A column of vertical writing is far taller than it is wide; a
        ruled line of horizontal writing is far wider than it is tall.
        Measured over the eight sheets the two never come close: 0.18-0.46
        against 5.76-8.91.

        This is the property, not the number. Boxes of the same *positions*
        read in opposite orders depending only on their shape.
        """
        tall = self._regions(
            ("問一", 0.639, 0.270, 0.703, 0.720),
            ("問二", 0.798, 0.270, 0.843, 0.671),
        )
        wide = self._regions(
            ("問一", 0.400, 0.270, 0.900, 0.300),
            ("問二", 0.100, 0.500, 0.900, 0.530),
        )

        assert reading_order_conflicts(tall, ("問一", "問二")) == (("問一", "問二"),)
        assert reading_order_conflicts(wide, ("問一", "問二")) == ()
