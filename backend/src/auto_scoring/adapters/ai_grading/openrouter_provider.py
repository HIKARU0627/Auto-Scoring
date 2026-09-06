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
import json
import time

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._prompt import (
    GRADING_SYSTEM_INSTRUCTIONS,
    build_grading_user_content,
    sniff_image_format,
)
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema
from auto_scoring.domain.ai_grading import parse_ai_grading_result
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

#: OpenRouter's provider-routing preference restricting a request to
#: upstream providers whose data-collection policy is "deny" (no retention
#: of, or training on, submitted data) -- request-level zero-data-retention
#: enforcement. The decision record requires enabling an opt-out/ZDR option
#: wherever a cloud AI provider offers one for content sent off-device
#: (docs/business-rules-and-evaluation-data.md; code review finding: a
#: real answer-image crop must not reach an upstream that may retain or
#: train on it just because the caller's OpenRouter account itself hasn't
#: been switched to a global zero-data-retention setting). Whether
#: OpenRouter honours this preference for every upstream is unverified
#: against a live call -- see the live probe in docs/poc-2-ai-grading.md
#: section 7.4.
_ZERO_DATA_RETENTION_PROVIDER_PREFERENCE = {"data_collection": "deny"}


def _build_response_format() -> dict[str, object]:
    """OpenAI-compatible ``response_format`` constraining the completion to
    :class:`AIGradingResult`'s wire shape (camelCase aliases, ``extra:
    forbid`` -- section 3.6 of ``docs/poc-2-ai-grading.md``).

    Uses the strict-mode schema (``_schema.strict_ai_grading_result_schema``):
    a strict-mode backend rejects Pydantic's own ``model_json_schema()``
    output outright (fields with a default are missing from ``required``),
    which would fail every call before the model ever runs (code review
    finding). Schema *validation* still happens locally via
    ``parse_ai_grading_result`` regardless of whether the routed-to model
    actually honours this hint (Issue #14 acceptance: never trust a
    provider's own claim of schema-conformance without checking).
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ai_grading_result",
            "strict": True,
            "schema": strict_ai_grading_result_schema(),
        },
    }


def _describe_http_failure(exc: Exception) -> str:
    """A short, body-free description of a failed HTTP call. Includes the
    numeric status code for an ``httpx.HTTPStatusError`` (never the response
    body, which may echo request content) so callers can apply the
    documented 429 backoff and tell a persistent 4xx (auth/config) apart
    from a transient 5xx (code review finding)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTPStatusError (status {exc.response.status_code})"
    return type(exc).__name__


