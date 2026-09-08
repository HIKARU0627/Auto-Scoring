"""The OpenAI Chat Completions call path, shared by the OpenRouter and
direct-OpenAI adapters (Issue #35).

OpenRouter deliberately exposes an OpenAI-compatible API, so the two
adapters differ only in four things: the base URL, the vendor-specific
request field each one needs (OpenRouter's zero-data-retention routing
preference; OpenAI's ``store: false``), the ``provider`` name recorded in
the descriptor, and the label that appears in an error message. Everything
else -- the strict-mode ``response_format``, the system/user message split,
the image data URL, the failure classification, and the "never
free-text-parse a malformed response" rule -- was duplicated between them
before this module existed, which is exactly the drift ``_prompt.py``
already exists to prevent for the prompt text.

Never logs the API key, the request payload (answer image / OCR text /
rubric text), or the raw response body (AGENTS.md "Security"): exceptions
carry only HTTP status codes and pydantic's structural error locations,
never field values (mirrors ``poc/issue_14_ai_grading/report.py``'s
``_sanitize_validation_error``).
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._http import raise_classified_unavailable
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
    SchemaViolation,
    grading_response_from_result,
)

#: The structured-output mode both adapters request, recorded verbatim into
#: ``ProviderDescriptor.structured_output_mode`` (docs/poc-2-ai-grading.md
#: section 3.3).
_STRUCTURED_OUTPUT_MODE = "json_schema"

DEFAULT_TIMEOUT_SECONDS = 60.0


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


def _routing_fingerprint(data: dict[str, Any]) -> str | None:
    """Identifies the actual deployment that answered, for
    ``ProviderDescriptor.version`` (Issue #14 "再現条件").

    OpenRouter can route the same requested model slug (``data["model"]``
    only echoes that slug back, unless OpenRouter substituted a fallback)
    through different upstream inference providers -- the top-level
    ``data["provider"]`` field. OpenAI has no such field but echoes the
    dated snapshot it actually ran (``gpt-4o-mini-2024-07-18`` for a
    request that asked for ``gpt-4o-mini``), which is the same kind of
    information. Recording the requested slug alone would pool calls that
    actually ran against different upstream deployments into the same
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


class ChatCompletionsAIProvider:
    """``AIProvider`` over an OpenAI-compatible ``/chat/completions`` endpoint.

    Not registered as a candidate itself -- ``name`` is supplied by the
    concrete subclass (``openrouter`` / ``openai``), which is the id the
    PoC harness buckets results under and the value that ends up in
    ``GradeResult.provider`` (business-rules-and-evaluation-data.md section
    3 (B): "どの provider で採点したかを結果に残す").
    """

    #: Overridden by every concrete subclass.
    name = "chat-completions"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_version: str,
        base_url: str,
        label: str,
        extra_payload: dict[str, Any],
        temperature: float = 0.0,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError(f"{type(self).__name__}.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError(f"{type(self).__name__}.model must be a non-blank string")
        self._model = model
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._label = label
        self._extra_payload = extra_payload
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
            structured_output_mode=_STRUCTURED_OUTPUT_MODE,
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        # Reset before every attempt: if this call fails before a response
        # body is available at all (transport error, timeout, 429,
        # non-JSON body), `describe()`/a later failure record must not keep
        # reporting the *previous* successful call's route -- that would
        # misattribute this attempt's unavailability to an upstream it
        # never actually reached (code review finding).
        self._last_route = None

        image_data_url = (
            f"data:image/{sniff_image_format(request.answer_image)};base64,"
            f"{base64.b64encode(request.answer_image).decode('ascii')}"
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": _build_response_format(),
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
            **self._extra_payload,
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
            UnicodeDecodeError,
        ) as exc:
            # A non-JSON body (an outage page, a misbehaving proxy, ...)
            # must not escape as an uncaught JSONDecodeError -- callers
            # only expect SchemaViolation/ProviderUnavailable from this
            # port. A body containing invalid UTF-8 fails even earlier, as
            # a UnicodeDecodeError from `httpx.Response.json()`'s internal
            # text decoding, before JSON parsing is ever attempted --
            # normalized the same way, never left to escape as an
            # unclassified exception with the raw response bytes in its
            # traceback (code review finding).
            raise_classified_unavailable(exc, label=self._label)
        latency_seconds = time.monotonic() - started_at

        if not isinstance(data, dict):
            # A 2xx response whose top-level JSON value isn't even an
            # object (an array, a bare scalar, ...) is a malformed
            # structured response, not a transport failure --
            # SchemaViolation routes it to the documented needs-review path
            # (code review finding: `_routing_fingerprint`'s `.get(...)`
            # calls would otherwise raise an uncaught AttributeError on a
            # non-dict value).
            raise SchemaViolation(f"{self._label} response body was not a JSON object")

        # Recorded before validating the completion's structure/content any
        # further: see the `_last_route` docstring above.
        self._last_route = _routing_fingerprint(data)

        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            # A 2xx response with valid JSON but a missing/malformed
            # completion envelope (a refusal, a changed response shape,
            # ...) is a malformed *structured response*, not a transport
            # failure -- SchemaViolation routes it to the documented
            # needs-review path instead of triggering a retry/unavailable-
            # rate count (code review finding).
            raise SchemaViolation(
                f"{self._label} response did not contain a chat completion message"
            ) from None

        try:
            parsed_result = parse_ai_grading_result(content)
        except ValidationError:
            # Do not chain the raw ValidationError (`from exc`): pydantic's
            # `errors()` retains the actual malformed field value under
            # `input_value`, and Python's default traceback rendering
            # prints a chained cause's own `str()` -- which would leak that
            # value (possibly OCR'd student content) into logs (AGENTS.md
            # "Security", docs/poc-2-ai-grading.md section 3.7).
            raise SchemaViolation(
                f"{self._label} response failed AIGradingResult schema validation"
            ) from None

        return grading_response_from_result(
            parsed_result, descriptor=self.describe(), latency_seconds=latency_seconds
        )
