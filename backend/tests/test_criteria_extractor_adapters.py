"""Contract tests for the `CriteriaExtractor` adapters and their factory
(Issue #103).

Both adapters are driven against an ``httpx.MockTransport`` and fake ADC
credentials -- no real API is called and the developer's ``gcloud`` login is
never touched, the same rule ``test_ai_provider_vertex_gemini_contract.py``
follows.

The two properties worth pinning are the ones that protect a point value:

* a response that does not satisfy the schema is a `SchemaViolation`, and
  the adapter never salvages a partial reading out of it;
* the pages actually travel as images.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai_grading._google_adc import AdcTokenSource
from auto_scoring.adapters.criteria_extraction._prompt import (
    build_criteria_user_content,
    sniff_image_format,
    strict_criteria_extraction_schema,
)
from auto_scoring.adapters.criteria_extraction.extractor import (
    ChatCompletionsCriteriaExtractor,
    UnconfiguredCriteriaExtractor,
    VertexGeminiCriteriaExtractor,
)
from auto_scoring.adapters.criteria_extraction.factory import (
    CriteriaExtractorConfigError,
    create_criteria_extractor,
)
from auto_scoring.domain.ai_provider import (
    ProviderRateLimitedError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderUnavailable,
    SchemaViolation,
)
from auto_scoring.domain.criteria_extraction import CriteriaExtractionRequest

_PROJECT = "test-project"
_PNG = b"\x89PNG\r\n\x1a\n-fake-page"

_VALID_EXTRACTION = {
    "questions": [
        {
            "number": "問1",
            "points": 5,
            "model_answer": "模範解答",
            "criteria": [{"description": "要点に触れている", "kind": "add", "points": 5}],
            "source_pages": [1],
            "note": None,
        }
    ],
    "total_points": 5,
    "unreadable_pages": [],
    "note": None,
}

#: A 2xx body that parses as JSON but is not a valid extraction -- a string
#: where the score belongs.
_MALFORMED_EXTRACTION: dict[str, Any] = {
    "questions": [
        {
            "number": "問1",
            "points": "5",
            "model_answer": None,
            "criteria": [],
            "source_pages": [],
            "note": None,
        }
    ],
    "total_points": None,
    "unreadable_pages": [],
    "note": None,
}


class _FakeCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def _tokens() -> AdcTokenSource:
    return AdcTokenSource(credentials=_FakeCredentials(), project_id=_PROJECT)


def _request(pages: int = 2, *, texts: tuple[str, ...] = ()) -> CriteriaExtractionRequest:
    return CriteriaExtractionRequest(page_images=tuple([_PNG] * pages), page_texts=texts)


def _vertex(handler: httpx.MockTransport) -> VertexGeminiCriteriaExtractor:
    return VertexGeminiCriteriaExtractor(
        model="fake-model", tokens=_tokens(), client=httpx.Client(transport=handler)
    )


def _chat(handler: httpx.MockTransport) -> ChatCompletionsCriteriaExtractor:
    return ChatCompletionsCriteriaExtractor(
        name="openai",
        api_key="fake-key",
        model="fake-model",
        base_url="https://example.invalid/v1",
        label="OpenAI",
        extra_payload={"store": False},
        client=httpx.Client(
            transport=handler,
            base_url="https://example.invalid/v1",
            headers={"Authorization": "Bearer fake-key"},
        ),
    )


def _vertex_body(payload: object) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


def _chat_body(payload: object) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


# --------------------------------------------------------------------------- #
# Happy path and payload shape
# --------------------------------------------------------------------------- #


def test_vertex_extracts_and_sends_every_page_as_an_image() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_vertex_body(_VALID_EXTRACTION))

    output = _vertex(httpx.MockTransport(handler)).extract(_request(pages=3))
    assert output.questions[0].points == 5

    parts = seen["contents"][0]["parts"]
    images = [part for part in parts if "inlineData" in part]
    assert len(images) == 3
    assert images[0]["inlineData"]["data"] == base64.b64encode(_PNG).decode("ascii")
    # The fixed rules travel on the trusted instruction channel, never mixed
    # into the same message as the document being read.
    assert "systemInstruction" in seen
    assert seen["generationConfig"]["responseJsonSchema"] == strict_criteria_extraction_schema()


def test_chat_completions_extracts_and_sends_every_page_as_an_image() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_chat_body(_VALID_EXTRACTION))

    output = _chat(httpx.MockTransport(handler)).extract(_request(pages=2))
    assert output.total_points == 5

    content = seen["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url", "image_url"]
    assert seen["messages"][0]["role"] == "system"
    assert seen["response_format"]["json_schema"]["strict"] is True
    # The per-request retention opt-out is not dropped on this path.
    assert seen["store"] is False


# --------------------------------------------------------------------------- #
# Schema violations (Issue #103 acceptance criterion 6)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_a_malformed_response_is_a_schema_violation(transport: str) -> None:
    body = _vertex_body if transport == "vertex" else _chat_body
    handler = httpx.MockTransport(
        lambda request: httpx.Response(200, json=body(_MALFORMED_EXTRACTION))
    )
    extractor = _vertex(handler) if transport == "vertex" else _chat(handler)
    with pytest.raises(SchemaViolation):
        extractor.extract(_request())


@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_a_schema_violation_never_quotes_the_response(transport: str) -> None:
    """The pages are a school's copyrighted material. An exception message
    that echoed the body would put it into the sidecar log, which outlives
    the session (AGENTS.md "Security", Issue #95 決定 7)."""
    body = _vertex_body if transport == "vertex" else _chat_body
    handler = httpx.MockTransport(
        lambda request: httpx.Response(200, json=body(_MALFORMED_EXTRACTION))
    )
    extractor = _vertex(handler) if transport == "vertex" else _chat(handler)
    with pytest.raises(SchemaViolation) as error:
        extractor.extract(_request())
    message = str(error.value)
    assert "問1" not in message
    assert "模範解答" not in message


def test_vertex_response_without_a_text_part_is_a_schema_violation() -> None:
    """A safety block or a changed response shape. Not `ProviderUnavailable`:
    the call succeeded, so retrying reproduces it."""
    handler = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"candidates": [{"content": {"parts": []}}]})
    )
    with pytest.raises(SchemaViolation):
        _vertex(handler).extract(_request())


