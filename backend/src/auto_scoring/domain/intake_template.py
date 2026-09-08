"""Reusable "取込の型": name rules that propose a role for each scanned file
(Issue #101).

A *template* is the shape a batch of grading material is expected to have --
"files starting with `01_` are student answers, `02_` is the grading
criteria, ...". It exists because the structure of a real batch is decided
by the cram school, not by this app: the numbering convention observed in
one school's material is only a **default**, and a school that names things
differently must be usable by editing the template rather than by changing
code.

**A rule never decides anything.** What it produces is a *proposal* that a
human confirms before anything is imported (Issue #101 stage 3). This
distinction is the whole reason it is safe to match on file names at all:
the observed material proved that names cannot be trusted --

* the separator is inconsistent (``04-1_`` and ``04_1_`` both occur),
* sample numbering mixes ``①②③`` with ``1 2 3``,
* one file has a doubled extension (``....pdf.pdf``),
* one file has whitespace immediately before its extension,
* a role word can be followed by a suffix (``A``, ``(A3・B1)``),
* the ``.txt`` companion file is present for some subjects and not others,
* **and one subject's sample file is named after a different subject's
  course** (the two share a task).

The last one is why nothing in this module ever looks at a subject name:
matching is anchored on the leading serial number only. The rest are handled
by :func:`normalize_for_matching`, which is applied to the file name *and*
to the rule's own pattern, so the two always meet in the same normal form.

Framework-free (``AGENTS.md`` "Architecture"): no FastAPI, no SQLAlchemy, no
filesystem access. Callers hand in an already-scanned listing.

**Nothing here may be logged.** A ``relative_path`` carries the school's own
course names; it travels from the app to the local sidecar and back, and
must not reach a log line, an exception message, or a recorded dataset (the
same rule Issue #35 established for provider payloads).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

from auto_scoring.domain.models import DomainError


class IntakeTemplateError(DomainError):
    """A template (or a rule inside it) is not usable."""


class MaterialRole(StrEnum):
    """What one file is, once a human has confirmed it.

    Mirrors the material kinds Issue #95 recorded for the real batches. Note
    what is *not* here: there is no "model answer" role. The model-answer PDF
    was dropped as a required input (Issue #95 decision 1) because it does
    not exist in the real material -- a model answer that happens to be on
    hand is imported as :attr:`REFERENCE`.
    """

    #: 生徒答案. Becomes a `Submission` of the test it is bound to.
    STUDENT_ANSWER = "student_answer"
    #: 採点基準. The required material for a *newly created* test.
    GRADING_CRITERIA = "grading_criteria"
    #: 添削資料 (Word / Excel). Optional but strongly recommended.
    ANNOTATION_RESOURCE = "annotation_resource"
    #: 添削サンプル. A marked-up example answer.
    ANNOTATION_SAMPLE = "annotation_sample"
    #: 参考資料. Anything else worth keeping, including a model answer.
    REFERENCE = "reference"
    #: Explicitly not imported (e.g. the companion ``.txt`` notes).
    IGNORE = "ignore"


class Requirement(StrEnum):
    """How badly a role is needed, for the confirmation screen's own warning.

    Only :attr:`REQUIRED` is enforced, and only for a group that creates a
    *new* test -- a group that adds files to an already-registered test needs
    no grading criteria, because that test already has one (Issue #101, the
    second-week flow). The enforcement itself is not here: it is the
    ``POST /tests`` signature, which cannot be called without the criteria
    file at all (``AGENTS.md``: guarantee invariants with real constraints,
    not with UI state).
    """

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class RuleScope(StrEnum):
    """What a rule's pattern is matched against."""

    #: The file's own (normalized) name.
    FILE = "file"
    #: The name of the folder directly containing the file. This is what lets
    #: one rule cover a folder of forty answers -- see `IntakeRule.pattern`.
    FOLDER = "folder"


#: Longest pattern/name we will compile a matcher for. A template is
#: user-editable and round-trips through JSON, so an absurdly long pattern is
#: reachable input rather than a theoretical one; bounding it keeps
#: `_compiled_pattern`'s cache (and the regex it builds) small.
MAX_PATTERN_LENGTH = 200

#: Bound on a template's own fields, for the same reason.
MAX_TEMPLATE_NAME_LENGTH = 100

#: Bound on how many rules one template may carry. Rules are evaluated in
#: order for every scanned file, so this is what stops a pathological
#: template from turning a 500-file scan into a quadratic walk.
MAX_RULES_PER_TEMPLATE = 100


def _strip_doubled_extension(name: str) -> str:
    """``"a.pdf.pdf"`` -> ``"a.pdf"``; anything else unchanged.

    Only collapses when the two trailing extensions are *identical*: a real
    file named ``"notes.tar.gz"`` must keep both. Observed once in the real
    material, where a file had its extension appended twice.
    """
    stem, dot, extension = name.rpartition(".")
    if not dot:
        return name
    inner_stem, inner_dot, inner_extension = stem.rpartition(".")
    if inner_dot and inner_extension == extension:
        return f"{inner_stem}.{extension}"
    return name


def normalize_for_matching(value: str) -> str:
    """Put a file name (or a rule pattern) into the one form both are matched in.

    Applied to **both** sides, which is what makes the transformations below
    safe: a template author who writes ``04-1_*`` and a file actually named
    ``04_1_...`` meet in the middle instead of one of them having to know
    about the other.

    The steps, each traceable to something observed in the real material:

    * ``NFKC`` -- folds ``①②③`` onto ``1 2 3`` and full-width digits onto
      ASCII, so sample numbering written either way matches one rule.
    * lower-cased -- ``.PDF`` and ``.pdf`` are the same file kind.
    * whitespace stripped from both ends, and removed immediately before the
      final ``.`` -- one real file has a space sitting there.
    * ``-`` folded onto ``_`` -- the separator is inconsistent between
      subjects (``04-1_`` vs ``04_1_``) and neither spelling is more correct
      than the other.

    Deliberately *not* done: anything involving a subject or course name. One
    subject's file is named after a different subject's course, so a name's
    subject word is not evidence about what the file is.
    """
    text = unicodedata.normalize("NFKC", value).strip().lower()
    # Before the doubled-extension check, so `"a.pdf .pdf"` collapses too.
    text = re.sub(r"\s+(?=\.[^.]*$)", "", text)
    text = _strip_doubled_extension(text)
    return text.replace("-", "_")


@lru_cache(maxsize=512)
def _compiled_pattern(normalized_pattern: str) -> re.Pattern[str]:
    """Compile a normalized glob pattern, supporting only ``*`` and ``?``.

    Hand-translated rather than handed to :mod:`fnmatch` because
    :func:`normalize_for_matching` runs over the pattern too: it folds ``-``
    onto ``_``, which would silently corrupt a character range like
    ``[a-z]`` into ``[a_z]``. Supporting only the two wildcards a template
    author actually needs means every other character -- brackets included --
    is escaped and matches itself, so no pattern can be broken by
    normalization.
    """
    parts = []
    for character in normalized_pattern:
        if character == "*":
            parts.append(".*")
        elif character == "?":
            parts.append(".")
        else:
            parts.append(re.escape(character))
    return re.compile("".join(parts) + r"\Z")


def matches_pattern(pattern: str, value: str) -> bool:
    """Whether ``value`` matches ``pattern``, both taken through
    :func:`normalize_for_matching` first.
    """
    return (
        _compiled_pattern(normalize_for_matching(pattern)).match(normalize_for_matching(value))
        is not None
    )


@dataclass(frozen=True, kw_only=True)
class IntakeRule:
    """One line of a template: "names shaped like *this* are probably *that*".

    ``pattern`` is a glob over the normalized name (``*`` and ``?`` only).
    With ``scope=FOLDER`` it is matched against the containing folder's name
    instead of the file's, which is how a folder holding forty answers is
    covered by a single rule -- and, downstream, collapses to a single row on
    the confirmation screen rather than forty (Issue #101: the reviewer must
    not have to click once per answer).
    """

    scope: RuleScope
    pattern: str
    role: MaterialRole
    requirement: Requirement = Requirement.OPTIONAL

    def __post_init__(self) -> None:
        if not self.pattern.strip():
            raise IntakeTemplateError("IntakeRule.pattern must not be blank")
        if len(self.pattern) > MAX_PATTERN_LENGTH:
            raise IntakeTemplateError(
                f"IntakeRule.pattern must be at most {MAX_PATTERN_LENGTH} characters"
            )
        if self.role is MaterialRole.IGNORE and self.requirement is not Requirement.OPTIONAL:
            # "required" and "ignore" contradict each other: the confirmation
            # screen would report the group as incomplete for a role nothing
            # can ever satisfy, since an IGNORE file is never imported.
            raise IntakeTemplateError("a rule with role IGNORE must have requirement OPTIONAL")


@dataclass(frozen=True, kw_only=True)
class IntakeTemplate:
    """An ordered rule list, saved under a name and reusable across batches.

    Rules are evaluated **in order, first match wins**. Order is therefore
    part of the template's meaning, which is why the settings screen lets a
    rule be moved rather than only added and removed.

    ``split_child_directories`` says how a chosen folder is read: when true
    (the default, and what the observed material needs), each *child* folder
    becomes its own group -- selecting the parent of eleven subject folders
    imports eleven tests. When false, everything under the chosen folder is
    one group.
    """

    id: str
    name: str
    rules: tuple[IntakeRule, ...] = ()
    split_child_directories: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise IntakeTemplateError("IntakeTemplate.id must not be blank")
        if not self.name.strip():
            raise IntakeTemplateError("IntakeTemplate.name must not be blank")
        if len(self.name) > MAX_TEMPLATE_NAME_LENGTH:
            raise IntakeTemplateError(
                f"IntakeTemplate.name must be at most {MAX_TEMPLATE_NAME_LENGTH} characters"
            )
        if len(self.rules) > MAX_RULES_PER_TEMPLATE:
            raise IntakeTemplateError(
                f"IntakeTemplate.rules must hold at most {MAX_RULES_PER_TEMPLATE} rules"
            )

    def required_roles(self) -> tuple[MaterialRole, ...]:
        """Roles this template marks ``REQUIRED``, de-duplicated, in rule order."""
        seen: list[MaterialRole] = []
        for rule in self.rules:
            if rule.requirement is Requirement.REQUIRED and rule.role not in seen:
                seen.append(rule.role)
        return tuple(seen)


#: Id of the template seeded on first use. Stable, because a saved batch
#: setting refers to a template by id.
DEFAULT_TEMPLATE_ID = "serial-number-prefix"

#: The numbering convention observed across eleven subject folders of real
#: material (Issue #101). Seeded as a starting point, **not** as a claim
#: about what grading material looks like in general -- every rule here is
#: editable, and a school that numbers files differently is expected to
#: replace them. `01_`/`02_` are marked required because a newly created test
#: cannot be graded without an answer to grade and criteria to grade it by.
DEFAULT_TEMPLATE = IntakeTemplate(
    id=DEFAULT_TEMPLATE_ID,
    name="連番の接頭辞 (既定)",
    rules=(
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="01_*",
            role=MaterialRole.STUDENT_ANSWER,
            requirement=Requirement.REQUIRED,
        ),
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="02_*",
            role=MaterialRole.GRADING_CRITERIA,
            requirement=Requirement.REQUIRED,
        ),
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="03*_*",
            role=MaterialRole.ANNOTATION_RESOURCE,
            requirement=Requirement.RECOMMENDED,
        ),
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="04*_*",
            role=MaterialRole.ANNOTATION_SAMPLE,
            requirement=Requirement.OPTIONAL,
        ),
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="*.txt",
            role=MaterialRole.IGNORE,
            requirement=Requirement.OPTIONAL,
        ),
    ),
)


