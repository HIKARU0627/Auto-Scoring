"""``AIProvider`` adapter over the direct OpenAI API (Issue #35).

Candidate ④ -- the last link -- of the adopted fallback chain
(business-rules-and-evaluation-data.md section 3 (B), Issue #81: Gemini API
-> Codex App Server -> OpenRouter -> OpenAI API). The whole call path lives
in :class:`ChatCompletionsAIProvider`; OpenRouter's API is OpenAI-compatible
by design, so this module only adds what is specific to calling OpenAI
directly.
"""

from __future__ import annotations

import httpx

from auto_scoring.adapters.ai_grading._openai_chat import (
    DEFAULT_TIMEOUT_SECONDS,
    ChatCompletionsAIProvider,
)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"

#: OpenAI does not train on API inputs by default, but it does retain
#: completions for the account's dashboard/logs unless the request opts out.
#: ``store: false`` is that opt-out, applied per request so it holds
#: regardless of the account's own default -- the same reason the OpenRouter
#: adapter sends its zero-data-retention routing preference on every call
#: rather than relying on an account-level toggle (decision record: enable
#: the retention opt-out wherever a cloud AI provider offers one for content
#: sent off-device, business-rules-and-evaluation-data.md section 6.6).
#: It does not shorten OpenAI's own abuse-monitoring retention, which is not
#: request-controllable; the payload is still limited to one question's
#: material with no student-identifying data (decision record section 2 (2)).
_NO_RESPONSE_STORAGE = {"store": False}


class OpenAIAIProvider(ChatCompletionsAIProvider):
    """Calls one OpenAI model per ``grade()``.

    ``model`` is OpenAI's own model name (e.g. ``"gpt-4o-mini"``), not an
    OpenRouter routing slug -- the two namespaces are not interchangeable,
    which is why this is a separate adapter rather than an ``OPENAI_BASE_URL``
    on the OpenRouter one.
    """

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_version: str,
        temperature: float = 0.0,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            prompt_version=prompt_version,
            base_url=base_url,
            label="OpenAI",
            extra_payload=_NO_RESPONSE_STORAGE,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            client=client,
        )