def test_chat_response_without_a_completion_is_a_schema_violation() -> None:
    handler = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(SchemaViolation):
        _chat(handler).extract(_request())


@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_a_non_object_body_is_a_schema_violation(transport: str) -> None:
    handler = httpx.MockTransport(lambda request: httpx.Response(200, json=[1, 2, 3]))
    extractor = _vertex(handler) if transport == "vertex" else _chat(handler)
    with pytest.raises(SchemaViolation):
        extractor.extract(_request())


# --------------------------------------------------------------------------- #
# Failure classification
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ProviderRateLimitedError),
        (500, ProviderServerError),
        (401, ProviderUnavailable),
    ],
)
@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_http_failures_are_classified(
    status: int, expected: type[Exception], transport: str
) -> None:
    handler = httpx.MockTransport(lambda request: httpx.Response(status, json={"error": "x"}))
    extractor = _vertex(handler) if transport == "vertex" else _chat(handler)
    with pytest.raises(expected):
        extractor.extract(_request())


@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_a_timeout_is_a_timeout(transport: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    extractor = (
        _vertex(httpx.MockTransport(handler))
        if transport == "vertex"
        else _chat(httpx.MockTransport(handler))
    )
    with pytest.raises(ProviderTimeoutError):
        extractor.extract(_request())


def test_unconfigured_extractor_raises_with_its_reason() -> None:
    with pytest.raises(ProviderUnavailable) as error:
        UnconfiguredCriteriaExtractor("AUTO_SCORING_GEMINI_MODEL is not set").extract(_request())
    assert "AUTO_SCORING_GEMINI_MODEL" in str(error.value)


# --------------------------------------------------------------------------- #
# Prompt content
# --------------------------------------------------------------------------- #


def test_user_content_says_the_images_are_authoritative_when_text_exists() -> None:
    content = build_criteria_user_content(_request(pages=2, texts=("ページ1の文字", "")))
    assert "ページ1の文字" in content
    assert "UNTRUSTED EMBEDDED TEXT" in content
    assert "never in place of the" in content


def test_user_content_says_so_when_there_is_no_text_layer() -> None:
    """The image-only case -- 6 of the 11 measured subjects."""
    content = build_criteria_user_content(_request(pages=2))
    assert "no usable embedded text layer" in content
    assert "UNTRUSTED EMBEDDED TEXT" not in content


def test_strict_schema_requires_every_property() -> None:
    """OpenAI-compatible strict Structured Outputs reject a schema that
    expresses optionality with an absent key plus a ``default``."""
    schema = strict_criteria_extraction_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert "default" not in json.dumps(schema)


def test_strict_schema_carries_no_value_range_keywords() -> None:
    """Vertex AI compiles this schema into a decoding constraint and answers
    400 INVALID_ARGUMENT when it grows too large -- which it did, verified
    against a live call, because of the numeric bounds and length caps the
    domain schema declares.

    This test exists so that adding a bound to
    `domain.criteria_extraction` fails here rather than at the next live
    extraction. The values are still enforced: `parse_criteria_extraction`
    validates every response locally, which is what the adapters turn into
    `SchemaViolation`.
    """
    rendered = json.dumps(strict_criteria_extraction_schema())
    for keyword in (
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "format",
    ):
        assert f'"{keyword}"' not in rendered, keyword


def test_the_prompt_states_the_length_limit_the_schema_no_longer_carries() -> None:
    """Since the wire schema drops ``maxLength``, the instructions are the
    only place a model is told about it."""
    from auto_scoring.adapters.criteria_extraction._prompt import (
        CRITERIA_SYSTEM_INSTRUCTIONS,
    )
    from auto_scoring.domain.criteria_extraction import MAX_CRITERIA_TEXT_CHARS

    assert str(MAX_CRITERIA_TEXT_CHARS) in CRITERIA_SYSTEM_INSTRUCTIONS


def test_bounds_are_still_enforced_locally_after_the_wire_schema_drops_them() -> None:
    """The pair to the two tests above: nothing was actually relaxed."""
    over_the_bound: dict[str, Any] = {
        "questions": [
            {
                "number": "問1",
                "points": 10_001,
                "model_answer": None,
                "criteria": [],
                "source_pages": [],
                "note": None,
            }
        ],
        "total_points": None,
        "unreadable_pages": [],
        "note": None,
    }
    handler = httpx.MockTransport(
        lambda request: httpx.Response(200, json=_vertex_body(over_the_bound))
    )
    with pytest.raises(SchemaViolation):
        _vertex(handler).extract(_request())


def test_png_and_jpeg_are_told_apart() -> None:
    assert sniff_image_format(_PNG) == "png"
    assert sniff_image_format(b"\xff\xd8\xff-fake-jpeg") == "jpeg"


# --------------------------------------------------------------------------- #
# The factory
# --------------------------------------------------------------------------- #


def test_factory_skips_codex_app_server() -> None:
    """It has no image input, and every measured subject needs one. Listing
    it must not consume the first slot of the chain."""
    extractor = create_criteria_extractor(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server,openai",
            "AUTO_SCORING_OPENAI_API_KEY": "key",
            "AUTO_SCORING_OPENAI_MODEL": "model",
        }
    )
    assert extractor.name == "openai"


