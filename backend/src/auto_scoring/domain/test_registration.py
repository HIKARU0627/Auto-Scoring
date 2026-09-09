"""Turn a confirmed profile's regions into the `Question`/`Rubric` rows a test
actually needs (Issue #16).

`domain.profile.Profile` (Issue #15/PoC 4) only knows about PDF-layout
regions bound to a document *format* -- it has no idea what a "question" is
in the business sense. This module is the missing bridge: once a human has
confirmed every region, `build_questions_and_rubrics` groups them by question
number (`Region.label`) and produces the `Question`/`Rubric` entities the
rest of the system (submissions, dependency graph, grading) already depends
on.

Validation here covers the Issue #16 acceptance criteria the domain layer is
responsible for: invalid scoring, duplicate question numbers, and regions
that don't add up to a usable question. Out-of-range coordinates are already
rejected by `NormalizedBBox`/`NormalizedRect` themselves.

Issue #103 added a second source for the same rows. Real grading material
has no model-answer PDF to derive a layout from, so most tests never get a
profile at all and the region path alone can produce no questions for them
(`api.test_registration_router.analyze_profile` answers 409 in that case).
A `CriteriaDraft` -- per-question points, criteria, and model answers read
out of the 採点基準PDF and corrected by a human -- can therefore stand in
for, or override, what the regions carry:

* **regions** remain the only source of *coordinates* (which page, and where
  the answer/score/comment areas are);
* **the criteria draft** is the source of *points, criteria, and model
  answers* whenever it has them.

`build_questions_and_rubrics` takes both and is the only place they are
combined, so whichever confirm step runs last -- `/profile/confirm` or
`/criteria/confirm` -- rebuilds the same rows from the same two artefacts
and the order the reviewer works in does not matter. Passing
``criteria=None`` reproduces the pre-Issue-#103 behaviour exactly.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from auto_scoring.domain.annotation_layout import derive_mark_areas
from auto_scoring.domain.criteria_extraction import (
    CriteriaDraft,
    CriteriaQuestion,
    CriterionKind,
)
from auto_scoring.domain.models import (
    DomainError,
    NormalizedRect,
    Question,
    Rubric,
    RubricCriterion,
    ScoringMethod,
)
from auto_scoring.domain.profile import NormalizedBBox, Region, RegionKind


class TestRegistrationError(DomainError):
    """A confirmed profile's regions could not be turned into a valid test."""


class DuplicateQuestionNumberError(TestRegistrationError):
    """Two or more `QUESTION` regions share the same label (question number)."""


class InvalidScoreError(TestRegistrationError):
    """A question has no usable score, or a `SCORE` region wasn't numeric."""


class IncompleteRegionsError(TestRegistrationError):
    """The confirmed regions contain no question at all."""


class CrossPageRegionError(TestRegistrationError):
    """A question's area regions are not all on the same page as its
    `QUESTION` region.
    """


class QuestionsInUseError(TestRegistrationError):
    """Rebuilding this test's questions would destroy grading data.

    `build_questions_and_rubrics`' callers rebuild by **deleting every
    `Question` row and re-inserting** (see `confirm_profile`'s own comment on
    why replace-not-merge is right for a retry). Six tables carry a
    ``question_id`` foreign key declared ``ON DELETE CASCADE`` -- answer
    images, recognitions, grades, criterion results, annotations, review
    history. So once a submission has been imported for this test, that
    delete is not a rebuild, it is **an irreversible loss of every answer
    image and every grade**, and re-inserting a `Question` with an identical
    id does not bring any of it back.

    Until Issue #103 this was unreachable by accident rather than by rule:
    the only rebuild path was `/profile/confirm`, a submission requires the
    test to be READY, READY requires a confirmed profile, and confirming an
    already-confirmed profile is a 409. Issue #103 added a second rebuild
    path with no such lifecycle in front of it -- a test made READY through
    the pre-Issue-#103 `SCORE`-region route has no confirmed criteria, so
    `/criteria/confirm` reached the delete on a test that was already being
    graded (code review P1).

    The rule now exists in its own right, and both paths state it, rather
    than one of them being safe because of a coincidence somewhere else.
    """


