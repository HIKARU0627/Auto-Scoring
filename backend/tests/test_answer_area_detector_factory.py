"""`create_answer_area_detector` reads the grading transport list and picks the
first image-capable, credentialed vendor (Issue #105).

The leak rule is the one `adapters.ai_grading.factory` already carries and
`test_grading_availability.py` enforces for its counterpart: every message
this module produces is published (it becomes the reason the テスト設定 screen
shows), so it may name configuration *variables* but never their values. The
matrix below puts a sentinel in each variable in turn and asserts none of them
comes back.
"""

from __future__ import annotations

import pytest

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.answer_area_detection.detector import (
    ChatCompletionsAnswerAreaDetector,
    VertexGeminiAnswerAreaDetector,
)
from auto_scoring.adapters.answer_area_detection.factory import (
    AnswerAreaDetectorConfigError,
    create_answer_area_detector,
)

_SENTINEL = "s3cr3t-value-that-must-not-be-published"

_ALL_VARIABLES = (
    "AUTO_SCORING_AI_GRADING_TRANSPORT",
    "AUTO_SCORING_GEMINI_MODEL",
    "AUTO_SCORING_VERTEX_PROJECT",
    "AUTO_SCORING_VERTEX_LOCATION",
    "AUTO_SCORING_OPENROUTER_API_KEY",
    "AUTO_SCORING_OPENROUTER_MODEL",
    "AUTO_SCORING_OPENAI_API_KEY",
    "AUTO_SCORING_OPENAI_MODEL",
    "AUTO_SCORING_CODEX_EXECUTABLE",
)


def _no_adc(project_id: str | None) -> AdcTokenSource:
    raise AdcCredentialsError("no application default credentials on this host")


def _fake_adc(project_id: str | None) -> AdcTokenSource:
    class _Credentials:
        token = "fake"

        def refresh(self, request: object) -> None: ...

    return AdcTokenSource(
        credentials=_Credentials(),  # type: ignore[arg-type]
        project_id=project_id or "test-project",
    )


def test_builds_vertex_when_gemini_leads_and_adc_is_present() -> None:
    detector = create_answer_area_detector(
        {"AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini", "AUTO_SCORING_GEMINI_MODEL": "m"},
        token_source_factory=_fake_adc,
    )
    assert isinstance(detector, VertexGeminiAnswerAreaDetector)


def test_falls_through_to_the_next_vendor_when_credentials_are_missing() -> None:
    """The list is a priority order, not a requirement that every entry work."""
    detector = create_answer_area_detector(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini,openai",
            "AUTO_SCORING_GEMINI_MODEL": "m",
            "AUTO_SCORING_OPENAI_API_KEY": "k",
            "AUTO_SCORING_OPENAI_MODEL": "m",
        },
        token_source_factory=_no_adc,
    )
    assert isinstance(detector, ChatCompletionsAnswerAreaDetector)
    assert detector.name == "openai"


def test_skips_codex_app_server_because_it_has_no_image_input() -> None:
    """Detection's only input is the page image, so leaving this in the chain
    would guarantee one failed call before every run.
    """
    detector = create_answer_area_detector(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server,openrouter",
            "AUTO_SCORING_OPENROUTER_API_KEY": "k",
            "AUTO_SCORING_OPENROUTER_MODEL": "m",
        },
        token_source_factory=_no_adc,
    )
    assert detector.name == "openrouter"


def test_a_codex_only_host_says_detection_needs_an_image_capable_vendor() -> None:
    with pytest.raises(AnswerAreaDetectorConfigError) as caught:
        create_answer_area_detector(
            {"AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server"},
            token_source_factory=_no_adc,
        )
    assert "no image input" in str(caught.value)


def test_an_unset_transport_list_is_a_configuration_error() -> None:
    with pytest.raises(AnswerAreaDetectorConfigError):
        create_answer_area_detector({}, token_source_factory=_no_adc)


def test_the_openai_and_openrouter_retention_opt_outs_are_sent() -> None:
    """Issue #95 decision 7 permits sending this material to the configured
    provider; it does not permit leaving copies of it around. Copied from the
    grading adapters so the same material is treated the same way whichever
    call sends it.
    """
    openai = create_answer_area_detector(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "openai",
            "AUTO_SCORING_OPENAI_API_KEY": "k",
            "AUTO_SCORING_OPENAI_MODEL": "m",
        },
        token_source_factory=_no_adc,
    )
    openrouter = create_answer_area_detector(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter",
            "AUTO_SCORING_OPENROUTER_API_KEY": "k",
            "AUTO_SCORING_OPENROUTER_MODEL": "m",
        },
        token_source_factory=_no_adc,
    )
    assert isinstance(openai, ChatCompletionsAnswerAreaDetector)
    assert isinstance(openrouter, ChatCompletionsAnswerAreaDetector)
    assert openai._extra_payload == {"store": False}
    assert openrouter._extra_payload == {"provider": {"data_collection": "deny", "zdr": True}}


@pytest.mark.parametrize("variable", _ALL_VARIABLES)
def test_no_configuration_value_reaches_a_published_message(variable: str) -> None:
    """One sentinel per variable, in turn. Whatever combination fails to build,
    the reason must name variables only -- it is returned by
    ``GET /tests/{id}/answer-layout`` and shown on screen.
    """
    env = dict.fromkeys(_ALL_VARIABLES, "")
    env[variable] = _SENTINEL
    try:
        create_answer_area_detector(env, token_source_factory=_no_adc)
    except AnswerAreaDetectorConfigError as error:
        assert _SENTINEL not in str(error)
