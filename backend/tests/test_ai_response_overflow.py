"""One over-long string throws the whole response away -- identically in all
three image-carrying AI adapters, because one function decides it (Issue #125
acceptance 2).

Issue #121 is the worked example. A live run against real Vertex AI returned
complete (``finishReason: STOP``) grading responses whose score, criterion
ids and question id were every one of them correct, and every one of them was
discarded because a single annotation comment ran 147 characters against a
120 cap. 5 of the 6 permanent grading failures in that run were this.

The structure that produced it -- "send a strict JSON Schema, validate the
answer locally, discard what does not fit" -- is what 採点基準の抽出, 回答欄の
検出 and 資料の分類 all have, so the defect shape is in all three. Until this
Issue each of them wrote its own ``raise SchemaViolation``, so revisiting the
decision meant finding three copies of it. Now they all reach
`adapters.ai.image_call.discard_response`, and this module is the proof: the
three cases below assert the *same* treatment through one shared helper, so
changing that function's mind about over-long answers turns all of them red at
once -- exactly as `test_ai_response_language.py` does for Issue #140's shared
language instruction.

Every adapter is driven against an ``httpx.MockTransport`` and fake ADC
credentials: no real API is called, and the developer's ``gcloud`` login is
never touched.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from google.auth.credentials import Credentials

from auto_scoring.adapters.ai.image_call import (
    ChatCompletionsImageCall,
    ImageJsonCall,
    VertexGeminiImageCall,
    discard_response,
)
from auto_scoring.adapters.ai_classification.classifier import StructuredMaterialClassifier
from auto_scoring.adapters.ai_grading._google_adc import AdcTokenSource
from auto_scoring.adapters.answer_area_detection.detector import StructuredAnswerAreaDetector
from auto_scoring.adapters.criteria_extraction.extractor import StructuredCriteriaExtractor
from auto_scoring.domain.ai_provider import SchemaViolation
from auto_scoring.domain.answer_area_detection import (
    MAX_NOTE_CHARS,
    AnswerAreaDetectionRequest,
)
from auto_scoring.domain.criteria_extraction import (
    MAX_CRITERIA_TEXT_CHARS,
    CriteriaExtractionRequest,
)

_PAGE = b"\x89PNG\r\n\x1a\nfake-page"

#: Stands in for what a real over-long field carries: the model's own prose
#: about a cram school's material. The marker is what the assertions look for
#: -- an exception that quoted the offending value would put it into the
#: sidecar log, which outlives the session (AGENTS.md "Security").
_MARKER = "MUST-NOT-BE-QUOTED"


def _overlong(cap: int) -> str:
    return _MARKER + "あ" * cap


class _FakeCredentials(Credentials):
    """ADC credentials that are always valid and never hit the network."""

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.token = "fake-access-token"

    def refresh(self, request: object) -> None:
        self.token = "fake-access-token"


def _vertex(answer: str) -> VertexGeminiImageCall:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": answer}]}}]}
        )

    return VertexGeminiImageCall(
        model="fake-model",
        tokens=AdcTokenSource(credentials=_FakeCredentials(), project_id="test-project"),
        temperature=0.0,
        timeout_seconds=1.0,
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )


def _chat(answer: str) -> ChatCompletionsImageCall:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    return ChatCompletionsImageCall(
        provider="openai",
        api_key="fake-key",
        model="fake-model",
        base_url="https://example.invalid/v1",
        label="OpenAI",
        schema_name="test",
        extra_payload={},
        temperature=0.0,
        timeout_seconds=1.0,
        client=httpx.Client(
            transport=httpx.MockTransport(handle), base_url="https://example.invalid/v1"
        ),
    )


# --------------------------------------------------------------------------- #
# One complete, otherwise-correct response per adapter, spoiled by exactly one
# over-long string. Everything a person would act on is right in all three.
# --------------------------------------------------------------------------- #


def _criteria_answer(note: str | None) -> str:
    """A 採点基準 reading whose 配点 and criteria are correct."""
    return json.dumps(
        {
            "questions": [
                {
                    "number": "問1",
                    "points": 5,
                    "model_answer": None,
                    "criteria": [{"description": "要点に触れている", "kind": "add", "points": 5}],
                    "source_pages": [1],
                    "note": note,
                }
            ],
            "total_points": 5,
            "unreadable_pages": [],
            "note": None,
        },
        ensure_ascii=False,
    )


def _answer_area_answer(note: str | None) -> str:
    """A 回答欄 reading whose page, question and rectangle are correct."""
    return json.dumps(
        {
            "areas": [
                {
                    "page": 1,
                    "question_number": "Q1",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.4},
                    "note": note,
                }
            ]
        },
        ensure_ascii=False,
    )


def _extract(call: ImageJsonCall) -> None:
    StructuredCriteriaExtractor(call).extract(
        CriteriaExtractionRequest(page_images=(_PAGE,), page_texts=())
    )


def _detect(call: ImageJsonCall) -> None:
    StructuredAnswerAreaDetector(call).detect(
        AnswerAreaDetectionRequest(page_images=(_PAGE,), question_numbers=("Q1", "Q2"))
    )


def _classify(call: ImageJsonCall) -> None:
    StructuredMaterialClassifier(call, prompt_version="test").classify_role(_PAGE)


#: ``(name, answer with an over-long string, answer with a fitting one, the
#: adapter call)``. `ai_classification` is the odd one out on purpose: its
#: schema has no free-text field at all -- every property is an ``enum``-
#: constrained string or a number (`test_ai_response_language
#: .test_classification_schemas_have_no_free_text_field` pins that) -- so the
#: only string a provider sends it is the answer itself, and a string too long
#: to be one of the offered roles is this adapter's version of the same input.
_ADAPTERS: tuple[tuple[str, str, str, Callable[[ImageJsonCall], None]], ...] = (
    (
        "criteria_extraction",
        _criteria_answer(_overlong(MAX_CRITERIA_TEXT_CHARS)),
        _criteria_answer("読み取れた"),
        _extract,
    ),
    (
        "answer_area_detection",
        _answer_area_answer(_overlong(MAX_NOTE_CHARS)),
        _answer_area_answer("罫線が薄い"),
        _detect,
    ),
    (
        "ai_classification",
        json.dumps({"role": _overlong(64), "confidence": 0.8}, ensure_ascii=False),
        json.dumps({"role": "student_answer", "confidence": 0.8}),
        _classify,
    ),
)

_IDS = [name for name, *_ in _ADAPTERS]


@pytest.mark.parametrize(("over", "fits", "run"), [entry[1:] for entry in _ADAPTERS], ids=_IDS)
@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_a_response_that_fits_is_accepted(
    over: str, fits: str, run: Callable[[ImageJsonCall], None], transport: str
) -> None:
    """The control. Without this the test below would pass on a response that
    was broken for some other reason -- the over-long string has to be the
    only thing wrong with it."""
    run(_vertex(fits) if transport == "vertex" else _chat(fits))


@pytest.mark.parametrize(("over", "fits", "run"), [entry[1:] for entry in _ADAPTERS], ids=_IDS)
@pytest.mark.parametrize("transport", ["vertex", "chat"])
def test_one_over_long_string_discards_the_whole_response(
    over: str, fits: str, run: Callable[[ImageJsonCall], None], transport: str
) -> None:
    """The same input shape, the same answer, in all three: nothing is
    salvaged, nothing is quoted, and nothing is chained.

    This is Issue #121's shape, and it is *asserted*, not endorsed -- the
    grading schema now cuts an over-long comment instead of rejecting the
    response (`domain.ai_grading`). Whether these three should do the same is
    a decision for its own Issue; what this Issue fixes is that the decision
    now has one place to be made in rather than three.
    """
    call = _vertex(over) if transport == "vertex" else _chat(over)
    with pytest.raises(SchemaViolation) as caught:
        run(call)

    message = str(caught.value)
    assert _MARKER not in message
    # `discard_response`'s own shape: a fixed name for the vendor, then a
    # fixed reason. Two of the three name it by its display label and
    # `ai_classification` by its transport id; both are literals written in
    # this repository, which is the property that matters -- neither can
    # carry a configuration value or a fragment of the response.
    assert message.startswith((call.label, call.provider))
    # `raise ... from None`: pydantic keeps the offending value in the
    # `ValidationError`'s `input_value`, and Python renders a chained cause's
    # own `str()`. Both flags are needed -- the context object still exists
    # (it is what was being handled), but neither `traceback` nor
    # `logging.exception` renders it once suppressed.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


# --------------------------------------------------------------------------- #
# The one place all three reach.
# --------------------------------------------------------------------------- #


def test_discard_response_never_carries_anything_but_its_two_fixed_strings() -> None:
    """What every case above depends on. Both arguments are literals written
    in this repository -- a vendor name and a reason -- so the message can
    carry no part of the request or the response however the caller fails.
    """
    with pytest.raises(SchemaViolation) as caught:
        discard_response("Vertex AI", "response body was not a JSON object")
    assert str(caught.value) == "Vertex AI response body was not a JSON object"
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


def test_discard_response_suppresses_a_cause_it_is_raised_inside() -> None:
    """The case that matters: called from an ``except`` block, which is where
    every adapter calls it from."""
    try:
        try:
            raise ValueError(_MARKER)
        except ValueError:
            discard_response("OpenAI", "response failed schema validation")
    except SchemaViolation as violation:
        assert _MARKER not in str(violation)
        assert violation.__cause__ is None
        assert violation.__suppress_context__ is True
