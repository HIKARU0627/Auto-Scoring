"""SQLAlchemy 2.0 tables for the MVP schema.

Invariants are guaranteed here with real constraints, not application checks
(``AGENTS.md`` "Architecture"): foreign keys reject orphan rows, ``CHECK``
constraints reject out-of-range scores and confidences, ``UNIQUE`` constraints
reject duplicates, and every state column is a ``CHECK ... IN (...)`` produced by
:class:`sqlalchemy.Enum`.

``Base.metadata`` here is the full head schema. The Alembic migrations under
``backend/migrations/versions`` build it up revision by revision; keep the two in
step (run ``uv run alembic revision --autogenerate`` when you change a table).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import DDL

from auto_scoring.db.base import Base
from auto_scoring.domain.dependency_graph import DependencyGraphStatus, DependencyProvision
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.models import (
    AnnotationKind,
    AnswerImageFinding,
    AnswerImageStatus,
    ErrorCategory,
    GradingSource,
    JobKind,
    JobState,
    ReviewAction,
    ScoringMethod,
    SubmissionState,
    TestStatus,
)

_CONFIDENCE_RANGE = "confidence >= 0.0 AND confidence <= 1.0"


def _enum(enum_cls: type[enum.StrEnum]) -> SAEnum:
    """A VARCHAR column constrained to the enum's *values* via ``CHECK ... IN``."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def _pk() -> Mapped[str]:
    return mapped_column(String, primary_key=True)


def _json_list() -> Mapped[list[dict[str, Any]]]:
    return mapped_column(JSON, nullable=False, default=list)


