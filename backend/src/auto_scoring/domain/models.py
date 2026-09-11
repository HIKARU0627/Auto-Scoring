"""MVP business entities and their invariants.

Framework-free: this module imports only the standard library (see `AGENTS.md`
"Architecture" — the domain must not import FastAPI, SQLAlchemy, HTTP clients,
or any external SDK). Persistence lives in `auto_scoring.db` /
`auto_scoring.adapters`; this module only describes the shape of the data and
the rules that must always hold.

Design decisions this module encodes (sources in `docs/`):

* AI proposals and human-confirmed values are *separate* records. ``source`` on
  :class:`RecognitionResult` / :class:`GradeResult` / :class:`Annotation`
  distinguishes them; nothing here mutates an existing result
  (simplified-design-specification.md §19, §35-5).
* Recognition confidence and grading confidence are held independently
  (§10).
* Submission and job state machines only allow the transitions listed below
  (§25, business-rules-and-evaluation-data.md §4.4).
* Scores stay within ``0..maximum``; normalized coordinates stay within
  ``0..1`` (issue #11 acceptance: "配点範囲外の値を … 拒否する").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

_EPS = 1e-9

#: A client posting directly to the API (bypassing the Flutter UI, which
#: never sends more than a short label) could otherwise pack most of the
#: request size limit into this one field -- it's stored verbatim and
#: returned in full on every submissions-list response, so a handful of
#: megabyte-scale labels would bloat both the database and every response's
#: memory footprint (AGENTS.md "Validate every input that crosses a trust
#: boundary"). ``migrations/versions/0006_student_label_length.py`` mirrors
#: this as a DB CHECK constraint, a second line of defence.
MAX_STUDENT_LABEL_LENGTH = 200

#: Same reasoning as ``MAX_STUDENT_LABEL_LENGTH``, for the multipart upload's
#: client-supplied filename: nothing but ``.pdf`` at the end and printable
#: characters is required, and the whole body can be up to ~50MiB, so a
#: client posting directly to the API could otherwise pack an arbitrarily
#: long name into ``original_filename`` -- stored verbatim, returned on every
#: submission response. Enforced in ``domain.pdf_intake.validate_filename``
#: (the first, cheapest check on a fresh upload) and mirrored as a DB CHECK
#: constraint in ``migrations/versions/0007_original_filename_length.py``.
MAX_ORIGINAL_FILENAME_LENGTH = 255

#: Same reasoning as ``MAX_STUDENT_LABEL_LENGTH``: an authenticated caller of
#: ``POST /tests`` can send ``name``/``subject`` as multipart form fields up
#: to the whole request's own size limit, and both are stored verbatim and
#: returned in full on every test-registration list response -- a handful of
#: megabyte-scale values would bloat both the database and every such
#: response's memory footprint (AGENTS.md "Validate every input that
#: crosses a trust boundary"). Enforced in ``Test.__post_init__``, the same
#: place ``Test.id``/``Test.name`` non-emptiness already is (Issue #16
#: review round 8).
MAX_TEST_NAME_LENGTH = 200
MAX_TEST_SUBJECT_LENGTH = 200

#: Upper bound for a single annotation comment, in characters
#: (business-rules-and-evaluation-data.md §2 (6): "全角 120 文字"). Mirrored
#: as DB CHECK constraints (`migrations/versions/0012_grade_result_ai_metadata.py`,
#: `0013_review_history_edit.py`), so it is a real limit on what can be
#: stored, not only a validation rule.
MAX_COMMENT_CHARS = 120

#: Appended by `truncate_comment` to a comment it had to cut, so the cut is
#: visible in every place the comment is later shown (review screen, exported
#: PDF) rather than silently changing the text. The same character the PDF
#: engine already uses for text that overflows its mark's rect
#: (`adapters.pdf.pdfium_pypdf_engine._ELLIPSIS`) -- one truncation mark for
#: the whole project, not a second vocabulary.
COMMENT_TRUNCATION_MARK = "…"


def truncate_comment(text: str) -> str:
    """``text`` cut down to fit `MAX_COMMENT_CHARS`, marked as cut.

    Issue #121: an AI response whose score, criterion ids and question id
    were all correct was discarded whole because one comment ran 147
    characters against the 120-character cap. Raising the cap does not fix
    that -- while a cap exists, a response will exceed it -- so an over-long
    comment is cut here instead of costing the grade it came with. The
    caller decides *whether* a given comment is allowed to be cut; a
    human-entered one still is not (`api.review_router` rejects it at the
    request boundary, where the person can shorten it themselves).

    Trailing whitespace on the kept prefix is dropped before the mark, so a
    cut in the middle of a space does not read as "…" floating away from the
    text. The result is therefore *at most* `MAX_COMMENT_CHARS`, not always
    exactly it.
    """
    if len(text) <= MAX_COMMENT_CHARS:
        return text
    kept = text[: MAX_COMMENT_CHARS - len(COMMENT_TRUNCATION_MARK)].rstrip()
    return kept + COMMENT_TRUNCATION_MARK


#: Same reasoning as ``MAX_STUDENT_LABEL_LENGTH``: a human's manual-entry
#: recognition text (Issue #19, ``POST .../recognitions``) is the other new
#: free-text field a client posting directly to the API could otherwise pack
#: without bound -- stored verbatim, returned on every history read.
#: ``migrations/versions/0010_recognition_text_length.py`` mirrors this as a
#: DB CHECK constraint. Generous relative to any real answer-area transcript,
#: which is what an actual OCR provider's own text is bounded by in practice.
MAX_RECOGNIZED_TEXT_LENGTH = 10_000


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class DomainError(Exception):
    """A domain rule was violated."""


class InvalidStateTransition(DomainError):
    """A state machine was asked for a move it does not allow."""

    def __init__(self, entity: str, current: object, target: object) -> None:
        super().__init__(f"{entity}: cannot move from {current!s} to {target!s}")
        self.entity = entity
        self.current = current
        self.target = target


class ScoreOutOfRange(DomainError):
    """A score or point value fell outside its allowed range."""


class InvalidCoordinate(DomainError):
    """A normalized coordinate fell outside ``0..1`` (or its rect left the page)."""


class JobSaveConflict(DomainError):
    """A `Job` row changed state after it was read, before this save could apply.

    Distinct from `InvalidStateTransition`: that means "this state machine
    forbids this move"; this means "some other writer already moved the row
    since we last read it", detected by the compare-and-set in
    `JobRepository.save` (Issue #26 review: without this, a worker's
    completion write -- validated in Python against a stale read -- could
    silently overwrite a `CANCELLED` another transaction had already
    committed, since a plain ORM ``UPDATE`` matches on primary key only).
    """

    def __init__(self, job_id: str, expected_state: object) -> None:
        super().__init__(
            f"job {job_id!r}: expected state {expected_state!s} no longer matches "
            "the persisted row; it was changed by another writer"
        )
        self.job_id = job_id
        self.expected_state = expected_state


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class ScoringMethod(StrEnum):
    """Per-question scoring style; the marking manual is authoritative (§2 (8))."""

    ADDITIVE = "additive"
    SUBTRACTIVE = "subtractive"


class TestStatus(StrEnum):
    """Registration lifecycle of one test (Issue #16, simplified-design-spec.md §6.1).

    A test starts ``DRAFT`` the moment its two PDFs are registered and stays
    there through candidate generation and human review of the profile and
    dependency graph. Only an explicit, one-way move to ``READY`` (see
    ``Test.mark_ready``) unblocks answer processing for it -- there is no path
    back to ``DRAFT``.
    """

    #: Not a pytest test class -- only named ``TestStatus`` because it
    #: describes ``Test.status``. Without this, pytest's default
    #: ``Test*``-prefix collection heuristic tries (and fails) to collect it,
    #: emitting a `PytestCollectionWarning` on every run.
    __test__ = False

    DRAFT = "draft"
    READY = "ready"


class GradingSource(StrEnum):
    """Who produced a result. AI values are proposals; humans confirm (§17)."""

    AI = "ai"
    HUMAN = "human"


class CriterionOutcome(StrEnum):
    """Result of one rubric criterion (§9.2)."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class AnnotationKind(StrEnum):
    """Annotation types fixed for the MVP (§2 (5)). Extensible later."""

    CIRCLE = "circle"
    CROSS = "cross"
    TRIANGLE = "triangle"
    SCORE = "score"
    COMMENT = "comment"
    UNDERLINE = "underline"
    BOX = "box"


class SubmissionState(StrEnum):
    """Lifecycle of one student's submission (§25)."""

    UNPROCESSED = "unprocessed"
    AI_PROCESSING = "ai_processing"
    AI_PROCESSED = "ai_processed"
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    EXPORTED = "exported"
    ERROR = "error"


class JobKind(StrEnum):
    """What a background job does (§29, §3.4)."""

    RECOGNITION = "recognition"
    GRADING = "grading"
    EXPORT = "export"


class JobState(StrEnum):
    """Lifecycle of a background job. ``BLOCKED`` = waiting on a dependency (§4.4).

    ``BLOCKED`` covers both "a prerequisite is still processing" and "a
    prerequisite finished but was not usable (low confidence, failed, or
    cancelled)" -- Issue #18 deliberately does not add a separate
    "locked_by_dependency" state for the latter, since the machine behaviour
    is identical (stay put, never call the external provider, resume only
    when the prerequisite becomes usable). See docs/job-queue.md
    "`BLOCKED`を「待機中」と「前提がusableでないためロック中」の両方に使う".
    """

    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(StrEnum):
    """How a failed `Job` attempt is classified for retry purposes (Issue #18).

    Only ``TIMEOUT``/``RATE_LIMITED``/``SERVER_ERROR`` are retryable
    (docs/job-queue.md "retry対象の分類"); ``PERMANENT`` never is. Deciding
    which category a real provider failure belongs to is the concrete
    `auto_scoring.domain.job_execution.JobProcessor` implementation's
    responsibility (a later issue), not this enum's.
    """

    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    PERMANENT = "permanent"


#: Categories a queue worker should automatically retry (docs/job-queue.md).
RETRYABLE_ERROR_CATEGORIES = frozenset(
    {ErrorCategory.TIMEOUT, ErrorCategory.RATE_LIMITED, ErrorCategory.SERVER_ERROR}
)


class ReviewAction(StrEnum):
    """The human decision recorded in the operation history (§19, Issue #22).

    ``APPROVED``/``MODIFIED``/``REJECTED`` are the original three (Issue #21's
    domain groundwork). Issue #22 adds the remaining two: ``REGRADE_REQUESTED``
    (a human asked the AI to redo this question -- see
    ``adapters.review_actions.regrade_question``) and ``UNDONE`` (Ctrl+Z:
    revert the immediately preceding human operation as a *new* row, per
    ``docs/review-edit-history.md`` "Undo" -- the reverted row itself is never
    deleted, matching this table's append-only design).
    """

    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"
    REGRADE_REQUESTED = "regrade_requested"
    UNDONE = "undone"


#: `ReviewAction` values whose effect is "this question's grade is confirmed"
#: (`docs/review-edit-history.md` "確定済みの定義"). Used both to gate a
#: `Submission`'s `REVIEWED` transition (see
#: `domain.review_workflow.all_questions_confirmed`) and by the review UI to
#: decide whether "承認して次へ" still needs to record a fresh confirmation or
#: may just navigate (the question is already confirmed by an ``APPROVED``
#: or ``MODIFIED`` row that Undo has not since reverted).
CONFIRMED_REVIEW_ACTIONS = frozenset({ReviewAction.APPROVED, ReviewAction.MODIFIED})


class AnswerImageStatus(StrEnum):
    """Outcome of extracting one question's answer-area image from a submission
    (§7.1, §24 "回答欄検出失敗"). ``NEEDS_REVIEW`` means the crop could not be
    trusted (e.g. the submission's page count didn't match the test's
    registered pages) and the original page image is shown to a human instead.
    """

    OK = "ok"
    NEEDS_REVIEW = "needs_review"


class AnswerImageFinding(StrEnum):
    """What the grading AI reports it actually saw in the answer image it was
    given -- as distinct from the score it awarded (Issue #136).

    Three values, not a boolean, and the reason is the whole point. On the
    real re-run that produced this Issue, 7 of the 14 questions that got a
    grade were a **wrong** 0 with confidence 1.00, and the AI's own rationale
    already said so in two different ways:

    * 2 said the image it was given is not this question's answer at all
      (one described a header field, one described another question's
      label) -- :attr:`NOT_THE_ANSWER`;
    * 4 said only that the answer is blank -- :attr:`BLANK`.

    Collapsing those into one "something is wrong" flag would put the same
    flag on a genuinely unanswered question, which is a real thing a student
    does and a correct 0. So the two claims stay separate values, and only
    :attr:`NOT_THE_ANSWER` currently stops a grade
    (`jobs.grading_processor`): a crop that does not show this question's
    answer is a *detection* failure, and no score derived from it means
    anything. :attr:`BLANK` is recorded and otherwise left alone until the
    frequency of genuinely unanswered questions has been measured -- see
    docs/ai-grading-pipeline.md.

    ``None`` (the field's absence) is its own, fourth state everywhere this
    appears: the provider did not report anything. It is never read as
    :attr:`ANSWER` -- that would be vouching for a crop nothing looked at.
    """

    #: The image shows this question's answer area, with an answer in it.
    ANSWER = "answer"
    #: The image shows this question's answer area, and nothing is written
    #: in it. A grade produced from this may well be a correct 0.
    BLANK = "blank"
    #: The image does not show this question's answer area at all (it shows
    #: another question, a header, a label, or the margin). Nothing graded
    #: from it can be trusted.
    NOT_THE_ANSWER = "not_the_answer"


# --------------------------------------------------------------------------- #
# State machines
# --------------------------------------------------------------------------- #
_SUBMISSION_TRANSITIONS: dict[SubmissionState, frozenset[SubmissionState]] = {
    SubmissionState.UNPROCESSED: frozenset({SubmissionState.AI_PROCESSING, SubmissionState.ERROR}),
    SubmissionState.AI_PROCESSING: frozenset({SubmissionState.AI_PROCESSED, SubmissionState.ERROR}),
    SubmissionState.AI_PROCESSED: frozenset(
        {
            SubmissionState.NEEDS_REVIEW,
            # A submission intake finished cleanly reaches REVIEWED directly,
            # without the NEEDS_REVIEW detour (§25.1, Issue #112). NEEDS_REVIEW
            # means "intake could not pin the answer areas" -- it carries a
            # `review_reason` saying which (`adapters.submission_intake`) -- so
            # routing a clean submission through it to record that a human
            # confirmed every question would be claiming an intake problem that
            # never happened.
            SubmissionState.REVIEWED,
            SubmissionState.AI_PROCESSING,
            SubmissionState.ERROR,
        }
    ),
    SubmissionState.NEEDS_REVIEW: frozenset(
        {
            SubmissionState.REVIEWED,
            SubmissionState.AI_PROCESSING,
            SubmissionState.ERROR,
        }
    ),
    SubmissionState.REVIEWED: frozenset(
        {
            SubmissionState.EXPORTED,
            SubmissionState.NEEDS_REVIEW,
            # The way back out of REVIEWED for a submission that entered it from
            # AI_PROCESSED (Issue #112). Undo can un-confirm a question at any
            # time, and the submission then has to return to *where intake left
            # it*: sending a cleanly-intaken submission to NEEDS_REVIEW instead
            # would raise the one flag this app reserves for "a human must look
            # before this can go on" (`docs/design-tokens.md` §3.1) over a
            # submission with nothing wrong with it, and nothing would ever
            # lower it again. `adapters.review_actions` picks between the two
            # using `review_reason`.
            SubmissionState.AI_PROCESSED,
            SubmissionState.ERROR,
        }
    ),
    SubmissionState.EXPORTED: frozenset({SubmissionState.NEEDS_REVIEW}),
    SubmissionState.ERROR: frozenset({SubmissionState.UNPROCESSED, SubmissionState.AI_PROCESSING}),
}

_JOB_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.BLOCKED, JobState.CANCELLED}),
    JobState.RUNNING: frozenset(
        {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.BLOCKED,
            JobState.CANCELLED,
            # Startup crash recovery only (Issue #18: a job left RUNNING by a
            # killed process is requeued, not treated as failed, when it
            # still has retry attempts left) -- see
            # `domain.job_scheduling.recover_running_job`. Application code
            # never uses this transition directly.
            JobState.QUEUED,
        }
    ),
    JobState.BLOCKED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.FAILED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.SUCCEEDED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def ensure_submission_transition(
    current: SubmissionState, target: SubmissionState
) -> SubmissionState:
    """Return ``target`` if reachable from ``current``, else raise."""
    if target not in _SUBMISSION_TRANSITIONS[current]:
        raise InvalidStateTransition("submission", current, target)
    return target