@dataclass(frozen=True, kw_only=True)
class ScannedFile:
    """One file the app found under the folder the reviewer chose.

    ``relative_path`` is POSIX-separated and relative to that folder, so
    ``"国語/01_answers.pdf"`` names a file one level down. It carries the
    school's own course names: see this module's docstring on not logging it.
    """

    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.relative_path.strip():
            raise IntakeTemplateError("ScannedFile.relative_path must not be blank")
        if self.relative_path.startswith("/") or ".." in self.relative_path.split("/"):
            # The path is echoed back to the app and used to build a group
            # key; it never opens a file on the sidecar's side, but a caller
            # should not be able to describe a location outside the chosen
            # folder in the first place (AGENTS.md: validate every input that
            # crosses a trust boundary).
            raise IntakeTemplateError(
                "ScannedFile.relative_path must stay inside the chosen folder"
            )
        if self.size_bytes < 0:
            raise IntakeTemplateError("ScannedFile.size_bytes must be >= 0")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise IntakeTemplateError("ScannedFile.sha256 must be a lowercase hex digest")

    @property
    def file_name(self) -> str:
        return self.relative_path.rsplit("/", 1)[-1]

    @property
    def parent_folder(self) -> str:
        """The containing folder's *name*, or ``""`` for a file at the top."""
        head, separator, _ = self.relative_path.rpartition("/")
        return head.rsplit("/", 1)[-1] if separator else ""