class TestRow(Base):
    __tablename__ = "tests"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'ready')", name="ck_tests_status_valid"),
    )

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    default_scoring_method: Mapped[ScoringMethod] = mapped_column(
        _enum(ScoringMethod), nullable=False
    )
    #: Registration lifecycle (Issue #16). Mirrors `domain.models.Test.status`;
    #: the one-way draft->ready move is enforced in the domain
    #: (`Test.mark_ready`), this CHECK only rejects an unknown value reaching
    #: the DB outside the domain (repair, import, direct SQL).
    status: Mapped[TestStatus] = mapped_column(
        _enum(TestStatus), nullable=False, default=TestStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class TestMaterialRow(Base):
    """One registered file of a test, with its confirmed role (Issue #101).

    Replaces the two fixed PDF slots registration used to have -- see
    `domain.test_material.TestMaterial` for why a list, not a pair.

    ``uq_test_materials_test_role_hash`` makes re-attaching the *same* file
    under the same role a detectable duplicate rather than a second copy on
    disk: the intake screen can retry a partially-failed batch (Issue #101:
    "成功した分は残る") and must not multiply materials each time it does.
    The same file may still be attached under two different roles, which is
    legitimate -- a criteria PDF a reviewer also wants kept as reference.
    """

    __tablename__ = "test_materials"
    __table_args__ = (
        # Every `MaterialRole` value *except* `ignore`, which is the role of
        # a file the reviewer chose not to import -- a stored row can never
        # carry it. `domain.test_material.TestMaterial` rejects it too; this
        # is the constraint that also holds for a write bypassing the domain
        # (mirrors `ck_submissions_state_valid`).
        CheckConstraint(
            "role IN ('student_answer', 'grading_criteria', 'annotation_resource', "
            "'annotation_sample', 'reference')",
            name="ck_test_materials_role_valid",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_test_materials_size_non_negative"),
        CheckConstraint(
            "original_filename IS NULL OR length(original_filename) <= 255",
            name="ck_test_materials_original_filename_length",
        ),
        UniqueConstraint("test_id", "role", "sha256", name="uq_test_materials_test_role_hash"),
        Index("ix_test_materials_test_id", "test_id"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[MaterialRole] = mapped_column(_enum(MaterialRole), nullable=False)
    stored_path: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class QuestionRow(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("test_id", "number", name="uq_questions_test_number"),
        CheckConstraint("page >= 1", name="ck_questions_page_positive"),
        CheckConstraint("points >= 0", name="ck_questions_points_non_negative"),
        CheckConstraint("page_2 IS NULL OR page_2 >= 1", name="ck_questions_page_2_positive"),
        CheckConstraint("page_2 IS NULL OR page_2 > page", name="ck_questions_page_2_greater"),
        CheckConstraint(
            "(page_2 IS NULL AND (answer_area_2 IS NULL OR answer_area_2 = 'null')) OR "
            "(page_2 IS NOT NULL AND answer_area_2 IS NOT NULL AND answer_area_2 != 'null')",
            name="ck_questions_page_2_and_area_2_paired",
        ),
        Index("ix_questions_test_id", "test_id"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    scoring_method: Mapped[ScoringMethod] = mapped_column(_enum(ScoringMethod), nullable=False)
    model_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    answer_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    score_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    comment_area: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    page_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer_area_2: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)


class RubricRow(Base):
    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("question_id", name="uq_rubrics_question"),)

    id: Mapped[str] = _pk()
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )


class RubricCriterionRow(Base):
    __tablename__ = "rubric_criteria"
    __table_args__ = (
        UniqueConstraint("rubric_id", "position", name="uq_rubric_criteria_position"),
        CheckConstraint("max_points >= 0", name="ck_rubric_criteria_max_points_non_negative"),
        CheckConstraint("position >= 0", name="ck_rubric_criteria_position"),
        Index("ix_rubric_criteria_rubric_id", "rubric_id"),
    )

    id: Mapped[str] = _pk()
    rubric_id: Mapped[str] = mapped_column(
        ForeignKey("rubrics.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    max_points: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class SubmissionRow(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('unprocessed', 'ai_processing', 'ai_processed', "
            "'needs_review', 'reviewed', 'exported', 'error')",
            name="ck_submissions_state_valid",
        ),
        CheckConstraint("page_count >= 1", name="ck_submissions_page_count_positive"),
        CheckConstraint(
            "student_label IS NULL OR length(student_label) <= 200",
            name="ck_submissions_student_label_length",
        ),
        CheckConstraint(
            "original_filename IS NULL OR length(original_filename) <= 255",
            name="ck_submissions_original_filename_length",
        ),
        UniqueConstraint("test_id", "source_pdf_sha256", name="uq_submissions_test_content_hash"),
        Index("ix_submissions_test_id", "test_id"),
        Index("ix_submissions_state", "state"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    source_pdf_path: Mapped[str] = mapped_column(String, nullable=False)
    source_pdf_sha256: Mapped[str] = mapped_column(String, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[SubmissionState] = mapped_column(_enum(SubmissionState), nullable=False)
    student_label: Mapped[str | None] = mapped_column(String, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AnswerImageRow(Base):
    """One question's extracted answer-area image for one submission (Issue #17 §7.1)."""

    __tablename__ = "answer_images"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "question_id", name="uq_answer_images_submission_question"
        ),
        CheckConstraint("page >= 1", name="ck_answer_images_page_positive"),
        CheckConstraint("status IN ('ok', 'needs_review')", name="ck_answer_images_status_valid"),
        CheckConstraint(
            "(status = 'ok' AND reason IS NULL) OR "
            "(status = 'needs_review' AND reason IS NOT NULL AND trim(reason) != '')",
            name="ck_answer_images_reason_matches_status",
        ),
        Index("ix_answer_images_submission_id", "submission_id"),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[AnswerImageStatus] = mapped_column(_enum(AnswerImageStatus), nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RecognitionResultRow(Base):
    __tablename__ = "recognition_results"
    __table_args__ = (
        CheckConstraint(_CONFIDENCE_RANGE, name="ck_recognition_confidence_range"),
        CheckConstraint("length(text) <= 10000", name="ck_recognition_results_text_length"),
        Index(
            "ix_recognition_results_submission_question",
            "submission_id",
            "question_id",
        ),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    boxes: Mapped[list[dict[str, Any]]] = _json_list()
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GradeResultRow(Base):
    __tablename__ = "grade_results"
    __table_args__ = (
        CheckConstraint("maximum >= 0", name="ck_grade_results_maximum_non_negative"),
        CheckConstraint(
            "awarded >= 0 AND awarded <= maximum",
            name="ck_grade_results_awarded_in_range",
        ),
        CheckConstraint(_CONFIDENCE_RANGE, name="ck_grade_results_confidence_range"),
        CheckConstraint(
            "comment IS NULL OR length(comment) <= 120", name="ck_grade_results_comment_length"
        ),
        # Mirrors `domain.models.GradeResult.__post_init__`: the AI
        # reproducibility triple (Issue #20 "provider/model/prompt versionが
        # 追跡でき") is recorded together or not at all -- a human-confirmed
        # row has no such call to reproduce.
        CheckConstraint(
            "(provider IS NULL AND model IS NULL AND prompt_version IS NULL) OR "
            "(provider IS NOT NULL AND model IS NOT NULL AND prompt_version IS NOT NULL)",
            name="ck_grade_results_ai_metadata_complete",
        ),
        CheckConstraint(
            "dependency_graph_version IS NULL OR dependency_graph_version >= 1",
            name="ck_grade_results_dependency_graph_version_positive",
        ),
        CheckConstraint(
            "(input_tokens IS NULL AND output_tokens IS NULL) OR "
            "(input_tokens IS NOT NULL AND output_tokens IS NOT NULL)",
            name="ck_grade_results_token_counts_paired",
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="ck_grade_results_token_counts_non_negative",
        ),
        CheckConstraint(
            "(input_tokens IS NULL AND output_tokens IS NULL) OR source = 'ai'",
            name="ck_grade_results_token_counts_ai_only",
        ),
        Index("ix_grade_results_submission_question", "submission_id", "question_id"),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    criteria: Mapped[list[dict[str, Any]]] = _json_list()
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    #: AI総評コメント (Issue #20; simplified-design-specification.md section
    #: 16.5's "コメント" review-UI field). ``None`` for a human-confirmed row
    #: that carries no such AI-generated comment.
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    #: AI reproducibility triple (Issue #20 acceptance). All three or none.
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The confirmed DependencyGraph version in effect when this grade was
    #: produced (Issue #20 additional acceptance), mirroring
    #: `JobRow.dependency_graph_version` (Issue #26).
    dependency_graph_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Which prerequisite RecognitionResult/GradeResult row(s) fed this grade
    #: (Issue #20: "前提result versionをGradeResultへ記録"), as a JSON list of
    #: {question_id, recognition_result_id, grade_result_id}. Empty for a
    #: question with no prerequisite.
    context: Mapped[list[dict[str, Any]]] = _json_list()
    #: What the grading AI reported the answer image shows (Issue #136).
    #: ``NULL`` for a human-confirmed row, a provider that reported nothing,
    #: and every row written before this column existed. Stored so the
    #: frequency of genuinely unanswered questions can be counted from data
    #: already on disk -- that number is what decides whether ``blank``
    #: should stop a grade too (docs/ai-grading-pipeline.md).
    answer_image_finding: Mapped[AnswerImageFinding | None] = mapped_column(
        _enum(AnswerImageFinding), nullable=True
    )
    #: Provider-reported token counts (Issue #187). Both or neither.
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


#: A grade may not exist for an image the grading AI itself said is not this
#: question's answer (Issue #136) -- the invariant
#: `domain.models.GradeResult.__post_init__` states, held by the database as
#: well, because a score that looks ordinary while the crop behind it was
#: wrong is the entire failure that Issue removes (AGENTS.md "Architecture":
#: guarantee important invariants with real constraints).
#:
#: **A trigger, not a ``CheckConstraint``.** SQLite cannot add a CHECK to an
#: existing table, so a migration adding one must rebuild ``grade_results``.
#: When ``0017`` was written that rebuild broke deleting a test, because it
#: moved the table behind ``reviews`` in ``sqlite_master`` and so flipped the
#: cascade order into ``ck_reviews_confirmed_requires_ai_grade``; ``ADD
#: COLUMN`` plus a trigger avoided the rebuild. Issue #149 has since removed
#: that hazard at its source (``ReviewRow``'s references cascade instead of
#: blanking), so rebuilding this table is safe again -- the trigger simply
#: stays, since re-expressing the same rule as a CHECK would rebuild the
#: table for no behavioural gain. The dependency-graph triggers above are
#: there for the other reason: what they enforce does not fit a CHECK on the
#: table as it stands. See migrations ``0017`` and ``0018``.
#:
#: It rejects any value other than ``answer``/``blank``/``NULL``, so it also
#: carries the "known value" half that a migrated database would otherwise
#: lack (a freshly created one has the enum's own unnamed ``CHECK ... IN``).
_ANSWER_IMAGE_FINDING_GRADABLE_MESSAGE = (
    "grade_results.answer_image_finding must be NULL, ''answer'' or ''blank''"
)

_answer_image_finding_gradable_insert_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    f"""
    CREATE TRIGGER trg_grade_results_answer_image_finding_gradable_insert
    BEFORE INSERT ON grade_results
    FOR EACH ROW
    WHEN NEW.answer_image_finding IS NOT NULL
        AND NEW.answer_image_finding NOT IN ('answer', 'blank')
    BEGIN
        SELECT RAISE(ABORT, '{_ANSWER_IMAGE_FINDING_GRADABLE_MESSAGE}');
    END;
    """
)

_answer_image_finding_gradable_update_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    f"""
    CREATE TRIGGER trg_grade_results_answer_image_finding_gradable_update
    BEFORE UPDATE OF answer_image_finding ON grade_results
    FOR EACH ROW
    WHEN NEW.answer_image_finding IS NOT NULL
        AND NEW.answer_image_finding NOT IN ('answer', 'blank')
    BEGIN
        SELECT RAISE(ABORT, '{_ANSWER_IMAGE_FINDING_GRADABLE_MESSAGE}');
    END;
    """
)

event.listen(
    GradeResultRow.__table__, "after_create", _answer_image_finding_gradable_insert_trigger
)
event.listen(
    GradeResultRow.__table__, "after_create", _answer_image_finding_gradable_update_trigger
)


class AnnotationRow(Base):
    __tablename__ = "annotations"
    __table_args__ = (Index("ix_annotations_submission_question", "submission_id", "question_id"),)

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[GradingSource] = mapped_column(_enum(GradingSource), nullable=False)
    kind: Mapped[AnnotationKind] = mapped_column(_enum(AnnotationKind), nullable=False)
    rect: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    anchor_text: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewRow(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_submission_question", "submission_id", "question_id"),
        # The optimistic-concurrency guard (Issue #22): the real constraint
        # that stops two concurrent/duplicate review requests from both
        # appending a row for the same ``(submission_id, question_id)``
        # pair's next slot -- see `domain.review_workflow.next_review_version`
        # and `docs/review-edit-history.md` "同時実行制御". Application code
        # computes ``version`` as ``1 + <this pair's current row count>``
        # before insert; the loser of a race between two callers who both
        # computed the same value hits this constraint's `IntegrityError`.
        UniqueConstraint(
            "submission_id", "question_id", "version", name="uq_reviews_submission_question_version"
        ),
        CheckConstraint("version >= 1", name="ck_reviews_version_positive"),
        CheckConstraint(
            "action IN ('approved', 'modified', 'rejected', 'regrade_requested', 'undone')",
            name="ck_reviews_action_valid",
        ),
        # Mirrors `Review.__post_init__`: a row written outside the domain
        # (repair, import, direct SQL) could otherwise persist an
        # ``approved`` row with no AI grade to confirm, a ``modified`` row
        # with no human grade recording what it was modified *to*, a
        # ``regrade_requested`` row with no record of which `Job` it queued,
        # or an ``undone`` row with nothing to say what it undid -- each of
        # which `Review`'s own constructor already rejects, so a row like
        # that would only ever surface as a hydration crash on the next read
        # of this question's history.
        #
        # ``modified`` is deliberately *not* on the first of those since
        # Issue #118: see `Review`'s own docstring. The constraint name is
        # kept (renaming it would mean recreating the table for nothing) but
        # what it now says is "approved requires an AI grade".
        CheckConstraint(
            "action != 'approved' OR ai_grade_result_id IS NOT NULL",
            name="ck_reviews_confirmed_requires_ai_grade",
        ),
        CheckConstraint(
            "action != 'modified' OR human_grade_result_id IS NOT NULL",
            name="ck_reviews_modified_requires_human_grade",
        ),
        CheckConstraint(
            "action != 'regrade_requested' OR regrade_job_id IS NOT NULL",
            name="ck_reviews_regrade_requires_job",
        ),
        CheckConstraint(
            "action != 'undone' OR undone_review_id IS NOT NULL",
            name="ck_reviews_undone_requires_target",
        ),
        CheckConstraint("note IS NULL OR length(note) <= 120", name="ck_reviews_note_length"),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[ReviewAction] = mapped_column(_enum(ReviewAction), nullable=False)
    #: 1-based sequence number within this (submission_id, question_id)'s own
    #: review history (Issue #22 optimistic concurrency). See the unique
    #: constraint above.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Every one of the four references below is ``ON DELETE CASCADE``, not
    #: ``SET NULL`` (Issue #149). ``SET NULL`` *rewrites* the review row while
    #: it still exists, so removing the row it names aborts the delete on the
    #: matching CHECK above -- and whether that happens is decided by the
    #: order SQLite walks the tables in, i.e. by whatever the last migration
    #: left in ``sqlite_master``. ``CASCADE`` never produces that intermediate
    #: row at all: a review disappears together with the thing it is a
    #: decision about, in every order. See
    #: ``docs/data-model-and-local-storage.md`` "Review が指す行の削除".
    ai_grade_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("grade_results.id", ondelete="CASCADE"), nullable=True
    )
    human_grade_result_id: Mapped[str | None] = mapped_column(
        ForeignKey("grade_results.id", ondelete="CASCADE"), nullable=True
    )
    #: The `Job` a ``regrade_requested`` row queued (Issue #22). ``None`` for
    #: every other action.
    regrade_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True
    )
    #: The prior `Review` row an ``undone`` row reverts (Issue #22). Never
    #: physically removed while that row lives -- see
    #: `domain.review_workflow.effective_latest_review`.
    undone_review_id: Mapped[str | None] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued', 'running', 'blocked', 'succeeded', 'failed', 'cancelled')",
            name="ck_jobs_state_valid",
        ),
        CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts_positive"),
        CheckConstraint(
            "dependency_graph_version IS NULL OR dependency_graph_version >= 1",
            name="ck_jobs_dependency_graph_version_positive",
        ),
        # Explicit named mirror of `_enum(ErrorCategory)`'s own (unnamed, and
        # therefore untracked by `alembic check`) CHECK -- same pattern as
        # `ck_jobs_state_valid` above, and required for the same reason:
        # without a name matching the migration's, autogenerate sees this as
        # a constraint the migrations never created.
        CheckConstraint(
            "error_code IS NULL OR error_code IN "
            "('timeout', 'rate_limited', 'server_error', 'permanent')",
            name="ck_jobs_error_code_valid",
        ),
        # Mirrors `Job.__post_init__`: `error_code`/`usable` may only be set
        # while the job is in a state they describe (Issue #18). Both are
        # one-directional -- a FAILED job need not carry an error_code
        # (nothing before this issue ever set one), but nothing may carry one
        # outside the states allowed here.
        CheckConstraint(
            "error_code IS NULL OR state = 'failed'", name="ck_jobs_error_code_matches_state"
        ),
        # `usable` is allowed on FAILED too (review round 2, P1): a human can
        # confirm a failed attempt's downstream effect is usable anyway
        # (business-rules-and-evaluation-data.md §4.4) without the row lying
        # about `state` -- the attempt itself really did fail.
        CheckConstraint(
            "usable IS NULL OR state IN ('succeeded', 'failed')",
            name="ck_jobs_usable_matches_state",
        ),
        # The real idempotency key for Submission-DAG jobs (Issue #18,
        # docs/job-queue.md "二重処理防止"): re-running job creation for the
        # same submission/question/confirmed-graph-version must not create a
        # second row. SQLite treats NULLs as distinct, so this only actually
        # constrains rows where both columns are set -- exactly the
        # DAG-scheduled jobs this issue creates.
        UniqueConstraint(
            "submission_id",
            "question_id",
            "dependency_graph_version",
            name="uq_jobs_submission_question_graph_version",
        ),
        Index("ix_jobs_state", "state"),
        Index("ix_jobs_submission_id", "submission_id"),
        Index("ix_jobs_dependency_graph_version", "dependency_graph_version"),
    )

    id: Mapped[str] = _pk()
    kind: Mapped[JobKind] = mapped_column(_enum(JobKind), nullable=False)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=True
    )
    state: Mapped[JobState] = mapped_column(_enum(JobState), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Categorized reason for the most recent FAILED attempt (Issue #18
    #: retry classification), distinct from the free-text `last_error`.
    error_code: Mapped[ErrorCategory | None] = mapped_column(_enum(ErrorCategory), nullable=True)
    blocked_on_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    #: Whether a SUCCEEDED job's result may release a dependent question
    #: (Issue #18 §4.4). NULL until the job reaches SUCCEEDED.
    usable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    #: The confirmed DependencyGraph version this job was queued against
    #: (Issue #26). No FK: dependency_graphs is keyed by (test_id, version),
    #: not by version alone, so this stays a plain int matched against
    #: DependencyGraphRepository.list_incomplete_for_stale_versions.
    dependency_graph_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ExportRow(Base):
    """A successful annotated-PDF output (Issue #23). ``job_id`` is unique --
    the `Job` (kind=``EXPORT``) that produced it never produces a second row
    (``jobs.export_processor.ExportJobProcessor`` looks one up by ``job_id``
    before generating anything, for idempotent replay after a crash).
    """

    __tablename__ = "exports"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_exports_job_id"),
        Index("ix_exports_submission_id", "submission_id"),
    )

    id: Mapped[str] = _pk()
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String, nullable=False)
    #: JSON list of ``{"question_id": ..., "version": ...}`` -- the
    #: `QuestionReviewVersion` snapshot this output was generated from.
    review_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class DependencyGraphRow(Base):
    """One version of one test's dependency graph (Issue #26).

    ``(test_id, version)`` is the real identity a repository upserts against:
    a DRAFT row is replaced in place by later analysis/confirm calls for the
    same version, but a CONFIRMED row is never updated again -- changing a
    confirmed graph means inserting a new, higher version (see
    ``domain.dependency_graph.DependencyGraph.confirm`` and
    docs/dependency-graph.md).
    """

    __tablename__ = "dependency_graphs"
    __table_args__ = (
        UniqueConstraint("test_id", "version", name="uq_dependency_graphs_test_version"),
        CheckConstraint("version >= 1", name="ck_dependency_graphs_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'confirmed')", name="ck_dependency_graphs_status_valid"
        ),
        # Mirrors DependencyGraph.__post_init__: a confirmed graph can never
        # carry unresolved questions, checked here too so a row written
        # outside the domain layer (repair, import) can't slip past it.
        CheckConstraint(
            "status != 'confirmed' OR json_array_length(unresolved) = 0",
            name="ck_dependency_graphs_confirmed_has_no_unresolved",
        ),
        # The check above only constrains CONFIRMED rows -- a DRAFT row had no
        # shape requirement at all, so a row written outside the domain
        # (repair, import, direct SQL) could persist `unresolved = 'null'`,
        # `'{}'`, or a bare scalar. `json_array_length` returns 0 for all of
        # those (SQLite: "0 if X is not a JSON array"), so they would even
        # slip past a CONFIRMED row's check above; but `DependencyGraph.
        # from_dict` always iterates `data["unresolved"]` expecting a JSON
        # array of question/reason objects, and hydration blows up on
        # anything else (Issue #26 review). Applies to every row regardless
        # of status.
        CheckConstraint(
            "json_valid(unresolved) AND json_type(unresolved) = 'array'",
            name="ck_dependency_graphs_unresolved_is_array",
        ),
        # Mirrors DependencyGraph.__post_init__'s status/confirmed_at pairing
        # (CONFIRMED <=> confirmed_at IS NOT NULL) at the DB layer too, so a
        # row written outside the domain (repair, import, direct SQL) can't
        # produce a state `_hydrate` refuses to load -- `DependencyGraph`'s
        # own constructor raises `DependencyGraphError` for exactly this
        # mismatch, which would otherwise surface as a 500 on every GET/list
        # of that row instead of being rejected at write time (Issue #26
        # review).
        CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="ck_dependency_graphs_confirmed_at_matches_status",
        ),
        # `DependencyGraph.__post_init__` requires `question_ids` to be a
        # non-empty set (a graph over zero questions is not a graph); nothing
        # short of the domain enforced that at the DB layer, so a row written
        # outside it (repair, import, direct SQL) could persist
        # `question_ids = '[]'` and every later GET/list of it would raise on
        # hydration (Issue #26 review). `json_valid` guards against a
        # non-JSON string reaching `json_array_length`, which would otherwise
        # error out the constraint check itself rather than simply failing it.
        CheckConstraint(
            "json_valid(question_ids) AND json_array_length(question_ids) > 0",
            name="ck_dependency_graphs_question_ids_non_empty",
        ),
        Index("ix_dependency_graphs_test_id", "test_id"),
    )

    id: Mapped[str] = _pk()
    test_id: Mapped[str] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DependencyGraphStatus] = mapped_column(
        _enum(DependencyGraphStatus), nullable=False
    )
    question_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unresolved: Mapped[list[dict[str, Any]]] = _json_list()
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DependencyEdgeRow(Base):
    """One edge of one dependency-graph version.

    Primary key is the composite ``(graph_id, from_question_id,
    to_question_id)`` -- there is no synthetic ``id``. A synthetic id built by
    joining the three parts with a separator (e.g. ``f"{graph_id}:{a}:{b}"``)
    can collide: question ids are only required to be non-empty (see
    ``domain.models._require_non_empty``), so ``from="a:b", to="c"`` and
    ``from="a", to="b:c"`` would produce the identical joined string even
    though they are different, otherwise-valid edges (Issue #26 review). The
    composite key sidesteps the whole class of separator-collision bugs.
    """

    __tablename__ = "dependency_edges"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_dependency_edges_confidence_range",
        ),
        # Mirrors `DependencyEdge.__post_init__`'s remaining invariants (only
        # `confidence` had a DB-level mirror before): a row written outside
        # the domain (repair, import, direct SQL) could otherwise persist a
        # self-loop, or an edge with no `provides`/blank `rationale`, and
        # `DependencyEdge`'s own constructor would raise `SelfLoopError`/
        # `DependencyGraphError` the next time that graph is hydrated,
        # breaking every API call touching it (Issue #26 review).
        CheckConstraint(
            "from_question_id != to_question_id", name="ck_dependency_edges_no_self_loop"
        ),
        # `domain.models._require_non_empty` requires both endpoint ids to be
        # non-blank strings; the self-loop check above compares them to each
        # other but never checks either against blank on its own (Issue #26
        # review).
        CheckConstraint(
            "length(trim(from_question_id)) > 0",
            name="ck_dependency_edges_from_question_id_non_empty",
        ),
        CheckConstraint(
            "length(trim(to_question_id)) > 0",
            name="ck_dependency_edges_to_question_id_non_empty",
        ),
        CheckConstraint(
            "json_valid(provides) AND json_array_length(provides) > 0",
            name="ck_dependency_edges_provides_non_empty",
        ),
        CheckConstraint(
            "length(trim(rationale)) > 0", name="ck_dependency_edges_rationale_non_empty"
        ),
        Index("ix_dependency_edges_graph_id", "graph_id"),
    )

    graph_id: Mapped[str] = mapped_column(
        ForeignKey("dependency_graphs.id", ondelete="CASCADE"), primary_key=True
    )
    from_question_id: Mapped[str] = mapped_column(String, primary_key=True)
    to_question_id: Mapped[str] = mapped_column(String, primary_key=True)
    provides: Mapped[list[DependencyProvision]] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


