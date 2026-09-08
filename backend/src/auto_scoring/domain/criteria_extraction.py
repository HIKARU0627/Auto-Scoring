"""Per-question points and marking criteria, read out of a 採点基準PDF and
then corrected by a human (Issue #103).

Registering a test (Issue #101) gets its files onto disk; it does not make
the test gradable. Grading needs a **maximum score per question** and a
rubric to grade against, and until this module existed the only way to
supply either was for a reviewer to hand-place a ``SCORE``/``RUBRIC`` region
on a PDF page and let ``domain.test_registration`` read a number out of its
text with a regular expression. Real material does not support that:

* **6 of the 11 measured subjects' criteria PDFs have no text layer at all**
  (0 extractable characters), and those 6 include every subject whose
  answers are formulae. A text-first path is not a path for them.
* The structural markers a parser would key on are **not present in every
  subject**: one measured subject has no 【解答】/【解説】 headings and is
  written as deductions from a total instead, and three have no ``問N``
  numbering. Counts of ``N点`` ranged from 3 to 39.

So the page **images** are the input, an LLM reads them, and the result is a
*proposal a human edits* -- never something grading consumes directly
(GitHub Issue #95 decision 5 案A: AI proposes per-question points, a human
confirms them). This module holds three things:

1. :class:`CriteriaExtractionOutput` and friends -- the pydantic schema that
   the untrusted LLM response has to satisfy, mirroring ``domain.ai_grading``
   exactly: ``strict=True``, ``extra="forbid"``, and **no free-text
   fallback**. A malformed response becomes a
   :class:`~auto_scoring.domain.ai_provider.SchemaViolation` in the adapter,
   because a wrong number here is a wrong number of *points*, and a test
   graded against it is silently wrong for every submission.
2. :class:`CriteriaDraft` -- the reviewable, editable, persisted form.
3. :func:`criteria_totals` -- the arithmetic the screen shows.

**Unknown is a value here, not an absence.** Every points field is
``int | None``, and ``None`` means "could not be read", never 0 and never 1.
Issue #103's acceptance criteria make this explicit ("黙って 0 件にしない。
『不明』として見せる"), and :func:`criteria_totals` reports the count of
unknowns alongside the sum so a partial total can never be mistaken for a
complete one.

What this module deliberately does **not** cover, so that nothing reads a
capability into it that was not built (Issue #103 "『必ずある』『全教科で動く』
と書かないこと"):

* the 添削資料 (Excel/Word) catalogues of 誤答パターン → 減点 → 赤入れ案.
  Neither format is read at all. See ``docs/criteria-extraction.md``.
* any claim about subjects beyond the 11 that were measured, or about
  extraction *accuracy* on any of them. What was verified is that the
  extraction runs to completion and that whatever it could not read is
  visible as 不明.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from auto_scoring.domain.models import DomainError

#: Same shape as ``domain.ai_grading._NonBlankStr``: ``min_length=1`` alone
#: would accept ``" "``.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

#: Upper bound on any single points value a model may return. Not a rule
#: about real exams -- it is a guard on the one field whose corruption is
#: invisible: a response with a mangled digit run ("50" -> "5000000") would
#: otherwise be stored as a question's maximum score and quietly rescale
#: every grade computed against it. Well above any plausible per-question
#: allocation, and far below ``domain.test_registration``'s SQLite integer
#: ceiling, so a value that trips this is a defect rather than an unusual
#: exam.
MAX_EXTRACTED_POINTS = 10_000

#: Bound on the free-text fields a model returns. Long enough for a full
#: 採点基準 clause or a model answer with a character-count instruction,
#: short enough that a runaway generation is rejected rather than persisted
#: into ``criteria.json`` and re-sent on every later screen load.
MAX_CRITERIA_TEXT_CHARS = 4_000

#: Bound on how many questions one criteria PDF may yield. A model that
#: starts repeating itself must fail the schema rather than produce a
#: thousand-row editing screen a reviewer cannot work through.
MAX_EXTRACTED_QUESTIONS = 200

#: Bound on a question number, in **characters**. Deliberately not the same
#: bound as ``domain.test_registration``'s ``_MAX_QUESTION_NUMBER_BYTES``,
#: which is 40 *bytes* -- 30 Japanese characters is 90 bytes, so a number
#: that satisfies this one can still be rejected there. That is intended:
#: this bound exists to stop a runaway generation from becoming a question
#: number at all, while the byte bound protects a filename component and
#: belongs where the filename is built. A number between the two surfaces as
#: a 422 at confirm time naming the byte limit, which a reviewer can act on
#: -- not as a silent truncation. Real numbers are short ("問1(2)ア").
MAX_QUESTION_NUMBER_CHARS = 30


class CriteriaError(DomainError):
    """A criteria draft could not be built, edited, or confirmed."""


class CriteriaStatus(StrEnum):
    """Whether a human has signed off on this draft.

    One-way, exactly like ``domain.profile.ProfileStatus``: ``CONFIRMED`` is
    the attestation that a person looked at every point value, and there is
    no path back that would let an edit slip in behind that attestation.
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"