def test_factory_takes_the_first_transport_with_credentials() -> None:
    extractor = create_criteria_extractor(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter,openai",
            "AUTO_SCORING_OPENAI_API_KEY": "key",
            "AUTO_SCORING_OPENAI_MODEL": "model",
        }
    )
    assert extractor.name == "openai"


def test_factory_rejects_a_list_with_no_image_capable_transport() -> None:
    with pytest.raises(CriteriaExtractorConfigError) as error:
        create_criteria_extractor({"AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server"})
    assert "codex_app_server" not in str(error.value)


def test_factory_requires_the_transport_variable() -> None:
    with pytest.raises(CriteriaExtractorConfigError) as error:
        create_criteria_extractor({})
    assert "AUTO_SCORING_AI_GRADING_TRANSPORT" in str(error.value)


def test_factory_error_names_variables_and_never_quotes_their_values() -> None:
    """This message is published: it becomes
    `UnconfiguredCriteriaExtractor.reason`, which the extract endpoint
    returns and the app shows. A key pasted into the wrong variable must not
    be read back out of it (the rule
    ``adapters.ai_grading.factory``'s docstring states)."""
    secret = "sk-secret-value-do-not-print"
    with pytest.raises(CriteriaExtractorConfigError) as error:
        create_criteria_extractor(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "openai",
                "AUTO_SCORING_OPENAI_API_KEY": secret,
                # model missing -> this transport is skipped, nothing is left
            }
        )
    message = str(error.value)
    assert secret not in message
    assert "AUTO_SCORING_OPENAI_MODEL" in message


def test_factory_uses_adc_for_gemini_and_skips_it_without_a_login() -> None:
    def failing_token_source(project_id: str | None) -> AdcTokenSource:
        raise AssertionError("must not be reached once the model variable is missing")

    with pytest.raises(CriteriaExtractorConfigError):
        create_criteria_extractor(
            {"AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini"},
            token_source_factory=failing_token_source,
        )