# The remaining invariants below need `json_each`, a table-valued function,
# to inspect array *elements* -- and SQLite's `CHECK` constraints cannot
# contain subqueries (including table-valued functions), so every one of
# these is a pair of `BEFORE INSERT`/`BEFORE UPDATE OF <col>` triggers
# instead of a `CheckConstraint`. All are mirrored in
# `migrations/versions/0003_dependency_graph.py`.

# `provides_non_empty` only checks JSON shape, not element values -- a row
# written outside the domain (repair, import, direct SQL) could still
# persist e.g. `provides = '["bogus"]'` or `provides = '[null]'`, which
# `DependencyProvision(...)` rejects with a `ValueError` the next time
# `_mappers.dependency_graph_from_rows` hydrates that graph (Issue #26
# review). `value NOT IN (...)` alone does not catch a JSON `null` element --
# SQL's `NULL NOT IN (...)` evaluates to NULL (neither true nor false), which
# `WHERE` treats as "don't select this row" -- so `value IS NULL` must be
# checked explicitly. Keep the value list in sync with
# `domain.dependency_graph.DependencyProvision`'s members.
_KNOWN_DEPENDENCY_PROVISIONS_SQL = "'recognized_text', 'score', 'criterion_result'"

_provides_known_values_insert_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    f"""
    CREATE TRIGGER trg_dependency_edges_provides_known_values_insert
    BEFORE INSERT ON dependency_edges
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.provides)
        WHERE value IS NULL OR value NOT IN ({_KNOWN_DEPENDENCY_PROVISIONS_SQL})
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_edges.provides contains an unknown value');
    END;
    """
)

