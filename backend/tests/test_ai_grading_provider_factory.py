"""Tests for the config-driven ``AIProvider`` transport switch (Issue #44)."""

import pytest

from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.adapters.ai_grading.openrouter_provider import OpenRouterAIProvider

_COMMON = {
    "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter",
    "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
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
