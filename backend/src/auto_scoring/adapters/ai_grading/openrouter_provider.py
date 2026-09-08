"""``AIProvider`` adapter over OpenRouter (Issue #44).

OpenRouter (https://openrouter.ai) exposes an OpenAI-Chat-Completions-compatible
HTTP API in front of many vendors' models (Gemini / Claude / GPT / others)
behind a single API key, and is candidate ③ of the adopted fallback chain
(business-rules-and-evaluation-data.md section 3 (B), Issue #81). The whole
call path -- strict-mode ``response_format``, the system/user message split,
failure classification, and the "never free-text-parse a malformed response"
rule -- lives in :class:`ChatCompletionsAIProvider`, shared with the direct
OpenAI adapter (Issue #35); this module only adds what is specific to
OpenRouter.
"""

from __future__ import annotations

import httpx

from auto_scoring.adapters.ai_grading._openai_chat import (
    DEFAULT_TIMEOUT_SECONDS,
    ChatCompletionsAIProvider,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: OpenRouter's provider-routing preference restricting a request to
#: zero-data-retention upstream providers -- request-level enforcement so
#: that a real answer-image crop and OCR text never reach an upstream that
#: may retain or train on them, regardless of whether the caller's
#: OpenRouter account itself has been switched to a global zero-data-
#: retention setting. The decision record requires enabling an opt-out/ZDR
#: option wherever a cloud AI provider offers one for content sent
#: off-device (docs/business-rules-and-evaluation-data.md).
#:
#: Two distinct fields, both required (code review findings):
#: ``data_collection: "deny"`` restricts routing to providers whose
#: *training/data-collection* policy is "deny", but a provider can still
#: retain input for other purposes (e.g. abuse monitoring) under that
#: policy alone. ``zdr: True`` is OpenRouter's separate, stricter routing
#: constraint that actually enforces zero data retention -- without it,
#: the account-level ZDR setting being off would still let a request reach
#: a non-ZDR endpoint despite this adapter's own zero-retention claim.
#: Whether OpenRouter honours both constraints for every upstream is
#: unverified against a live call -- see the live probe in
#: docs/poc-2-ai-grading.md section 7.4.
ZERO_DATA_RETENTION_PROVIDER_PREFERENCE = {"data_collection": "deny", "zdr": True}


class OpenRouterAIProvider(ChatCompletionsAIProvider):
    """Calls one OpenRouter-routed model per ``grade()``.

    ``model`` is OpenRouter's routing identifier (e.g.
    ``"anthropic/claude-sonnet-4.5"``, ``"google/gemini-2.5-flash"``), not a
    vendor-specific SDK model name -- OpenRouter's own namespacing.
    """

    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_version: str,
        temperature: float = 0.0,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            prompt_version=prompt_version,
            base_url=base_url,
            label="OpenRouter",
            extra_payload={"provider": ZERO_DATA_RETENTION_PROVIDER_PREFERENCE},
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            client=client,
        )
