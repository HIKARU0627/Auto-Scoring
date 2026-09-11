"""One real call with the saved key, so "saved" and "works" stay different
words (Issue #96).

Storing a key proves the credential store works. It proves nothing about the
key: a typo, a revoked key, a key for the wrong account and a machine behind
a proxy that blocks the provider all look identical on the settings screen
until something actually tries to use one. Issue #96 requires a button that
tries, and requires success, an authentication failure and an unreachable
network to be told apart on screen -- because the three call for three
different actions (retype it, make a new one, ask about the network).

**The call is OpenRouter's ``GET /key``, not a grading request.** It is the
provider's own "is this credential live" endpoint: it runs no model, so it
consumes no tokens and appears on no invoice, and it authenticates with
exactly the header a grading call would use. A grading request would cost the
user money every time they pressed a button whose entire purpose is to be
pressed when unsure.

What it does **not** prove is that the account has credit left, or that the
chosen model is available to it -- a live key with an empty balance passes
here and fails at the first grade. The response carries the account's usage
and limit, so when OpenRouter reports a limit that is already spent this says
so rather than reporting a clean success.

**Nothing here renders a response body or a key.** The outcome carries a
fixed sentence written in this module plus, at most, an HTTP status number --
the discipline `adapters.ai_grading._http` states: a body can echo the
request, and an auth failure's body can echo part of the credential.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import httpx

from auto_scoring.adapters.ai_grading.openrouter_provider import OPENROUTER_BASE_URL
from auto_scoring.adapters.credentials.api_keys import ApiKeySlot

#: Short on purpose. This runs while somebody watches a spinner on a settings
#: screen, unlike a grading call that is allowed a minute.
VERIFY_TIMEOUT_SECONDS: Final = 15.0

_UNAUTHORIZED_STATUSES: Final = frozenset({401, 403})


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


def verify_api_key(
    slot: ApiKeySlot,
    api_key: str,
    *,
    base_url: str = OPENROUTER_BASE_URL,
    client: httpx.Client | None = None,
) -> VerificationOutcome:
    """Try ``api_key`` against ``slot``'s provider exactly once.

    ``client`` is injected by every test: this function is the one place in
    Issue #96 that touches the network, and a test that reached the real
    OpenRouter would be both flaky and, over a CI run, somebody's bill.
    """
    if slot.transport != "openrouter":  # pragma: no cover - one slot exists
        return VerificationOutcome(
            VerificationResult.PROVIDER_ERROR,
            "この provider の疎通確認には対応していません。",
        )
    owned = client is None
    http = client or httpx.Client(base_url=base_url, timeout=VERIFY_TIMEOUT_SECONDS)
    try:
        response = http.get("/key", headers={"Authorization": f"Bearer {api_key}"})
        response.raise_for_status()
        return _read_key_response(response)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in _UNAUTHORIZED_STATUSES:
            return VerificationOutcome(
                VerificationResult.UNAUTHORIZED,
                "キーが受け付けられませんでした。値が正しいか、まだ有効かを確認してください。",
                status_code=status,
            )
        return VerificationOutcome(
            VerificationResult.PROVIDER_ERROR,
            f"provider がエラーを返しました（HTTP {status}）。時間をおいて試してください。",
            status_code=status,
        )
    except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as error:
        # The same root-class catch `adapters.ai_grading._http` argues for:
        # enumerating the interesting subclasses let `httpx.DecodingError`
        # through once already. Only the type name crosses into the message.
        return VerificationOutcome(
            VerificationResult.UNREACHABLE,
            f"provider に接続できませんでした（{type(error).__name__}）。"
            "ネットワークやプロキシの設定を確認してください。",
        )
    finally:
        if owned:
            http.close()


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
