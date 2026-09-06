"""Tests for the config-driven ``AIProvider`` transport switch (Issue #44)."""

import pytest

from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider

_COMMON = {
    "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter",
    "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
}

_OPENROUTER_CREDENTIALS = {
    "AUTO_SCORING_OPENROUTER_API_KEY": "key",
    "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model",
}


def test_create_ai_provider_selects_openrouter() -> None:
    provider = create_ai_provider(
        {
            **_COMMON,
            "AUTO_SCORING_OPENROUTER_API_KEY": "key",
            "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model",
        }
    )
    assert isinstance(provider, OpenRouterAIProvider)


def test_create_ai_provider_selects_codex_app_server() -> None:
    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
        }
    )
    assert isinstance(provider, CodexAppServerProvider)


def test_create_ai_provider_rejects_an_unknown_transport() -> None:
    with pytest.raises(AIProviderConfigError):
        create_ai_provider({**_COMMON, "AUTO_SCORING_AI_GRADING_TRANSPORT": "bogus"})


def test_create_ai_provider_requires_the_prompt_version() -> None:
    with pytest.raises(AIProviderConfigError):
        create_ai_provider({"AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter"})


def test_create_ai_provider_requires_the_openrouter_api_key() -> None:
    with pytest.raises(AIProviderConfigError):
        create_ai_provider({**_COMMON, "AUTO_SCORING_OPENROUTER_MODEL": "vendor/model"})


def test_create_ai_provider_requires_the_openrouter_model() -> None:
    with pytest.raises(AIProviderConfigError):
        create_ai_provider({**_COMMON, "AUTO_SCORING_OPENROUTER_API_KEY": "key"})


@pytest.mark.parametrize("raw_temperature", ["not-a-number", "nan", "inf", "-1"])
def test_create_ai_provider_rejects_an_invalid_openrouter_temperature(raw_temperature: str) -> None:
    """A malformed AUTO_SCORING_AI_GRADING_TEMPERATURE must fail fast as
    AIProviderConfigError at this trust boundary, not as an unclassified
    ValueError or a provider that later fails to describe()/grade() (code
    review finding)."""
    with pytest.raises(AIProviderConfigError):
        create_ai_provider(
            {
                **_COMMON,
                **_OPENROUTER_CREDENTIALS,
                "AUTO_SCORING_AI_GRADING_TEMPERATURE": raw_temperature,
            }
        )


@pytest.mark.parametrize("raw_temperature", ["2.1", "3", "100"])
def test_create_ai_provider_rejects_an_openrouter_temperature_above_two(
    raw_temperature: str,
) -> None:
    """OpenRouter/OpenAI's Chat Completions API caps sampling temperature at
    2; a higher configured value must fail fast at configuration time, not
    as a remote 4xx on every grading call (code review finding)."""
    with pytest.raises(AIProviderConfigError):
        create_ai_provider(
            {
                **_COMMON,
                **_OPENROUTER_CREDENTIALS,
                "AUTO_SCORING_AI_GRADING_TEMPERATURE": raw_temperature,
            }
        )


def test_create_ai_provider_accepts_an_openrouter_temperature_of_exactly_two() -> None:
    provider = create_ai_provider(
        {
            **_COMMON,
            **_OPENROUTER_CREDENTIALS,
            "AUTO_SCORING_AI_GRADING_TEMPERATURE": "2.0",
        }
    )
    assert isinstance(provider, OpenRouterAIProvider)


def test_create_ai_provider_ignores_temperature_for_codex_app_server() -> None:
    """Codex app-server has no temperature knob (code review finding), so an
    invalid value in this shared env var must not block selecting it."""
    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            "AUTO_SCORING_AI_GRADING_TEMPERATURE": "not-a-number",
        }
    )
    assert isinstance(provider, CodexAppServerProvider)
