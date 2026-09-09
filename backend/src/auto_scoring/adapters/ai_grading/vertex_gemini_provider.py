"""``AIProvider`` adapter over Gemini on Vertex AI (Issue #35).

Candidate ① -- the first link -- of the adopted fallback chain
(business-rules-and-evaluation-data.md section 3 (B), Issue #81: Gemini API
-> Codex App Server -> OpenRouter -> OpenAI API).

**Vertex AI, not the Gemini Developer API.** The two are different products
with different auth: the Developer API takes a ``GEMINI_API_KEY``, which
this project's Google Cloud organization policy forbids outright. Vertex AI
authenticates with Application Default Credentials instead (``_google_adc``),
which is also why no GCP project id is stored in this repository -- ADC
resolves it at runtime (AGENTS.md "Security").

Uses ``generationConfig.responseJsonSchema``, which accepts the same
strict-mode JSON Schema (``$defs``/``$ref`` included) the OpenAI-compatible
adapters send as ``response_format`` -- verified against a live call, see
``docs/poc-2-ai-grading.md`` section 7.4. That is the reason this adapter
does not carry its own hand-maintained copy of the schema in Vertex's older,
narrower ``responseSchema`` dialect: a second copy would be free to drift
from ``domain.ai_grading.AIGradingResult``, and the local
``parse_ai_grading_result`` check (Issue #14 acceptance) would then start
rejecting responses the adapter itself had asked for.

Never logs the access token, the request payload (answer image / OCR text /
rubric text), or the raw response body (AGENTS.md "Security"): exceptions
carry only HTTP status codes, exception type names, and -- for a schema
violation -- the failing field paths and pydantic error codes this project's
own schema defines (``domain.ai_grading.describe_schema_violation``), never
field values.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading._http import (
    CONVERTIBLE_HTTP_ERRORS,
    raise_classified_unavailable,
)
from auto_scoring.adapters.ai_grading._prompt import (
    GRADING_SYSTEM_INSTRUCTIONS,
    build_grading_user_content,
    sniff_image_format,
)
from auto_scoring.adapters.ai_grading._schema import strict_ai_grading_result_schema
from auto_scoring.domain.ai_grading import (
    describe_schema_violation,
    parse_ai_grading_result,
)
from auto_scoring.domain.ai_provider import (
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
    grading_response_from_result,
)

_DEFAULT_LOCATION = "global"
_DEFAULT_TIMEOUT_SECONDS = 120.0
_LABEL = "Vertex AI"

#: Recorded verbatim into ``ProviderDescriptor.structured_output_mode``
#: (docs/poc-2-ai-grading.md section 3.3). Distinct from the OpenAI-
#: compatible adapters' ``"json_schema"``: the same schema is enforced by a
#: different mechanism, and two configurations that differ only in how the
#: structured output was constrained must not share a metrics bucket.
_STRUCTURED_OUTPUT_MODE = "response_json_schema"


def vertex_generate_content_endpoint(*, location: str, project_id: str, model: str) -> str:
    """The ``generateContent`` URL for one model.

    The ``global`` location has its own hostname (no region prefix); every
    regional location prefixes the host with the region id.
    """
    host = "aiplatform.googleapis.com"
    if location != "global":
        host = f"{location}-{host}"
    return (
        f"https://{host}/v1/projects/{project_id}/locations/{location}"
        f"/publishers/google/models/{model}:generateContent"
    )


def _response_text(data: dict[str, Any]) -> str:
    """The single text part of a ``generateContent`` response.

    Raises :class:`SchemaViolation` for a 2xx body that is not a completed
    text candidate at all -- a safety block (``promptFeedback.blockReason``,
    or a candidate with ``finishReason`` other than ``STOP`` and no text),
    a truncated response, or a changed response shape. Like the
    OpenAI-compatible adapters, that is deliberately *not*
    ``ProviderUnavailable``: the call itself succeeded, so retrying the same
    request against the same model reproduces it, and it belongs on the
    needs-review path (docs/ai-grading-pipeline.md "どの失敗で次へ落とすか").
    """
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise SchemaViolation(
            f"{_LABEL} response did not contain a completed text candidate"
        ) from None
    if not isinstance(parts, list):
        raise SchemaViolation(f"{_LABEL} response candidate's 'parts' was not a list")
    # Each element is type-checked before anything reads it: a 2xx body
    # like ``{"parts": [null]}`` used to reach ``part.get()`` and raise an
    # uncaught AttributeError, which is outside this port's exception
    # contract -- so the fallback chain stopped on it instead of moving to
    # the next provider (code review finding).
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        raise SchemaViolation(f"{_LABEL} response candidate contained no text part")
    # Gemini may split one JSON document across several text parts; they are
    # concatenated in order, exactly as the API documents, rather than only
    # the first being read (which would truncate a long grading rationale
    # into invalid JSON and report it as a schema violation that the model
    # did not actually commit).
    return "".join(texts)


class VertexGeminiAIProvider:
    """Calls one Gemini model on Vertex AI per ``grade()``."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: str,
        prompt_version: str,
        tokens: AdcTokenSource,
        temperature: float = 0.0,
        location: str = _DEFAULT_LOCATION,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("VertexGeminiAIProvider.model must be a non-blank string")
        if not location.strip():
            raise ValueError("VertexGeminiAIProvider.location must be a non-blank string")
        self._model = model
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._tokens = tokens
        self._endpoint = vertex_generate_content_endpoint(
            location=location.strip(), project_id=tokens.project_id, model=model
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)
        #: The ``modelVersion`` Vertex AI reports for the deployment that
        #: actually answered, recorded into ``ProviderDescriptor.version``
        #: (Issue #14 "再現条件"). Set as soon as a response body is
        #: available and before the response's *content* is validated, so a
        #: schema-violating response is attributed to the same
        #: configuration bucket as the successful calls against it (code
        #: review finding, mirrored from the OpenAI-compatible adapters).
        self._last_model_version: str | None = None

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model=self._model,
            version=self._last_model_version,
            prompt_version=self._prompt_version,
            temperature=self._temperature,
            structured_output_mode=_STRUCTURED_OUTPUT_MODE,
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        # Reset before every attempt so a call that fails before any body
        # is available cannot keep reporting the previous call's deployment
        # (code review finding, mirrored from the OpenAI-compatible
        # adapters).
        self._last_model_version = None

        payload = {
            # The fixed grading rules travel on Vertex's own trusted
            # instruction channel, never mixed into the same message as the
            # student-controlled OCR text/answer image (see `_prompt`).
            "systemInstruction": {"parts": [{"text": GRADING_SYSTEM_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": build_grading_user_content(request)},
                        {
                            "inlineData": {
                                "mimeType": f"image/{sniff_image_format(request.answer_image)}",
                                "data": base64.b64encode(request.answer_image).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": self._temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": strict_ai_grading_result_schema(),
            },
        }

        started_at = time.monotonic()
        try:
            # The token is fetched inside the try: an expired-credential
            # refresh goes over the network too, and AdcCredentialsError is
            # not something callers of this port expect (they only handle
            # SchemaViolation/ProviderUnavailable), so it is classified
            # here alongside the call itself.
            headers = {"Authorization": f"Bearer {self._tokens.bearer_token()}"}
            http_response = self._client.post(self._endpoint, json=payload, headers=headers)
            http_response.raise_for_status()
            data = http_response.json()
        except AdcCredentialsError as exc:
            # An expired refresh token, or a token endpoint that is down,
            # is a *this provider is not reachable right now* failure --
            # not a reason for the whole fallback chain to stop before it
            # has tried Codex/OpenRouter/OpenAI (code review finding: this
            # was raised from inside the `try` above but matched by none of
            # its handlers, so it escaped the port's exception contract).
            # Only the exception type crosses over; `AdcCredentialsError`
            # already carries no token material, and nothing more is added.
            raise ProviderUnavailable(
                f"{_LABEL} credentials are unavailable: {type(exc).__name__}"
            ) from None
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label=_LABEL)
        latency_seconds = time.monotonic() - started_at

        if not isinstance(data, dict):
            raise SchemaViolation(f"{_LABEL} response body was not a JSON object")

        model_version = data.get("modelVersion")
        if isinstance(model_version, str) and model_version.strip():
            self._last_model_version = model_version.strip()

        try:
            parsed_result = parse_ai_grading_result(_response_text(data))
        except ValidationError as exc:
            # Never chain the ValidationError: pydantic keeps the offending
            # field value in `input_value`, and a chained cause's `str()`
            # is printed by Python's default traceback rendering -- which
            # would leak OCR'd student content into logs (AGENTS.md
            # "Security", docs/poc-2-ai-grading.md section 3.7).
            # The *summary* is safe and goes on the exception as
            # `detail` (Issue #121): field paths and pydantic error
            # codes only, never `input_value` -- see
            # `describe_schema_violation`.
            raise SchemaViolation(
                f"{_LABEL} response failed AIGradingResult schema validation",
                detail=describe_schema_violation(exc),
            ) from None

        return grading_response_from_result(
            parsed_result, descriptor=self.describe(), latency_seconds=latency_seconds
        )
