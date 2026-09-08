"""The classification port's own contract (Issue #101).

What is pinned here is that **attribution is a multiple-choice question**:
an answer outside the offered candidate set is a `SchemaViolation`, not a
value that flows onward. Issue #101 asked for this explicitly -- the batch
already contains the criteria PDFs, so the candidate set is known and there
is no reason to accept free text.
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.ai_provider import ProviderDescriptor, SchemaViolation
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_classifier import (
    UNKNOWN,
    AttributionCandidate,
    AttributionProposal,
    RoleProposal,
    validate_attribution,
)


def _descriptor() -> ProviderDescriptor:
    return ProviderDescriptor(
        provider="fake",
        model="fake-model",
        version=None,
        prompt_version="test",
        temperature=0.0,
        structured_output_mode="json_schema",
    )


_CANDIDATES = (
    AttributionCandidate(id="test-1", label="第1回"),
    AttributionCandidate(id="test-2", label="第2回"),
)


def test_a_candidate_id_passes_through() -> None:
    assert validate_attribution("test-2", _CANDIDATES) == "test-2"


def test_unknown_maps_to_none_and_is_not_an_error() -> None:
    """The observed answer sheets often carry nothing identifying at all --
    the course-name field is printed on some, blank on others, handwritten on
    the rest, and every inspected sheet had blank student name/id fields. A
    classifier that never says "I could not tell" would be inventing answers.
    """
    assert validate_attribution(UNKNOWN, _CANDIDATES) is None


@pytest.mark.parametrize("answer", ["test-3", "第1回", "", "TEST-1", "unknown "])
def test_an_answer_outside_the_candidate_set_is_a_schema_violation(answer: str) -> None:
    with pytest.raises(SchemaViolation):
        validate_attribution(answer, _CANDIDATES)


def test_the_violation_message_leaks_neither_the_answer_nor_a_candidate_label() -> None:
    """Candidate labels are test names taken from the school's material, and
    the raw answer may quote the page. Only counts may appear.
    """
    with pytest.raises(SchemaViolation) as raised:
        validate_attribution("第3回 現代文", _CANDIDATES)
    message = str(raised.value)
    assert "第3回 現代文" not in message
    assert "第1回" not in message
    assert "test-1" not in message
    assert "2" in message


def test_a_candidate_may_not_use_the_reserved_unknown_id() -> None:
    """Otherwise "this candidate" and "none of them" would be the same value."""
    with pytest.raises(ValueError):
        AttributionCandidate(id=UNKNOWN, label="whatever")


def test_a_role_proposal_may_decline_to_choose() -> None:
    proposal = RoleProposal(role=None, confidence=0.0, descriptor=_descriptor())
    assert proposal.role is None


def test_a_role_proposal_carries_a_real_role_when_it_has_one() -> None:
    proposal = RoleProposal(
        role=MaterialRole.GRADING_CRITERIA, confidence=0.8, descriptor=_descriptor()
    )
    assert proposal.role is MaterialRole.GRADING_CRITERIA


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_outside_zero_to_one_is_rejected(confidence: float) -> None:
    with pytest.raises(ValueError):
        AttributionProposal(candidate_id=None, confidence=confidence, descriptor=_descriptor())
    with pytest.raises(ValueError):
        RoleProposal(role=None, confidence=confidence, descriptor=_descriptor())