_provides_known_values_update_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    f"""
    CREATE TRIGGER trg_dependency_edges_provides_known_values_update
    BEFORE UPDATE OF provides ON dependency_edges
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.provides)
        WHERE value IS NULL OR value NOT IN ({_KNOWN_DEPENDENCY_PROVISIONS_SQL})
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_edges.provides contains an unknown value');
    END;
    """
)

# `ck_dependency_graphs_question_ids_non_empty` only checks that
# `question_ids` is a non-empty JSON array, not that every element is a
# (non-blank) string -- a row written outside the domain could persist
# `question_ids = '[null]'` or `'["q1", null]'`, and `DependencyGraph`'s own
# type (`frozenset[str]`) plus every downstream consumer (layer/response
# sorting, API responses) expects plain strings, not `None` (Issue #26
# review).
_question_ids_elements_insert_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_graphs_question_ids_elements_insert
    BEFORE INSERT ON dependency_graphs
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.question_ids)
        WHERE json_each.type IS NOT 'text' OR length(trim(json_each.value)) = 0
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_graphs.question_ids contains a non-string or blank value');
    END;
    """
)

_question_ids_elements_update_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_graphs_question_ids_elements_update
    BEFORE UPDATE OF question_ids ON dependency_graphs
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.question_ids)
        WHERE json_each.type IS NOT 'text' OR length(trim(json_each.value)) = 0
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_graphs.question_ids contains a non-string or blank value');
    END;
    """
)

