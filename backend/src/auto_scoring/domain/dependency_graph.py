"""Dependency graph domain model (Issue #26).

A dependency graph says which questions of one test must be recognized/graded
before which others: an edge ``A -> B`` means "grading/recognizing B needs A's
result". The graph is analyzed once per test (not per submission, see
docs/dependency-graph.md) and goes through the same draft-then-human-review
lifecycle PoC 4's `Profile` established (`from_candidates` -> `confirm`):

* AI-generated candidates are always saved as :class:`DependencyGraphStatus.DRAFT`.
* A human reviews them; :meth:`DependencyGraph.confirm` is the only path to
  :class:`DependencyGraphStatus.CONFIRMED`, and only a CONFIRMED graph may gate
  Submission processing (see ``can_start_submission_processing``).
* Ambiguous relationships the analyzer could not resolve are never silently
  treated as "no dependency" -- they are carried as :class:`UnresolvedQuestion`
  entries so a human sees exactly what still needs a decision.
* self-loops, edges referencing unknown question ids, duplicate edges and
  cycles are all rejected at construction time with the offending ids named in
  the error, so nothing invalid is ever stored.

Framework-free (see `AGENTS.md` "Architecture" -- the domain must not import
FastAPI, SQLAlchemy, or any external SDK).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any


class DependencyGraphError(Exception):
    """A dependency-graph rule was violated."""


class SelfLoopError(DependencyGraphError):
    """A question was made to depend on itself."""

    def __init__(self, question_id: str) -> None:
        super().__init__(f"question {question_id!r} cannot depend on itself")
        self.question_id = question_id


class UnknownQuestionError(DependencyGraphError):
    """An edge or unresolved entry referenced a question id outside the graph."""

    def __init__(self, question_ids: Sequence[str]) -> None:
        ids = ", ".join(sorted(set(question_ids)))
        super().__init__(f"references question ids not in this graph: {ids}")
        self.question_ids = tuple(question_ids)


class DuplicateEdgeError(DependencyGraphError):
    """The same ``from -> to`` pair was declared more than once."""

    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        rendered = ", ".join(f"{a}->{b}" for a, b in pairs)
        super().__init__(f"duplicate dependency edges: {rendered}")
        self.pairs = tuple(pairs)


class CycleDetectedError(DependencyGraphError):
    """The edge set is not a DAG; ``cycle_question_ids`` names the offenders."""

    def __init__(self, cycle_question_ids: Sequence[str]) -> None:
        rendered = ", ".join(cycle_question_ids)
        super().__init__(f"dependency graph contains a cycle among: {rendered}")
        self.cycle_question_ids = tuple(cycle_question_ids)


class DependencyProvision(StrEnum):
    """What a prerequisite question hands to its dependent (§9.2 result shape)."""

    RECOGNIZED_TEXT = "recognized_text"
    SCORE = "score"
    CRITERION_RESULT = "criterion_result"


class DependencyGraphStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, kw_only=True)
class DependencyEdge:
    """``from_question_id -> to_question_id``: grading ``to`` needs ``from``'s result."""

    from_question_id: str
    to_question_id: str
    provides: tuple[DependencyProvision, ...]
    rationale: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.from_question_id.strip():
            raise DependencyGraphError("DependencyEdge.from_question_id must be non-empty")
        if not self.to_question_id.strip():
            raise DependencyGraphError("DependencyEdge.to_question_id must be non-empty")
        if self.from_question_id == self.to_question_id:
            raise SelfLoopError(self.from_question_id)
        if not self.provides:
            raise DependencyGraphError("DependencyEdge.provides must include at least one item")
        if not self.rationale.strip():
            raise DependencyGraphError("DependencyEdge.rationale must be non-empty (根拠は必須)")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise DependencyGraphError(
                f"DependencyEdge.confidence must be within 0..1, got {self.confidence}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_question_id": self.from_question_id,
            "to_question_id": self.to_question_id,
            "provides": [p.value for p in self.provides],
            "rationale": self.rationale,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DependencyEdge:
        return cls(
            from_question_id=str(data["from_question_id"]),
            to_question_id=str(data["to_question_id"]),
            provides=tuple(DependencyProvision(p) for p in data["provides"]),
            rationale=str(data["rationale"]),
            confidence=data.get("confidence"),
        )


@dataclass(frozen=True, kw_only=True)
class UnresolvedQuestion:
    """A question the analyzer found signal for but could not confidently resolve.

    Never inferred away as "no dependency" (Issue #26: "分析不能・曖昧な関係は
    「依存なし」と推測せず、要確認として…根拠不足を表示する").
    """

    question_id: str
    reason: str

    def __post_init__(self) -> None:
        if not self.question_id.strip():
            raise DependencyGraphError("UnresolvedQuestion.question_id must be non-empty")
        if not self.reason.strip():
            raise DependencyGraphError("UnresolvedQuestion.reason must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {"question_id": self.question_id, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UnresolvedQuestion:
        return cls(question_id=str(data["question_id"]), reason=str(data["reason"]))


def _duplicate_pairs(edges: Sequence[DependencyEdge]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    dupes: list[tuple[str, str]] = []
    for edge in edges:
        pair = (edge.from_question_id, edge.to_question_id)
        if pair in seen:
            dupes.append(pair)
        seen.add(pair)
    return dupes


def _kahn_layers(
    question_ids: frozenset[str], edges: Sequence[DependencyEdge]
) -> tuple[tuple[str, ...], ...]:
    """Group every question into parallel-execution layers (Kahn's algorithm).

    Each layer holds every question whose prerequisites are all in an earlier
    layer, so independent questions always land in the same layer (Issue #26:
    "依存なしの全設問は同じ実行層となり、不要な直列化を行わない"). Raises
    :class:`CycleDetectedError` -- naming the leftover ids -- if the edge set is
    not a DAG.
    """
    adjacency: dict[str, list[str]] = {qid: [] for qid in question_ids}
    remaining_in_degree: dict[str, int] = dict.fromkeys(question_ids, 0)
    for edge in edges:
        adjacency[edge.from_question_id].append(edge.to_question_id)
        remaining_in_degree[edge.to_question_id] += 1

    placed: set[str] = set()
    layers: list[tuple[str, ...]] = []
    while len(placed) < len(question_ids):
        layer = sorted(
            qid for qid in question_ids if qid not in placed and remaining_in_degree[qid] == 0
        )
        if not layer:
            cycle_nodes = tuple(sorted(qid for qid in question_ids if qid not in placed))
            raise CycleDetectedError(cycle_nodes)
        placed.update(layer)
        for qid in layer:
            for neighbor in adjacency[qid]:
                remaining_in_degree[neighbor] -= 1
        layers.append(tuple(layer))
    return tuple(layers)


@dataclass(frozen=True, kw_only=True)
class DependencyGraph:
    """One version of one test's dependency graph, at a point in its review lifecycle.

    Immutable once :attr:`status` is CONFIRMED: changing a confirmed graph
    means creating a new, higher :attr:`version` (Issue #26: "確定graphを変更
    した場合はversionを更新し、古いgraphで未完了の採点jobを無効化・再作成できる
    ようにする" -- see docs/dependency-graph.md for the scope this covers).
    """

    id: str
    test_id: str
    version: int
    question_ids: frozenset[str]
    edges: tuple[DependencyEdge, ...]
    unresolved: tuple[UnresolvedQuestion, ...]
    status: DependencyGraphStatus
    created_at: datetime
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DependencyGraphError("DependencyGraph.id must be non-empty")
        if not self.test_id.strip():
            raise DependencyGraphError("DependencyGraph.test_id must be non-empty")
        if self.version < 1:
            raise DependencyGraphError("DependencyGraph.version must be >= 1")
        if not self.question_ids:
            raise DependencyGraphError("DependencyGraph must contain at least one question")

        unknown_edge_refs = [
            qid
            for edge in self.edges
            for qid in (edge.from_question_id, edge.to_question_id)
            if qid not in self.question_ids
        ]
        unknown_unresolved_refs = [
            unresolved.question_id
            for unresolved in self.unresolved
            if unresolved.question_id not in self.question_ids
        ]
        unknown_refs = unknown_edge_refs + unknown_unresolved_refs
        if unknown_refs:
            raise UnknownQuestionError(unknown_refs)

        dupes = _duplicate_pairs(self.edges)
        if dupes:
            raise DuplicateEdgeError(dupes)

        _kahn_layers(self.question_ids, self.edges)  # raises CycleDetectedError

        if self.status is DependencyGraphStatus.CONFIRMED:
            if self.confirmed_at is None:
                raise DependencyGraphError("a confirmed graph must record confirmed_at")
        elif self.confirmed_at is not None:
            raise DependencyGraphError("a draft graph cannot have confirmed_at set")

    @classmethod
    def from_candidates(
        cls,
        *,
        id: str,
        test_id: str,
        version: int,
        question_ids: Sequence[str],
        edges: Sequence[DependencyEdge] = (),
        unresolved: Sequence[UnresolvedQuestion] = (),
        created_at: datetime,
    ) -> DependencyGraph:
        """Save analyzer-generated candidates. Always DRAFT.

        Mirrors `Profile.from_candidates` (PoC 4 / Issue #15): the acceptance
        criterion "AIによる候補はdraftとして保存し、人間が…確認するまで採点開始
        を許可しない" is enforced here, not left to callers to remember.
        """
        return cls(
            id=id,
            test_id=test_id,
            version=version,
            question_ids=frozenset(question_ids),
            edges=tuple(edges),
            unresolved=tuple(unresolved),
            status=DependencyGraphStatus.DRAFT,
            created_at=created_at,
        )

    def confirm(
        self, *, edges: Sequence[DependencyEdge], confirmed_at: datetime
    ) -> DependencyGraph:
        """Human review step: replace the candidate edges with the human-reviewed set.

        The human's final edge list supersedes every draft candidate and every
        `unresolved` entry -- once confirmed, ambiguity has been explicitly
        resolved one way or another, so a confirmed graph never carries
        `unresolved` entries. Raises if this version is already confirmed
        (confirmed versions are immutable; start a new version instead).
        """
        if self.status is DependencyGraphStatus.CONFIRMED:
            raise DependencyGraphError(
                f"dependency graph {self.id!r} (test {self.test_id!r} v{self.version}) is "
                "already confirmed; create a new version to change it"
            )
        return replace(
            self,
            edges=tuple(edges),
            unresolved=(),
            status=DependencyGraphStatus.CONFIRMED,
            confirmed_at=confirmed_at,
        )

    def topological_layers(self) -> tuple[tuple[str, ...], ...]:
        """Parallel-execution layers, in dependency order (see `_kahn_layers`)."""
        return _kahn_layers(self.question_ids, self.edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "test_id": self.test_id,
            "version": self.version,
            "question_ids": sorted(self.question_ids),
            "edges": [edge.to_dict() for edge in self.edges],
            "unresolved": [unresolved.to_dict() for unresolved in self.unresolved],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "confirmed_at": (
                self.confirmed_at.isoformat() if self.confirmed_at is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DependencyGraph:
        confirmed_at = data.get("confirmed_at")
        return cls(
            id=str(data["id"]),
            test_id=str(data["test_id"]),
            version=int(data["version"]),
            question_ids=frozenset(str(qid) for qid in data["question_ids"]),
            edges=tuple(DependencyEdge.from_dict(edge) for edge in data["edges"]),
            unresolved=tuple(UnresolvedQuestion.from_dict(u) for u in data["unresolved"]),
            status=DependencyGraphStatus(data["status"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            confirmed_at=datetime.fromisoformat(str(confirmed_at)) if confirmed_at else None,
        )


def can_start_submission_processing(graph: DependencyGraph | None) -> bool:
    """Gate for Issue #26's acceptance criterion:

    "人間未確認または分析失敗のgraphではSubmissionのOCR/AI採点を開始できない".
    ``None`` covers both "no graph was ever produced" (analysis failure) and
    "not analyzed yet"; anything short of a human-confirmed graph blocks
    processing.
    """
    return graph is not None and graph.status is DependencyGraphStatus.CONFIRMED