def _routing_fingerprint(data: dict[str, object]) -> str | None:
    """Identifies the actual deployment that answered, for
    ``ProviderDescriptor.version`` (Issue #14 "再現条件").

    OpenRouter can route the same requested model slug (``data["model"]``
    only echoes that slug back, unless OpenRouter substituted a fallback)
    through different upstream inference providers -- the top-level
    ``data["provider"]`` field. Recording ``model`` alone would pool calls
    that actually ran against different upstream deployments into the same
    reproducibility bucket (``descriptor_key``, docs/poc-2-ai-grading.md
    section 3.3; code review finding). Encoded as a JSON object rather than
    a delimited string for the same collision-avoidance reason
    ``ai_provider.descriptor_key`` gives for not using ``"|"``-joins.
    """
    fingerprint: dict[str, str] = {}
    routed_model = data.get("model")
    if isinstance(routed_model, str) and routed_model.strip():
        fingerprint["model"] = routed_model
    upstream_provider = data.get("provider")
    if isinstance(upstream_provider, str) and upstream_provider.strip():
        fingerprint["provider"] = upstream_provider
    return json.dumps(fingerprint, sort_keys=True) if fingerprint else None


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
        #: Populated as soon as a response body is available (before the
        #: completion's structure/content is validated at all), and reused
        #: by both `describe()` and every later response descriptor -- a
        #: schema-violating response must not be attributed to a different
        #: (empty) route fingerprint than the successful calls against the
        #: same actual route (code review finding: computing this only
        #: after a successful parse left every schema-violation exception
        #: with no way to record which model/upstream provider actually
        #: produced the malformed output, understating that route's own
        #: schema_violation_rate).
        self._last_route: str | None = None

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model=self._model,
            version=self._last_route,
            prompt_version=self._prompt_version,
            temperature=self._temperature,
            structured_output_mode="json_schema",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        # Reset before every attempt: if this call fails before a response
        # body is available at all (transport error, timeout, 429,
        # non-JSON body), `describe()`/a later failure record must not
        # keep reporting the *previous* successful call's route -- that
        # would misattribute this attempt's unavailability to an upstream
        # it never actually reached (code review finding).
        self._last_route = None

        image_data_url = (
            f"data:image/{sniff_image_format(request.answer_image)};base64,"
            f"{base64.b64encode(request.answer_image).decode('ascii')}"
        )
        payload = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": _build_response_format(),
            "provider": _ZERO_DATA_RETENTION_PROVIDER_PREFERENCE,
            "messages": [
                {"role": "system", "content": GRADING_SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_grading_user_content(request)},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
        }

        started_at = time.monotonic()
        try:
            http_response = self._client.post("/chat/completions", json=payload)
            http_response.raise_for_status()
            data = http_response.json()
        except (
            httpx.TransportError,
            httpx.HTTPStatusError,
            httpx.TimeoutException,
            json.JSONDecodeError,
        ) as exc:
            # A non-JSON body (OpenRouter outage page, proxy error, ...) must
            # not escape as an uncaught JSONDecodeError -- callers only
            # expect SchemaViolation/ProviderUnavailable from this port. The
            # numeric HTTP status (never the response body) is included so
            # callers can apply the documented 429 backoff and distinguish a
            # persistent auth/config failure from a transient server error
            # (code review finding).
            detail = _describe_http_failure(exc)
            raise ProviderUnavailable(f"OpenRouter request failed: {detail}") from None
        latency_seconds = time.monotonic() - started_at

        if not isinstance(data, dict):
            # A 2xx response whose top-level JSON value isn't even an
            # object (an array, a bare scalar, ...) is a malformed
            # structured response, not a transport failure --
            # SchemaViolation routes it to the documented needs-review path
            # (code review finding: `_routing_fingerprint`'s `.get(...)`
            # calls would otherwise raise an uncaught AttributeError on a
            # non-dict value).
            raise SchemaViolation("OpenRouter response body was not a JSON object")

        # Computed before validating the completion's structure/content any
        # further: see the `_last_route` docstring above.
        self._last_route = _routing_fingerprint(data)

        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            # A 2xx response with valid JSON but a missing/malformed
            # completion envelope (a refusal, a changed response shape, ...)
            # is a malformed *structured response*, not a transport failure
            # -- SchemaViolation routes it to the documented needs-review
            # path instead of triggering a retry/unavailable-rate count
            # (code review finding).
            raise SchemaViolation(
                "OpenRouter response did not contain a chat completion message"
            ) from None

        try:
            parsed_result = parse_ai_grading_result(content)
        except ValidationError:
            # Do not chain the raw ValidationError (`from exc`): pydantic's
            # `errors()` retains the actual malformed field value under
            # `input_value`, and Python's default traceback rendering prints
            # a chained cause's own `str()` -- which would leak that value
            # (possibly OCR'd student content) into logs (AGENTS.md
            # "Security", docs/poc-2-ai-grading.md section 3.7).
            raise SchemaViolation(
                "OpenRouter response failed AIGradingResult schema validation"
            ) from None

        descriptor = ProviderDescriptor(
            provider=self.name,
            model=self._model,
            version=self._last_route,
            prompt_version=self._prompt_version,
            temperature=self._temperature,
            structured_output_mode="json_schema",
        )
        return grading_response_from_result(
            parsed_result, descriptor=descriptor, latency_seconds=latency_seconds
        )
