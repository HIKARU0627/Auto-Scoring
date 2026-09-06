"""``AIProvider`` adapter over OpenRouter (Issue #44).

OpenRouter (https://openrouter.ai) exposes an OpenAI-Chat-Completions-compatible
HTTP API in front of many vendors' models (Gemini / Claude / GPT / others)
behind a single API key. This adapter never falls back to free-text parsing
(``domain.ai_provider`` contract): a malformed structured response is a
:class:`~auto_scoring.domain.ai_provider.SchemaViolation`, and a transport /
rate-limit / non-2xx failure is a
:class:`~auto_scoring.domain.ai_provider.ProviderUnavailable` -- mirroring the
direct-vendor-API adapters this PoC has not implemented yet
(``docs/poc-2-ai-grading.md`` section 7.1).

Never logs the API key, the request payload (answer image / OCR text / rubric
text), or the raw response body (AGENTS.md "Security"): exceptions carry only
HTTP status codes and pydantic's structural error locations, never field
values (mirrors ``poc/issue_14_ai_grading/report.py``'s
``_sanitize_validation_error``).
"""

from __future__ import annotations

import base64
import time

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._prompt import build_grading_prompt, sniff_image_format
from auto_scoring.domain.ai_grading import AIGradingResult, parse_ai_grading_result
from auto_scoring.domain.ai_provider import (
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
    grading_response_from_result,
)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_TIMEOUT_SECONDS = 60.0


def _build_response_format() -> dict[str, object]:
    """OpenAI-compatible ``response_format`` constraining the completion to
    :class:`AIGradingResult`'s wire shape (camelCase aliases, ``extra:
    forbid`` -- section 3.6 of ``docs/poc-2-ai-grading.md``).

    Schema *validation* still happens locally via ``parse_ai_grading_result``
    regardless of whether the routed-to model actually honours this hint
    (Issue #14 acceptance: never trust a provider's own claim of
    schema-conformance without checking).
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_grading_result",
            "strict": True,
            "schema": AIGradingResult.model_json_schema(by_alias=True),
        },
    }


class OpenRouterAIProvider:
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
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenRouterAIProvider.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError("OpenRouterAIProvider.model must be a non-blank string")
        self._model = model
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model=self._model,
            version=None,
            prompt_version=self._prompt_version,
            temperature=self._temperature,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        image_data_url = (
            f"data:image/{sniff_image_format(request.answer_image)};base64,"
            f"{base64.b64encode(request.answer_image).decode('ascii')}"
        )
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": _build_response_format(),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_grading_prompt(request)},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
        }

        started_at = time.monotonic()
        try:
            http_response = self._client.post("/chat/completions", json=payload)
            http_response.raise_for_status()
            data = http_response.json()
        except (httpx.TransportError, httpx.HTTPStatusError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(f"OpenRouter request failed: {type(exc).__name__}") from exc
        latency_seconds = time.monotonic() - started_at

        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderUnavailable(
                "OpenRouter response did not contain a chat completion message"
            ) from exc

        try:
            parsed_result = parse_ai_grading_result(content)
        except ValidationError as exc:
            raise SchemaViolation(
                "OpenRouter response failed AIGradingResult schema validation"
            ) from exc

        routed_model = data.get("model")
        version = routed_model if isinstance(routed_model, str) and routed_model.strip() else None
        descriptor = ProviderDescriptor(
            provider=self.name,
            model=self._model,
            version=version,
            prompt_version=self._prompt_version,
            temperature=self._temperature,
            structured_output_mode="json_schema",
        )
        return grading_response_from_result(
            parsed_result, descriptor=descriptor, latency_seconds=latency_seconds
        )
