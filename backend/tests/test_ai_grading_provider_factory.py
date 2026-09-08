"""Tests for the config-driven ``AIProvider`` transport switch (Issues #44, #35)."""

import shutil

import pytest

from auto_scoring.adapters.ai_grading import factory
from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError
from auto_scoring.adapters.ai_grading.codex_app_server_provider import CodexAppServerProvider
from auto_scoring.adapters.ai_grading.factory import AIProviderConfigError, create_ai_provider
from auto_scoring.adapters.ai_grading.fallback_provider import FallbackAIProvider
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


def test_create_ai_provider_selects_codex_app_server(_codex_installed: None) -> None:
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


def test_create_ai_provider_ignores_temperature_for_codex_app_server(
    _codex_installed: None,
) -> None:
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


# --- Issue #35: the transport list builds the Issue #81 fallback chain ---


class _FakeAdcTokenSource:
    """Stands in for ADC so these tests do not depend on whether the host
    running them happens to have a `gcloud` login."""

    project_id = "test-project"

    def __init__(self, *, project_id: str | None = None) -> None:
        if project_id:
            self.project_id = project_id

    def bearer_token(self) -> str:  # pragma: no cover - never called offline
        return "fake"


@pytest.fixture
def _codex_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the ``codex`` executable is on PATH.

    Whether it actually is differs between a developer machine and a CI
    runner, and ``create_ai_provider`` now (correctly) leaves the Codex link
    out of the chain when it is missing. Any test about *transport
    selection* therefore has to state which of the two worlds it is in, or
    it passes locally and fails in CI -- which is exactly what happened
    (CI: "the 'codex' executable was not found on this host"). Tests about
    the detection itself patch this for themselves, below.
    """
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/local/bin/{name}")


@pytest.fixture
def _adc_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory, "AdcTokenSource", _FakeAdcTokenSource)


@pytest.fixture
def _adc_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**_kwargs: object) -> None:
        raise AdcCredentialsError("no ADC on this host")

    monkeypatch.setattr(factory, "AdcTokenSource", _raise)


def test_a_transport_list_builds_the_priority_chain(
    _adc_available: None, _codex_installed: None
) -> None:
    """business-rules-and-evaluation-data.md section 3 (B): the adopted
    configuration is the order itself, not a single vendor."""
    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini,codex_app_server,openrouter,openai",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
            **_OPENROUTER_CREDENTIALS,
            "AUTO_SCORING_OPENAI_API_KEY": "key",
            "AUTO_SCORING_OPENAI_MODEL": "gpt-4o-mini",
        }
    )
    assert isinstance(provider, FallbackAIProvider)
    assert [child.name for child in provider.providers] == [
        "gemini",
        "codex-app-server",
        "openrouter",
        "openai",
    ]


def test_transports_without_credentials_are_left_out_of_the_chain(_adc_missing: None) -> None:
    """docs/ai-grading-pipeline.md: an unconfigured provider must not
    consume one step of the chain by failing at call time."""
    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini,openrouter,openai",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
            **_OPENROUTER_CREDENTIALS,
        }
    )
    # Gemini has no ADC here and OpenAI has no key, so only OpenRouter is
    # buildable -- and a one-link chain is just that adapter.
    assert isinstance(provider, OpenRouterAIProvider)


def test_no_configured_transport_at_all_is_an_error_not_an_empty_chain(
    _adc_missing: None,
) -> None:
    """An empty chain would grade nothing while looking configured."""
    with pytest.raises(AIProviderConfigError, match="usable credentials"):
        create_ai_provider(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini,openai",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
            }
        )


def test_a_repeated_transport_is_rejected() -> None:
    """Silently de-duplicating would leave the operator believing a
    provider they listed twice is tried twice."""
    with pytest.raises(AIProviderConfigError, match="twice"):
        create_ai_provider(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter,openrouter",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                **_OPENROUTER_CREDENTIALS,
            }
        )


def test_one_unknown_entry_rejects_the_whole_list() -> None:
    with pytest.raises(AIProviderConfigError, match="unknown transport"):
        create_ai_provider(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "openrouter,bogus",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                **_OPENROUTER_CREDENTIALS,
            }
        )


def test_gemini_never_accepts_an_api_key(_adc_missing: None) -> None:
    """Gemini API keys are blocked by organization policy, so a key in the
    environment must not make the Gemini link buildable -- the operator
    needs the ADC error, not a chain that silently drops the candidate."""
    with pytest.raises(AIProviderConfigError, match="usable credentials"):
        create_ai_provider(
            {
                "AUTO_SCORING_AI_GRADING_TRANSPORT": "gemini",
                "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
                "AUTO_SCORING_GEMINI_MODEL": "gemini-2.5-flash",
                "AUTO_SCORING_GEMINI_API_KEY": "should-be-ignored",
            }
        )


def test_codex_is_skipped_when_its_executable_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/ai-grading-pipeline.md: "認証情報が揃っているものだけをチェーンに
    組む". A host without `codex` cannot grade anything through it, so
    leaving the link in guarantees one wasted failure ahead of every
    provider below it (code review finding)."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server,openrouter",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            **_OPENROUTER_CREDENTIALS,
        }
    )

    assert isinstance(provider, OpenRouterAIProvider)


def test_codex_is_included_when_its_executable_is_installed(_codex_installed: None) -> None:
    """Being installed is necessary, not sufficient: a host with `codex`
    but no login still fails at call time, and the chain falls through
    then. That is a runtime failure, not a construction-time one."""
    provider = create_ai_provider(
        {
            "AUTO_SCORING_AI_GRADING_TRANSPORT": "codex_app_server,openrouter",
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION": "v1",
            **_OPENROUTER_CREDENTIALS,
        }
    )

    assert isinstance(provider, FallbackAIProvider)
    assert [child.name for child in provider.providers] == ["codex-app-server", "openrouter"]