# `ck_dependency_graphs_unresolved_is_array` only checks the outer JSON
# shape -- each element must additionally be an object matching
# `UnresolvedQuestion`'s shape (non-blank string `question_id`/`reason`), or
# `UnresolvedQuestion.from_dict` raises the next time that graph is hydrated
# (Issue #26 review).
_unresolved_elements_insert_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_graphs_unresolved_elements_insert
    BEFORE INSERT ON dependency_graphs
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.unresolved)
        WHERE json_each.type IS NOT 'object'
           OR json_type(json_each.value, '$.question_id') IS NOT 'text'
           OR length(trim(json_extract(json_each.value, '$.question_id'))) = 0
           OR json_type(json_each.value, '$.reason') IS NOT 'text'
           OR length(trim(json_extract(json_each.value, '$.reason'))) = 0
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_graphs.unresolved contains a malformed entry');
    END;
    """
)

_unresolved_elements_update_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_graphs_unresolved_elements_update
    BEFORE UPDATE OF unresolved ON dependency_graphs
    FOR EACH ROW
    WHEN EXISTS (
        SELECT 1 FROM json_each(NEW.unresolved)
        WHERE json_each.type IS NOT 'object'
           OR json_type(json_each.value, '$.question_id') IS NOT 'text'
           OR length(trim(json_extract(json_each.value, '$.question_id'))) = 0
           OR json_type(json_each.value, '$.reason') IS NOT 'text'
           OR length(trim(json_extract(json_each.value, '$.reason'))) = 0
    )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_graphs.unresolved contains a malformed entry');
    END;
    """
)

