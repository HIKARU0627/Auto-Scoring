"""The two transports a classification call can go over (Issue #101).

Classification asks a much smaller question than grading -- one page image
in, one enum value out -- but it needs the same two things every grading
adapter needs: an authenticated request carrying an image, and a
structured-output constraint the model must answer inside. Rather than
duplicating `adapters.ai_grading`'s adapters (whose payloads are built
around `GradingRequest` and whose response schema is `AIGradingResult`),
this module reduces both transports to one narrow port -- "send a system
instruction, some text, an image and a JSON schema; give me back the JSON
text" -- so `classifier.py` holds the prompt and parsing logic exactly once.

Failure classification, credential handling and the "never log a payload or
a response body" rule are all reused verbatim from `adapters.ai_grading`
rather than re-derived: `_http.raise_classified_unavailable`,
`_google_adc.AdcTokenSource`, `_prompt.sniff_image_format`.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol

import httpx

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading._http import (
    CONVERTIBLE_HTTP_ERRORS,
    raise_classified_unavailable,
)
from auto_scoring.adapters.ai_grading._prompt import sniff_image_format
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import (
    vertex_generate_content_endpoint,
)
from auto_scoring.domain.ai_provider import (
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
)

#: Classification is a single-token-ish answer over one image, so it is far
#: quicker than a grading call -- but a batch runs one call per file, and a
#: reviewer is watching a progress line while it does. A shorter ceiling
#: than grading's keeps one stuck request from stalling the whole run.
DEFAULT_TIMEOUT_SECONDS = 60.0

_STRUCTURED_OUTPUT_MODE = "json_schema"
_VERTEX_DEFAULT_LOCATION = "global"


class StructuredJsonCall(Protocol):
    """One provider round trip that must answer inside ``schema``."""

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def call(
        self, *, system: str, user_text: str, image: bytes, schema: dict[str, Any]
    ) -> tuple[str, str | None]:
        """Return ``(json_text, route_version)``.

        Raises ``SchemaViolation`` when the response is 2xx but not a usable
        completion envelope, and ``ProviderUnavailable`` (or a subclass) when
        the provider could not be reached.
        """
        ...


def _descriptor(
    call: StructuredJsonCall, *, prompt_version: str, temperature: float, version: str | None
) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider=call.provider,
        model=call.model,
        version=version,
        prompt_version=prompt_version,
        temperature=temperature,
        structured_output_mode=_STRUCTURED_OUTPUT_MODE,
    )


class ChatCompletionsJsonCall:
    """OpenAI-compatible ``/chat/completions`` (OpenRouter, OpenAI)."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        label: str,
        extra_payload: dict[str, Any],
        temperature: float = 0.0,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ChatCompletionsJsonCall.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError("ChatCompletionsJsonCall.model must be a non-blank string")
        self._provider = provider
        self._model = model
        self._label = label
        self._temperature = temperature
        self._extra_payload = extra_payload
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def call(
        self, *, system: str, user_text: str, image: bytes, schema: dict[str, Any]
    ) -> tuple[str, str | None]:
        image_data_url = (
            f"data:image/{sniff_image_format(image)};base64,"
            f"{base64.b64encode(image).decode('ascii')}"
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "classification", "strict": True, "schema": schema},
            },
            "messages": [
                # The fixed instructions travel as the system message, never
                # mixed into the same message as the page image -- the page
                # is material to look at, not a source of instructions
                # (mirrors `ai_grading._prompt`'s own separation).
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                },
            ],
            **self._extra_payload,
        }
        try:
            response = self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label=self._label)

        if not isinstance(data, dict):
            raise SchemaViolation(f"{self._label} response body was not a JSON object")
        route = data.get("model")
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            raise SchemaViolation(
                f"{self._label} response did not contain a chat completion message"
            ) from None
        return content, route if isinstance(route, str) and route.strip() else None


class VertexGeminiJsonCall:
    """Gemini on Vertex AI, authenticated with ADC.

    Same product and same auth path as the grading adapter -- see
    `adapters.ai_grading.vertex_gemini_provider` for why it is Vertex rather
    than the Gemini Developer API, and why no project id lives in this
    repository.
    """

    provider = "gemini"

    def __init__(
        self,
        *,
        model: str,
        tokens: AdcTokenSource,
        temperature: float = 0.0,
        location: str = _VERTEX_DEFAULT_LOCATION,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("VertexGeminiJsonCall.model must be a non-blank string")
        self._model = model
        self._tokens = tokens
        self._temperature = temperature
        # The URL shape (regional host prefix, `global`'s lack of one) lives
        # in one place; duplicating it here would be free to drift from the
        # grading adapter that talks to the same deployment.
        self._endpoint = vertex_generate_content_endpoint(
            location=location.strip(), project_id=tokens.project_id, model=model
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def model(self) -> str:
        return self._model

    def call(
        self, *, system: str, user_text: str, image: bytes, schema: dict[str, Any]
    ) -> tuple[str, str | None]:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_text},
                        {
                            "inlineData": {
                                "mimeType": f"image/{sniff_image_format(image)}",
                                "data": base64.b64encode(image).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": self._temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        try:
            headers = {"Authorization": f"Bearer {self._tokens.bearer_token()}"}
            response = self._client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except AdcCredentialsError as exc:
            # Only the exception type crosses over: `AdcCredentialsError`
            # carries no token material and nothing more is added (mirrors
            # the grading adapter).
            raise ProviderUnavailable(
                f"Vertex AI credentials are unavailable: {type(exc).__name__}"
            ) from None
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label="Vertex AI")

        if not isinstance(data, dict):
            raise SchemaViolation("Vertex AI response body was not a JSON object")
        model_version = data.get("modelVersion")
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            raise SchemaViolation("Vertex AI response did not contain a text candidate") from None
        if not isinstance(parts, list):
            raise SchemaViolation("Vertex AI response candidate's 'parts' was not a list")
        texts = [
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if not texts:
            raise SchemaViolation("Vertex AI response candidate contained no text part")
        # Gemini may split one JSON document across several text parts; they
        # are concatenated in order, exactly as the API documents.
        return (
            "".join(texts),
            model_version.strip()
            if isinstance(model_version, str) and model_version.strip()
            else None,
        )


def parse_json_object(text: str, *, label: str) -> dict[str, Any]:
    """Parse a provider's structured answer, or raise :class:`SchemaViolation`.

    The raised message never quotes the text: a classification response can
    echo the page it looked at, which is the school's material.
    """
    try:
        parsed = json.loads(text)
    except ValueError:
        raise SchemaViolation(f"{label} response was not valid JSON") from None
    if not isinstance(parsed, dict):
        raise SchemaViolation(f"{label} response was not a JSON object")
    return parsed


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "ChatCompletionsJsonCall",
    "StructuredJsonCall",
    "VertexGeminiJsonCall",
    "_descriptor",
    "parse_json_object",
]
