"""The classification adapter's prompts, schemas and parsing (Issue #101).

Pins the two properties the design depends on:

* attribution is constrained to the caller's candidate set **at the provider**
  (the schema carries the ids as an ``enum``) *and* on the way back;
* nothing identifying travels -- no file name, no path, no student data.
"""

from __future__ import annotations

from typing import Any

import pytest

from auto_scoring.adapters.ai_classification.classifier import (
    StructuredMaterialClassifier,
    attribution_response_schema,
    role_response_schema,
)
from auto_scoring.adapters.ai_classification.factory import create_material_classifier
from auto_scoring.domain.ai_provider import SchemaViolation
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.material_classifier import (
    AttributionCandidate,
    ClassifierUnavailable,
)

_IMAGE = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

_CANDIDATES = (
    AttributionCandidate(id="test-1", label="第1回"),
    AttributionCandidate(id="test-2", label="第2回", hint="評論文"),
)


class _FakeCall:
    """Records what was sent and replies with a canned JSON document."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.sent: list[dict[str, Any]] = []

    def call(
        self, *, system: str, user_text: str, image: bytes, schema: dict[str, Any]
    ) -> tuple[str, str | None]:
        self.sent.append(
            {"system": system, "user_text": user_text, "image": image, "schema": schema}
        )
        return self._reply, "fake-route"


def _classifier(reply: str) -> tuple[StructuredMaterialClassifier, _FakeCall]:
    call = _FakeCall(reply)
    return StructuredMaterialClassifier(call, prompt_version="test"), call


# --------------------------------------------------------------------------- #
# Attribution is a multiple-choice question
# --------------------------------------------------------------------------- #
def test_the_schema_sent_offers_only_the_candidates_and_unknown() -> None:
    """The constraint is on the provider, not just in the prompt text: a
    model cannot answer with a subject name because no such value exists in
    the schema it must answer inside.
    """
    schema = attribution_response_schema(_CANDIDATES)
    assert schema["properties"]["candidate_id"]["enum"] == ["test-1", "test-2", "unknown"]


def test_a_candidate_answer_is_returned() -> None:
    classifier, call = _classifier('{"candidate_id": "test-2", "confidence": 0.9}')
    proposal = classifier.attribute_answer(_IMAGE, _CANDIDATES)
    assert proposal.candidate_id == "test-2"
    assert proposal.confidence == pytest.approx(0.9)
    assert call.sent[0]["schema"]["properties"]["candidate_id"]["enum"] == [
        "test-1",
        "test-2",
        "unknown",
    ]


def test_unknown_comes_back_as_no_candidate() -> None:
    classifier, _ = _classifier('{"candidate_id": "unknown", "confidence": 0.1}')
    assert classifier.attribute_answer(_IMAGE, _CANDIDATES).candidate_id is None


def test_an_answer_outside_the_candidate_set_is_rejected_even_though_the_schema_forbade_it() -> (
    None
):
    """A provider is free to ignore a structured-output constraint. An id the
    reviewer's own list never contained must not reach the plan.
    """
    classifier, _ = _classifier('{"candidate_id": "test-9", "confidence": 1.0}')
    with pytest.raises(SchemaViolation):
        classifier.attribute_answer(_IMAGE, _CANDIDATES)


def test_attribution_without_candidates_is_a_caller_error() -> None:
    """Asking a provider to choose from a list of one -- or of none -- spends
    money to confirm a foregone conclusion. Callers skip the call instead.
    """
    classifier, _ = _classifier('{"candidate_id": "unknown", "confidence": 0.0}')
    with pytest.raises(ValueError):
        classifier.attribute_answer(_IMAGE, ())


# --------------------------------------------------------------------------- #
# What travels
# --------------------------------------------------------------------------- #
def test_no_file_name_or_path_is_ever_sent() -> None:
    """Names in real material are actively misleading -- one subject's sample
    is named after another subject's course -- so a name would bias the
    proposal toward the exact mistake the rules already make cheaply and
    visibly. The port has no parameter for one; this pins that the prompt
    does not smuggle one in either.
    """
    classifier, call = _classifier('{"role": "grading_criteria", "confidence": 0.8}')
    classifier.classify_role(_IMAGE)
    first = call.sent[0]

    classifier, call = _classifier('{"role": "grading_criteria", "confidence": 0.8}')
    classifier.classify_role(b"\x89PNG\r\n\x1a\n" + b"\xff" * 32)
    second = call.sent[0]

    # The text is byte-identical for two different files, so it cannot be
    # carrying anything about either of them. Only the image differs.
    assert first["system"] == second["system"]
    assert first["user_text"] == second["user_text"]
    assert first["image"] != second["image"]
    assert first["image"] == _IMAGE


def test_attribution_sends_the_candidate_labels_but_no_file_names() -> None:
    classifier, call = _classifier('{"candidate_id": "test-1", "confidence": 0.5}')
    classifier.attribute_answer(_IMAGE, _CANDIDATES)
    user_text = call.sent[0]["user_text"]
    assert "test-1" in user_text and "第1回" in user_text
    assert ".pdf" not in user_text


# --------------------------------------------------------------------------- #
# Role classification
# --------------------------------------------------------------------------- #
def test_a_role_answer_is_mapped_to_the_enum() -> None:
    classifier, _ = _classifier('{"role": "student_answer", "confidence": 0.7}')
    assert classifier.classify_role(_IMAGE).role is MaterialRole.STUDENT_ANSWER


def test_an_unknown_role_answer_leaves_the_file_undecided() -> None:
    classifier, _ = _classifier('{"role": "unknown", "confidence": 0.0}')
    assert classifier.classify_role(_IMAGE).role is None


def test_ignore_is_not_offered_as_a_role() -> None:
    """ "Do not import this" is a decision about what the reviewer wants, not
    something visible on a page.
    """
    assert "ignore" not in role_response_schema()["properties"]["role"]["enum"]


def test_a_role_outside_the_offered_set_is_a_schema_violation() -> None:
    classifier, _ = _classifier('{"role": "ignore", "confidence": 1.0}')
    with pytest.raises(SchemaViolation):
        classifier.classify_role(_IMAGE)


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[]",
        '{"role": "student_answer"}',
        '{"role": "student_answer", "confidence": "high"}',
        '{"role": "student_answer", "confidence": 1.5}',
        '{"role": "student_answer", "confidence": true}',
    ],
)
def test_a_malformed_reply_is_a_schema_violation_not_a_crash(reply: str) -> None:
    classifier, _ = _classifier(reply)
    with pytest.raises(SchemaViolation):
        classifier.classify_role(_IMAGE)


def test_a_violation_message_never_quotes_the_reply() -> None:
    """A reply can echo the page it looked at, which is the school's own
    material.
    """
    classifier, _ = _classifier('{"role": "第3回 現代文 答案", "confidence": 1.0}')
    with pytest.raises(SchemaViolation) as raised:
        classifier.classify_role(_IMAGE)
    assert "第3回" not in str(raised.value)


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def test_an_unconfigured_host_says_so_rather_than_failing_later() -> None:
    with pytest.raises(ClassifierUnavailable):
        create_material_classifier({})


def test_a_codex_only_host_is_unavailable_for_classification() -> None:
    """Codex app-server's protocol carries no image input, and classification
    is entirely about looking at a page. Saying so beats a chain link that
    always fails.
    """
    with pytest.raises(ClassifierUnavailable):
        create_material_classifier(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            }
        )


def test_the_unavailable_reason_names_no_configuration_value() -> None:
    """This text is returned by the API and shown on screen -- an operator who
    pasted a key into the wrong variable must not have it read back to them.
    """
    with pytest.raises(ClassifierUnavailable) as raised:
        create_material_classifier(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                "AUTO_SCORING_OPENROUTER_API_KEY": "sk-secret-value",
            }
        )
    assert "sk-secret-value" not in raised.value.reason


def test_an_openrouter_host_builds_a_classifier() -> None:
    classifier = create_material_classifier(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server,openrouter",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            "AUTO_SCORING_OPENROUTER_API_KEY": "key",
            "AUTO_SCORING_OPENROUTER_MODEL": "some/model",
        }
    )
    assert isinstance(classifier, StructuredMaterialClassifier)
