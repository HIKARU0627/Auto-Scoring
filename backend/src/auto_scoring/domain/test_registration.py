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
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

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


def _bbox_to_rect(bbox: NormalizedBBox) -> NormalizedRect:
    """`NormalizedBBox` (x0/y0/x1/y1, Issue #15) -> `NormalizedRect` (x/y/width/height,
    Issue #11). Both use the same top-left-origin, 0..1 convention (see
    `NormalizedBBox`'s docstring), so this is a pure reshape, no coordinate
    transform.
    """
    return NormalizedRect(x=bbox.x0, y=bbox.y0, width=bbox.x1 - bbox.x0, height=bbox.y1 - bbox.y0)


def _combined_text(regions: Sequence[Region]) -> str | None:
    texts = [region.text.strip() for region in regions if region.text and region.text.strip()]
    return "\n".join(texts) if texts else None


def _require_same_page(
    number: str, question_region: Region, *area_region_groups: Sequence[Region]
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
    """
    for regions in area_region_groups:
        for region in regions:
            if region.page_index != question_region.page_index:
                raise CrossPageRegionError(
                    f"question {number!r}'s {region.kind.value} region is on page "
                    f"{region.page_index + 1}, but its QUESTION region is on page "
                    f"{question_region.page_index + 1}; areas must be on the same "
                    "page as their question"
                )


def _extract_points(score_regions: Sequence[Region]) -> int | None:
    """Pull an integer point value out of the `SCORE` region(s)' text.

    Candidate generation (`domain.profile_candidate_generation`) writes the
    matched number as region text; a human can also type a corrected value in
    directly before confirming. Returns `None` when there is no `SCORE`
    region or its text carries no digits -- the caller treats that as an
    invalid score, not a silent zero (Issue #16 acceptance: "配点不正…を拒否
    する").
    """
    for region in score_regions:
        if not region.text:
            continue
        match = _SCORE_NUMBER_PATTERN.search(region.text)
        if match is not None:
            return int(match.group())
    return None


def build_questions_and_rubrics(
    test_id: str,
    regions: Sequence[Region],
    *,
    default_scoring_method: ScoringMethod = ScoringMethod.ADDITIVE,
) -> tuple[list[Question], list[Rubric]]:
    """Group confirmed `regions` by question number and build the test's
    `Question`/`Rubric` rows.

    Every region's `label` is treated as the question number it belongs to
    (candidate generation and manual region edits both set this) -- a
    `QUESTION` region names the question itself, and any `ANSWER_AREA` /
    `ANNOTATION_AREA` / `SCORE` / `MODEL_ANSWER` / `RUBRIC` region sharing the
    same label is folded into that question. Labels with no `QUESTION` region
    (e.g. a stray manually-added area) are ignored rather than raising, since
    the profile itself is not required to be question-shaped end to end --
    only the labels that *do* have a `QUESTION` region become real questions.

    Raises `DuplicateQuestionNumberError` if the same number has more than
    one `QUESTION` region, `InvalidScoreError` if a question has no usable
    (positive, numeric) score, and `IncompleteRegionsError` if no question
    was found at all.
    """
    grouped: dict[str, dict[RegionKind, list[Region]]] = defaultdict(lambda: defaultdict(list))
    for region in regions:
        grouped[region.label][region.kind].append(region)

    questions: list[Question] = []
    rubrics: list[Rubric] = []
    for number in sorted(grouped):
        kinds = grouped[number]
        question_regions = kinds.get(RegionKind.QUESTION, [])
        if not question_regions:
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
        question_region = question_regions[0]

        score_regions = kinds.get(RegionKind.SCORE, [])
        answer_regions = kinds.get(RegionKind.ANSWER_AREA, [])
        annotation_regions = kinds.get(RegionKind.ANNOTATION_AREA, [])
        model_answer_regions = kinds.get(RegionKind.MODEL_ANSWER, [])
        rubric_regions = kinds.get(RegionKind.RUBRIC, [])

        _require_same_page(
            number, question_region, answer_regions, score_regions, annotation_regions
        )

        points = _extract_points(score_regions)
        if points is None:
            raise InvalidScoreError(
                f"question {number!r} has no valid score (SCORE region missing or non-numeric)"
            )
        if points <= 0:
            raise InvalidScoreError(f"question {number!r} has a non-positive score: {points}")
        if points > _MAX_SQLITE_INTEGER:
            raise InvalidScoreError(f"question {number!r} has a score too large to store: {points}")

        question_id = f"{test_id}:{number}"
        questions.append(
            Question(
                id=question_id,
                test_id=test_id,
                number=number,
                page=question_region.page_index + 1,
                points=points,
                scoring_method=default_scoring_method,
                model_answer=_combined_text(model_answer_regions),
                answer_area=_bbox_to_rect(answer_regions[0].bbox) if answer_regions else None,
                score_area=_bbox_to_rect(score_regions[0].bbox) if score_regions else None,
                comment_area=(
                    _bbox_to_rect(annotation_regions[0].bbox) if annotation_regions else None
                ),
            )
        )

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

    if not questions:
        raise IncompleteRegionsError(
            "no QUESTION regions found; a test needs at least one confirmed question"
        )
    return questions, rubrics
