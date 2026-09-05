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

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

_EPS = 1e-9

#: Upper bound for a single annotation comment, in characters
#: (business-rules-and-evaluation-data.md §2 (6): "全角 120 文字").
MAX_COMMENT_CHARS = 120


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
    """Lifecycle of a background job. ``BLOCKED`` = waiting on a dependency (§4.4)."""

    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewAction(StrEnum):
    """The human decision recorded in the operation history (§19)."""

    APPROVED = "approved"
    MODIFIED = "modified"
    REJECTED = "rejected"


# --------------------------------------------------------------------------- #
# State machines
# --------------------------------------------------------------------------- #
_SUBMISSION_TRANSITIONS: dict[SubmissionState, frozenset[SubmissionState]] = {
    SubmissionState.UNPROCESSED: frozenset({SubmissionState.AI_PROCESSING, SubmissionState.ERROR}),
    SubmissionState.AI_PROCESSING: frozenset({SubmissionState.AI_PROCESSED, SubmissionState.ERROR}),
    SubmissionState.AI_PROCESSED: frozenset(
        {
            SubmissionState.NEEDS_REVIEW,
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
    """One OCR word box, used to place text-anchored annotations (§12.3)."""

    text: str
    rect: NormalizedRect


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

    def __post_init__(self) -> None:
        _require_non_empty("Test.id", self.id)
        _require_non_empty("Test.name", self.name)


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

    def __post_init__(self) -> None:
        _require_non_empty("Question.id", self.id)
        _require_non_empty("Question.test_id", self.test_id)
        _require_non_empty("Question.number", self.number)
        if self.page < 1:
            raise DomainError("Question.page must be >= 1")
        if self.points < 0:
            raise ScoreOutOfRange("Question.points must be non-negative")


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
    """One student's answers for a test. ``student_label`` stays local-only (§2 (13))."""

    id: str
    test_id: str
    source_pdf_path: str
    created_at: datetime
    state: SubmissionState = SubmissionState.UNPROCESSED
    student_label: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Submission.id", self.id)
        _require_non_empty("Submission.test_id", self.test_id)
        _require_non_empty("Submission.source_pdf_path", self.source_pdf_path)

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


@dataclass(frozen=True, kw_only=True)
class GradeResult:
    """A grade for one submission-question.

    Append-only: the AI proposal and the human-confirmed grade are two rows,
    each with its own ``source`` and ``confidence`` (§19, §35-5).
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

    def __post_init__(self) -> None:
        _require_non_empty("GradeResult.id", self.id)
        _require_non_empty("GradeResult.submission_id", self.submission_id)
        _require_non_empty("GradeResult.question_id", self.question_id)
        _require_confidence("GradeResult.confidence", self.confidence)
        _require_unique("GradeResult.criteria ids", [c.criterion_id for c in self.criteria])


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
    """One human decision over an AI grade — the operation history (§19)."""

    id: str
    submission_id: str
    question_id: str
    action: ReviewAction
    created_at: datetime
    ai_grade_result_id: str | None = None
    human_grade_result_id: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("Review.id", self.id)
        _require_non_empty("Review.submission_id", self.submission_id)
        _require_non_empty("Review.question_id", self.question_id)
        if (
            self.action in (ReviewAction.APPROVED, ReviewAction.MODIFIED)
            and not self.ai_grade_result_id
        ):
            raise DomainError(f"{self.action} review must reference the AI grade result")
        if self.action is ReviewAction.MODIFIED and not self.human_grade_result_id:
            raise DomainError("modified review must reference the human grade result")


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
    blocked_on_question_id: str | None = None
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

    def transitioned_to(
        self,
        target: JobState,
        *,
        updated_at: datetime,
        error: str | None = None,
        blocked_on_question_id: str | None = None,
    ) -> Job:
        """Return a copy in ``target`` state (raises on an illegal move).

        Entering ``RUNNING`` counts as one attempt.
        """
        ensure_job_transition(self.state, target)
        attempts = self.attempts + 1 if target is JobState.RUNNING else self.attempts
        return replace(
            self,
            state=target,
            attempts=attempts,
            last_error=error,
            blocked_on_question_id=blocked_on_question_id,
            updated_at=updated_at,
        )


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
        blocked_on_question_id=None,
        dependency_graph_version=new_version,
        created_at=at,
        updated_at=at,
    )
    return cancelled, replacement
