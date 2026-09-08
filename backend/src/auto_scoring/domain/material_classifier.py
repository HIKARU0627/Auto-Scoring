"""``MaterialClassifier`` port: look at one page image and *propose* what a
file is, or which test an answer belongs to (Issue #101 stage 2).

Framework-free, like ``domain.ai_provider`` whose failure taxonomy it reuses
(``SchemaViolation`` / ``ProviderUnavailable``): a classification is another
structured-output call to the same provider chain, so a caller that already
knows how to categorize a grading failure does not need a second, parallel
vocabulary for a classification failure.

Three properties this port exists to pin down.

**Attribution is a multiple-choice question, never free text.** The caller
supplies the candidate set -- the tests already registered, plus the ones
this batch would create -- and the only answers a provider may give are one
of those ids or :data:`UNKNOWN`. :func:`validate_attribution` rejects
anything else as a :class:`SchemaViolation` rather than letting a plausible
made-up name through. "Which of these N tests is this?" is a question with a
checkable answer; "what subject is this?" is not.

**"I could not tell" is a correct answer, not a failure.** The real answer
sheets carry a 講座名(回) field that is printed on some, blank on others and
handwritten on the rest, and the student-name and student-id fields were
blank on every sheet inspected. So a first page frequently contains *nothing*
that identifies which test it belongs to, and a classifier that always
returns a candidate would be inventing one. :data:`UNKNOWN` is how it says so,
and the reviewer picks.

**A proposal is never applied on its own.** Nothing in this module or its
adapters writes anything; the confirmation step (Issue #101 stage 3) is not
an optimization that may be skipped. Accuracy has not been measured -- the
material on hand holds one answer per subject, so there is no second answer
for the same test to measure against -- and until it has been, there is no
basis for a setting that would skip the human.

**What travels, and under which rule.** Both questions are answered from a
page image, and for :meth:`MaterialClassifier.attribute_answer` that page is a
student's answer sheet -- **header included**, because the course-name field
this question reads *is* the header. Business rules section 2 (2) permits it
under "版面を見る": deciding which test an answer belongs to,
like detecting where the answer boxes are, cannot be done without seeing the
page. It is **not** the grading payload, which carries the answer-region crop
only and no header at all.

That rule was widened to cover this on 2026-09-09. It previously allowed a
whole page only for answer-box detection, justified by frequency -- once per
format, versus once per answer for grading. Attribution runs once per *answer*
while still sending a whole page, so it satisfied neither row. What makes it
acceptable is stated there rather than assumed here: the reviewer can narrow
the candidates to one test and skip the call entirely (which is the ordinary
week), and there is no alternative, since the header is the thing being read.

**Stripping the header before sending is deliberately not implemented.**
Issue #99 considered it and rejected it: page layout differs per school, so a
mask is not reliable. Do not add one and describe it as safe.

**Nothing sent or received here may be logged.** Page images are the school's
copyrighted material and student work; the same rule Issue #35 established
for grading payloads applies unchanged (send is permitted by Issue #95
decision 7, publishing is not).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from auto_scoring.domain.ai_provider import ProviderDescriptor, SchemaViolation
from auto_scoring.domain.intake_template import MaterialRole

#: The answer a classifier gives when the page shows nothing that decides the
#: question. Not an error: see this module's docstring.
UNKNOWN = "unknown"

#: Longest candidate label handed to a provider. Labels are test names a
#: human typed (`Test.name`), so they are already bounded, but the prompt
#: builds one line per candidate and an unbounded label would let a single
#: oddly-named test dominate the request.
MAX_CANDIDATE_LABEL_LENGTH = 200

#: Longest optional hint per candidate. A hint is a short excerpt of the
#: criteria PDF's own first-page text, present only when that PDF has a
#: readable text layer -- six of ten distinct criteria documents inspected
#: had none, so most candidates carry no hint at all and the label is all the
#: provider gets.
MAX_CANDIDATE_HINT_LENGTH = 300


@dataclass(frozen=True, kw_only=True)
class AttributionCandidate:
    """One test an answer could belong to.

    ``id`` is what the provider must echo back; it is never a name, so a
    provider cannot "nearly" match a candidate by paraphrasing it.
    """

    id: str
    label: str
    hint: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("AttributionCandidate.id must be a non-blank string")
        if self.id == UNKNOWN:
            # Otherwise a candidate could shadow the sentinel and
            # `validate_attribution` could not tell "this one" from "none of
            # them".
            raise ValueError(f"AttributionCandidate.id must not be the reserved id {UNKNOWN!r}")
        if not self.label.strip():
            raise ValueError("AttributionCandidate.label must be a non-blank string")
        if len(self.label) > MAX_CANDIDATE_LABEL_LENGTH:
            raise ValueError(
                f"AttributionCandidate.label must be at most "
                f"{MAX_CANDIDATE_LABEL_LENGTH} characters"
            )
        if self.hint is not None and len(self.hint) > MAX_CANDIDATE_HINT_LENGTH:
            raise ValueError(
                f"AttributionCandidate.hint must be at most {MAX_CANDIDATE_HINT_LENGTH} characters"
            )


@dataclass(frozen=True, kw_only=True)
class RoleProposal:
    """What a classifier thinks one file is.

    ``role is None`` means the model declined to choose. Callers keep the
    file unresolved and let the reviewer pick; they must not substitute a
    default.
    """

    role: MaterialRole | None
    confidence: float
    descriptor: ProviderDescriptor

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"RoleProposal.confidence must be within 0..1, got {self.confidence}")


@dataclass(frozen=True, kw_only=True)
class AttributionProposal:
    """Which candidate a classifier picked, or ``None`` for :data:`UNKNOWN`."""

    candidate_id: str | None
    confidence: float
    descriptor: ProviderDescriptor

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"AttributionProposal.confidence must be within 0..1, got {self.confidence}"
            )


def validate_attribution(
    raw_candidate_id: str, candidates: Sequence[AttributionCandidate]
) -> str | None:
    """Map a provider's raw answer onto a candidate id, or ``None`` for unknown.

    Raises :class:`SchemaViolation` for anything that is neither
    :data:`UNKNOWN` nor one of ``candidates``. This is the check that keeps
    attribution a multiple-choice question: without it, a provider that
    answered with a subject name, a paraphrase, or an id from a previous
    request would have that value flow onward as if the reviewer's own list
    had contained it.

    The message names neither the raw answer nor a candidate label -- both
    are the school's material (see the module docstring) -- only counts.
    """
    if raw_candidate_id == UNKNOWN:
        return None
    known = {candidate.id for candidate in candidates}
    if raw_candidate_id not in known:
        raise SchemaViolation(
            f"classifier answered with an id that was not among the {len(known)} candidates offered"
        )
    return raw_candidate_id


class ClassifierUnavailable(Exception):
    """No classifier is configured on this host.

    Distinct from a call that failed: it means the feature cannot be offered
    at all, so the screen keeps every unmatched file unresolved and says the
    reviewer must assign roles by hand -- the same shape
    ``adapters.ai.unconfigured_provider`` gives grading.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@runtime_checkable
class MaterialClassifier(Protocol):
    """Port both classification questions go through.

    Each method takes **one page image and nothing else**. In particular no
    file name is passed: names in the observed material are actively
    misleading (one subject's sample is named after another subject's
    course), so a name would bias the proposal toward exactly the mistake the
    rules already make cheaply and visibly.
    """

    def classify_role(self, page_image: bytes) -> RoleProposal:
        """Propose what this document is, from its first page.

        Raises :class:`SchemaViolation` if the structured output fails
        validation, or ``ai_provider.ProviderUnavailable`` if the provider
        could not be reached.
        """
        ...

    def attribute_answer(
        self, page_image: bytes, candidates: Sequence[AttributionCandidate]
    ) -> AttributionProposal:
        """Pick which of ``candidates`` this answer belongs to.

        ``candidates`` must be non-empty. A caller with a single candidate
        should not call this at all -- the reviewer has already decided, and
        asking a provider to choose from a list of one spends money to
        confirm a foregone conclusion (Issue #101: cost control).
        """
        ...
