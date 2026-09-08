"""`AnswerAreaDetector` adapters over Vertex AI Gemini and any
OpenAI-compatible ``/chat/completions`` endpoint (Issue #105).

Both send the *page images* of one answer sheet plus the per-test JSON Schema
from ``_prompt``, and both turn a response that does not satisfy
:class:`~auto_scoring.domain.answer_area_detection.AnswerAreaDetectionOutput`
into :class:`~auto_scoring.domain.ai_provider.SchemaViolation` -- never into a
best-effort reading. The failure classification, the "never render a response
body" rule, and the exception contract are the ones ``adapters.ai_grading``
already established, and its helpers (``_http``, ``_google_adc``) are reused
rather than re-implemented.

Why these two and not the whole grading chain: ``codex_app_server`` has no
image input at all, and the page image is the only input detection has.

**Nothing here logs, or puts into an exception, any part of the request or
the response.** The pages are a cram school's copyrighted material and carry
teacher and school names, printed dates, QR codes, and whatever the student
wrote by hand -- including a name, if they wrote one (Issue #95 decision 7:
sending them to the configured provider is allowed, publishing them is not).
Exceptions carry HTTP status codes and exception type names only.
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
from auto_scoring.adapters.answer_area_detection._prompt import (
    ANSWER_AREA_SYSTEM_INSTRUCTIONS,
    build_answer_area_user_content,
    sniff_image_format,
    strict_answer_area_detection_schema,
)
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation
from auto_scoring.domain.answer_area_detection import (
    AnswerAreaDetectionOutput,
    AnswerAreaDetectionRequest,
    parse_answer_area_detection,
)

#: Matches the criteria extractor's own timeout rather than the grading
#: adapters' 120s: this is one call carrying every page of a sheet, started
#: by a person watching a screen, where a grading call carries one cropped
#: answer. Measured sheets run 1-3 pages.
DEFAULT_TIMEOUT_SECONDS = 300.0

_VERTEX_DEFAULT_LOCATION = "global"


def _parse_or_violate(
    text: str, *, request: AnswerAreaDetectionRequest, label: str
) -> AnswerAreaDetectionOutput:
    """Validate one response body, or raise `SchemaViolation`.

    Never chains the ``ValidationError``: pydantic keeps the offending value
    in ``input_value``, and Python prints a chained cause's ``str()`` -- which
    would put the school's material into a log (AGENTS.md "Security", the
    same rule ``ai_grading``'s and ``criteria_extraction``'s adapters follow).
    """
    try:
        return parse_answer_area_detection(
            text,
            question_numbers=request.question_numbers,
            page_count=len(request.page_images),
        )
    except ValidationError:
        raise SchemaViolation(
            f"{label} response failed AnswerAreaDetectionOutput schema validation"
        ) from None


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


def _vertex_response_text(data: dict[str, Any], *, label: str) -> str:
    """The text parts of a ``generateContent`` response, concatenated.

    Mirrors ``adapters.ai_grading.vertex_gemini_provider._response_text``,
    including why a malformed 2xx body is a `SchemaViolation` and not a
    `ProviderUnavailable`: the call itself succeeded, so retrying reproduces
    it. Gemini may split one JSON document across several text parts, so they
    are joined in order rather than only the first being read.
    """
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise SchemaViolation(f"{label} response did not contain a completed text candidate") from (
            None
        )
    if not isinstance(parts, list):
        raise SchemaViolation(f"{label} response candidate's 'parts' was not a list")
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        raise SchemaViolation(f"{label} response candidate contained no text part")
    return "".join(texts)


class VertexGeminiAnswerAreaDetector:
    """Calls one Gemini model on Vertex AI per ``detect()``."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: str,
        tokens: AdcTokenSource,
        location: str = _VERTEX_DEFAULT_LOCATION,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("VertexGeminiAnswerAreaDetector.model must be a non-blank string")
        if not location.strip():
            raise ValueError("VertexGeminiAnswerAreaDetector.location must be a non-blank string")
        self._label = "Vertex AI"
        self._tokens = tokens
        self._endpoint = _vertex_endpoint(
            location=location.strip(), project_id=tokens.project_id, model=model
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        payload = {
            # The fixed rules travel on Vertex's own trusted instruction
            # channel, never mixed into the same message as the scanned pages
            # (whose printed and handwritten content this app does not
            # control -- see `_prompt` rule 9).
            "systemInstruction": {"parts": [{"text": ANSWER_AREA_SYSTEM_INSTRUCTIONS}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": build_answer_area_user_content(request)},
                        *(
                            {
                                "inlineData": {
                                    "mimeType": f"image/{sniff_image_format(image)}",
                                    "data": base64.b64encode(image).decode("ascii"),
                                }
                            }
                            for image in request.page_images
                        ),
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "responseJsonSchema": strict_answer_area_detection_schema(request.question_numbers),
            },
        }

        try:
            # The token is fetched inside the try for the same reason
            # `vertex_gemini_provider` does it: a refresh goes over the
            # network too, and `AdcCredentialsError` is outside this port's
            # exception contract.
            headers = {"Authorization": f"Bearer {self._tokens.bearer_token()}"}
            http_response = self._client.post(self._endpoint, json=payload, headers=headers)
            http_response.raise_for_status()
            data = http_response.json()
        except AdcCredentialsError as exc:
            raise ProviderUnavailable(
                f"{self._label} credentials are unavailable: {type(exc).__name__}"
            ) from None
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label=self._label)

        if not isinstance(data, dict):
            raise SchemaViolation(f"{self._label} response body was not a JSON object")
        return _parse_or_violate(
            _vertex_response_text(data, label=self._label), request=request, label=self._label
        )


class ChatCompletionsAnswerAreaDetector:
    """`AnswerAreaDetector` over an OpenAI-compatible ``/chat/completions``
    endpoint (OpenRouter, OpenAI).

    One class for both, as ``adapters.ai_grading._openai_chat`` already
    concluded: the two differ only in base URL, the vendor-specific retention
    field, the provider id and the error label.
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
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ChatCompletionsAnswerAreaDetector.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError("ChatCompletionsAnswerAreaDetector.model must be a non-blank string")
        self.name = name
        self._model = model
        self._label = label
        self._extra_payload = extra_payload
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "answer_area_detection",
                    "strict": True,
                    "schema": strict_answer_area_detection_schema(request.question_numbers),
                },
            },
            "messages": [
                {"role": "system", "content": ANSWER_AREA_SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_answer_area_user_content(request)},
                        *(
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
                        ),
                    ],
                },
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
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            # A 2xx body with valid JSON but no completion envelope (a
            # refusal, a changed response shape) is a malformed structured
            # response, not a transport failure -- the same call would fail
            # the same way on retry.
            raise SchemaViolation(
                f"{self._label} response did not contain a chat completion message"
            ) from None
        return _parse_or_violate(content, request=request, label=self._label)
