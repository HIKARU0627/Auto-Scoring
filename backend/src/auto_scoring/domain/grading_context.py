"""Assemble the prerequisite context one dependent question's grading call may
see (Issue #20; business-rules-and-evaluation-data.md section 4.3).

Pure domain logic: given a confirmed `DependencyGraph` (Issue #26) and the
*already-resolved* latest usable result for each prerequisite question, this
builds exactly the `auto_scoring.domain.ai_provider.PrerequisiteAnswer` tuple
section 4.3 allows to cross into a dependent question's `GradingRequest` --
never the prerequisite's answer image, AI comment, or any student-identifying
data (section 4.3's "渡してはならないもの"), and never a question outside the
graph's own edges into this one.

Framework-free (see `AGENTS.md` "Architecture"): no I/O, no SQLAlchemy. The
caller (`auto_scoring.jobs.grading_processor.GradingJobProcessor`) is the one
that reads `RecognitionResult`/`GradeResult` rows from the database and picks
"the" result for each prerequisite question before calling this.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from auto_scoring.domain.ai_provider import PrerequisiteAnswer
from auto_scoring.domain.dependency_graph import DependencyGraph, DependencyProvision
from auto_scoring.domain.models import (
    CriterionResult,
    DomainError,
    GradeResult,
    GradeResultContextEntry,
    RecognitionResult,
)


class MissingPrerequisiteContextError(DomainError):
    """A prerequisite edge calls for data this caller did not supply.

    Should not happen in practice: `auto_scoring.domain.job_scheduling`
    already blocks a dependent question's `Job` until every prerequisite is
    USABLE, so by the time a `GradingJobProcessor` builds this context, the
    required rows should already exist. Raised defensively rather than
    silently omitting the provision or fabricating a value -- the same
    "never guess" rule the schema-violation/needs-review paths already
    follow (AGENTS.md "Verification").
    """

    def __init__(self, question_id: str, provision: DependencyProvision) -> None:
        super().__init__(
            f"prerequisite question {question_id!r} has no result for {provision.value!r}, "
            "but a confirmed dependency edge requires it"
        )
        self.question_id = question_id
        self.provision = provision


@dataclass(frozen=True, kw_only=True)
class PrerequisiteSource:
    """The single, already-chosen result row for one prerequisite question.

    Callers resolve "the" `RecognitionResult`/`GradeResult` for a
    prerequisite (e.g. preferring a human confirmation over an AI proposal)
    before calling `build_prerequisite_context` -- this module only shapes
    whatever was chosen into the provider-facing form, and does not itself
    pick among a question's result history.
    """

    recognition: RecognitionResult | None = None
    grade: GradeResult | None = None


def build_prerequisite_context(
    graph: DependencyGraph,
    question_id: str,
    *,
    sources: Mapping[str, PrerequisiteSource],
) -> tuple[PrerequisiteAnswer, ...]:
    """One `PrerequisiteAnswer` per prerequisite edge into ``question_id``.

    ``sources`` maps a prerequisite question id to the single result row
    chosen for it; a question with no incoming edge (or no edges in
    ``graph`` at all) yields an empty tuple. Raises
    `MissingPrerequisiteContextError` if an edge's `provides` calls for data
    ``sources`` does not have for that prerequisite.
    """
    answers: list[PrerequisiteAnswer] = []
    prerequisite_edges = sorted(
        (edge for edge in graph.edges if edge.to_question_id == question_id),
        key=lambda edge: edge.from_question_id,
    )
    for edge in prerequisite_edges:
        source = sources.get(edge.from_question_id, PrerequisiteSource())
        recognized_text: str | None = None
        score: int | None = None
        max_score: int | None = None
        criteria: tuple[CriterionResult, ...] = ()

        if DependencyProvision.RECOGNIZED_TEXT in edge.provides:
            if source.recognition is None:
                raise MissingPrerequisiteContextError(
                    edge.from_question_id, DependencyProvision.RECOGNIZED_TEXT
                )
            recognized_text = source.recognition.text

        if DependencyProvision.SCORE in edge.provides:
            if source.grade is None:
                raise MissingPrerequisiteContextError(
                    edge.from_question_id, DependencyProvision.SCORE
                )
            score = source.grade.score.awarded
            max_score = source.grade.score.maximum

        if DependencyProvision.CRITERION_RESULT in edge.provides:
            if source.grade is None or not source.grade.criteria:
                raise MissingPrerequisiteContextError(
                    edge.from_question_id, DependencyProvision.CRITERION_RESULT
                )
            criteria = source.grade.criteria

        answers.append(
            PrerequisiteAnswer(
                question_id=edge.from_question_id,
                provides=edge.provides,
                recognized_text=recognized_text,
                score=score,
                max_score=max_score,
                criteria=criteria,
            )
        )
    return tuple(answers)


def build_context_entries(
    graph: DependencyGraph,
    question_id: str,
    *,
    sources: Mapping[str, PrerequisiteSource],
) -> tuple[GradeResultContextEntry, ...]:
    """Traceability rows for `GradeResult.context`: which prerequisite result
    row(s) fed this grading call, for every prerequisite question of
    ``question_id`` -- independent of `build_prerequisite_context`'s
    provider-facing shape, so the two never drift (both walk the same
    ``prerequisite_edges``).
    """
    entries: list[GradeResultContextEntry] = []
    prerequisite_ids = sorted(
        {edge.from_question_id for edge in graph.edges if edge.to_question_id == question_id}
    )
    for prerequisite_id in prerequisite_ids:
        source = sources.get(prerequisite_id, PrerequisiteSource())
        recognition_id = source.recognition.id if source.recognition is not None else None
        grade_id = source.grade.id if source.grade is not None else None
        if recognition_id is None and grade_id is None:
            continue
        entries.append(
            GradeResultContextEntry(
                question_id=prerequisite_id,
                recognition_result_id=recognition_id,
                grade_result_id=grade_id,
            )
        )
    return tuple(entries)
