"""One image-carrying, JSON-Schema-constrained provider call, shared by every
adapter that makes one (Issue #125).

Three adapters -- 採点基準の抽出 (`adapters.criteria_extraction`), 回答欄の検出
(`adapters.answer_area_detection`) and 資料の分類
(`adapters.ai_classification`) -- ask the same thing of a provider:

    send some page images and a strict JSON Schema, once; give back the JSON
    text the model answered with, and discard a response that is not one.

Until this module they each wrote that out for themselves, twice over (Vertex
AI and OpenAI-compatible), which is why Issue #125 exists: a defect in that
shape -- Issue #121's "one over-long string throws away the whole response"
is the worked example -- had to be found and fixed three times, and finding
it the second and third time meant knowing the other two copies existed.

**What is here and what is not.** Here: the payload envelope, the image
encoding, the strict-schema field each vendor reads, the response envelope,
and :func:`discard_response` -- the one place a response is thrown away.
Not here: the prompts, the schemas and the parsers, which are what the three
adapters actually differ in and which stay in their own packages (Issue #125
"やらないこと").

**Nothing here logs, or puts into an exception, any part of the request or
the response.** The images are a cram school's copyrighted material and
carry teacher names, school names and a student's handwriting (Issue #95
decision 7: sending them to the configured provider is allowed, publishing
them is not). Exceptions carry HTTP status codes, fixed labels and exception
type names only.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Sequence
from typing import Any, NoReturn, Protocol

import httpx
from pydantic import ValidationError

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading._http import (
    CONVERTIBLE_HTTP_ERRORS,
    raise_classified_unavailable,
)
from auto_scoring.adapters.ai_grading._prompt import sniff_image_format
from auto_scoring.adapters.ai_grading.vertex_gemini_provider import (
    vertex_generate_content_endpoint,
)
from auto_scoring.domain.ai_provider import ProviderUnavailable, SchemaViolation

_VERTEX_DEFAULT_LOCATION = "global"


def discard_response(label: str, because: str) -> NoReturn:
    """Throw one provider response away whole, as a `SchemaViolation`.

    **The single place these three adapters decide a response cannot be
    believed** (Issue #125 acceptance 2). Issue #121 is what that is worth: a
    live run returned complete (``finishReason: STOP``) grading responses
    whose score, criterion ids and question id were all correct, and every
    one of them was discarded because one annotation comment ran 147
    characters against a 120 cap. The grading schema now cuts the comment
    instead (`domain.ai_grading`); the same input shape still reaches these
    three, and when that is revisited it is revisited once, here, rather than
    in three copies of the same ``raise``.

    ``label`` and ``because`` are fixed strings written in this repository --
    a vendor name and a reason -- never anything read out of the request or
    the response.

    ``from None`` throughout: pydantic keeps the offending value in the
    ``ValidationError``'s ``input_value`` and Python renders a chained
    cause's own ``str()``, which would put the school's material into the
    sidecar log (AGENTS.md "Security").
    """
    raise SchemaViolation(f"{label} {because}") from None


def parse_or_violate[T](text: str, parse: Callable[[str], T], *, label: str, schema_name: str) -> T:
    """Validate one response body against an adapter's own schema, or
    :func:`discard_response`.

    ``parse`` is the adapter's parser -- `domain.criteria_extraction
    .parse_criteria_extraction`, `domain.answer_area_detection
    .parse_answer_area_detection` -- so what a response has to satisfy stays
    with the adapter that asked for it, while what happens when it does not
    is decided here.
    """
    try:
        return parse(text)
    except ValidationError:
        discard_response(label, f"response failed {schema_name} schema validation")


class ImageJsonCall(Protocol):
    """One provider round trip carrying page images that must answer inside
    ``schema``."""

    @property
    def provider(self) -> str:
        """The transport id (``"gemini"``, ``"openrouter"``, ``"openai"``)."""

    @property
    def model(self) -> str: ...

    @property
    def label(self) -> str:
        """The vendor name an exception message may carry (``"Vertex AI"``)."""

    def call(
        self,
        *,
        system: str,
        user_text: str,
        images: Sequence[bytes],
        schema: dict[str, Any],
    ) -> tuple[str, str | None]:
        """Return ``(json_text, route_version)``.

        Raises ``SchemaViolation`` when the response is 2xx but not a usable
        completion envelope, and ``ProviderUnavailable`` (or a subclass) when
        the provider could not be reached.
        """
        ...


class ChatCompletionsImageCall:
    """OpenAI-compatible ``/chat/completions`` (OpenRouter, OpenAI).

    One class for both, as ``adapters.ai_grading._openai_chat`` already
    concluded for grading: the two differ only in base URL, the
    vendor-specific retention field, the provider id and the error label --
    all supplied by the caller's factory.
    """

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        label: str,
        schema_name: str,
        extra_payload: dict[str, Any],
        temperature: float,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("ChatCompletionsImageCall.api_key must be a non-blank string")
        if not model.strip():
            raise ValueError("ChatCompletionsImageCall.model must be a non-blank string")
        self._provider = provider
        self._model = model
        self._label = label
        self._schema_name = schema_name
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

    @property
    def label(self) -> str:
        return self._label

    def call(
        self,
        *,
        system: str,
        user_text: str,
        images: Sequence[bytes],
        schema: dict[str, Any],
    ) -> tuple[str, str | None]:
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": self._schema_name, "strict": True, "schema": schema},
            },
            "messages": [
                # The fixed instructions travel as the system message, never
                # mixed into the same message as the pages -- a scanned page
                # is material to examine, not a source of instructions, and
                # this app controls neither what is printed on it nor what
                # the student wrote (AGENTS.md "Security").
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        *(
                            {"type": "image_url", "image_url": {"url": _data_url(image)}}
                            for image in images
                        ),
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
            discard_response(self._label, "response body was not a JSON object")
        route = data.get("model")
        try:
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError("choices[0].message.content must be a string")
        except (KeyError, IndexError, TypeError):
            # A 2xx body with valid JSON but no completion envelope (a
            # refusal, a changed response shape) is a malformed structured
            # response, not a transport failure -- the same call would fail
            # the same way on retry.
            discard_response(self._label, "response did not contain a chat completion message")
        return content, route if isinstance(route, str) and route.strip() else None


class VertexGeminiImageCall:
    """Gemini on Vertex AI, authenticated with Application Default
    Credentials.

    Vertex AI and not the Gemini Developer API, for the reason
    ``adapters.ai_grading.vertex_gemini_provider`` records: this project's
    Google Cloud organization policy blocks the API-key product.
    """

    provider = "gemini"
    label = "Vertex AI"

    def __init__(
        self,
        *,
        model: str,
        tokens: AdcTokenSource,
        temperature: float,
        timeout_seconds: float,
        location: str = _VERTEX_DEFAULT_LOCATION,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("VertexGeminiImageCall.model must be a non-blank string")
        if not location.strip():
            raise ValueError("VertexGeminiImageCall.location must be a non-blank string")
        self._model = model
        self._tokens = tokens
        self._temperature = temperature
        # The URL shape (regional host prefix, `global`'s lack of one) lives
        # in one place; a copy here would be free to drift from the grading
        # adapter that talks to the same deployment.
        self._endpoint = vertex_generate_content_endpoint(
            location=location.strip(), project_id=tokens.project_id, model=model
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def model(self) -> str:
        return self._model

    def call(
        self,
        *,
        system: str,
        user_text: str,
        images: Sequence[bytes],
        schema: dict[str, Any],
    ) -> tuple[str, str | None]:
        payload = {
            # The fixed rules travel on Vertex's own trusted instruction
            # channel -- same separation, same reason, as the chat call.
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_text},
                        *(
                            {
                                "inlineData": {
                                    "mimeType": f"image/{sniff_image_format(image)}",
                                    "data": _b64(image),
                                }
                            }
                            for image in images
                        ),
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
            # The token is fetched inside the try because a credential
            # refresh is itself a network call, and `AdcCredentialsError` is
            # not part of any of these ports' exception contracts.
            headers = {"Authorization": f"Bearer {self._tokens.bearer_token()}"}
            response = self._client.post(self._endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        except AdcCredentialsError as exc:
            # Only the exception type crosses over: `AdcCredentialsError`
            # carries no token material and nothing more is added.
            raise ProviderUnavailable(
                f"{self.label} credentials are unavailable: {type(exc).__name__}"
            ) from None
        except CONVERTIBLE_HTTP_ERRORS as exc:
            raise_classified_unavailable(exc, label=self.label)

        if not isinstance(data, dict):
            discard_response(self.label, "response body was not a JSON object")
        model_version = data.get("modelVersion")
        return _vertex_text(data), (
            model_version.strip()
            if isinstance(model_version, str) and model_version.strip()
            else None
        )


def _vertex_text(data: dict[str, Any]) -> str:
    """The text parts of a ``generateContent`` response, concatenated.

    A 2xx body that is not a completed text candidate (a safety block, a
    truncation, a changed response shape) is discarded rather than reported
    as `ProviderUnavailable`: the call itself succeeded, so retrying
    reproduces it -- the classification
    ``docs/ai-grading-pipeline.md`` "どの失敗で次へ落とすか" makes.
    """
    label = VertexGeminiImageCall.label
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        discard_response(label, "response did not contain a completed text candidate")
    if not isinstance(parts, list):
        discard_response(label, "response candidate's 'parts' was not a list")
    # Each element is type-checked before anything reads it: a 2xx body like
    # ``{"parts": [null]}`` would otherwise reach ``part.get()`` and raise an
    # uncaught AttributeError, outside every one of these ports' exception
    # contracts.
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    if not texts:
        discard_response(label, "response candidate contained no text part")
    # Gemini may split one JSON document across several text parts; they are
    # concatenated in order, exactly as the API documents, rather than only
    # the first being read -- which would truncate a long answer into invalid
    # JSON and report a violation the model never committed.
    return "".join(texts)


def _b64(image: bytes) -> str:
    return base64.b64encode(image).decode("ascii")


def _data_url(image: bytes) -> str:
    return f"data:image/{sniff_image_format(image)};base64,{_b64(image)}"