class QuestionNumberTooLongError(TestRegistrationError):
    """A question's number/label is too long to become part of a safe
    on-disk filename (see `_MAX_QUESTION_NUMBER_BYTES`).
    """


#: Matches a run of digits that is not itself part of a negative number or a
#: decimal (e.g. rejects the "5" inside "-5" or "5.5" -- a bare `\d+` search
#: would extract a positive integer out of both and let an invalid score
#: through `int(match.group())` without ever reaching the non-positive check
#: below, defeating the "配点不正を拒否する" acceptance criterion). Requires
#: the match not be preceded by `-`/`.`/another digit, nor followed by `.`/
#: another digit. The `{1,19}` bound (19 == len(str(2**63 - 1))) additionally
#: guarantees `int(match.group())` never sees more digits than a legitimate
#: score could ever need: without it, a region whose text happened to
#: contain a run of thousands of digits would make `int()` itself raise
#: `ValueError` (Python's int-string conversion has its own digit-count
#: limit) before `build_questions_and_rubrics` ever reaches its own
#: `_MAX_SQLITE_INTEGER` check below -- and `confirm_profile` only
#: translates `DomainError` into a 422, so that `ValueError` would surface
#: as an unhandled 500 instead of the expected `InvalidScoreError` (Issue
#: #16 review round 6). A run longer than 19 digits simply produces no
#: match at all (every possible sub-run either isn't yet at the real
#: boundary or doesn't start at one), which `_extract_points` already
#: treats as "no valid score".
_SCORE_NUMBER_PATTERN = re.compile(r"(?<![-.\d])\d{1,19}(?![.\d])")

#: Same digit-run boundary as `_SCORE_NUMBER_PATTERN`, but additionally
#: anchored to a following `点` (with optional whitespace in between) --
#: `_extract_points` prefers this whenever a region's text contains it, so
#: a descriptive field like "問1 配点5点" resolves to the score (5) instead
#: of the first standalone integer found anywhere in the text (1, from
#: "問1") -- the maximum this becomes a `Question.points`, which grading
#: depends on, so silently picking the wrong number is worse than
#: rejecting the input outright (Issue #16 review round 8).
_SCORE_WITH_UNIT_PATTERN = re.compile(r"(?<![-.\d])(\d{1,19})(?![.\d])\s*点")

#: `QuestionRow.points`/`RubricCriterionRow.max_points` (db/orm.py) are both
#: SQLite `INTEGER` columns, which store at most a signed 64-bit value.
#: Python's own `int` has no such ceiling, so a `SCORE` region whose text
#: contains a larger positive run of digits would otherwise sail through
#: every check below and only fail once `uow.questions.add()` hands it to
#: the sqlite3 driver, as an unhandled `OverflowError` (500) instead of a
#: normal 422 (Issue #16 review round 5, AGENTS.md "Validate every input
#: that crosses a trust boundary").
_MAX_SQLITE_INTEGER = 2**63 - 1

#: `Question.id` (`f"{test_id}:{number}"`) becomes a filename component --
#: hex-encoded (doubling its UTF-8 byte length) by
#: `LocalFileStore.submission_question_image_path`, itself then wrapped in
#: a temp-file name of its own (a leading ".", that encoded name, a 32-char
#: `uuid4().hex`, and a ".part" suffix) by `write_atomic` -- all of which
#: must fit within Windows' 255-character filename-*component* limit. A
#: 32-char hex `test_id` alone already spends much of that budget; an
#: unbounded, human-editable `number` (profile confirm accepts any string
#: as `Region.label`) could push the final encoded name past the limit,
#: only failing the first time a submission with an answer area tries to
#: finalize -- by which point the profile is already immutable (Issue #16
#: review round 6). Bounded in UTF-8 bytes, not characters: a multi-byte
#: character costs more of the shared budget than an ASCII one.
_MAX_QUESTION_NUMBER_BYTES = 40