class CriterionKind(StrEnum):
    """Whether a criterion adds points or takes them away.

    Both exist in the measured material: most subjects list what earns
    points, and at least one is written entirely as deductions from a full
    allocation. Collapsing the two into a signed number was rejected -- a
    reviewer editing "-2" cannot tell a deduction of 2 from a typo, and the
    grading prompt (``jobs.grading_processor._rubric_text_for``) has to say
    which it is.
    """

    ADD = "add"
    DEDUCT = "deduct"


# --------------------------------------------------------------------------- #
# The untrusted wire boundary (mirrors domain.ai_grading)
# --------------------------------------------------------------------------- #


class ExtractedCriterionOutput(BaseModel):
    """One marking criterion as the model reported it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    description: Annotated[_NonBlankStr, Field(max_length=MAX_CRITERIA_TEXT_CHARS)]
    kind: CriterionKind
    #: ``None`` when the criterion's own point value could not be read --
    #: which happens legitimately (a clause that says 「文意が通らない場合は
    #: 減点」 with no number). Never coerced to 0: a 0-point criterion and an
    #: unread one are different facts, and only the second one needs a human.
    points: int | None = Field(default=None, ge=0, le=MAX_EXTRACTED_POINTS)


class ExtractedQuestionOutput(BaseModel):
    """One question's points, model answer, and criteria as the model
    reported them."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    number: Annotated[_NonBlankStr, Field(max_length=MAX_QUESTION_NUMBER_CHARS)]
    #: The maximum score. ``None`` is the whole point of this field (see the
    #: module docstring): a criteria PDF that does not state a question's
    #: allocation must produce 不明, not a guess.
    points: int | None = Field(default=None, ge=0, le=MAX_EXTRACTED_POINTS)
    #: 【解答】 from the same PDF. `jobs.grading_processor` refuses to grade a
    #: question whose ``model_answer`` is blank, and Issue #95 decision 1
    #: established that the criteria PDF already carries the model answer --
    #: so it is read here rather than requiring a document that does not
    #: exist in real material.
    model_answer: Annotated[str, Field(max_length=MAX_CRITERIA_TEXT_CHARS)] | None = None
    criteria: tuple[ExtractedCriterionOutput, ...] = ()
    #: 1-based pages this question was read from, so a reviewer checking a
    #: value against the original knows where to look. Not validated against
    #: the real page count here (the domain does not know it); the adapter
    #: that rendered the pages does that.
    source_pages: tuple[Annotated[int, Field(ge=1)], ...] = ()
    #: The model's own note about what it could not determine. Shown to the
    #: reviewer verbatim next to the question.
    note: Annotated[_NonBlankStr, Field(max_length=MAX_CRITERIA_TEXT_CHARS)] | None = None


