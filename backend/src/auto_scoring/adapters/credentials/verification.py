"""One real call with the saved configuration, so "saved" and "works" stay
different words (Issues #96, #386).

Storing a credential proves the credential store works. It proves nothing
about the credential: a typo, a revoked key, a key for the wrong account and a
machine behind a proxy that blocks the provider all look identical on the
settings screen until something actually tries to use one. Issue #96 requires
a button that tries, and requires success, an authentication failure and an
unreachable network to be told apart on screen -- because the three call for
three different actions (retype it, make a new one, ask about the network).

**Each provider is tried with its own free "is this credential live"
endpoint**, not a grading request:

* OpenRouter: its own ``GET /key`` (the existing behaviour), which also
  reports the account's usage/limit.
* OpenAI: ``GET /models``, which authenticates the key without running a
  model and appears on no invoice.
* Gemini (Vertex AI): there is **no key to try** -- authentication is
  Application Default Credentials (`_google_adc`) -- so this resolves a token
  once. That is exactly the question the screen needs answered: is ADC set up
  on this host, and can it mint a token for the configured project.
* Codex app-server: there is no key either; the check is whether the ``codex``
  executable named by ``AUTO_SCORING_CODEX_EXECUTABLE`` (default ``codex``)
  is installed. Being installed is necessary, not sufficient, and the screen
  says so through the outcome text.

**Nothing here renders a response body, a key, or any other configuration
value.** The outcome carries a fixed sentence written in this module plus, at
most, an HTTP status number -- the discipline `adapters.ai_grading._http`
states: a body can echo the request, and an auth failure's body can echo part
of the credential. A failed ADC resolution contributes only its exception
type, exactly as `_google_adc` does, never google-auth's own message.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

import httpx

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading.openai_provider import OPENAI_BASE_URL
from auto_scoring.adapters.ai_grading.openrouter_provider import OPENROUTER_BASE_URL
from auto_scoring.adapters.credentials.api_keys import ApiKeySlot

#: Short on purpose. This runs while somebody watches a spinner on a settings
#: screen, unlike a grading call that is allowed a minute.
VERIFY_TIMEOUT_SECONDS: Final = 15.0

_UNAUTHORIZED_STATUSES: Final = frozenset({401, 403})

_CODEX_EXECUTABLE_VARIABLE: Final = "AUTO_SCORING_CODEX_EXECUTABLE"


class VerificationResult(StrEnum):
    """The distinct outcomes the screen renders differently."""

    OK = "ok"
    #: Reachable, and it refused the credential.
    UNAUTHORIZED = "unauthorized"
    #: Never got an answer: DNS, TLS, a proxy, a timeout, no network.
    UNREACHABLE = "unreachable"
    #: Answered, but with something this app cannot read as success.
    PROVIDER_ERROR = "provider_error"
    #: Reachable and the credential is live, but it will not buy anything.
    NO_CREDIT = "no_credit"
    #: Nothing to try -- no key is in force for this slot.
    NOT_CONFIGURED = "not_configured"
    #: This provider authenticates with a *host* credential that is missing
    #: (ADC for Vertex AI, the Codex CLI for app-server), so there is nothing
    #: on this screen to retype -- the fix is on the host.
    MISSING_HOST_AUTH = "missing_host_auth"


@dataclass(frozen=True)
class VerificationOutcome:
    result: VerificationResult
    detail: str
    #: Present only for a response that arrived. A number cannot carry a
    #: credential, which is why it is the one thing from the response that
    #: is allowed out.
    status_code: int | None = None
    #: OpenRouter ``GET /key`` account usage/limit (Issue #187). Shown on a
    #: separate line from this app's own token accumulation -- never mixed.
    provider_account_usage: float | None = None
    provider_account_limit: float | None = None


NOT_CONFIGURED = VerificationOutcome(
    VerificationResult.NOT_CONFIGURED,
    "キーが未設定です。先にキーを入力して保存してください。",
)


def _default_token_source(project_id: str | None) -> AdcTokenSource:
    return AdcTokenSource(project_id=project_id)


def _default_executable_available(name: str) -> bool:
    """Whether ``name`` resolves to something runnable on this host.

    Mirrors `adapters.ai_grading.factory._executable_available`; not imported
    from there because that one is private to the factory, and this module's
    tests must be able to state which host they are on instead.
    """
    return shutil.which(name) is not None or Path(name).is_file()


def verify_api_key(
    slot: ApiKeySlot,
    values: Mapping[str, str],
    *,
    client: httpx.Client | None = None,
    base_url: str = OPENROUTER_BASE_URL,
    openai_client: httpx.Client | None = None,
    openai_base_url: str = OPENAI_BASE_URL,
    token_source_factory: Callable[[str | None], AdcTokenSource] = _default_token_source,
    executable_available: Callable[[str], bool] = _default_executable_available,
) -> VerificationOutcome:
    """Try ``slot``'s configuration against its provider exactly once.

    ``values`` is the effective configuration in force (key and readable
    settings), as `ApiKeySettings.resolved_settings` returns it. Every HTTP
    client and host probe is injected by tests: this function is the one place
    in these Issues that touches the network or the host, and a test that
    reached the real provider would be both flaky and, over a CI run,
    somebody's bill.
    """
    if slot.transport == "openrouter":
        return _verify_openrouter(slot, values, client=client, base_url=base_url)
    if slot.transport == "openai":
        return _verify_openai(slot, values, client=openai_client, base_url=openai_base_url)
    if slot.transport == "gemini":
        return _verify_vertex(values, token_source_factory=token_source_factory)
    if slot.transport == "codex_app_server":
        return _verify_codex(values, executable_available=executable_available)
    return VerificationOutcome(
        VerificationResult.PROVIDER_ERROR,
        "この provider の疎通確認には対応していません。",
    )


def _api_key(slot: ApiKeySlot, values: Mapping[str, str]) -> str | None:
    if slot.key_variable is None:
        return None
    value = values.get(slot.key_variable, "").strip()
    return value or None


def _http_error_outcome(label: str, error: httpx.HTTPStatusError) -> VerificationOutcome:
    """``label`` must be a literal written by this module, never a value.

    It is the one thing this function interpolates into a message (the 401/403
    branch returns a fixed sentence and does not use it), so a caller that
    passed configuration into it would publish that value. The tests assert
    no key reaches the message on these branches; keep every call a literal.
    """
    status = error.response.status_code
    if status in _UNAUTHORIZED_STATUSES:
        return VerificationOutcome(
            VerificationResult.UNAUTHORIZED,
            "キーが受け付けられませんでした。値が正しいか、まだ有効かを確認してください。",
            status_code=status,
        )
    return VerificationOutcome(
        VerificationResult.PROVIDER_ERROR,
        f"{label} がエラーを返しました（HTTP {status}）。時間をおいて試してください。",
        status_code=status,
    )


def _unreachable(label: str, error: BaseException) -> VerificationOutcome:
    # The same root-class catch `adapters.ai_grading._http` argues for:
    # enumerating the interesting subclasses let `httpx.DecodingError`
    # through once already. Only the type name crosses into the message.
    # Like `_http_error_outcome`, `label` is a literal from this module, never
    # a configuration value; the tests assert no key reaches this message.
    return VerificationOutcome(
        VerificationResult.UNREACHABLE,
        f"{label} に接続できませんでした（{type(error).__name__}）。"
        "ネットワークやプロキシの設定を確認してください。",
    )


def _verify_openrouter(
    slot: ApiKeySlot,
    values: Mapping[str, str],
    *,
    client: httpx.Client | None,
    base_url: str,
) -> VerificationOutcome:
    api_key = _api_key(slot, values)
    if api_key is None:
        return NOT_CONFIGURED
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=VERIFY_TIMEOUT_SECONDS)
    try:
        response = http.get("/key", headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        return _read_key_response(response)
    except httpx.HTTPStatusError as error:
        return _http_error_outcome("provider", error)
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return _unreachable("provider", error)
    finally:
        if owned:
            http.close()


def _verify_openai(
    slot: ApiKeySlot,
    values: Mapping[str, str],
    *,
    client: httpx.Client | None,
    base_url: str,
) -> VerificationOutcome:
    """``GET /models``: authenticates the key and runs no model.

    Deliberately not a completion: the button's whole purpose is to be pressed
    when unsure, and every press of a completion would cost the user money.
    """
    api_key = _api_key(slot, values)
    if api_key is None:
        return NOT_CONFIGURED
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=VERIFY_TIMEOUT_SECONDS)
    try:
        response = http.get("/models", headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        return VerificationOutcome(
            VerificationResult.OK,
            "疎通しました。このキーで採点できます。",
            status_code=response.status_code,
        )
    except httpx.HTTPStatusError as error:
        return _http_error_outcome("provider", error)
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return _unreachable("provider", error)
    finally:
        if owned:
            http.close()


def _verify_vertex(
    values: Mapping[str, str],
    *,
    token_source_factory: Callable[[str | None], AdcTokenSource],
) -> VerificationOutcome:
    """Resolve one ADC access token for the configured project.

    There is no key on this screen for Vertex AI: the credential is on the
    host, and the honest check is whether it can be resolved at all. Only the
    exception *type* is published, never google-auth's own message (which can
    quote the token endpoint's response body -- `_google_adc`).
    """
    project = values.get("AUTO_SCORING_VERTEX_PROJECT", "").strip() or None
    try:
        token_source = token_source_factory(project)
        token_source.bearer_token()
    except AdcCredentialsError as error:
        return VerificationOutcome(
            VerificationResult.MISSING_HOST_AUTH,
            "この PC に ADC（Application Default Credentials）がありません。"
            "`gcloud auth application-default login` を実行してください"
            f"（{type(error).__name__}）。",
        )
    return VerificationOutcome(
        VerificationResult.OK,
        "ADC を確認できました。この PC で Gemini（Vertex AI）を利用できます。",
    )


def _verify_codex(
    values: Mapping[str, str],
    *,
    executable_available: Callable[[str], bool],
) -> VerificationOutcome:
    executable = values.get(_CODEX_EXECUTABLE_VARIABLE, "").strip() or "codex"
    if executable_available(executable):
        return VerificationOutcome(
            VerificationResult.OK,
            "Codex CLI が見つかりました。この PC で Codex App Server を利用できます"
            "（ログイン済みかどうかは実行時に確認されます）。",
        )
    return VerificationOutcome(
        VerificationResult.MISSING_HOST_AUTH,
        "この PC に Codex CLI が見つかりません。先に Codex CLI をインストールし、"
        "`codex login` を実行してください。",
    )


def _read_key_response(response: httpx.Response) -> VerificationOutcome:
    """A 200 from ``GET /key``, read for the one thing beyond "it answered".

    OpenRouter returns ``{"data": {"usage": ..., "limit": ...}}``, where
    ``limit`` is ``null`` for a key with no cap. A capped key whose usage has
    reached the cap authenticates perfectly and grades nothing, so it gets
    its own outcome instead of a green tick the first grading job would
    contradict. Anything unreadable in that shape is *not* an error: the key
    answered, which is what was asked.
    """
    status = response.status_code
    ok = VerificationOutcome(
        VerificationResult.OK,
        "疎通しました。このキーで採点できます。",
        status_code=status,
    )
    try:
        data = response.json().get("data")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return ok
    if not isinstance(data, dict):
        return ok
    limit = data.get("limit")
    usage = data.get("usage")
    provider_usage = float(usage) if isinstance(usage, int | float) else None
    provider_limit = float(limit) if isinstance(limit, int | float) else None
    if (
        provider_limit is not None
        and provider_usage is not None
        and provider_usage >= provider_limit
    ):
        return VerificationOutcome(
            VerificationResult.NO_CREDIT,
            "キーは有効ですが、利用上限に達しています。provider 側で残高か上限を確認してください。",
            status_code=status,
            provider_account_usage=provider_usage,
            provider_account_limit=provider_limit,
        )
    return VerificationOutcome(
        VerificationResult.OK,
        ok.detail,
        status_code=status,
        provider_account_usage=provider_usage,
        provider_account_limit=provider_limit,
    )


__all__ = [
    "NOT_CONFIGURED",
    "VERIFY_TIMEOUT_SECONDS",
    "VerificationOutcome",
    "VerificationResult",
    "verify_api_key",
]