def ensure_questions_can_be_rebuilt(*, test_id: str, submission_count: int) -> None:
    """Refuse to rebuild a test's questions once answers have been imported.

    Checked on the **server**, not in the screen: AGENTS.md ("Architecture")
    requires an invariant this important to be guaranteed by something other
    than UI state, and the screen is not the only caller of these endpoints.

    ``submission_count`` is the caller's read of the test's submissions
    inside the same transaction as the rebuild. That read and the delete are
    not isolated from a submission created in between by a *different*
    process -- but importing an answer requires the test to be READY with a
    confirmed dependency graph, and this app is a single-operator desktop
    tool, so the remaining window is not one a person can drive. Stated here
    rather than left for a reader to wonder about.

    The message names the way forward, not just the refusal: a reviewer who
    has to correct a wrong 配点 needs to know that the answer is a new test,
    and that nothing they already have is going to be taken away.
    """
    if submission_count <= 0:
        return
    raise QuestionsInUseError(
        f"このテストにはすでに答案が {submission_count} 件取り込まれています。"
        "設問と配点を作り直すと、取り込んだ答案の画像・文字認識結果・採点結果・"
        "レビュー履歴がすべて失われ、元に戻せません。"
        "配点を直すには、新しいテストとして登録し直してください。"
        "いまのテストと答案はそのまま残ります。"
    )


def _bbox_to_rect(bbox: NormalizedBBox) -> NormalizedRect:
    """`NormalizedBBox` (x0/y0/x1/y1, Issue #15) -> `NormalizedRect` (x/y/width/height,
    Issue #11). Both use the same top-left-origin, 0..1 convention (see
    `NormalizedBBox`'s docstring), so this is a pure reshape, no coordinate
    transform.
    """
    return NormalizedRect(x=bbox.x0, y=bbox.y0, width=bbox.x1 - bbox.x0, height=bbox.y1 - bbox.y0)


def _union_bbox(regions: Sequence[Region]) -> NormalizedRect:
    """The smallest rect covering every region in ``regions`` (never empty).

    Only `ANSWER_AREA` regions are unioned, and only because
    ``Question.answer_area`` is a single rect while a real question's answer
    space is sometimes several separate boxes -- one measured subject gives
    one question five small squares, one per sub-item (Issue #105). Taking
    the first region and ignoring the rest, which is what this did before,
    cropped four fifths of that answer away and said nothing; the student's
    writing simply never reached the grader.

    Deliberately *not* applied to `SCORE` / `ANNOTATION_AREA` below. Those
    are placement points -- where a mark gets drawn on the exported PDF
    (`domain.pdf_export`) -- not crop regions, and the union of two
    placements is a third position where nothing belongs. Those keep
    first-wins.
    """
    return NormalizedRect(
        x=min(region.bbox.x0 for region in regions),
        y=min(region.bbox.y0 for region in regions),
        width=max(region.bbox.x1 for region in regions) - min(region.bbox.x0 for region in regions),
        height=max(region.bbox.y1 for region in regions)
        - min(region.bbox.y0 for region in regions),
    )


def _combined_text(regions: Sequence[Region]) -> str | None:
    texts = [region.text.strip() for region in regions if region.text and region.text.strip()]
    return "\n".join(texts) if texts else None