def ensure_job_transition(current: JobState, target: JobState) -> JobState:
    """Return ``target`` if reachable from ``current``, else raise."""
    if target not in _JOB_TRANSITIONS[current]:
        raise InvalidStateTransition("job", current, target)
    return target


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _require_non_empty(field: str, value: str) -> None:
    if not value or not value.strip():
        raise DomainError(f"{field} must be a non-empty string")


def _require_confidence(field: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise DomainError(f"{field} must be within 0..1, got {value}")


def _require_unique(field: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise DomainError(f"{field} contains duplicates")


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, kw_only=True)
class NormalizedRect:
    """A rectangle in page-normalized coordinates (0..1 on both axes, §5.2)."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        for name, value in (
            ("x", self.x),
            ("y", self.y),
            ("width", self.width),
            ("height", self.height),
        ):
            if not 0.0 <= value <= 1.0:
                raise InvalidCoordinate(f"{name} must be within 0..1, got {value}")
        if self.x + self.width > 1.0 + _EPS:
            raise InvalidCoordinate("x + width must not exceed 1.0")
        if self.y + self.height > 1.0 + _EPS:
            raise InvalidCoordinate("y + height must not exceed 1.0")


@dataclass(frozen=True, kw_only=True)
class Score:
    """An awarded point value bounded by its maximum."""

    awarded: int
    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < 0:
            raise ScoreOutOfRange("maximum must be non-negative")
        if not 0 <= self.awarded <= self.maximum:
            raise ScoreOutOfRange(f"awarded {self.awarded} outside range 0..{self.maximum}")


@dataclass(frozen=True, kw_only=True)
class BoundingBox:
    """One OCR word box, used to place text-anchored annotations (§12.3).

    ``unreadable`` marks a span the provider returned but could not read
    (below the configured Recognition Confidence threshold when it was
    recognized -- `domain.ocr.unreadable_spans`). Kept per box, rather than
    as one number on the row, because *where* the reading is missing is what
    a human can act on, and because a count on its own grows with the length
    of the answer (Issue #158, docs/ocr-recognition-pipeline.md §9).

    Rows written before Issue #158 carry no such flag and read back as
    ``False``; they still carry the row's `RecognitionResult.confidence`.
    """

    text: str
    rect: NormalizedRect
    unreadable: bool = False


@dataclass(frozen=True, kw_only=True)
class CriterionResult:
    """Outcome of a single rubric criterion within a grade."""

    criterion_id: str
    outcome: CriterionOutcome
    confidence: float | None = None

    def __post_init__(self) -> None:
        _require_non_empty("CriterionResult.criterion_id", self.criterion_id)
        if self.confidence is not None:
            _require_confidence("CriterionResult.confidence", self.confidence)


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, kw_only=True)
class Test:
    """A registered test (one set of model answer + marking manual)."""

    id: str
    name: str
    created_at: datetime
    subject: str | None = None
    default_scoring_method: ScoringMethod = ScoringMethod.ADDITIVE
    status: TestStatus = TestStatus.DRAFT

    def __post_init__(self) -> None:
        _require_non_empty("Test.id", self.id)
        _require_non_empty("Test.name", self.name)
        if len(self.name) > MAX_TEST_NAME_LENGTH:
            raise DomainError(f"Test.name must be at most {MAX_TEST_NAME_LENGTH} characters")
        if self.subject is not None and len(self.subject) > MAX_TEST_SUBJECT_LENGTH:
            raise DomainError(f"Test.subject must be at most {MAX_TEST_SUBJECT_LENGTH} characters")

    def mark_ready(self) -> Test:
        """Return a copy transitioned to ``READY`` -- the only allowed move.

        Raises ``InvalidStateTransition`` if this test is already ``READY``:
        the move is one-way (Issue #16), so re-confirming an already-ready
        test is a caller bug, not an idempotent no-op.
        """
        if self.status is TestStatus.READY:
            raise InvalidStateTransition("test", self.status, TestStatus.READY)
        return replace(self, status=TestStatus.READY)


@dataclass(frozen=True, kw_only=True)
class Question:
    """One question inside a test, with its profile areas (§5.2)."""

    id: str
    test_id: str
    number: str
    page: int
    points: int
    scoring_method: ScoringMethod = ScoringMethod.ADDITIVE
    model_answer: str | None = None
    answer_area: NormalizedRect | None = None
    score_area: NormalizedRect | None = None
    comment_area: NormalizedRect | None = None
    page_2: int | None = None
    answer_area_2: NormalizedRect | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Question.id", self.id)
        _require_non_empty("Question.test_id", self.test_id)
        _require_non_empty("Question.number", self.number)
        if self.page < 1:
            raise DomainError("Question.page must be >= 1")
        if self.points < 0:
            raise ScoreOutOfRange("Question.points must be non-negative")
        if self.page_2 is not None:
            if self.page_2 < 1:
                raise DomainError("Question.page_2 must be >= 1")
            if self.page_2 <= self.page:
                raise DomainError("Question.page_2 must be greater than Question.page")
            if self.answer_area_2 is None:
                raise DomainError("Question.answer_area_2 must be provided when page_2 is set")
        if self.page_2 is None and self.answer_area_2 is not None:
            raise DomainError("Question.page_2 must be set when answer_area_2 is provided")

    @property
    def pages(self) -> tuple[int, ...]:
        return (self.page, self.page_2) if self.page_2 is not None else (self.page,)


@dataclass(frozen=True, kw_only=True)
class RubricCriterion:
    """One line item of a rubric."""

    id: str
    description: str
    max_points: int
    position: int

    def __post_init__(self) -> None:
        _require_non_empty("RubricCriterion.id", self.id)
        _require_non_empty("RubricCriterion.description", self.description)
        if self.max_points < 0:
            raise ScoreOutOfRange("RubricCriterion.max_points must be non-negative")
        if self.position < 0:
            raise DomainError("RubricCriterion.position must be non-negative")


@dataclass(frozen=True, kw_only=True)
class Rubric:
    """The marking scheme for one question."""

    id: str
    question_id: str
    criteria: tuple[RubricCriterion, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("Rubric.id", self.id)
        _require_non_empty("Rubric.question_id", self.question_id)
        _require_unique("Rubric.criteria ids", [c.id for c in self.criteria])
        _require_unique("Rubric.criteria positions", [str(c.position) for c in self.criteria])


@dataclass(frozen=True, kw_only=True)
class Submission:
    """One student's answers for a test. ``student_label`` stays local-only (§2 (13)).

    ``source_pdf_sha256`` is the intake dedupe key (see
    ``domain.submission_intake.decide_reintake``) and ``page_count`` is learned
    once, at intake, so later code doesn't need to reopen the PDF just to know
    how many pages it has. ``original_filename`` is never used as a storage
    path (Issue #17: "path traversalと上書きを防ぐ") and is local-only, like
    ``student_label``. ``review_reason`` records why intake routed this
    submission to ``NEEDS_REVIEW`` (e.g. a page-count mismatch against the
    test's registered questions), for display without re-deriving it.
    """

    id: str
    test_id: str
    source_pdf_path: str
    source_pdf_sha256: str
    page_count: int
    created_at: datetime
    state: SubmissionState = SubmissionState.UNPROCESSED
    student_label: str | None = None
    original_filename: str | None = None
    review_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Submission.id", self.id)
        _require_non_empty("Submission.test_id", self.test_id)
        _require_non_empty("Submission.source_pdf_path", self.source_pdf_path)
        _require_non_empty("Submission.source_pdf_sha256", self.source_pdf_sha256)
        if self.page_count < 1:
            raise DomainError("Submission.page_count must be >= 1")
        if self.student_label is not None and len(self.student_label) > MAX_STUDENT_LABEL_LENGTH:
            raise DomainError(
                f"Submission.student_label must be at most {MAX_STUDENT_LABEL_LENGTH} characters"
            )
        if (
            self.original_filename is not None
            and len(self.original_filename) > MAX_ORIGINAL_FILENAME_LENGTH
        ):
            raise DomainError(
                "Submission.original_filename must be at most "
                f"{MAX_ORIGINAL_FILENAME_LENGTH} characters"
            )

    def with_state(self, target: SubmissionState) -> Submission:
        """Return a copy in ``target`` state, or raise if the move is illegal."""
        ensure_submission_transition(self.state, target)
        return replace(self, state=target)


@dataclass(frozen=True, kw_only=True)
class RecognitionResult:
    """A character-recognition result for one submission-question.

    Append-only: an AI result and a later human correction are two rows.
    """

    id: str
    submission_id: str
    question_id: str
    source: GradingSource
    text: str
    confidence: float
    created_at: datetime
    boxes: tuple[BoundingBox, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("RecognitionResult.id", self.id)
        _require_non_empty("RecognitionResult.submission_id", self.submission_id)
        _require_non_empty("RecognitionResult.question_id", self.question_id)
        _require_confidence("RecognitionResult.confidence", self.confidence)
        if len(self.text) > MAX_RECOGNIZED_TEXT_LENGTH:
            raise DomainError(
                f"RecognitionResult.text must be at most {MAX_RECOGNIZED_TEXT_LENGTH} characters"
            )


@dataclass(frozen=True, kw_only=True)
class GradeResultContextEntry:
    """One prerequisite question's result used to produce a `GradeResult`
    (Issue #20: "使用した...前提result versionをGradeResultへ記録し、前提が
    更新された場合は古い下流結果を再利用しない").

    Names the *specific* `RecognitionResult`/`GradeResult` row read for that
    prerequisite, not just its question id -- a fresh grading attempt for the
    same dependent question after the prerequisite has been corrected reads a
    different row and so produces a `GradeResult` whose `context` visibly
    differs from the old one, letting the two be told apart (append-only
    history is what makes the old one "not reused": nothing here mutates it).
    """

    question_id: str
    recognition_result_id: str | None = None
    grade_result_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("GradeResultContextEntry.question_id", self.question_id)
        if self.recognition_result_id is None and self.grade_result_id is None:
            raise DomainError(
                "GradeResultContextEntry must reference at least one of "
                "recognition_result_id/grade_result_id"
            )


@dataclass(frozen=True, kw_only=True)
class GradeResult:
    """A grade for one submission-question.

    Append-only: the AI proposal and the human-confirmed grade are two rows,
    each with its own ``source`` and ``confidence`` (§19, §35-5).

    ``provider``/``model``/``prompt_version`` are the AI reproducibility
    triple (Issue #20 acceptance: "provider/model/prompt versionが追跡でき");
    set only together, and only for an AI-sourced row -- a human confirmation
    has no such call to reproduce. ``dependency_graph_version``/``context``
    record which confirmed `DependencyGraph` version and which prerequisite
    result rows (if any) informed this grade, so a later re-grade against an
    updated prerequisite produces a distinguishable new row rather than being
    confused with this one (Issue #20 additional acceptance).
    """

    id: str
    submission_id: str
    question_id: str
    source: GradingSource
    score: Score
    confidence: float
    created_at: datetime
    criteria: tuple[CriterionResult, ...] = ()
    rationale: str | None = None
    comment: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    dependency_graph_version: int | None = None
    context: tuple[GradeResultContextEntry, ...] = ()
    #: What the grading AI said it saw in the answer image (Issue #136), or
    #: ``None`` when it reported nothing -- a human-confirmed row, a provider
    #: that ignored the field, or a grade recorded before this Issue.
    #:
    #: Recorded so "how often is a question genuinely unanswered?" can be
    #: counted from data already on disk, instead of costing another full
    #: real-material run to find out. That number is what decides whether
    #: `AnswerImageFinding.BLANK` should also stop a grade; without it the
    #: decision has nothing to stand on.
    #:
    #: Never `AnswerImageFinding.NOT_THE_ANSWER`: a grade must not exist for
    #: an image the grader itself said is not this question's answer -- that
    #: is precisely the "0点・確信度 1.00" this Issue removes, and a
    #: contradictory response (not the answer, yet a score above 0) must not
    #: be resolved in favour of the score. `jobs.grading_processor` routes
    #: that case to a human instead; this invariant, and the matching DB
    #: trigger (`db.orm`, migration ``0017``), are what keep a later code
    #: path from quietly persisting one anyway.
    answer_image_finding: AnswerImageFinding | None = None
    #: Provider-reported input tokens for this AI grade (Issue #187), or
    #: ``None`` when the provider did not report usage. Human rows leave
    #: both token fields ``None``.
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty("GradeResult.id", self.id)
        _require_non_empty("GradeResult.submission_id", self.submission_id)
        _require_non_empty("GradeResult.question_id", self.question_id)
        _require_confidence("GradeResult.confidence", self.confidence)
        _require_unique("GradeResult.criteria ids", [c.criterion_id for c in self.criteria])
        if self.comment is not None and len(self.comment) > MAX_COMMENT_CHARS:
            raise DomainError(f"GradeResult.comment exceeds {MAX_COMMENT_CHARS} characters")
        ai_metadata = (self.provider, self.model, self.prompt_version)
        if any(v is not None for v in ai_metadata) and any(v is None for v in ai_metadata):
            raise DomainError(
                "GradeResult.provider/model/prompt_version must be set together or not at all"
            )
        if any(v is not None and not v.strip() for v in ai_metadata):
            raise DomainError("GradeResult.provider/model/prompt_version must not be blank")
        if self.dependency_graph_version is not None and self.dependency_graph_version < 1:
            raise DomainError("GradeResult.dependency_graph_version must be >= 1")
        _require_unique("GradeResult.context question_ids", [c.question_id for c in self.context])
        if self.answer_image_finding is AnswerImageFinding.NOT_THE_ANSWER:
            raise DomainError(
                "GradeResult.answer_image_finding must not be 'not_the_answer': a grade "
                "cannot be recorded for an image the grader said is not this question's answer"
            )
        token_fields = (self.input_tokens, self.output_tokens)
        if any(v is not None for v in token_fields) and any(v is None for v in token_fields):
            raise DomainError(
                "GradeResult.input_tokens and output_tokens must be set together or not at all"
            )
        if self.source is not GradingSource.AI and any(v is not None for v in token_fields):
            raise DomainError("GradeResult token counts are only recorded for AI-sourced rows")
        for field_name, value in (("input_tokens", self.input_tokens), ("output_tokens", self.output_tokens)):
            if value is not None and value < 0:
                raise DomainError(f"GradeResult.{field_name} must be >= 0, got {value!r}")


_ANCHORED_KINDS = frozenset({AnnotationKind.UNDERLINE, AnnotationKind.BOX})


@dataclass(frozen=True, kw_only=True)
class Annotation:
    """A mark to overlay on the PDF. AI never sets coordinates directly (§12.1)."""

    id: str
    submission_id: str
    question_id: str
    source: GradingSource
    kind: AnnotationKind
    created_at: datetime
    rect: NormalizedRect | None = None
    anchor_text: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Annotation.id", self.id)
        _require_non_empty("Annotation.submission_id", self.submission_id)
        _require_non_empty("Annotation.question_id", self.question_id)
        if self.kind is AnnotationKind.COMMENT and not (self.comment and self.comment.strip()):
            raise DomainError("comment annotation requires comment text")
        if self.comment is not None and len(self.comment) > MAX_COMMENT_CHARS:
            raise DomainError(f"annotation comment exceeds {MAX_COMMENT_CHARS} characters")
        if self.kind in _ANCHORED_KINDS and self.rect is None and not self.anchor_text:
            raise DomainError(
                f"{self.kind} annotation needs a rect or an anchor_text (§12.3/§12.4)"
            )


@dataclass(frozen=True, kw_only=True)
class Review:
    """One human decision over an AI grade — the operation history (§19).

    ``version`` is the optimistic-concurrency token (Issue #22): the ``n``-th
    `Review` ever recorded for this ``(submission_id, question_id)`` pair is
    always ``version=n`` (1-based), and ``uq_reviews_submission_question_version``
    (``db.orm.ReviewRow``) rejects a second row at the same version -- see
    ``domain.review_workflow.next_review_version`` and
    ``docs/review-edit-history.md`` "同時実行制御" for why a real unique
    constraint, not just this domain check, is what actually prevents two
    concurrent/duplicate requests from both creating history.

    ``regrade_job_id`` names the fresh `Job` a ``REGRADE_REQUESTED`` row
    queued (see ``adapters.review_actions.regrade_question``); ``None`` for
    every other action. ``undone_review_id`` names the specific prior `Review`
    row an ``UNDONE`` row reverts -- required for that action and for no
    other, and never physically removes the row it names (append-only, same
    as every other table here); see
    ``domain.review_workflow.effective_latest_review``.

    ``ai_grade_result_id`` is *the AI attempt this decision was made
    against*, and is required only for ``APPROVED`` -- there is nothing to
    approve without one. A ``MODIFIED`` row may leave it unset (Issue #118):
    when AI grading failed permanently there is no `GradeResult` at all
    (Issue #97 deliberately writes none rather than a fabricated one), and a
    person still has to be able to grade the question. Such a row is
    therefore also the *record* that they did -- "confirmed, with no AI
    proposal behind it" -- which is what the review screen reads to say so.
    ``human_grade_result_id`` stays required for ``MODIFIED`` either way, so
    no confirmed row can be silent about what it decided.
    """

    id: str
    submission_id: str
    question_id: str
    action: ReviewAction
    created_at: datetime
    version: int
    ai_grade_result_id: str | None = None
    human_grade_result_id: str | None = None
    regrade_job_id: str | None = None
    undone_review_id: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Review.id", self.id)
        _require_non_empty("Review.submission_id", self.submission_id)
        _require_non_empty("Review.question_id", self.question_id)
        if self.version < 1:
            raise DomainError("Review.version must be >= 1")
        if self.action is ReviewAction.APPROVED and not self.ai_grade_result_id:
            raise DomainError("approved review must reference the AI grade result")
        if self.action is ReviewAction.MODIFIED and not self.human_grade_result_id:
            raise DomainError("modified review must reference the human grade result")
        if self.action is ReviewAction.REGRADE_REQUESTED and not self.regrade_job_id:
            raise DomainError("regrade_requested review must reference the queued job")
        if self.action is ReviewAction.UNDONE and not self.undone_review_id:
            raise DomainError("undone review must reference the review it undoes")
        if self.note is not None and len(self.note) > MAX_COMMENT_CHARS:
            raise DomainError(f"Review.note exceeds {MAX_COMMENT_CHARS} characters")


@dataclass(frozen=True, kw_only=True)
class AnswerImage:
    """The per-question image cropped from a submission's answer area (§7.1).

    One row per ``(submission_id, question_id)`` -- a fresh submission (e.g. a
    retry) gets its own set. ``image_path`` follows the same
    app-data-root-relative convention as ``Submission.source_pdf_path``.
    """

    id: str
    submission_id: str
    question_id: str
    page: int
    image_path: str
    status: AnswerImageStatus
    created_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("AnswerImage.id", self.id)
        _require_non_empty("AnswerImage.submission_id", self.submission_id)
        _require_non_empty("AnswerImage.question_id", self.question_id)
        _require_non_empty("AnswerImage.image_path", self.image_path)
        if self.page < 1:
            raise DomainError("AnswerImage.page must be >= 1")
        needs_review = self.status is AnswerImageStatus.NEEDS_REVIEW
        if needs_review and not (self.reason and self.reason.strip()):
            raise DomainError("needs_review answer image requires a reason")
        if self.status is AnswerImageStatus.OK and self.reason is not None:
            raise DomainError("ok answer image must not carry a reason")


@dataclass(frozen=True, kw_only=True)
class Job:
    """A unit of background work, persisted so it survives a restart (§3.4)."""

    id: str
    kind: JobKind
    submission_id: str
    created_at: datetime
    updated_at: datetime
    question_id: str | None = None
    state: JobState = JobState.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    #: Categorized reason for the most recent ``FAILED`` (retry classification,
    #: Issue #18). ``None`` once the job leaves FAILED, and always ``None``
    #: for every other state -- it describes the *last failed attempt*, not
    #: the job overall.
    error_code: ErrorCategory | None = None
    blocked_on_question_id: str | None = None
    #: Whether this job's terminal result is usable by a dependent question
    #: (Issue #18 §4.4: low-confidence results must not release a dependent).
    #: ``None`` until the job reaches ``SUCCEEDED`` or ``FAILED``. A fresh
    #: transition into either state always starts this at ``None``
    #: (`transitioned_to` never sets it to ``FAILED``'s target); deciding the
    #: value for a ``SUCCEEDED`` job is `auto_scoring.domain.job_execution.
    #: JobProcessor`'s responsibility. ``FAILED`` is included too (review
    #: round 2, P1) so a human who has corrected/approved a failed attempt's
    #: downstream effect (business-rules-and-evaluation-data.md §4.4: "人間が
    #: …前提を承認して続行") can flip it later via
    #: `JobRepository.mark_usable` without lying about ``state`` -- the
    #: attempt itself really did fail; only whether dependents may now
    #: proceed changes.
    usable: bool | None = None
    #: The confirmed `DependencyGraph` version this job was queued against, if
    #: any (Issue #26). Lets a later confirm supersede a still-incomplete job
    #: whose dependency structure has since changed -- see
    #: `reissue_job_for_graph_version`.
    dependency_graph_version: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Job.id", self.id)
        _require_non_empty("Job.submission_id", self.submission_id)
        if self.max_attempts < 1:
            raise DomainError("Job.max_attempts must be >= 1")
        if self.attempts < 0:
            raise DomainError("Job.attempts must be >= 0")
        if self.dependency_graph_version is not None and self.dependency_graph_version < 1:
            raise DomainError("Job.dependency_graph_version must be >= 1")
        if self.error_code is not None and self.state is not JobState.FAILED:
            raise DomainError("Job.error_code may only be set while state is FAILED")
        if self.usable is not None and self.state not in (JobState.SUCCEEDED, JobState.FAILED):
            raise DomainError("Job.usable may only be set once state is SUCCEEDED or FAILED")

    def transitioned_to(
        self,
        target: JobState,
        *,
        updated_at: datetime,
        error: str | None = None,
        error_code: ErrorCategory | None = None,
        blocked_on_question_id: str | None = None,
        usable: bool | None = None,
    ) -> Job:
        """Return a copy in ``target`` state (raises on an illegal move).

        Entering ``RUNNING`` counts as one attempt. ``error_code`` only makes
        sense alongside ``target is JobState.FAILED``; ``usable`` only
        alongside ``target is JobState.SUCCEEDED`` -- both are dropped
        (reset to ``None``) for every other target, matching ``__post_init__``.
        """
        ensure_job_transition(self.state, target)
        attempts = self.attempts + 1 if target is JobState.RUNNING else self.attempts
        return replace(
            self,
            state=target,
            attempts=attempts,
            last_error=error,
            error_code=error_code if target is JobState.FAILED else None,
            blocked_on_question_id=blocked_on_question_id,
            usable=usable if target is JobState.SUCCEEDED else None,
            updated_at=updated_at,
        )


@dataclass(frozen=True, kw_only=True)
class QuestionReviewVersion:
    """One question's review-history length at the moment an `Export` was
    produced (Issue #23) -- ``version`` is exactly ``len(ReviewRepository.
    history(submission_id, question_id))`` at that instant, which (per
    ``domain.review_workflow.next_review_version``) is also the ``version``
    of the latest `Review` row for that pair. Recorded so a later export
    request can tell whether anything happened to this question's review
    history since (``domain.pdf_export.decide_reexport``) without re-reading
    every `Review` row again.
    """

    question_id: str
    version: int

    def __post_init__(self) -> None:
        _require_non_empty("QuestionReviewVersion.question_id", self.question_id)
        if self.version < 1:
            raise DomainError("QuestionReviewVersion.version must be >= 1")


@dataclass(frozen=True, kw_only=True)
class Export:
    """One generated annotated-PDF output (Issue #23, simplified-design-spec
    §14).

    Only ever created after every question of ``submission_id``'s test is
    confirmed (``domain.review_workflow.all_questions_confirmed``) and the
    output file has been generated, verified, and atomically written --
    there is no "failed" or "pending" `Export` row; a `Job` (kind=``EXPORT``)
    tracks in-flight/failed attempts instead (``docs/pdf-export.md``).

    ``file_path`` follows the same app-data-root-relative convention as
    ``Submission.source_pdf_path``. ``review_versions`` is the snapshot this
    output was generated from -- see `QuestionReviewVersion` -- and
    ``job_id`` names the `Job` that produced it, so both are independently
    retrievable per Issue #23's "出力job、hash、生成時刻、元Submission、
    review versionを保存する".
    """

    id: str
    submission_id: str
    job_id: str
    file_path: str
    file_sha256: str
    created_at: datetime
    review_versions: tuple[QuestionReviewVersion, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty("Export.id", self.id)
        _require_non_empty("Export.submission_id", self.submission_id)
        _require_non_empty("Export.job_id", self.job_id)
        _require_non_empty("Export.file_path", self.file_path)
        _require_non_empty("Export.file_sha256", self.file_sha256)
        _require_unique(
            "Export.review_versions question_ids",
            [v.question_id for v in self.review_versions],
        )


def find_answer_image(images: Sequence[AnswerImage], question_id: str) -> AnswerImage | None:
    """Pick ``question_id``'s row out of one submission's `AnswerImage` list.

    `AnswerImageRepository` keeps at most one row per ``(submission_id,
    question_id)`` at a time (`replace_for_submission` deletes the old set
    before inserting a retry's new one), so this is normally just a filter;
    the ``created_at`` tie-break only guards against reading between that
    delete and insert.
    """
    matches = [image for image in images if image.question_id == question_id]
    if not matches:
        return None
    return max(matches, key=lambda image: image.created_at)


#: `JobState`s past which nothing still running could produce a grade.
#:
#: ``FAILED`` is here even though the queue's own retry policy can move it back
#: to ``QUEUED``: from the reviewer's side it has stopped, and a retry that
#: revives it will simply move the question on again. Mirrored on the client as
#: `_PdfReviewPageState._terminalJobStates` -- the two must agree, because the
#: same question must not offer 「点数を入力」 on one screen and be counted as
#: still-running on the other (Issue #84).
TERMINAL_JOB_STATES = frozenset({JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED})


def latest_job_for_question(jobs: Sequence[Job], question_id: str) -> Job | None:
    """The `Job` that describes where ``question_id`` currently stands.

    A question accumulates jobs: a 再判定 request, a re-submission under a newer
    confirmed graph version, and a retry after a failure each add one
    (`reissue_job_for_graph_version`, `adapters.review_actions.regrade_question`).
    **Only the newest of them says anything about now** -- an old ``failed`` row
    sitting behind a newer ``succeeded`` one describes an attempt that has since
    been superseded.

    This is deliberately the same rule the review screen already draws with
    (`app/lib/core/question_status.dart`'s ``_latestJobFor`` +
    ``deriveQuestionStatus``). Issue #84 was three places on that screen deriving
    one question's state separately and disagreeing; a *server* that counted
    these differently would be the fourth.
    """
    matches = [job for job in jobs if job.question_id == question_id]
    if not matches:
        return None
    return max(matches, key=lambda job: job.created_at)


def reissue_job_for_graph_version(
    job: Job, *, new_version: int, new_id: str, at: datetime
) -> tuple[Job, Job]:
    """Cancel a job that was queued against a now-superseded dependency-graph
    version, and return a fresh replacement queued against ``new_version``
    (Issue #26 acceptance: "確定graphを変更した場合は…古いgraphで未完了の採点
    jobを無効化・再作成できるようにする").

    The replacement keeps the same ``kind``/``submission_id``/``question_id``
    but resets attempts and ``blocked_on_question_id`` -- the new graph's
    dependency structure may place it differently, so nothing about *how* it
    was blocked before is assumed to still hold. The caller is expected to
    persist both returned jobs in the same transaction as the graph
    confirmation that triggered this (see
    ``auto_scoring.api.dependency_graph_router``).
    """
    cancelled = job.transitioned_to(
        JobState.CANCELLED,
        updated_at=at,
        error=f"stale: dependency graph advanced to version {new_version}",
    )
    replacement = replace(
        job,
        id=new_id,
        state=JobState.QUEUED,
        attempts=0,
        last_error=None,
        error_code=None,
        blocked_on_question_id=None,
        usable=None,
        dependency_graph_version=new_version,
        created_at=at,
        updated_at=at,
    )
    return cancelled, replacement
