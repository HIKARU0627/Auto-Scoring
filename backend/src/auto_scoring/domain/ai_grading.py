"""Pydantic schema for AI structured grading output (simplified-design-specification.md
section 9.2, section 10, section 12.1; business-rules-and-evaluation-data.md section 3 (B)).

This is the untrusted-input boundary: an ``AIProvider`` returns raw JSON over the
wire, and this module is the single place that turns it into validated data or
raises. It never falls back to free-text parsing (GitHub Issue #14 acceptance:
"自由文のparseに依存せず、schema不適合をエラーまたは要確認へ送れる") -- a
malformed response is a :class:`SchemaViolation` (see ``ai_provider.py``), not a
best-effort guess.

``pydantic`` is a validation library, not a web framework, an HTTP client, or an
external-service SDK, so using it here does not cross the boundary
``AGENTS.md`` "Architecture" draws for the domain layer (``api -> domain <-
adapters``); ``backend/tests/test_architecture.py`` enforces the actual
forbidden-import list.

Design decisions this schema encodes:

* Recognition confidence and Grading confidence are separate required fields
  (section 10: "文字認識 98% / 採点判断 63%" must be representable
  simultaneously) -- never collapsed into one number.
* ``rationale`` (採点根拠, section 16.5 "採点根拠") is required, not optional:
  Issue #14 asks for score / criterion result / comment / 根拠 / Grading
  Confidence to all be schema-validated.
* ``annotations`` never carry coordinates (section 12.1): the AI returns a
  ``target`` word/phrase and a ``type``; placement is the app's job.
  ``type`` is restricted to :class:`~auto_scoring.domain.models.AnnotationKind`,
  the fixed MVP set (business-rules-and-evaluation-data.md section 2 (5)):
  section 12.1's own illustrative JSON (``"type": "correction"``) predates
  that fixed set and is not itself a valid value -- a provider must return
  one of the enum's members (e.g. ``"underline"``) or the response is a
  schema violation, never silently accepted as an unsupported type that
  would fail later at persistence or rendering time.
* ``comment`` reuses the same character cap as human-confirmed annotation
  comments (``domain.models.MAX_COMMENT_CHARS``,
  business-rules-and-evaluation-data.md section 2 (6): "全角 120 文字") --
  but as a *normalization*, not a rejection. Issue #121: a live run returned
  complete (``finishReason: STOP``) responses whose score, criterion ids and
  question id were all correct, and every one of them was discarded because
  a single annotation comment ran 147 characters. Everything in this schema
  except comment length says whether the grade can be believed; comment
  length says only how much of the comment fits, so it is the comment that
  gives (``domain.models.truncate_comment`` marks the cut). Raising the cap
  would not have helped: while a cap exists, a response will exceed it.
* ``answerImage`` asks what the attached crop *shows*, separately from the
  score (Issue #136). A wrong crop and an unanswered question both produce
  "0 points, confidence 1.00", and on real material half the grades produced
  were the first kind; the model's own rationale already distinguished them
  in prose, and this field is that same judgement in a form the pipeline can
  act on. Deliberately three values plus ``null`` -- see
  :class:`~auto_scoring.domain.models.AnswerImageFinding`.
* Every model is ``strict=True``: a provider sending ``"score": "4"`` or
  ``"confidence": "0.8"`` (a string standing in for a number) is a schema
  violation, not a value to coerce. Required text fields (``comment`` /
  ``rationale`` / criterion ``rationale`` / annotation ``target`` /
  ``type``) also reject a whitespace-only string, since ``min_length``
  alone would let one through.
* **Nothing here asks a provider to copy an identifier back** (Issue #117).
  A criterion is named by its 1-based ``index`` into the rubric as the
  prompt numbered it, and there is no ``questionId`` field at all: one call
  grades one question, so echoing its id proves nothing that the request
  does not already know. Found on real material against real Vertex AI --
  a 45-character rubric criterion id came back with one character
  duplicated, 4 times out of 4, and the grading job failed ``PERMANENT``.
  A JSON Schema constrains the *shape* of a response and can say nothing
  about whether a string inside that shape is an accurate transcription, so
  shortening the id would only have lowered the odds. Mapping ``index``
  back onto the registered criterion ids is
  ``ai_provider.grading_response_from_result``'s job, from the same ordered
  list the prompt was built from.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from auto_scoring.domain.ai_response_language import FIELD_LANGUAGE_NOTE
from auto_scoring.domain.models import (
    AnnotationKind,
    AnswerImageFinding,
    CriterionOutcome,
    truncate_comment,
)

#: A required string that must contain more than just whitespace. Plain
#: ``min_length=1`` accepts ``" "``; this also strips before checking length.
_NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _truncated_comment(value: object) -> object:
    """Cut an over-long comment down to the cap instead of failing the whole
    response (Issue #121); pass anything that is not a string through
    untouched so strict-mode type validation still reports it.
    """
    if isinstance(value, str):
        return truncate_comment(value.strip())
    return value


#: A comment field at this untrusted wire boundary: non-blank like any other
#: required text, but *normalized* to `domain.models.MAX_COMMENT_CHARS`
#: rather than rejected for exceeding it -- see `_truncated_comment` and the
#: module docstring's ``comment`` bullet.
_CommentStr = Annotated[_NonBlankStr, BeforeValidator(_truncated_comment)]

#: Issue #140: the model's own prose about what a mark means, not a
#: verbatim quote -- see `domain.ai_response_language` for why this
#: (unlike ``AnnotationCandidate.target``) carries the language instruction.
_ANNOTATION_COMMENT_DESCRIPTION = "What this mark means." + FIELD_LANGUAGE_NOTE


class RecognitionOutput(BaseModel):
    """What the AI believes the OCR text says, and how sure it is (section 9.2)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    #: Not a ``_NonBlankStr``: an unreadable region is a legitimate empty
    #: string, matching ``domain.ocr.OcrResult`` (never a guessed value).
    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class GradingOutput(BaseModel):
    """The numeric grade and the AI's confidence in *that judgement* (section 10).

    Deliberately a separate model from :class:`RecognitionOutput`: the two
    confidences must never be read from the same field.
    """

    #: ``populate_by_name`` is deliberately *not* set: this is an untrusted
    #: wire boundary (AGENTS.md "Verification"), and the documented contract
    #: (simplified-design-specification.md section 9.2) is the camelCase
    #: alias only. Accepting the Python-style name too would let a provider
    #: that returns ``max_score`` instead of the documented ``maxScore`` pass
    #: as schema-valid, silently understating the real schema violation rate
    #: (code review finding).
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    score: int = Field(ge=0)
    max_score: int = Field(ge=0, alias="maxScore")
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _score_within_max(self) -> GradingOutput:
        if self.score > self.max_score:
            raise ValueError(f"score {self.score} exceeds maxScore {self.max_score}")
        return self


class CriterionResultOutput(BaseModel):
    """One rubric criterion's outcome, confidence, and required rationale.

    ``index`` is which criterion this is: its 1-based position in the rubric
    exactly as the prompt numbered it
    (``jobs.grading_processor.build_rubric_prompt``). Deliberately a small
    integer rather than the criterion's registered id -- see this module's
    docstring, Issue #117. The upper bound is not expressible here (it is
    the calling request's own criterion count, not a property of the wire
    format); ``ai_provider.grading_response_from_result`` enforces it, and
    ``adapters.ai_grading._schema`` additionally pins the exact candidate
    set into the per-request JSON Schema so a provider that enforces the
    schema cannot emit an out-of-range one at all.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    index: int = Field(ge=1)
    result: CriterionOutcome
    confidence: float = Field(ge=0.0, le=1.0)
    #: Issue #140: the description reaches the model's schema, not just the
    #: system instructions -- see `domain.ai_response_language` for why both
    #: places need to say it.
    rationale: Annotated[
        _NonBlankStr,
        Field(description="Why this criterion got this result." + FIELD_LANGUAGE_NOTE),
    ]


class AnnotationCandidate(BaseModel):
    """AI never returns PDF coordinates directly (section 12.1): ``target`` +
    ``type`` (+ optional comment) only -- placement is decided by the app.

    ``comment`` is required (and so cannot be blank -- ``_NonBlankStr``) when
    ``type`` is :attr:`~auto_scoring.domain.models.AnnotationKind.COMMENT`:
    a comment-kind annotation with no comment text has nothing to display,
    and ``domain.models.Annotation`` requires non-blank text to construct
    one later. Rejecting it here, at the untrusted response boundary, keeps
    that failure a schema violation instead of a crash at persistence or
    rendering time (code review finding).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    #: The description reaches the model: it is what the generated JSON
    #: Schema carries for this field, and until Issue #141 there was none --
    #: the model was handed a bare ``{"type": "string"}`` and told nothing
    #: about what a usable ``target`` is. In the live re-verification several
    #: models filled it with text that is nowhere in the answer: a reading
    #: tidied up into correct notation, a handwritten formula rewritten in
    #: LaTeX, two non-adjacent sub-answers joined into one string, and in one
    #: case an invented placeholder for a blank answer. None of those can be
    #: found among the OCR boxes, so none of them could be placed.
    target: _NonBlankStr = Field(
        description=(
            "The text this annotation is about, copied verbatim from the "
            "student's OCR reading: the same characters in the same order, "
            "as one contiguous run, exactly as they appear there. Do not "
            "correct, normalize, translate, re-notate (for example into "
            "LaTeX) or tidy it, and do not join text from separate parts of "
            "the answer. The application finds this text among the reading's "
            "word boxes to decide where to draw the mark; text that does not "
            "appear there verbatim cannot be placed on the answer. If no "
            "verbatim quote fits what you mean, leave the annotation out."
        )
    )
    type: AnnotationKind
    #: Issue #140: unlike ``target`` above, this is the model's own prose
    #: (what the mark means), not a verbatim quote -- so it gets the
    #: language instruction ``target`` deliberately does not.
    comment: Annotated[_CommentStr, Field(description=_ANNOTATION_COMMENT_DESCRIPTION)] | None = (
        None
    )

    @model_validator(mode="after")
    def _comment_type_requires_comment_text(self) -> AnnotationCandidate:
        if self.type == AnnotationKind.COMMENT and self.comment is None:
            raise ValueError("annotation type 'comment' requires a non-blank 'comment' field")
        return self


class AIGradingResult(BaseModel):
    """The full structured output for one question (section 9.2 example).

    Carries no question identifier (Issue #117): the response belongs to
    the single question its request named, and the caller maps it back from
    that request rather than from anything the model wrote.
    """

    #: See :class:`GradingOutput` -- ``populate_by_name`` is deliberately
    #: off at this untrusted wire boundary: only the documented camelCase
    #: aliases are accepted, not the Python-style field names (code review
    #: finding).
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    recognition: RecognitionOutput
    grading: GradingOutput
    criteria: tuple[CriterionResultOutput, ...] = Field(min_length=1)
    #: Issue #140: both are the model's own prose (the overall comment/根拠
    #: shown to the teacher, section 16.5), so both get the language
    #: instruction in their schema description as well as in the system
    #: instructions -- see `domain.ai_response_language`.
    comment: Annotated[
        _CommentStr,
        Field(description="Overall comment for the student's answer." + FIELD_LANGUAGE_NOTE),
    ]
    rationale: Annotated[
        _NonBlankStr,
        Field(description="Why this grade was given, overall." + FIELD_LANGUAGE_NOTE),
    ]
    annotations: tuple[AnnotationCandidate, ...] = ()
    #: What the model says the attached image actually shows
    #: (`domain.models.AnswerImageFinding`, Issue #136) -- the crop it was
    #: given, not the answer it graded.
    #:
    #: **Nullable, and absence is not a claim.** ``None`` means the provider
    #: reported nothing, and is read as exactly that: the recorded PoC
    #: datasets predate this field, and a provider that ignores it must keep
    #: behaving the way it does today rather than being credited with
    #: vouching for the crop. `adapters.ai_grading._schema` still lists it in
    #: the strict schema's ``required`` (that is what that module does to
    #: every property), so a provider that enforces the schema has to answer
    #: -- with ``null`` if it will not commit to one of the three values.
    #:
    #: A single three-valued field rather than two booleans: "this is not the
    #: answer" and "the answer is blank" are different claims about different
    #: things, and a model cannot make both at once. Two flags would let it,
    #: and a caller would then have to decide which one it meant.
    answer_image_finding: AnswerImageFinding | None = Field(default=None, alias="answerImage")

    @model_validator(mode="after")
    def _criteria_indices_unique(self) -> AIGradingResult:
        indices = [c.index for c in self.criteria]
        if len(indices) != len(set(indices)):
            raise ValueError("criteria names the same rubric position twice")
        return self


#: Stands in for an ``extra_forbidden`` error's own ``loc`` segment (see
#: `describe_schema_violation`) -- never the real key.
_UNEXPECTED_FIELD_LABEL = "<unexpected field>"


def describe_schema_violation(error: ValidationError) -> str:
    """Which fields failed and why, with nothing that could be a value.

    Issue #121: `Job.last_error` stopped at ``[gemini SchemaViolation]``, so
    working out *why* a question failed permanently meant capturing the
    provider's response by hand. The field path and pydantic's error code
    are both fixed literals -- ``loc`` segments are this module's own field
    names and list indices, ``type`` is one of pydantic's own codes -- so
    both can be reported, which is the same "assemble diagnosis out of safe
    parts" rule `domain.ai_provider.ProviderAttempt` follows.

    What is never reported is ``error["input"]``: at this boundary that can
    be OCR'd student answer text, and ``str(ValidationError)`` (and so any
    f-string embedding it, or any default traceback printed for a chained
    exception) includes it for every error (AGENTS.md "Security").

    One ``loc`` segment is not a literal of this module: for an
    ``extra_forbidden`` error, pydantic's last segment *is* the unrecognized
    key, copied verbatim from the provider's response -- a model that echoed
    student text as a stray JSON key would otherwise carry it straight into
    this "safe" summary. That segment, and only that one, is replaced.
    """
    parts = []
    for detail in error.errors():
        loc = list(detail["loc"])
        if detail["type"] == "extra_forbidden" and loc:
            loc[-1] = _UNEXPECTED_FIELD_LABEL
        parts.append(f"{'.'.join(str(segment) for segment in loc)}: {detail['type']}")
    return "; ".join(parts) if parts else "validation failed"


def parse_ai_grading_result(raw: str | bytes) -> AIGradingResult:
    """Parse and validate one provider's raw JSON response.

    Raises ``pydantic.ValidationError`` on any schema violation (missing
    field, wrong type, score > maxScore, empty ``rationale``/``comment``,
    a rubric position named twice, unknown extra field, ...). Callers
    (``ai_provider`` adapters and the PoC harness) wrap this in
    :class:`auto_scoring.domain.ai_provider.SchemaViolation`
    -- there is no fallback that extracts a partial answer from invalid JSON
    or free text.
    """
    return AIGradingResult.model_validate_json(raw)