def _require_same_page(
    number: str, anchor_page_index: int, *area_region_groups: Sequence[Region]
) -> None:
    """`Question.page` (`domain.models.Question`) is a single page, and its
    `answer_area`/`score_area`/`comment_area` rects carry no page of their
    own -- they are only ever interpreted against `question.page`
    (`adapters.submission_intake` crops `answer_area` out of exactly that
    page's rendered image). A reviewer can still place an `ANSWER_AREA` /
    `SCORE` / `ANNOTATION_AREA` region on a different page than its
    `QUESTION` region -- the documented fallback for a question whose
    *prompt* spans two pages (docs/test-registration.md's "設問本文が
    ページをまたぐ場合") -- but doing so would silently crop every
    submission against the wrong page's geometry using coordinates that
    were actually drawn on a different page (Issue #16 review). Represent
    a genuinely multi-page question is out of scope here (same doc's
    "未設計"); reject the mismatch instead so it surfaces as a confirm-time
    error the reviewer can fix via `PUT /profile`, not a silently corrupt
    crop.

    ``anchor_page_index`` is the `QUESTION` region's page when there is one.
    Since Issue #103 a question can exist without a `QUESTION` region (it
    came from the criteria draft, and the reviewer only drew an answer
    area), in which case the first area region's own page anchors the rest
    -- the invariant being checked is "every area of one question is on one
    page", which does not depend on which region named that page.
    """
    for regions in area_region_groups:
        for region in regions:
            if region.page_index != anchor_page_index:
                raise CrossPageRegionError(
                    f"question {number!r}'s {region.kind.value} region is on page "
                    f"{region.page_index + 1}, but its other regions are on page "
                    f"{anchor_page_index + 1}; areas must be on the same "
                    "page as their question"
                )


def _extract_points(score_regions: Sequence[Region]) -> int | None:
    """Pull an integer point value out of the `SCORE` region(s)' text.

    Candidate generation (`domain.profile_candidate_generation`) writes the
    matched number as a bare digit string (e.g. "5"); a human can also type
    a corrected value in directly before confirming -- possibly a
    descriptive phrase like "問1 配点5点" rather than just a number. A
    number immediately followed by "点" is preferred whenever the text
    contains one, so that phrase resolves to 5 (the actual score) rather
    than 1 (the first standalone integer, from "問1"). Text with no "点"
    mention is only accepted if it is *unambiguously* one integer end to
    end (candidate generation's own bare digit string) -- never the first
    number found inside a longer, possibly unrelated sentence (Issue #16
    review round 8: `Question.points` drives grading, so guessing wrong is
    worse than rejecting the input).

    Returns `None` when there is no `SCORE` region or none of the above
    matches -- the caller treats that as an invalid score, not a silent
    zero (Issue #16 acceptance: "配点不正…を拒否する").
    """
    for region in score_regions:
        if not region.text:
            continue
        text = region.text.strip()
        with_unit = _SCORE_WITH_UNIT_PATTERN.search(text)
        if with_unit is not None:
            return int(with_unit.group(1))
        whole_field = _SCORE_NUMBER_PATTERN.fullmatch(text)
        if whole_field is not None:
            return int(whole_field.group())
    return None


def _points_from_draft_or_regions(
    number: str, draft_question: CriteriaQuestion | None, score_regions: Sequence[Region]
) -> int:
    """The question's maximum score, preferring the human-confirmed draft.

    The draft wins whenever it carries a value, because that value went
    through the 配点と採点基準 panel and someone signed off on it, while a
    `SCORE` region's number was read out of free text by
    `_extract_points`'s regular expression. The region path stays as the
    fallback for tests registered before Issue #103, which have no draft at
    all.

    `ensure_confirmable` already refuses a draft with an unknown or
    non-positive value, so reaching the region fallback here means the draft
    genuinely had nothing for this number (e.g. a question that exists only
    as regions).
    """
    if draft_question is not None and draft_question.points is not None:
        points = draft_question.points
    else:
        extracted = _extract_points(score_regions)
        if extracted is None:
            raise InvalidScoreError(
                f"question {number!r} has no valid score (SCORE region missing or non-numeric, "
                "and the confirmed 採点基準 carries no points for it)"
            )
        points = extracted
    if points <= 0:
        raise InvalidScoreError(f"question {number!r} has a non-positive score: {points}")
    if points > _MAX_SQLITE_INTEGER:
        raise InvalidScoreError(f"question {number!r} has a score too large to store: {points}")
    return points


