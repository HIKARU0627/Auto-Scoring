"""`CriteriaExtractor` adapters over Vertex AI Gemini and any
OpenAI-compatible ``/chat/completions`` endpoint (Issue #103).

Both send the *page images* of one 採点基準 document plus the strict JSON
Schema from ``_prompt``, and both turn a response that does not satisfy
:class:`~auto_scoring.domain.criteria_extraction.CriteriaExtractionOutput`
into :class:`~auto_scoring.domain.ai_provider.SchemaViolation` -- never into
a best-effort reading. The failure classification, the "never render a
response body" rule, and the exception contract are the ones
``adapters.ai_grading`` already established, and the helpers are shared with
it (``_http``, ``_google_adc``) rather than re-implemented.

Why these two and not the whole grading chain: ``codex_app_server`` has no
image input at all, and every measured subject needs one.

**Nothing here logs, or puts into an exception, any part of the request or
the response.** The pages are a cram school's copyrighted material and carry
teacher and school names (Issue #95 decision 7: sending them to the
configured provider is allowed, publishing them is not). Exceptions carry
HTTP status codes and exception type names only.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading._http import (
    CONVERTIBLE_HTTP_ERRORS,
    raise_classified_unavailable,
)
from auto_scoring.adapters.criteria_extraction._prompt import (
    CRITERIA_SYSTEM_INSTRUCTIONS,
    build_criteria_user_content,
    sniff_image_format,
    strict_criteria_extraction_schema,
)
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.criteria_extraction import (
    CriteriaExtractionOutput,
    CriteriaExtractionRequest,
    parse_criteria_extraction,
)

#: Longer than the grading adapters' 120s: a criteria document is up to
#: several full pages of dense Japanese read in one call, where a grading
#: call reads one cropped answer. Measured material runs 1-8 pages.
DEFAULT_TIMEOUT_SECONDS = 300.0

_VERTEX_DEFAULT_LOCATION = "global"


def _vertex_endpoint(*, location: str, project_id: str, model: str) -> str:
    """The ``generateContent`` URL for one model. The ``global`` location has
    no region prefix; every regional one prefixes the host."""
    host = "aiplatform.googleapis.com"
    if location != "global":
        host = f"{location}-{host}"
    return (
        f"https://{host}/v1/projects/{project_id}/locations/{location}"
        f"/publishers/google/models/{model}:generateContent"
    )


def _parse_or_violate(text: str, *, label: str) -> CriteriaExtractionOutput:
    """Validate one response body, or raise `SchemaViolation`.

    Never chains the ``ValidationError``: pydantic keeps the offending value
    in ``input_value``, and Python prints a chained cause's ``str()`` -- which
    would put the school's material into a log (AGENTS.md "Security", the
    same rule ``ai_grading``'s adapters follow).
    """
    try:
        return parse_criteria_extraction(text)
    except ValidationError:
        raise SchemaViolation(
            f"{label} response failed CriteriaExtractionOutput schema validation"
        ) from None


class VertexGeminiCriteriaExtractor:
    """Reads one criteria document per ``extract()`` with Gemini on Vertex AI.

    Vertex AI, not the Gemini Developer API -- this project's Google Cloud
    organization policy forbids the API-key product, so authentication is
    Application Default Credentials (``_google_adc``), the same as
    ``adapters.ai_grading.vertex_gemini_provider``.
    """

    name = "gemini"

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
            raise ValueError("VertexGeminiCriteriaExtractor.model must be a non-blank string")
        if not location.strip():
            raise ValueError("VertexGeminiCriteriaExtractor.location must be a non-blank string")
        self._model = model
        self._temperature = temperature
        self._tokens = tokens
        self._endpoint = _vertex_endpoint(
            location=location.strip(), project_id=tokens.project_id, model=model
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        parts: list[dict[str, Any]] = [{"text": build_criteria_user_content(request)}]
        parts.extend(
            {
                "inlineData": {
                    "mimeType": f"image/{sniff_image_format(image)}",
                    "data": base64.b64encode(image).decode("ascii"),
                }
            }
            for image in request.page_images
        )
        payload = {
            # The extraction rules travel on Vertex's own trusted
            # instruction channel, never mixed into the same message as the
            # document being read (see `_prompt`).
            "systemInstruction": {"parts": [{"text": CRITERIA_SYSTEM_INSTRUCTIONS}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": self._temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": strict_criteria_extraction_schema(),
            },
        }

        try:
            # The token is fetched inside the try for the same reason the
            # grading adapter does it: a credential refresh is itself a
            # network call, and `AdcCredentialsError` is not part of this
            # port's exception contract.
            headers = {"Authorization": f"Bearer {self._tokens.bearer_token()}"}
            http_response = self._client.post(self._endpoint, json=payload, headers=headers)
            http_response.raise_for_status()
            data = http_response.json()
        except AdcCredentialsError as exc:
            raise ProviderUnavailable(
                f"Vertex AI credentials are unavailable: {type(exc).__name__}"
            ) from None
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label="Vertex AI")

        if not isinstance(data, dict):
            raise SchemaViolation("Vertex AI response body was not a JSON object")
        return _parse_or_violate(_vertex_response_text(data), label="Vertex AI")


def _vertex_response_text(data: dict[str, Any]) -> str:
    """The concatenated text parts of a ``generateContent`` response.

    A 2xx body that is not a completed text candidate (a safety block, a
    truncation, a changed response shape) is a `SchemaViolation` and not
    `ProviderUnavailable`: the call itself succeeded, so retrying reproduces
    it -- the same classification ``ai_grading.vertex_gemini_provider`` makes.
    """
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise SchemaViolation(
            "Vertex AI response did not contain a completed text candidate"
        ) from None
    if not isinstance(parts, list):
        raise SchemaViolation("Vertex AI response candidate's 'parts' was not a list")
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        raise SchemaViolation("Vertex AI response candidate contained no text part")
    # Gemini may split one JSON document across several parts; concatenated
    # in order, or a long extraction would be truncated into invalid JSON
    # and reported as a violation the model never committed.
    return "".join(texts)


class ChatCompletionsCriteriaExtractor:
    """Reads one criteria document per ``extract()`` over an
    OpenAI-compatible ``/chat/completions`` endpoint.

    Covers both remaining image-capable transports: ``name`` and the
    per-request ``extra_payload`` (OpenAI's ``store: false``, OpenRouter's
    zero-data-retention routing preference) are supplied by the factory, the
    same split ``adapters.ai_grading._openai_chat`` uses.
    """

    def __init__(
        self,
        *,
        name: str,
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
            raise ValueError("ChatCompletionsCriteriaExtractor.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError("ChatCompletionsCriteriaExtractor.model must be a non-blank string")
        self.name = name
        self._model = model
        self._temperature = temperature
        self._label = label
        self._extra_payload = extra_payload
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": build_criteria_user_content(request)}
        ]
        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        f"data:image/{sniff_image_format(image)};base64,"
                        f"{base64.b64encode(image).decode('ascii')}"
                    )
                },
            }
            for image in request.page_images
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "criteria_extraction",
                    "strict": True,
                    "schema": strict_criteria_extraction_schema(),
                },
            },
            "messages": [
                {"role": "system", "content": CRITERIA_SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": content},
            ],
            **self._extra_payload,
        }

        try:
            http_response = self._client.post("/chat/completions", json=payload)
            http_response.raise_for_status()
            data = http_response.json()
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label=self._label)

        if not isinstance(data, dict):
            raise SchemaViolation(f"{self._label} response body was not a JSON object")
        try:
            message = data["choices"][0]["message"]["content"]
            if not isinstance(message, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            raise SchemaViolation(
                f"{self._label} response did not contain a chat completion message"
            ) from None
        return _parse_or_violate(message, label=self._label)


class UnconfiguredCriteriaExtractor:
    """`CriteriaExtractor` for a host where no image-capable transport could
    be built.

    Raises rather than answering, for the reason
    ``adapters.ai.unconfigured_provider`` documents at length: an extractor
    that returned an empty result would be indistinguishable, on screen,
    from a document a real model read and found nothing in -- and this
    screen's whole job is to make "could not read this" visible.

    :attr:`reason` is published (the extract endpoint returns it and the app
    shows it), so it names configuration *variables* and host prerequisites
    only, never their values.
    """

    name = "unconfigured"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    @property
    def reason(self) -> str:
        return self._reason

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        raise ProviderUnavailable(
            f"採点基準の抽出に使える AI provider が設定されていません: {self._reason}"
        )