event.listen(DependencyGraphRow.__table__, "after_create", _question_ids_elements_insert_trigger)
event.listen(DependencyGraphRow.__table__, "after_create", _question_ids_elements_update_trigger)
event.listen(DependencyGraphRow.__table__, "after_create", _unresolved_elements_insert_trigger)
event.listen(DependencyGraphRow.__table__, "after_create", _unresolved_elements_update_trigger)

event.listen(DependencyEdgeRow.__table__, "after_create", _provides_known_values_insert_trigger)
event.listen(DependencyEdgeRow.__table__, "after_create", _provides_known_values_update_trigger)

# The primary key / self-loop / non-empty checks above never verify an edge's
# endpoints actually belong to its own graph's `question_ids` snapshot -- a
# row written outside the domain (repair, import, direct SQL) could persist
# an edge whose `from_question_id`/`to_question_id` names a question that was
# never part of that graph version, and `DependencyGraph.__post_init__`
# raises `UnknownQuestionError` the next time it is hydrated, breaking every
# read of that graph (Issue #26 review). This needs a join against the
# parent `dependency_graphs` row, so -- like the element-value checks above
# -- it has to be a trigger, not a `CheckConstraint`.
_edge_endpoints_known_insert_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_edges_endpoints_known_insert
    BEFORE INSERT ON dependency_edges
    FOR EACH ROW
    WHEN
        NOT EXISTS (
            SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
            WHERE g.id = NEW.graph_id AND qi.value = NEW.from_question_id
        )
        OR NOT EXISTS (
            SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
            WHERE g.id = NEW.graph_id AND qi.value = NEW.to_question_id
        )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_edges endpoint is not in its graph''s question_ids');
    END;
    """
)

_edge_endpoints_known_update_trigger: DDL = DDL(  # type: ignore[no-untyped-call]
    """
    CREATE TRIGGER trg_dependency_edges_endpoints_known_update
    BEFORE UPDATE OF graph_id, from_question_id, to_question_id ON dependency_edges
    FOR EACH ROW
    WHEN
        NOT EXISTS (
            SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
            WHERE g.id = NEW.graph_id AND qi.value = NEW.from_question_id
        )
        OR NOT EXISTS (
            SELECT 1 FROM dependency_graphs g, json_each(g.question_ids) qi
            WHERE g.id = NEW.graph_id AND qi.value = NEW.to_question_id
        )
    BEGIN
        SELECT RAISE(ABORT, 'dependency_edges endpoint is not in its graph''s question_ids');
    END;
    """
)

event.listen(DependencyEdgeRow.__table__, "after_create", _edge_endpoints_known_insert_trigger)
event.listen(DependencyEdgeRow.__table__, "after_create", _edge_endpoints_known_update_trigger)


class OperationLogRow(Base):
    """Audit trail for destructive operations (business-rules §2 (11), §28).

    Added in migration ``0002`` — see that revision for the upgrade-an-existing-DB
    path exercised by the migration tests.
    """

    __tablename__ = "operation_log"
    __table_args__ = (Index("ix_operation_log_occurred_at", "occurred_at"),)

    id: Mapped[str] = _pk()
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