@dataclass(frozen=True, kw_only=True)
class RuleAssignment:
    """What the template proposes for one file, and which rule proposed it.

    ``role is None`` means **no rule matched** -- not "no role". Nothing may
    turn that into a guess; it is what sends the file to LLM classification
    (Issue #101 stage 2) and, failing that, to a human choosing from a list.
    """

    file: ScannedFile
    role: MaterialRole | None
    requirement: Requirement | None
    matched_rule_index: int | None


def classify_by_rules(
    files: Sequence[ScannedFile], template: IntakeTemplate
) -> tuple[RuleAssignment, ...]:
    """Apply ``template``'s rules to ``files``. Pure; order-preserving.

    First matching rule wins, so a template author orders from specific to
    general. A file no rule matches comes back with ``role=None`` rather than
    a default role -- see :class:`RuleAssignment`.
    """
    assignments: list[RuleAssignment] = []
    for scanned in files:
        assignment = RuleAssignment(
            file=scanned, role=None, requirement=None, matched_rule_index=None
        )
        for index, rule in enumerate(template.rules):
            candidate = scanned.file_name if rule.scope is RuleScope.FILE else scanned.parent_folder
            # A FOLDER rule cannot match a file sitting at the top of the
            # chosen folder: there is no containing folder name to compare,
            # and treating "" as matchable would let a pattern like `*` claim
            # every loose file as if it had been found inside a named folder.
            if rule.scope is RuleScope.FOLDER and not candidate:
                continue
            if matches_pattern(rule.pattern, candidate):
                assignment = RuleAssignment(
                    file=scanned,
                    role=rule.role,
                    requirement=rule.requirement,
                    matched_rule_index=index,
                )
                break
        assignments.append(assignment)
    return tuple(assignments)
