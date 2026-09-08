"""Turn a scanned folder plus a template into the plan a human confirms
(Issue #101).

The plan is the thing the confirmation screen renders, and it is deliberately
a *proposal*: every file carries where its role came from
(:class:`RoleSource`), so the screen can show a rule-matched file and an
LLM-guessed file differently, and so "nothing decided this yet" is a state
that exists rather than being papered over with a default.

Two design points worth stating, because both were requirements rather than
conveniences:

* **A group is bound to a target, not equated with a new test.** The
  observed workflow is that criteria arrive once for eleven subjects and
  answers arrive weekly, so the common case from week two onward is "add
  these answers to a test that already exists". A group bound to an existing
  test is not missing its grading criteria -- that test already has one.
  See :class:`GroupTarget`.
* **What cannot be classified says so.** Only PDFs can be rendered to a page
  image, so an unmatched Word/Excel file is reported as
  :attr:`ClassificationNeed.UNSUPPORTED`, not quietly counted into an LLM
  estimate that would never be spent on it.

Framework-free (``AGENTS.md`` "Architecture"). Pure functions over the
listing the app scanned; nothing here touches a disk or a network.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

from auto_scoring.domain.intake_template import (
    IntakeTemplate,
    MaterialRole,
    ScannedFile,
    classify_by_rules,
)


class RoleSource(StrEnum):
    """Where a file's proposed role came from.

    Rendered on the confirmation screen, because "a rule matched this name"
    and "a model looked at the first page and guessed" deserve different
    amounts of the reviewer's attention -- and :attr:`UNRESOLVED` deserves
    all of it.
    """

    #: A template rule matched the name. Free and instant; no LLM call.
    RULE = "rule"
    #: An LLM looked at the first page. A proposal, never applied on its own.
    LLM = "llm"
    #: The reviewer chose it. Outranks everything above.
    HUMAN = "human"
    #: Nothing decided it yet.
    UNRESOLVED = "unresolved"


class ClassificationNeed(StrEnum):
    """Whether this file would cost an LLM call, and if not, why not.

    This is what makes the pre-flight "how many calls, roughly how much"
    number on the confirmation screen honest: each file lands in exactly one
    of these, and only :attr:`PENDING` is charged for.
    """

    #: A rule already proposed a role (Issue #101: "名前の規則が当たった
    #: ファイルは LLM を呼ばない").
    NOT_NEEDED = "not_needed"
    #: Would be sent. This is the only bucket that costs anything.
    PENDING = "pending"
    #: This exact content was classified before, keyed by its digest.
    CACHED = "cached"
    #: No page image can be produced for it (Word/Excel and anything else
    #: that is not a PDF), so an LLM cannot look at it. The reviewer assigns
    #: the role by hand. Reported rather than hidden: promising a
    #: classification that structurally cannot happen is worse than saying so.
    UNSUPPORTED = "unsupported"


#: Extensions the sidecar can render a first page from. Kept here rather than
#: in the adapter so the *estimate* and the *capability* cannot drift apart:
#: a file counted as PENDING must be one `POST /intake/classify` can actually
#: accept.
CLASSIFIABLE_EXTENSIONS = frozenset({".pdf"})


class GroupTargetKind(StrEnum):
    """What a group of files is going to be imported into."""

    #: Create a new test from this group. Requires the template's REQUIRED
    #: roles to be present -- enforced by ``POST /tests`` itself, which
    #: cannot be called without the grading-criteria file.
    NEW = "new"
    #: Add these files to a test that is already registered. Needs no grading
    #: criteria: that test already has one. This is the weekly flow.
    EXISTING = "existing"
    #: The reviewer has not said yet. Cannot be imported in this state.
    UNASSIGNED = "unassigned"


@dataclass(frozen=True, kw_only=True)
class GroupTarget:
    kind: GroupTargetKind
    #: Set only for :attr:`GroupTargetKind.EXISTING`.
    test_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind is GroupTargetKind.EXISTING and not (self.test_id or "").strip():
            raise ValueError("GroupTarget.test_id is required when kind is EXISTING")
        if self.kind is not GroupTargetKind.EXISTING and self.test_id is not None:
            raise ValueError("GroupTarget.test_id is only meaningful when kind is EXISTING")


@dataclass(frozen=True, kw_only=True)
class PlannedFile:
    """One file, its proposed role, and what deciding that role would cost."""

    relative_path: str
    sha256: str
    size_bytes: int
    role: MaterialRole | None
    role_source: RoleSource
    classification: ClassificationNeed


@dataclass(frozen=True, kw_only=True)
class PlannedGroup:
    """One folder's worth of files, and what is missing if it becomes a test.

    ``missing_required_roles_if_new`` is computed unconditionally, under the
    assumption the group creates a new test, because the plan is built before
    the reviewer has chosen a target. A group later bound to an existing test
    ignores it -- see :func:`unmet_requirements`, which is the function that
    actually answers "can this be imported".
    """

    key: str
    suggested_name: str
    files: tuple[PlannedFile, ...]
    missing_required_roles_if_new: tuple[MaterialRole, ...]


@dataclass(frozen=True, kw_only=True)
class ClassificationEstimate:
    """The pre-flight numbers shown before anything is sent (Issue #101 #7).

    Attribution calls are not counted here: which answers need attributing
    depends on the reviewer's own narrowing of the candidate list, which
    happens after this plan is built. The screen adds that number live.
    """

    pending: int
    cached: int
    unsupported: int
    not_needed: int


@dataclass(frozen=True, kw_only=True)
class IntakePlan:
    groups: tuple[PlannedGroup, ...]
    estimate: ClassificationEstimate


def _extension(relative_path: str) -> str:
    name = relative_path.rsplit("/", 1)[-1]
    stem, dot, extension = name.rpartition(".")
    return f".{extension.strip().lower()}" if dot and stem else ""


def _group_key(relative_path: str, *, split_child_directories: bool) -> str:
    """Which group a file belongs to.

    With ``split_child_directories`` (the default), the *first* path segment
    is the group: choosing the parent of eleven subject folders yields eleven
    groups, and a file sitting loose at the top belongs to the root group
    (``""``). Nesting deeper than one level still groups by that first
    segment -- a subject folder with subfolders is still one test.
    """
    if not split_child_directories:
        return ""
    head, separator, _ = relative_path.partition("/")
    return head if separator else ""


def build_plan(
    files: Sequence[ScannedFile],
    template: IntakeTemplate,
    *,
    root_name: str,
    cached_digests: Collection[str] = (),
) -> IntakePlan:
    """Build the plan the confirmation screen renders.

    ``root_name`` names the folder the reviewer chose; it becomes the
    suggested test name for files that are not inside a child folder.
    ``cached_digests`` are the ``sha256`` values already classified, so a
    re-import of the same content costs nothing and is not asked about twice.
    """
    cached = set(cached_digests)
    assignments = classify_by_rules(files, template)
    required = template.required_roles()

    grouped: dict[str, list[PlannedFile]] = {}
    order: list[str] = []
    for assignment in assignments:
        extension = _extension(assignment.file.relative_path)
        if assignment.role is not None:
            need = ClassificationNeed.NOT_NEEDED
        elif extension not in CLASSIFIABLE_EXTENSIONS:
            need = ClassificationNeed.UNSUPPORTED
        elif assignment.file.sha256 in cached:
            need = ClassificationNeed.CACHED
        else:
            need = ClassificationNeed.PENDING

        planned = PlannedFile(
            relative_path=assignment.file.relative_path,
            sha256=assignment.file.sha256,
            size_bytes=assignment.file.size_bytes,
            role=assignment.role,
            role_source=RoleSource.RULE if assignment.role is not None else RoleSource.UNRESOLVED,
            classification=need,
        )
        key = _group_key(
            assignment.file.relative_path,
            split_child_directories=template.split_child_directories,
        )
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(planned)

    groups = tuple(
        PlannedGroup(
            key=key,
            suggested_name=key or root_name,
            files=tuple(grouped[key]),
            missing_required_roles_if_new=tuple(
                role
                for role in required
                if not any(planned.role is role for planned in grouped[key])
            ),
        )
        for key in order
    )

    counts = {need: 0 for need in ClassificationNeed}
    for group in groups:
        for planned in group.files:
            counts[planned.classification] += 1
    return IntakePlan(
        groups=groups,
        estimate=ClassificationEstimate(
            pending=counts[ClassificationNeed.PENDING],
            cached=counts[ClassificationNeed.CACHED],
            unsupported=counts[ClassificationNeed.UNSUPPORTED],
            not_needed=counts[ClassificationNeed.NOT_NEEDED],
        ),
    )


def unmet_requirements(
    group: PlannedGroup, target: GroupTarget, *, required_roles: Sequence[MaterialRole]
) -> tuple[MaterialRole, ...]:
    """Which required roles block importing ``group`` into ``target``.

    Empty for an :attr:`GroupTargetKind.EXISTING` target: the grading
    criteria a new test would need are already attached to the test being
    added to, which is what makes the weekly "answers only" folder importable
    at all (Issue #101 follow-up A).

    This is advisory -- it drives the screen's warning. What actually
    prevents a criteria-less test from being created is the ``POST /tests``
    signature, which has no way to be called without that file.
    """
    if target.kind is not GroupTargetKind.NEW:
        return ()
    present = {planned.role for planned in group.files if planned.role is not None}
    return tuple(role for role in required_roles if role not in present)