def _rubric_from_draft(
    question_id: str, points: int, draft_question: CriteriaQuestion
) -> tuple[Rubric, ScoringMethod] | None:
    """One `Rubric` built from the draft's per-criterion rows, plus the
    scoring method those rows imply.

    Returns `None` when the draft has no criteria for this question, so the
    caller falls back to the `RUBRIC`-region text.

    Two details the draft carries that `RubricCriterion` cannot:

    * a criterion with no point value of its own (a clause like 「文意が
      通らない場合は減点」 with no number) takes the question's full
      allocation as its `max_points`, which is what the pre-Issue-#103
      single-criterion rubric already did for the whole rubric text;
    * `CriterionKind`. A question whose criteria are *all* deductions is a
      `SUBTRACTIVE` question, and `jobs.grading_processor._rubric_text_for`
      states that method to the provider. In a mixed question the method
      cannot express it, so the deducting rows say so in their own
      description instead -- never dropped, because a deduction silently
      read as an addition inverts the grade.
    """
    if not draft_question.criteria:
        return None
    all_deduct = all(item.kind is CriterionKind.DEDUCT for item in draft_question.criteria)
    scoring_method = ScoringMethod.SUBTRACTIVE if all_deduct else ScoringMethod.ADDITIVE
    criteria = tuple(
        RubricCriterion(
            id=f"{question_id}:rubric:c{index + 1}",
            description=(
                item.description
                if all_deduct or item.kind is CriterionKind.ADD
                else f"減点: {item.description}"
            ),
            max_points=item.points if item.points is not None else points,
            position=index,
        )
        for index, item in enumerate(draft_question.criteria)
    )
    rubric = Rubric(id=f"{question_id}:rubric", question_id=question_id, criteria=criteria)
    return rubric, scoring_method


