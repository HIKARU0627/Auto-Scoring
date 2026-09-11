"""Detect where each question's answer box sits on a student's answer sheet
(Issue #105).

This is the third of the three things a test needs before grading can start:
the folder import (Issue #101) attaches the materials, the 採点基準 extraction
(Issue #103) produces the questions and their allocations, and this module
produces the *coordinates* -- the `RegionKind.ANSWER_AREA` regions
`domain.test_registration.build_questions_and_rubrics` turns into
``Question.answer_area``. Without them `complete_registration` never passes
its profile gate and no answer is ever processed.

**Why the student's answer sheet and not a model-answer document.** There is
no model-answer PDF in real material (Issue #95 decision 1). The answer sheet
itself is the only document that carries the boxes, and it is a paper scan:
all 11 measured 生徒答案 PDFs have an embedded text layer of exactly zero
characters. The page *image* is the only input there is, which is why this
port takes rendered pages and nothing else -- there is no "try the text layer
first" branch to take.

**Which question a box belongs to is asked as a multiple-choice question.**
`AnswerAreaDetectionRequest.question_numbers` is the confirmed question set
(the rows `Question` already holds for this test, which since Issue #103 come
from the human-confirmed 採点基準 draft), and the wire schema constrains
``question_number`` to that list plus :data:`UNASSIGNED_QUESTION_LABEL`.
A value outside it is a :class:`~auto_scoring.domain.ai_provider.SchemaViolation`,
never a new question -- the discipline Issue #101 established for answer
attribution, for the same reason: a free-text answer here invents a question
number that matches no allocation, and the box is then silently attached to
nothing.

**Nothing here is saved without a human confirming it.** The regions this
module builds go into a DRAFT `domain.profile.Profile`, which
`Profile.from_candidates` forces unconfirmed; the reviewer moves, adds,
deletes and re-assigns them on the overlay editor and only then confirms.
Two states are deliberately made visible rather than resolved by guessing:

* a question with no box at all (:func:`missing_question_numbers`) --
  derived, never stored, so it cannot go stale as the reviewer edits;
* a box whose question the model could not name
  (:data:`UNASSIGNED_QUESTION_LABEL`). That one *blocks* confirmation
  (:func:`ensure_answer_areas_confirmable`), because
  `build_questions_and_rubrics` ignores a region whose label matches no
  question -- so letting it through would mean the model found a box, nobody
  assigned it, and it vanished without a word.

An undetected question does **not** block confirmation, and the asymmetry
with Issue #103's "配点不明はブロックする" is deliberate:

* an unknown 配点 that is confirmed anyway becomes a **silently wrong**
  ``Question.points`` and rescales every grade for that question; nobody
  ever sees it;
* a question with no answer area is already handled loudly --
  `adapters.submission_intake._build_answer_image` sends the whole page and
  marks the submission ``no_answer_area_defined`` / ``NEEDS_REVIEW``, so it
  lands in front of a human on the review screen.

The rule that produces both decisions: **stop what would go wrong quietly,
let through what will go wrong loudly.**
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationInfo
from pydantic import model_validator as pydantic_model_validator

from auto_scoring.domain.ai_response_language import FIELD_LANGUAGE_NOTE
from auto_scoring.domain.answer_area_snapping import PageRuling, snap_bbox_to_ruling
from auto_scoring.domain.models import DomainError, Question
from auto_scoring.domain.profile import NormalizedBBox, Region, RegionKind

#: `Region.label` for a box the model found but could not attribute to any
#: question. Deliberately a reserved *label* rather than a new `RegionKind`:
#: a new kind would ripple through the OpenAPI schema, the generated Dart
#: client, and every `switch` over the enum in the app, to express something
#: that only exists between detection and the reviewer's next click. Chosen
#: to be un-typeable as a real question number by accident -- and if a school
#: ever did print this as a question number, the only consequence is that its
#: boxes must be re-assigned by hand before confirming.
UNASSIGNED_QUESTION_LABEL = "__unassigned__"

#: Same shape as ``domain.criteria_extraction._NonBlankStr`` /
#: ``domain.ai_grading._NonBlankStr``: ``min_length=1`` alone accepts ``" "``.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

#: Bound on how many boxes one answer sheet may yield. The measured material
#: runs 1-11 questions over 1-3 pages; a model that starts repeating itself
#: must fail the schema rather than produce an overlay a reviewer cannot work
#: through. Mirrors ``domain.criteria_extraction``'s own list bound and its
#: reasoning.
MAX_DETECTED_AREAS = 200

#: Bound on the free-text ``note``. Long enough for a real explanation of why
#: a box could not be attributed, short enough that a runaway generation is
#: rejected rather than persisted into the profile and re-sent on every later
#: screen load.
MAX_NOTE_CHARS = 500

#: Prefix for the note this module writes itself when it merges several
#: reported boxes into one region -- see :func:`regions_from_detection`.
MERGED_NOTE_PREFIX = "検出された枠"

#: Prefix for the note written when snapping moved a box onto the printed
#: ruling -- see :func:`regions_from_detection`. The reviewer is told, because
#: the rectangle on screen is then not the one the model reported.
SNAPPED_NOTE_PREFIX = "枠を印刷された罫線に合わせました"

#: Issue #140: the model's own explanation for why an area is unassigned or
#: undetected, not a transcription of anything printed on the sheet -- see
#: `domain.ai_response_language` for why this carries the language
#: instruction in its schema description.
_NOTE_DESCRIPTION = (
    "Why this area could not be attributed to a question, if you chose "
    f"'{UNASSIGNED_QUESTION_LABEL}'." + FIELD_LANGUAGE_NOTE
)


class AnswerAreaDetectionError(DomainError):
    """Answer areas could not be detected, or could not be confirmed."""


class UnassignedAnswerAreaError(AnswerAreaDetectionError):
    """At least one detected box still has no question assigned to it."""


# --------------------------------------------------------------------------- #
# Wire schema
# --------------------------------------------------------------------------- #
class DetectedBBoxOutput(BaseModel):
    """One box in the same normalized page space the rest of the app uses:
    origin top-left, axes ``0..1``, independent of page size / DPI / zoom
    (`domain.profile.NormalizedBBox`, adopted by PoC 3 / Issue #12).

    The model is told the convention in words as well
    (`adapters.answer_area_detection._prompt`), because the bounds below are
    stripped from the schema that goes on the wire -- see
    `_VALUE_CONSTRAINT_KEYWORDS` there. They are still enforced here, which
    is what actually rejects an out-of-range box.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @pydantic_model_validator(mode="after")
    def _has_positive_area(self) -> DetectedBBoxOutput:
        # `NormalizedBBox` raises `ValueError` for a degenerate box, and that
        # is not one of the two exceptions the detector port declares -- it
        # would escape as an unhandled 500 instead of the SchemaViolation
        # this is (Issue #105 acceptance: "誤った矩形が保存されない"). Caught
        # here, while it is still a pydantic validation error the adapters
        # already convert.
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError("bbox must have positive area (x0 < x1 and y0 < y1)")
        return self

    def to_domain(self) -> NormalizedBBox:
        return NormalizedBBox(x0=self.x0, y0=self.y0, x1=self.x1, y1=self.y1)


class DetectedAnswerAreaOutput(BaseModel):
    """One answer box as the model reported it: normally a *choice* among the
    boxes measured off the page, and only otherwise a rectangle of its own.

    **Why a choice.** Issue #122 established that the model does not measure a
    coordinate, it returns a stereotype, and handed it the printed rules to
    copy from instead. Issue #164 measured that on the real sheets and found
    the rules are not enough: a box whose sides are too short to be a rule is
    not in the list at all (so its edges are invented anyway), and where the
    list is complete nothing in it says *which* pair of values bounds a box --
    on one subject the pair chosen bounded the blank paper between two answer
    columns, and the crop taken from it was graded 0. Whole boxes are just as
    measurable as rules (`adapters.image.ink.measure_page_boxes`), so the
    model picks one instead of describing one, and the geometry stops being
    its problem.

    **Why ``bbox`` survives.** Not every answer space has a printed border.
    One measured subject gives each question a bordered 答え欄 plus an open
    region under 「考え方・計算過程」 with no border anywhere; nothing can be
    chosen for the second, and dropping it would drop half of what the
    student wrote. So exactly one of the two must be given, which
    :meth:`_exactly_one_location` enforces.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: 1-based, matching what the prompt shows the model and what a reviewer
    #: sees on screen. Converted to `Region.page_index` (0-based) by
    #: :func:`regions_from_detection`.
    page: int = Field(ge=1)
    #: One of `AnswerAreaDetectionRequest.question_numbers`, or
    #: :data:`UNASSIGNED_QUESTION_LABEL`. Checked against the actual
    #: candidate set in :func:`parse_answer_area_detection`.
    question_number: _NonBlankStr
    #: Indexes into this page's `AnswerAreaDetectionRequest.page_boxes`.
    #: Several when one question's answer space is several printed boxes
    #: (sub-items a / b / c, or the 90 cells of a 原稿用紙 grid); they are
    #: unioned by :func:`regions_from_detection`.
    box_indexes: list[int] = Field(default_factory=list)
    #: Only for an answer space with no printed border. ``None`` whenever
    #: ``box_indexes`` is given.
    bbox: DetectedBBoxOutput | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_CHARS, description=_NOTE_DESCRIPTION)

    @pydantic_model_validator(mode="after")
    def _exactly_one_location(self) -> DetectedAnswerAreaOutput:
        if bool(self.box_indexes) == (self.bbox is not None):
            raise ValueError(
                "an area must give either box_indexes or bbox, never both and never neither"
            )
        return self


class AnswerAreaDetectionOutput(BaseModel):
    """The full structured output for one answer sheet.

    **``questions_not_on_these_pages`` is the whole of Issue #164's second
    half.** A question with no box used to have exactly one possible reading,
    "detection missed it", and that reading was wrong far more often than it
    was right: measured over the real material, the registered answer sheet
    is *one page* of a longer one (measured: page 1 of 9, 1 of 2, 2 of 4, 2 of
    5, 1 of 5) while the 採点基準 the question list comes from covers the whole
    assignment. 26 of the 37 questions in that measurement had no answer space
    on the registered page **because the paper does not have one**, and
    counting them as detection failures is what produced the "27% detection
    rate" this Issue was opened for.

    The two cases need opposite things from the person looking at the screen:
    a question the model missed needs a box drawn, and a question that is not
    on the sheet needs the 採点基準 or the registered sheet fixed. So the model
    is asked to say which it is, and the answer is kept
    (`domain.profile.Profile.absent_question_numbers`) rather than derived --
    it cannot be derived, which is exactly the problem.

    A question in **both** lists is a ``ValidationError``: the two readings
    are contradictory and there is no way to choose between them.

    A question in **neither** is not, and deliberately so. The prompt asks
    for every question to be accounted for (and over eight measured runs of
    the real material it always was), but a response that omits one still
    carries every box it did find, and rejecting the whole thing would cost
    the reviewer all of them to punish an omission. An unaccounted question
    reads as "the model did not say", which is what
    :func:`missing_question_numbers` already calls *undetected* -- the
    conservative half of the split, where the reviewer is asked to look.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    areas: list[DetectedAnswerAreaOutput] = Field(max_length=MAX_DETECTED_AREAS)
    #: Questions the model looked for and could not find an answer space for
    #: anywhere on the attached pages -- see this class's docstring.
    questions_not_on_these_pages: list[_NonBlankStr] = Field(
        default_factory=list, max_length=MAX_DETECTED_AREAS
    )

    @pydantic_model_validator(mode="after")
    def _within_candidate_set(self, info: ValidationInfo) -> AnswerAreaDetectionOutput:
        """Reject a page number or question number the caller never offered.

        The candidate set and page count travel as a validation *context*
        rather than being baked into the class, because they differ per test
        -- see :func:`parse_answer_area_detection`. Absent context (e.g. a
        plain ``model_validate``) checks nothing; every path that parses a
        provider response goes through `parse_answer_area_detection`, which
        always supplies it.

        A question number outside the set is the failure this whole design
        exists to prevent: it looks like a confident reading and attaches the
        box to an allocation that does not exist.
        """
        context = info.context
        if not isinstance(context, Mapping):
            return self
        allowed = context.get("allowed_numbers")
        page_count = context.get("page_count")
        if isinstance(allowed, frozenset):
            unknown = sorted({area.question_number for area in self.areas} - allowed)
            if unknown:
                raise ValueError(
                    f"{len(unknown)} question number(s) are not in this test's confirmed "
                    "question set"
                )
            # The sentinel means "I found a box and could not attribute it",
            # which is a statement about a box. There is no box here.
            absent_unknown = sorted(
                {*self.questions_not_on_these_pages} - (allowed - {UNASSIGNED_QUESTION_LABEL})
            )
            if absent_unknown:
                raise ValueError(
                    f"{len(absent_unknown)} question number(s) reported as not on these pages "
                    "are not in this test's confirmed question set"
                )
        if isinstance(page_count, int):
            over = sorted({area.page for area in self.areas if area.page > page_count})
            if over:
                raise ValueError(
                    f"{len(over)} area(s) reference a page beyond the document's {page_count}"
                )
        both = sorted(
            {area.question_number for area in self.areas} & {*self.questions_not_on_these_pages}
        )
        if both:
            raise ValueError(
                f"{len(both)} question(s) are reported both with an answer area and as not "
                "being on these pages"
            )
        boxes_per_page = context.get("boxes_per_page")
        if isinstance(boxes_per_page, tuple):
            for area in self.areas:
                available = (
                    boxes_per_page[area.page - 1] if area.page - 1 < len(boxes_per_page) else 0
                )
                if any(not 0 <= index < available for index in area.box_indexes):
                    raise ValueError("an area chose a box index that was not offered for its page")
        return self


def parse_answer_area_detection(
    raw: str | bytes,
    *,
    question_numbers: Sequence[str],
    page_count: int,
    boxes_per_page: Sequence[int] = (),
) -> AnswerAreaDetectionOutput:
    """Parse and validate one provider's raw JSON response.

    Raises ``pydantic.ValidationError`` for anything malformed -- a bad
    shape, an out-of-range box, a page past the end of the document, or a
    question number outside ``question_numbers``. The adapters convert that
    into `domain.ai_provider.SchemaViolation` **without chaining it**:
    pydantic keeps the offending value in ``input_value`` and Python prints a
    chained cause's ``str()``, which would put a cram school's material into
    a log (AGENTS.md "Security" -- the rule ``adapters.ai_grading`` and
    ``adapters.criteria_extraction`` both already follow).

    There is no lenient path. A response this rejects saves nothing at all,
    rather than saving the areas that happened to validate: a partial region
    set looks exactly like a complete one on the overlay, and the reviewer
    has no way to tell that some boxes were dropped (Issue #105 acceptance
    5).
    """
    return AnswerAreaDetectionOutput.model_validate_json(
        raw,
        context={
            "allowed_numbers": frozenset(question_numbers) | {UNASSIGNED_QUESTION_LABEL},
            "page_count": page_count,
            "boxes_per_page": tuple(boxes_per_page),
        },
    )


# --------------------------------------------------------------------------- #
# Turning a validated response into regions
# --------------------------------------------------------------------------- #
def _union(boxes: Sequence[NormalizedBBox]) -> NormalizedBBox:
    return NormalizedBBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


def _merged_note(count: int, notes: Sequence[str], *, snap_shift: float = 0.0) -> str | None:
    """The reviewer-facing note for one merged region.

    Says how many boxes were merged (only when more than one was) and how far
    snapping moved the box (only when it moved), then the model's own notes.
    All three matter: the first two are this module's own actions, and the
    reviewer must be able to see that the rectangle on screen is not exactly
    what the model reported -- while the notes are the only place the model
    can say why it could not attribute a box.
    """
    parts: list[str] = []
    if count > 1:
        parts.append(f"{MERGED_NOTE_PREFIX} {count} 個を 1 つにまとめました。")
    if snap_shift > 0.0:
        parts.append(f"{SNAPPED_NOTE_PREFIX}。最大 {snap_shift:.3f} 動かしました。")
    parts.extend(notes)
    return " ".join(parts) if parts else None


def regions_from_detection(
    output: AnswerAreaDetectionOutput,
    *,
    existing_regions: Sequence[Region] = (),
    page_rulings: Sequence[PageRuling] = (),
    page_boxes: Sequence[Sequence[NormalizedBBox]] = (),
) -> tuple[Region, ...]:
    """Build the profile's new region set from a validated detection.

    **Boxes are merged per (question number, page).** A question whose answer
    space is several separate boxes is real and measured -- one subject's
    answer sheet gives 問一 five small boxes, one per sub-item -- and
    ``Question.answer_area`` is a single rectangle, so the crop that is
    actually sent for grading is one image either way. Merging here makes
    what is stored match what is sent, and the note says how many boxes went
    into it.

    **Boxes for one question on different pages are not merged**, because a
    union across two pages has no meaning: they are two different coordinate
    spaces. This is also measured -- one subject prints a question's first half
    on page 2 and its continuation on page 3. Both regions are kept, and
    `build_questions_and_rubrics` supports questions spanning up to two pages
    (`Question.page` and `Question.page_2`, Issue #108). Questions spanning
    three or more pages are refused at confirm time with `CrossPageRegionError`.

    ``existing_regions`` is the profile's current region set. Everything in
    it that is *not* an `ANSWER_AREA` is carried through untouched -- a
    reviewer's hand-drawn 問題文 or 添削記号領域 must survive re-running
    detection, which is a normal thing to do after a provider failure.

    ``page_rulings`` (indexed by ``page - 1``) is where the printed lines
    really run. Every box is snapped onto them before being merged
    (`domain.answer_area_snapping`), and *before* rather than after the merge
    on purpose: a union of two stereotyped rectangles is not a rectangle the
    page has anywhere, so snapping it would only pick a rule near an edge
    that was never real. The prompt already asks the model to copy these same
    values (`adapters.answer_area_detection._prompt`); doing it again here is
    the second half of the pattern that module documents -- state it once
    where it can be read, once where it can be enforced. When a box moves,
    the reviewer's note says so: a rectangle that shifted on its own is the
    kind of correction the person about to trust it has to be able to see.
    """
    # Grouped by (question number, page) -- **except** for the unassigned
    # ones, which each get a key of their own.
    #
    # `UNASSIGNED_QUESTION_LABEL` does not mean "the same question"; it means
    # "the model could not say". Merging two of them assumes exactly the thing
    # the model just said it could not establish, and a union across two
    # different questions swallows whatever lies between them. Worse, it is
    # irreversible: assigning that one merged rectangle to a question later
    # cannot recover which part belonged to which. Fixing the old
    # `answer_regions[0]` bug by replacing "drop the rest" with "blend the
    # rest" would lose the same information (Issue #105 review round 1, P1).
    #
    # So each unassigned box stays a region of its own, to be confirmed or
    # deleted one at a time -- which is also what makes the confirm gate
    # (`ensure_answer_areas_confirmable`) a per-box decision rather than a
    # single yes/no over a merged blob.
    grouped: dict[tuple[str, int, int], list[DetectedAnswerAreaOutput]] = {}
    for index, area in enumerate(output.areas):
        distinct = index if area.question_number == UNASSIGNED_QUESTION_LABEL else -1
        grouped.setdefault((area.question_number, area.page, distinct), []).append(area)

    regions = [region for region in existing_regions if region.kind is not RegionKind.ANSWER_AREA]
    # Sorted for a stable region order (and so stable region ids) regardless
    # of the order the model happened to list the boxes in: re-running
    # detection on the same response must not reshuffle the overlay.
    for index, key in enumerate(sorted(grouped)):
        number, page, _ = key
        areas = grouped[key]
        notes = [area.note.strip() for area in areas if area.note and area.note.strip()]
        ruling = page_rulings[page - 1] if page - 1 < len(page_rulings) else PageRuling()
        boxes = page_boxes[page - 1] if page - 1 < len(page_boxes) else ()
        located = [_locate(area, boxes=boxes, ruling=ruling) for area in areas]
        shift = max((shifted for _, shifted in located), default=0.0)
        regions.append(
            Region(
                region_id=f"answer-area-{index}",
                kind=RegionKind.ANSWER_AREA,
                page_index=page - 1,
                bbox=_union([bbox for bbox, _ in located]),
                label=number,
                confirmed=False,
                text=_merged_note(len(areas), notes, snap_shift=shift),
            )
        )
    return tuple(regions)


def _locate(
    area: DetectedAnswerAreaOutput,
    *,
    boxes: Sequence[NormalizedBBox],
    ruling: PageRuling,
) -> tuple[NormalizedBBox, float]:
    """One reported area's rectangle, and how far this module had to move it.

    A chosen box needs no repair and reports a shift of ``0.0``: it *is* the
    printed box, measured off the same raster the crop will be taken from. A
    rectangle the model described itself is still snapped onto the printed
    ruling, which is all Issue #122's repair was ever able to do -- and the
    reviewer is still told when that moved it.

    An out-of-range index cannot reach here: `parse_answer_area_detection`
    rejects the whole response for one, rather than quietly dropping the box
    (a partial region set looks exactly like a complete one on the overlay).
    """
    if area.box_indexes:
        return _union([boxes[index] for index in area.box_indexes]), 0.0
    assert area.bbox is not None  # `_exactly_one_location` leaves no third case
    snapped = snap_bbox_to_ruling(area.bbox.to_domain(), ruling)
    return snapped.bbox, snapped.largest_shift


# --------------------------------------------------------------------------- #
# What the reviewer has to be shown, and what stops a confirm
# --------------------------------------------------------------------------- #
def missing_question_numbers(
    regions: Sequence[Region],
    question_numbers: Iterable[str],
    absent_question_numbers: Iterable[str] = (),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The questions with no `ANSWER_AREA` region, split into the two cases a
    person has to act on differently (Issue #164).

    Returns ``(undetected, absent)``:

    * **undetected** -- the sheet should have an answer space for this
      question and none was found. The reviewer draws the box.
    * **absent** -- detection reported that this question has no answer space
      anywhere on the registered sheet. The reviewer fixes the 採点基準 or
      registers the right sheet; drawing a box would invent one.

    ``absent_question_numbers`` is what detection actually said
    (`Profile.absent_question_numbers`), and a number in it only counts as
    absent while it is still a confirmed question with no region -- so a
    reviewer who draws the box anyway (they can see the page; the model
    cannot be right about everything) moves it out of both lists without
    anything having to be un-stored.
    """
    covered = {region.label for region in regions if region.kind is RegionKind.ANSWER_AREA}
    reported_absent = set(absent_question_numbers)
    undetected: list[str] = []
    absent: list[str] = []
    for number in question_numbers:
        if number in covered:
            continue
        (absent if number in reported_absent else undetected).append(number)
    return tuple(undetected), tuple(absent)


#: Aspect ratio (height / width) at or above which a page's answer areas are
#: read as vertical, right-to-left Japanese.
#:
#: **Measured, not chosen** (Issue #171). The median aspect ratio of the
#: answer areas on each of the 8 registered real answer sheets:
#:
#: ==============  =========================================
#: horizontal (6)  0.18, 0.21, 0.23, 0.24, 0.35, 0.46
#: vertical (2)    5.76, 8.91
#: ==============  =========================================
#:
#: Twelve times apart, with nothing in between. The threshold sits in the
#: empty band, and 2 vertical sheets is a small sample -- so what the tests
#: pin is the *property* (a column of writing is far taller than it is wide,
#: a ruled line of writing is far wider than it is tall), never this number.
VERTICAL_ASPECT_RATIO = 2.0


def _reading_key(region: Region, *, vertical: bool) -> tuple[float, float]:
    """Where a region falls in reading order on its page.

    Vertical Japanese reads right to left, so the rightmost column comes
    first; horizontal reads top to bottom, then left to right.
    """
    if vertical:
        return (-region.bbox.x1, region.bbox.y0)
    return (region.bbox.y0, region.bbox.x0)


def _reads_vertically(regions: Sequence[Region]) -> bool:
    ratios = sorted(
        (region.bbox.y1 - region.bbox.y0) / (region.bbox.x1 - region.bbox.x0)
        for region in regions
        if region.bbox.x1 > region.bbox.x0
    )
    if not ratios:
        return False
    return ratios[len(ratios) // 2] >= VERTICAL_ASPECT_RATIO


def reading_order_conflicts(
    regions: Sequence[Region], question_numbers: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """Pairs of questions whose boxes sit in the opposite order to their
    numbers, on the page they share (Issue #171).

    **Why this is worth a check of its own.** Detection can put both boxes
    exactly on the printed columns and still attribute each to the *other*
    question. Measured on the real material, one subject does this every
    time: on a vertical, right-to-left sheet the model pairs each printed
    question label with the neighbouring column rather than its own. Nothing
    else notices -- every question has a box, so no question is undetected,
    the screen says so, and the two answers are then graded against each
    other's rubric. In one real run that produced 0/10 and 0/20, both at high
    confidence, both approved by a person.

    **Why order, and not the printed labels.** Reading the labels needs OCR,
    which would send the whole page to a second vendor and change the basis
    `docs/answer-area-detection.md` §3 gives for sending it to one. The
    order is already in hand: question numbers are a sequence, and boxes on
    paper are laid out in reading order. Measured over the 8 registered
    sheets, the true arrangement matches the declared question order on every
    one of them, and this check fires on exactly the subject that is wrong
    and none of the seven that are right.

    **This names a suspicion; it does not repair one.** The returned pair is
    "these two are in the opposite order to their numbers" -- which of the
    two boxes is the misplaced one is not decidable from the geometry, and
    re-labelling by reading order would be acting on an 8-sheet rule of
    thumb, which is how Issue #122's "consistently 0.035 to the right" went
    wrong.

    Checked per page: a question order spanning two pages says nothing about
    where on either page the boxes sit. A page with fewer than two attributed
    answer areas has no order to contradict.
    """
    rank = {number: index for index, number in enumerate(question_numbers)}
    by_page: dict[int, list[Region]] = {}
    for region in regions:
        if region.kind is not RegionKind.ANSWER_AREA or region.label not in rank:
            continue
        by_page.setdefault(region.page_index, []).append(region)

    conflicts: list[tuple[str, str]] = []
    for page in sorted(by_page):
        on_page = by_page[page]
        # No explicit "fewer than two" guard: `combinations` over a single
        # region is already empty, and a guard no test can distinguish from
        # its absence is a line that only looks like a decision.
        vertical = _reads_vertically(on_page)
        placed = sorted(on_page, key=lambda region: _reading_key(region, vertical=vertical))
        position = {region.label: index for index, region in enumerate(placed)}
        for first, second in combinations(sorted(on_page, key=lambda r: rank[r.label]), 2):
            if position[first.label] > position[second.label]:
                conflicts.append((first.label, second.label))
    return tuple(conflicts)


def question_answer_regions(questions: Sequence[Question]) -> tuple[Region, ...]:
    """`ANSWER_AREA` regions rebuilt from confirmed `Question` rows.

    Intake has no profile file on hand -- only the question table the
    profile became at confirm time -- but `reading_order_conflicts` needs
    the same geometry the detector produced. This is the one-way bridge.
    """
    regions: list[Region] = []
    for question in questions:
        area = question.answer_area
        if area is not None and area.width > 0 and area.height > 0:
            regions.append(
                Region(
                    region_id=question.id,
                    kind=RegionKind.ANSWER_AREA,
                    page_index=question.page - 1,
                    bbox=NormalizedBBox(
                        x0=area.x,
                        y0=area.y,
                        x1=area.x + area.width,
                        y1=area.y + area.height,
                    ),
                    label=question.number,
                )
            )
        area_2 = question.answer_area_2
        if (
            question.page_2 is not None
            and area_2 is not None
            and area_2.width > 0
            and area_2.height > 0
        ):
            regions.append(
                Region(
                    region_id=f"{question.id}:page2",
                    kind=RegionKind.ANSWER_AREA,
                    page_index=question.page_2 - 1,
                    bbox=NormalizedBBox(
                        x0=area_2.x,
                        y0=area_2.y,
                        x1=area_2.x + area_2.width,
                        y1=area_2.y + area_2.height,
                    ),
                    label=question.number,
                )
            )
    return tuple(regions)


def questions_reading_order_conflicts(
    questions: Sequence[Question], question_numbers: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """Pairs of question numbers whose confirmed boxes contradict their order.

    Thin wrapper over :func:`reading_order_conflicts` for the intake path:
    detection's advisory list on `PUT /profile` is not consulted at confirm
    time (Issue #213), so intake re-derives the same suspicion from the
    question rows it is about to crop against.
    """
    return reading_order_conflicts(question_answer_regions(questions), question_numbers)


def conflicted_question_numbers(
    conflicts: Sequence[tuple[str, str]],
) -> frozenset[str]:
    """Every question number that appears in at least one conflict pair."""
    numbers: set[str] = set()
    for first, second in conflicts:
        numbers.add(first)
        numbers.add(second)
    return frozenset(numbers)


def unassigned_answer_area_ids(regions: Sequence[Region]) -> tuple[str, ...]:
    """Region ids of every `ANSWER_AREA` still carrying
    :data:`UNASSIGNED_QUESTION_LABEL`."""
    return tuple(
        region.region_id
        for region in regions
        if region.kind is RegionKind.ANSWER_AREA and region.label == UNASSIGNED_QUESTION_LABEL
    )


def ensure_answer_areas_confirmable(regions: Sequence[Region]) -> None:
    """Raise `UnassignedAnswerAreaError` if any box still has no question.

    `build_questions_and_rubrics` ignores a region whose label matches no
    question rather than raising -- correct in general (a profile is not
    required to be question-shaped end to end), but it means an unassigned
    box would be dropped without a word. This is the check that turns that
    silence into a 422 the reviewer can act on: assign it, or delete it.

    Deliberately not extended to "every question has a box". See this
    module's docstring for why an undetected question is allowed through.
    """
    unassigned = unassigned_answer_area_ids(regions)
    if unassigned:
        raise UnassignedAnswerAreaError(
            f"{len(unassigned)} detected answer area(s) still have no question assigned; "
            "assign each one to a question or delete it before confirming"
        )


# --------------------------------------------------------------------------- #
# Port
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, kw_only=True)
class AnswerAreaDetectionRequest:
    """One answer sheet, rendered for a multimodal model.

    ``page_images`` is **every** page of the sheet, in order, as rendered
    images -- there is no text-layer variant to fall back to (see the module
    docstring). This is the one call in the whole app that sends a *whole
    page* rather than a cropped answer: grading sends one question's crop per
    answer, every time, while detection sends the full pages once per test
    (simplified-design-specification.md §26.1.1). That asymmetry is what
    keeps the exposure of identifying marks to a single call -- and it is not
    the same thing as removing them. **A handwritten name written on the page
    is sent.** There is no reliable way to erase it, and nothing here claims
    to.

    ``question_numbers`` is the confirmed question set the model must choose
    from. Never empty: a caller with no confirmed questions has nothing to
    offer as choices, and must stop before building this.

    ``page_boxes`` is the printed boxes on each page, measured from the very
    images being attached (`adapters.image.ink.measure_page_boxes`), and is
    what a reported area normally *chooses* rather than describes. One entry
    per page, in the order the prompt numbers them; empty means "not
    measured", and the prompt then offers nothing to choose from. A page with
    no printed box at all is a normal page and is listed as such -- see
    `DetectedAnswerAreaOutput`.

    ``page_rulings`` is where the long printed lines actually run on each
    page, measured from the very images being attached
    (`adapters.image.ink.measure_page_ruling`). Issue #122 measured that the
    model does not locate a thin ruled column -- it returns a stereotyped
    one -- so the lines are handed to it as the values to copy from, turning
    "estimate a coordinate" back into the multiple-choice question this
    prompt already makes of question attribution. Empty means "not measured",
    and the prompt simply omits the section; otherwise it must have one entry
    per page, or the numbers would be attached to the wrong image.
    """

    page_images: tuple[bytes, ...]
    question_numbers: tuple[str, ...]
    page_rulings: tuple[PageRuling, ...] = ()
    page_boxes: tuple[tuple[NormalizedBBox, ...], ...] = ()

    def __post_init__(self) -> None:
        if not self.page_images:
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.page_images must not be empty"
            )
        if self.page_rulings and len(self.page_rulings) != len(self.page_images):
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.page_rulings must be empty or have one entry "
                "per page image"
            )
        if self.page_boxes and len(self.page_boxes) != len(self.page_images):
            # An index is only meaningful against the list its page was
            # offered, so a shifted list would attach a question to another
            # page's box -- silently, and with a perfectly plausible
            # rectangle.
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.page_boxes must be empty or have one entry "
                "per page image"
            )
        if any(not image for image in self.page_images):
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.page_images must not contain an empty image"
            )
        if not self.question_numbers:
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.question_numbers must not be empty"
            )
        if UNASSIGNED_QUESTION_LABEL in self.question_numbers:
            # The sentinel is added to the candidate set by the schema
            # builder and the parser. A real question number equal to it
            # would make "the model could not decide" and "the model chose
            # this question" the same value.
            raise AnswerAreaDetectionError(
                "AnswerAreaDetectionRequest.question_numbers must not contain the reserved "
                "unassigned label"
            )


@runtime_checkable
class AnswerAreaDetector(Protocol):
    """Port every answer-area detection adapter implements."""

    @property
    def name(self) -> str: ...

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        """Locate each question's answer box on one answer sheet.

        Raises `domain.ai_provider.SchemaViolation` if the response fails
        validation and `domain.ai_provider.ProviderUnavailable` if the
        provider could not be reached. Never returns a value derived from
        free-text parsing of a response that failed validation.
        """
        ...


class UnconfiguredAnswerAreaDetector:
    """Stand-in for a host with no image-capable provider configured.

    Mirrors `adapters.ai.unconfigured_provider.UnconfiguredAIProvider`: the
    app must be able to open the screen, say *why* detection is unavailable,
    and let the reviewer draw the boxes by hand -- rather than fail at
    startup, or offer a button that dies with an opaque error.

    ``reason`` is built from configuration *variable names* only, never their
    values: it is returned by the API and shown on screen.
    """

    name = "unconfigured"

    def __init__(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("UnconfiguredAnswerAreaDetector.reason must be a non-blank string")
        self.reason = reason

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        raise AnswerAreaDetectionError(self.reason)


def question_number_choices(question_numbers: Sequence[str]) -> list[str]:
    """The candidate list the wire schema's ``question_number`` enum is built
    from: the confirmed question numbers plus the unassigned sentinel.

    Lives here, next to :func:`parse_answer_area_detection`, so the choices
    the model is offered and the set its answer is validated against can only
    ever be built from one place. Offering the sentinel is the point: a model
    with no way to say "I could not tell" answers with a question number it
    does not believe.
    """
    return [*question_numbers, UNASSIGNED_QUESTION_LABEL]