class CriteriaExtractionOutput(BaseModel):
    """The full structured output for one criteria PDF.

    ``questions`` may be **empty**, and that is not a schema violation: a
    criteria PDF the model genuinely could not read must surface as "0 件
    抽出できました" on screen for a human to fill in by hand (Issue #95
    decision 8), not as a failed request that leaves the reviewer with
    nothing and no explanation. What must never happen is an empty result
    being mistaken for a complete one, which is why ``unreadable_pages`` and
    ``note`` travel with it and the confirm step refuses an empty draft.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    questions: tuple[ExtractedQuestionOutput, ...] = Field(
        default=(), max_length=MAX_EXTRACTED_QUESTIONS
    )
    #: The total stated *in the document* (満点), if it states one. Compared
    #: against the sum of the per-question values by :func:`criteria_totals`
    #: -- a mismatch is the cheapest available signal that a question was
    #: missed. ``None`` when the document does not state a total, which is
    #: also what a page-number-looking ``(k/m)`` must produce: Issue #95
    #: decision 5 案A says the boxed ``得点/満点`` is the total and the footer
    #: page number is to be ignored.
    total_points: int | None = Field(default=None, ge=0, le=MAX_EXTRACTED_POINTS)
    unreadable_pages: tuple[Annotated[int, Field(ge=1)], ...] = ()
    note: Annotated[_NonBlankStr, Field(max_length=MAX_CRITERIA_TEXT_CHARS)] | None = None


def parse_criteria_extraction(raw: str | bytes) -> CriteriaExtractionOutput:
    """Parse and validate one provider's raw JSON response.

    Raises ``pydantic.ValidationError`` on any schema violation (a string
    where a number belongs, an unknown key, a negative or absurd points
    value, a blank description, ...). Adapters wrap that in
    :class:`~auto_scoring.domain.ai_provider.SchemaViolation`. There is no
    fallback that salvages a partial result out of invalid JSON -- the same
    rule ``domain.ai_grading.parse_ai_grading_result`` follows, and for a
    stronger reason: this output becomes the maximum score of every
    question in the test.
    """
    return CriteriaExtractionOutput.model_validate_json(raw)


# --------------------------------------------------------------------------- #
# The reviewable, persisted form
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, kw_only=True)
class CriteriaItem:
    """One marking criterion, after a human may have edited it."""

    description: str
    kind: CriterionKind = CriterionKind.ADD
    points: int | None = None

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise CriteriaError("CriteriaItem.description must be a non-blank string")
        if len(self.description) > MAX_CRITERIA_TEXT_CHARS:
            raise CriteriaError(
                f"CriteriaItem.description must be at most {MAX_CRITERIA_TEXT_CHARS} characters"
            )
        if self.points is not None and not 0 <= self.points <= MAX_EXTRACTED_POINTS:
            raise CriteriaError(
                f"CriteriaItem.points must be within 0..{MAX_EXTRACTED_POINTS} when given"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "kind": self.kind.value,
            "points": self.points,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CriteriaItem:
        return cls(
            description=str(data["description"]),
            kind=CriterionKind(data["kind"]),
            points=_optional_int(data.get("points"), "CriteriaItem.points"),
        )


@dataclass(frozen=True, kw_only=True)
class CriteriaQuestion:
    """One question's allocation and criteria, after a human may have edited
    it.

    ``points is None`` is 不明 and is what the screen renders in the 不明
    style and what :func:`ensure_confirmable` refuses to let through.
    """

    number: str
    points: int | None = None
    model_answer: str | None = None
    criteria: tuple[CriteriaItem, ...] = ()
    source_pages: tuple[int, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.number.strip():
            raise CriteriaError("CriteriaQuestion.number must be a non-blank string")
        if len(self.number) > MAX_QUESTION_NUMBER_CHARS:
            raise CriteriaError(
                f"CriteriaQuestion.number must be at most {MAX_QUESTION_NUMBER_CHARS} characters"
            )
        if self.points is not None and not 0 <= self.points <= MAX_EXTRACTED_POINTS:
            raise CriteriaError(
                f"CriteriaQuestion.points must be within 0..{MAX_EXTRACTED_POINTS} when given"
            )
        for field_name, value in (
            ("model_answer", self.model_answer),
            ("note", self.note),
        ):
            if value is not None and len(value) > MAX_CRITERIA_TEXT_CHARS:
                raise CriteriaError(
                    f"CriteriaQuestion.{field_name} must be at most "
                    f"{MAX_CRITERIA_TEXT_CHARS} characters"
                )
        if any(page < 1 for page in self.source_pages):
            raise CriteriaError("CriteriaQuestion.source_pages must all be 1-based page numbers")

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "points": self.points,
            "model_answer": self.model_answer,
            "criteria": [item.to_dict() for item in self.criteria],
            "source_pages": list(self.source_pages),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CriteriaQuestion:
        return cls(
            number=str(data["number"]),
            points=_optional_int(data.get("points"), "CriteriaQuestion.points"),
            model_answer=_optional_str(data.get("model_answer")),
            criteria=tuple(CriteriaItem.from_dict(item) for item in data.get("criteria", ())),
            source_pages=tuple(int(page) for page in data.get("source_pages", ())),
            note=_optional_str(data.get("note")),
        )


@dataclass(frozen=True, kw_only=True)
class CriteriaDraft:
    """Everything a reviewer edits on the 配点と採点基準 panel, plus the
    compare-and-set token that makes "I confirm what I reviewed" mean
    something.

    ``revision`` works exactly like ``domain.profile.Profile.revision``: the
    confirm request names the revision the reviewer actually looked at, and
    the server rejects it if anything has changed since. Without it, a
    second client's save landing between this reviewer's last edit and
    their confirm would have them attest to point values they never saw --
    which for this artefact means every submission is graded out of a
    maximum nobody approved.
    """

    test_id: str
    questions: tuple[CriteriaQuestion, ...] = ()
    #: The total stated in the source document, carried through review so
    #: the mismatch warning survives an edit. ``None`` when the document
    #: stated none, or when the draft was typed in by hand.
    declared_total_points: int | None = None
    unreadable_pages: tuple[int, ...] = ()
    note: str | None = None
    #: ``False`` for a draft a reviewer built entirely by hand -- the escape
    #: hatch Issue #95 decision 8 requires. Recorded so the screen can say
    #: whether anything was ever read from the PDF, rather than leaving an
    #: empty result ambiguous between "not run yet" and "ran, found
    #: nothing".
    extracted: bool = False
    revision: int = 1
    status: CriteriaStatus = CriteriaStatus.DRAFT

    def __post_init__(self) -> None:
        if not self.test_id.strip():
            raise CriteriaError("CriteriaDraft.test_id must be a non-blank string")
        if self.revision < 1:
            raise CriteriaError("CriteriaDraft.revision must be >= 1")
        numbers = [question.number for question in self.questions]
        duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
        if duplicates:
            # Two rows for the same question number would make "what is
            # question 3 worth?" unanswerable, and `build_questions_and_rubrics`
            # would silently keep whichever it saw last.
            raise CriteriaError(
                f"CriteriaDraft has {len(duplicates)} duplicated question number(s)"
            )
        if any(page < 1 for page in self.unreadable_pages):
            raise CriteriaError("CriteriaDraft.unreadable_pages must all be 1-based page numbers")

    def confirm(self) -> CriteriaDraft:
        """Mark this draft signed off. One-way (see :class:`CriteriaStatus`).

        Callers must have run :func:`ensure_confirmable` first; this method
        only performs the state change.
        """
        if self.status is CriteriaStatus.CONFIRMED:
            raise CriteriaError(f"test {self.test_id!r}'s criteria are already confirmed")
        return replace(self, status=CriteriaStatus.CONFIRMED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "questions": [question.to_dict() for question in self.questions],
            "declared_total_points": self.declared_total_points,
            "unreadable_pages": list(self.unreadable_pages),
            "note": self.note,
            "extracted": self.extracted,
            "revision": self.revision,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CriteriaDraft:
        extracted = data.get("extracted", False)
        if not isinstance(extracted, bool):
            raise CriteriaError("CriteriaDraft.extracted must be a boolean")
        return cls(
            test_id=str(data["test_id"]),
            questions=tuple(
                CriteriaQuestion.from_dict(question) for question in data.get("questions", ())
            ),
            declared_total_points=_optional_int(
                data.get("declared_total_points"), "CriteriaDraft.declared_total_points"
            ),
            unreadable_pages=tuple(int(page) for page in data.get("unreadable_pages", ())),
            note=_optional_str(data.get("note")),
            extracted=extracted,
            revision=int(data["revision"]),
            status=CriteriaStatus(data["status"]),
        )


#: Prepended to a question's note when its number had to be disambiguated.
#: See :func:`_unique_number`.
DUPLICATE_NUMBER_NOTE = "同じ設問番号が複数ありました。区別できる番号に直してください。"


def _unique_number(number: str, taken: set[str]) -> str:
    """``number``, or a suffixed variant of it that is not in ``taken``.

    Real documents restart their numbering per section, so a model reading
    one faithfully reports 問1 more than once. `CriteriaDraft` cannot hold
    two rows under one number -- "what is 問1 worth?" would have no answer,
    and `build_questions_and_rubrics` would keep whichever it saw last --
    but dropping the second row is worse still: that is a question, and its
    points, disappearing without a word.

    So the collision is made visible instead. The suffix is bounded by
    :data:`MAX_QUESTION_NUMBER_CHARS`, trimming the base when it has to, so
    that disambiguating a long number cannot itself produce a value
    `CriteriaQuestion` rejects -- which would turn a duplicate back into the
    crash this exists to prevent (found by running the extraction over the
    real material).
    """
    if number not in taken:
        return number
    for index in range(2, len(taken) + 3):
        suffix = f" ({index})"
        base = number[: MAX_QUESTION_NUMBER_CHARS - len(suffix)]
        candidate = f"{base}{suffix}"
        if candidate not in taken:
            return candidate
    # Unreachable: the loop tries more distinct candidates than there are
    # entries in `taken`. Raising rather than returning a duplicate keeps the
    # invariant a real one.
    raise CriteriaError(f"could not disambiguate duplicated question number {number!r}")


def _note_with_duplicate_warning(note: str | None) -> str:
    """``note`` with :data:`DUPLICATE_NUMBER_NOTE` in front of it, trimmed to
    the same length limit the schema enforces."""
    combined = DUPLICATE_NUMBER_NOTE if note is None else f"{DUPLICATE_NUMBER_NOTE} {note}"
    return combined[:MAX_CRITERIA_TEXT_CHARS]


def draft_from_extraction(
    test_id: str, output: CriteriaExtractionOutput, *, revision: int = 1
) -> CriteriaDraft:
    """Turn one validated extraction into an editable draft.

    Field-for-field -- no gap is filled in and no value is inferred. A
    question the model reported with ``points: null`` stays ``None`` all the
    way to the screen, which is the entire contract of this feature.

    The one thing that is not a straight copy is a repeated question number
    (:func:`_unique_number`): it is suffixed and flagged rather than dropped
    or allowed to break the draft's own invariant.
    """
    questions: list[CriteriaQuestion] = []
    taken: set[str] = set()
    for question in output.questions:
        number = _unique_number(question.number, taken)
        taken.add(number)
        questions.append(
            CriteriaQuestion(
                number=number,
                points=question.points,
                model_answer=question.model_answer,
                criteria=tuple(
                    CriteriaItem(description=item.description, kind=item.kind, points=item.points)
                    for item in question.criteria
                ),
                source_pages=question.source_pages,
                note=(
                    _note_with_duplicate_warning(question.note)
                    if number != question.number
                    else question.note
                ),
            )
        )
    return CriteriaDraft(
        test_id=test_id,
        questions=tuple(questions),
        declared_total_points=output.total_points,
        unreadable_pages=output.unreadable_pages,
        note=output.note,
        extracted=True,
        revision=revision,
    )


# --------------------------------------------------------------------------- #
# The arithmetic the screen shows (Issue #103 acceptance criterion 4)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, kw_only=True)
class CriteriaTotals:
    """The sum of what is known, and how much is not known.

    The two always travel together. A bare "38 点" next to a list that
    contains two unread allocations reads as the test's full mark, which is
    the specific way a wrong maximum would reach a grade unnoticed.
    """

    #: Sum of every question whose ``points`` is not ``None``.
    known_points: int
    #: How many questions are still 不明.
    unknown_count: int
    #: What the source document said the total was, if anything.
    declared_total_points: int | None
    #: ``declared_total_points - known_points`` when both a declared total
    #: and a complete set of per-question values exist and they disagree;
    #: ``None`` otherwise. Deliberately **not** computed while any question
    #: is 不明: a difference there is already explained by the missing
    #: values, and reporting it as a discrepancy would send a reviewer
    #: hunting for a second, non-existent problem.
    declared_difference: int | None

    @property
    def is_complete(self) -> bool:
        """Whether every question has a points value a human could confirm."""
        return self.unknown_count == 0


def criteria_totals(draft: CriteriaDraft) -> CriteriaTotals:
    """Per-question sum, unknown count, and the declared-total comparison."""
    known = [question.points for question in draft.questions if question.points is not None]
    unknown_count = len(draft.questions) - len(known)
    known_points = sum(known)
    declared = draft.declared_total_points
    difference: int | None = None
    if declared is not None and unknown_count == 0 and declared != known_points:
        difference = declared - known_points
    return CriteriaTotals(
        known_points=known_points,
        unknown_count=unknown_count,
        declared_total_points=declared,
        declared_difference=difference,
    )


def ensure_confirmable(draft: CriteriaDraft) -> None:
    """Raise unless every question in ``draft`` carries a usable score.

    The gate that keeps 不明 out of the database. ``Question.points`` drives
    every grade computed for that question, so a draft that still has an
    unread allocation must be corrected by a person before it can become
    rows -- not defaulted, not skipped, not stored as 0 (Issue #103
    acceptance criteria 5 and 6).
    """
    if not draft.questions:
        raise CriteriaError(
            "採点基準に設問が 1 件もありません。抽出をやり直すか、設問を手で追加してください。"
        )
    unknown = [question.number for question in draft.questions if question.points is None]
    if unknown:
        raise CriteriaError(
            f"配点が不明の設問が {len(unknown)} 件あります。"
            "すべての配点を入力してから確定してください。"
        )
    non_positive = [
        question.number
        for question in draft.questions
        if question.points is not None and question.points <= 0
    ]
    if non_positive:
        # Mirrors `domain.test_registration`'s own rule. A 0-point question
        # cannot be graded against anything, and letting one through here
        # would only move the failure to confirm time with a less useful
        # message.
        raise CriteriaError(
            f"配点が 0 以下の設問が {len(non_positive)} 件あります。1 以上を入力してください。"
        )


# --------------------------------------------------------------------------- #
# The port
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, kw_only=True)
class CriteriaExtractionRequest:
    """One criteria document, rendered for a multimodal model.

    ``page_images`` is the primary input and is required: 6 of the 11
    measured subjects have no text layer at all, so a request built without
    images could not work for them (module docstring). ``page_texts`` is
    whatever the PDF's own text layer yielded, in the same page order, and
    is **supplementary** -- it lets a model resolve a character its OCR is
    unsure of, and it is empty for the image-only subjects.
    """

    #: PNG (or JPEG) bytes, one per page, in page order.
    page_images: tuple[bytes, ...]
    #: Same length as ``page_images`` when supplied at all; an entry is the
    #: empty string for a page with no extractable text.
    page_texts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.page_images:
            raise CriteriaError("CriteriaExtractionRequest.page_images must not be empty")
        if any(not image for image in self.page_images):
            raise CriteriaError("CriteriaExtractionRequest.page_images must not contain empty data")
        if self.page_texts and len(self.page_texts) != len(self.page_images):
            raise CriteriaError(
                "CriteriaExtractionRequest.page_texts must have one entry per page image"
            )


class CriteriaExtractor(Protocol):
    """Reads a rendered criteria document into a validated proposal.

    Implementations raise
    :class:`~auto_scoring.domain.ai_provider.SchemaViolation` for a response
    that does not satisfy :class:`CriteriaExtractionOutput`, and
    :class:`~auto_scoring.domain.ai_provider.ProviderUnavailable` for a call
    that did not complete -- the same two-exception contract
    ``domain.ai_provider.AIProvider`` declares, so the API layer classifies
    both the same way it already does for grading.
    """

    @property
    def name(self) -> str: ...

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        """Read ``request``'s pages into a validated extraction."""
        ...


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        # `bool` is an `int` subclass; `True` must not silently become 1
        # points. Same guard `domain.ai_provider._DescriptorInput` applies.
        raise CriteriaError(f"{field} must be an integer or null")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CriteriaError("expected a string or null")
    return value