def build_questions_and_rubrics(
    test_id: str,
    regions: Sequence[Region],
    *,
    default_scoring_method: ScoringMethod = ScoringMethod.ADDITIVE,
    criteria: CriteriaDraft | None = None,
) -> tuple[list[Question], list[Rubric]]:
    """Build the test's `Question`/`Rubric` rows from its confirmed regions
    and, since Issue #103, its confirmed 採点基準 draft.

    Every region's `label` is treated as the question number it belongs to
    (candidate generation and manual region edits both set this) -- a
    `QUESTION` region names the question itself, and any `ANSWER_AREA` /
    `ANNOTATION_AREA` / `SCORE` / `MODEL_ANSWER` / `RUBRIC` region sharing the
    same label is folded into that question.

    A question exists if it has a `QUESTION` region **or** a row in
    ``criteria``. Labels with neither (e.g. a stray manually-added area) are
    ignored rather than raising, since the profile itself is not required to
    be question-shaped end to end.

    Where each field comes from, when both sources have something:

    ==================  ==========================================
    field               source
    ==================  ==========================================
    ``points``          ``criteria`` if it has one, else `SCORE`
    ``criteria``        ``criteria`` if it has any, else `RUBRIC`
    ``model_answer``    ``criteria`` if non-blank, else `MODEL_ANSWER`
    ``page``/areas      regions only (a draft has no coordinates)
    ==================  ==========================================

    A question that exists only in ``criteria`` gets ``page=1`` and no areas.
    That is deliberately not an error: `adapters.submission_intake` already
    flags such a question for human review (``no_answer_area_defined``)
    instead of cropping from guessed coordinates, so the honest outcome is
    a question that grades against the whole page and says so -- not a
    registration that refuses to complete.

    Raises `DuplicateQuestionNumberError` if the same number has more than
    one `QUESTION` region, `InvalidScoreError` if a question has no usable
    (positive, numeric) score from either source, and
    `IncompleteRegionsError` if no question was found at all.
    """
    grouped: dict[str, dict[RegionKind, list[Region]]] = defaultdict(lambda: defaultdict(list))
    for region in regions:
        grouped[region.label][region.kind].append(region)

    draft_questions: dict[str, CriteriaQuestion] = (
        {question.number: question for question in criteria.questions}
        if criteria is not None
        else {}
    )

    questions: list[Question] = []
    rubrics: list[Rubric] = []
    for number in sorted(set(grouped) | set(draft_questions)):
        kinds = grouped.get(number, {})
        draft_question = draft_questions.get(number)
        question_regions = kinds.get(RegionKind.QUESTION, [])
        if not question_regions and draft_question is None:
            continue
        if len(question_regions) > 1:
            raise DuplicateQuestionNumberError(
                f"question number {number!r} has {len(question_regions)} QUESTION regions; "
                "expected exactly one"
            )
        number_bytes = len(number.encode("utf-8"))
        if number_bytes > _MAX_QUESTION_NUMBER_BYTES:
            raise QuestionNumberTooLongError(
                f"question number {number!r} is {number_bytes} bytes, "
                f"exceeding the {_MAX_QUESTION_NUMBER_BYTES}-byte limit"
            )

        score_regions = kinds.get(RegionKind.SCORE, [])
        answer_regions = kinds.get(RegionKind.ANSWER_AREA, [])
        annotation_regions = kinds.get(RegionKind.ANNOTATION_AREA, [])
        model_answer_regions = kinds.get(RegionKind.MODEL_ANSWER, [])
        rubric_regions = kinds.get(RegionKind.RUBRIC, [])

        # The `QUESTION` region names the page when there is one. Otherwise
        # the first area region does, and a question with no regions at all
        # falls back to page 1 -- see this function's own docstring.
        anchor_region = next(
            iter(question_regions or answer_regions or score_regions or annotation_regions), None
        )
        if anchor_region is not None:
            _require_same_page(
                number,
                anchor_region.page_index,
                answer_regions,
                score_regions,
                annotation_regions,
            )

        points = _points_from_draft_or_regions(number, draft_question, score_regions)

        draft_model_answer = draft_question.model_answer if draft_question is not None else None
        model_answer = (
            draft_model_answer.strip()
            if draft_model_answer is not None and draft_model_answer.strip()
            else _combined_text(model_answer_regions)
        )

        question_id = f"{test_id}:{number}"
        scoring_method = default_scoring_method
        from_draft = (
            _rubric_from_draft(question_id, points, draft_question)
            if draft_question is not None
            else None
        )
        if from_draft is not None:
            rubric, scoring_method = from_draft
            rubrics.append(rubric)
        else:
            rubric_text = _combined_text(rubric_regions)
            if rubric_text is not None:
                rubrics.append(
                    Rubric(
                        id=f"{question_id}:rubric",
                        question_id=question_id,
                        criteria=(
                            RubricCriterion(
                                id=f"{question_id}:rubric:c1",
                                description=rubric_text,
                                max_points=points,
                                position=0,
                            ),
                        ),
                    )
                )

        answer_area = _union_bbox(answer_regions) if answer_regions else None
        # Issue #120: a question nobody placed a `SCORE`/`ANNOTATION_AREA`
        # region for still needs somewhere to draw its score and comment --
        # see `derive_mark_areas` for why that is derived from the answer box
        # rather than left `None` (the export used to succeed while writing
        # nothing) and why a hand-placed region still wins.
        derived = derive_mark_areas(answer_area)

        questions.append(
            Question(
                id=question_id,
                test_id=test_id,
                number=number,
                page=(anchor_region.page_index + 1) if anchor_region is not None else 1,
                points=points,
                # Issue #103 supplies the scoring method and model answer
                # (the confirmed 採点基準 draft); Issue #105 supplies the
                # coordinates. Each field comes from whichever artefact
                # actually knows it.
                scoring_method=scoring_method,
                model_answer=model_answer,
                answer_area=answer_area,
                # First-wins, unlike `answer_area` above -- see `_union_bbox`.
                score_area=(
                    _bbox_to_rect(score_regions[0].bbox)
                    if score_regions
                    else (derived[0] if derived is not None else None)
                ),
                comment_area=(
                    _bbox_to_rect(annotation_regions[0].bbox)
                    if annotation_regions
                    else (derived[1] if derived is not None else None)
                ),
            )
        )

    if not questions:
        raise IncompleteRegionsError(
            "no QUESTION regions found; a test needs at least one confirmed question"
        )
    return questions, rubrics
