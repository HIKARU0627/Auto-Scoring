"""``OCRProvider`` adapter over Google Document AI (Issue #114).

The adopted OCR service (business-rules-and-evaluation-data.md section 3 (A),
Issue #81 -- a change from PoC 1's first candidate, Cloud Vision). Until this
adapter existed, ``adapters/ocr/`` held only a placeholder and
``api/sidecar.py`` injected nothing, so every shipped install ran with no OCR
at all (Issue #114).

**Plain REST over httpx, not ``google-cloud-documentai``.** Authentication is
Application Default Credentials -- the project owner's organization policy
forbids API keys outright -- and `adapters.ai_grading._google_adc.
AdcTokenSource` already resolves those for the three Vertex AI callers in
this process. With the credential half solved, ``:process`` is one POST with
a JSON body, so a vendor SDK would add a dependency (and its own transitive
gRPC stack) to save nothing (AGENTS.md "Architecture": a new dependency only
when what is already present cannot meet the requirement). This mirrors what
`adapters.ai_grading.vertex_gemini_provider` already does for Vertex AI.

**What is sent: one answer-area crop, nothing else.** The caller
(`auto_scoring.jobs.recognition_processor.RecognitionJobProcessor`) reads
`domain.models.AnswerImage.image_path`, which is the cropped question region
produced at intake -- never a whole page. That is the rule, not an
implementation detail: simplified-design-specification.md section 26.1.1
splits sending by *purpose*, and reading a student's answer is the "answer
content" row, whose payload is "回答欄の矩形だけ" precisely because a full
page carries the header (name, student id, cram-school and course name).
Sending a page here would leak identifying data on every question of every
answer. `tests/test_document_ai_provider.py` pins that this adapter sends
exactly the bytes it was handed.

**Nothing about the request or the response is ever logged or raised.**
Not the image, not the recognized text, not the processor resource name (a
configuration *value*), not the access token. Exceptions carry an HTTP status
number and an exception class name and nothing else -- the discipline PR #100
established and `api.secret_redaction` backstops.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, NoReturn

import httpx

from auto_scoring.adapters.ai_grading._google_adc import AdcCredentialsError, AdcTokenSource
from auto_scoring.adapters.ai_grading._prompt import sniff_image_format
from auto_scoring.domain.ocr import (
    BoundingBox,
    OCRProviderError,
    OCRRateLimitedError,
    OCRResponseSchemaError,
    OcrResult,
    OCRServerError,
    OCRTimeoutError,
    OcrToken,
    OCRUnavailable,
    band_for,
)

#: Matches `adapters.ai_grading.vertex_gemini_provider`'s own timeout. Not a
#: constructor parameter: nothing overrides it, and a knob no caller turns is
#: one more thing to keep in step for no benefit. Add one when something
#: actually needs a different value.
_TIMEOUT_SECONDS = 120.0
_TOO_MANY_REQUESTS = 429
_SERVER_ERROR_FLOOR = 500

#: Recorded into `domain.ocr.OcrResult.provider` and used in `Job.last_error`
#: through `RecognitionJobProcessor`. A literal written in this repository --
#: never the processor resource name, which is configuration.
PROVIDER_NAME = "document_ai"

#: httpx failures this adapter converts. Same reasoning, and the same trap,
#: as `adapters.ai_grading._http.CONVERTIBLE_HTTP_ERRORS`: catching a hand-
#: picked list of subclasses let `httpx.DecodingError` (a corrupt gzip body)
#: escape, so this catches httpx's own root plus the two decode errors that
#: come from ``Response.json()`` rather than from the request.
_CONVERTIBLE_HTTP_ERRORS = (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError)


class DocumentAiOCRProvider:
    """Recognizes one answer-area crop with a Document AI processor.

    ``processor`` is the full resource name Cloud Console shows,
    ``projects/<p>/locations/<l>/processors/<id>``. One value rather than
    three (project / location / id) because the three have to agree -- a
    processor only exists in the location it was created in -- and splitting
    them just creates a way for an operator to make them disagree
    (Issue #114, decided with the project owner). The location is read back
    out of it here to build the regional host.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        processor: str,
        tokens: AdcTokenSource,
        client: httpx.Client | None = None,
    ) -> None:
        self._processor = processor
        self._location = _location_of(processor)
        self._tokens = tokens
        self._client = client if client is not None else httpx.Client()

    def recognize(self, image: bytes, *, language: str = "ja") -> OcrResult:
        try:
            bearer = self._tokens.bearer_token()
        except AdcCredentialsError as exc:
            # The credentials were there when the factory built this adapter
            # and are not now (an expired login, a revoked session). That is
            # "this host cannot do OCR", not "this call failed": retrying the
            # job cannot install credentials, and section 24 says grading
            # carries on without a reading rather than stopping.
            raise OCRUnavailable(f"ADC is no longer usable ({type(exc).__name__})") from None

        payload: dict[str, Any] = {
            # No human-review step: this project's reviewer is the teacher in
            # front of the app, and enabling Document AI's own would leave a
            # copy of the crop in a Google-side queue (section 26.2: no
            # copies left lying around).
            "skipHumanReview": True,
            "rawDocument": {
                "content": base64.b64encode(image).decode("ascii"),
                "mimeType": f"image/{sniff_image_format(image)}",
            },
            # The port's ``language`` parameter, finally used. Passed as a
            # *hint*, which is all Document AI offers -- and it is passed
            # from inside the adapter so the request shape stays here rather
            # than leaking outward (section 3.1 (A)).
            #
            # **Not measured.** No claim is made that it improves Japanese
            # handwriting recognition; it is the honest translation of the
            # parameter the port already has. Whether it changes anything,
            # and whether every processor type accepts ``processOptions`` at
            # all, are questions only the live probe (Issue #54) can answer
            # -- recorded as open in docs/ocr-recognition-pipeline.md section
            # 8.5.
            "processOptions": {"ocrConfig": {"hints": {"languageHints": [language]}}},
        }

        try:
            response = self._client.post(
                f"https://{self._location}-documentai.googleapis.com/v1/{self._processor}:process",
                headers={"Authorization": f"Bearer {bearer}"},
                json=payload,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            body = response.json()
        except _CONVERTIBLE_HTTP_ERRORS as exc:
            _raise_classified(exc)

        return _to_ocr_result(body)


def _location_of(processor: str) -> str:
    """The ``locations/<l>`` segment of a processor resource name.

    Validated here, at construction, rather than at the first call: a
    malformed value is a configuration mistake an operator can fix now, and
    `adapters.ocr.factory` turns this into "OCR is unavailable, because
    <variable> is not a processor resource name" before the app ever starts.

    The raised message names the *variable*, never the value -- see the
    factory, which is the only caller.
    """
    parts = processor.split("/")
    keywords = parts[0::2]
    values = parts[1::2]
    if len(parts) != 6 or keywords != ["projects", "locations", "processors"] or not all(values):
        raise ValueError("not a Document AI processor resource name")
    return values[1]


def _raise_classified(exc: Exception) -> NoReturn:
    """Re-raise a failed HTTP call as the `OCRProviderError` subclass that
    fits it, so `RecognitionJobProcessor`'s existing retry classification
    (`domain.retry_policy`) applies unchanged.

    Deliberately *not* `adapters.ai_grading._http.raise_classified_unavailable`,
    even though the shape is the same: that one raises
    `domain.ai_provider.ProviderUnavailable` subclasses, which belong to a
    different port. Sharing it would mean one of the two ports importing the
    other's exceptions to classify its own failures.

    Never renders a response body: a Document AI body echoes the recognized
    answer text, and an auth failure's body can quote part of the credential.
    Only the numeric status and the exception class name survive.
    """
    if isinstance(exc, httpx.TimeoutException):
        raise OCRTimeoutError("Document AI timed out") from None
    if isinstance(exc, json.JSONDecodeError | UnicodeDecodeError):
        # A 200 whose body is not decodable JSON at all -- an HTML error page
        # from a proxy, say. That is the same fact as a JSON body in a shape
        # this adapter cannot read, so it gets the same exception
        # (`_to_ocr_result` raises the other half).
        raise OCRResponseSchemaError(
            f"Document AI returned an undecodable response ({type(exc).__name__})"
        ) from None
    status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
    if status == _TOO_MANY_REQUESTS:
        # `status` is only ever non-None (and so only ever able to equal
        # `_TOO_MANY_REQUESTS`) via the `isinstance` branch just above, so
        # `exc` is always an `httpx.HTTPStatusError` here -- spelled out
        # again for mypy, which cannot narrow across the ternary.
        assert isinstance(exc, httpx.HTTPStatusError)
        retry_after = _parse_retry_after_seconds(
            exc.response.headers.get("Retry-After"), now=datetime.now(UTC)
        )
        raise OCRRateLimitedError(
            f"Document AI rate limited the request (HTTP {status})",
            retry_after_seconds=retry_after,
        ) from None
    if status is not None and status >= _SERVER_ERROR_FLOOR:
        raise OCRServerError(f"Document AI returned HTTP {status}") from None
    if status is not None:
        # A 4xx: wrong processor id, API not enabled, no Vertex/Document AI
        # role on the project. Permanent for this queue -- retrying will not
        # fix a misconfiguration -- so it stays a bare `OCRProviderError`,
        # which `RecognitionJobProcessor` maps to `ErrorCategory.PERMANENT`.
        #
        # The number is the whole diagnosis, and it is why it is in the
        # message at all: 401 means the ADC login lapsed, 403 means the API
        # is off or the account lacks the Document AI role, and 404 means the
        # processor id is wrong. Without it all three read as "call failed"
        # (the gap Issue #97 review round 4 found on the grading side).
        raise OCRProviderError(f"Document AI rejected the request (HTTP {status})") from None
    raise OCRProviderError(f"the Document AI call failed ({type(exc).__name__})") from None


def _parse_retry_after_seconds(value: str | None, *, now: datetime) -> float | None:
    """Parse a ``Retry-After`` header value into a non-negative seconds-from-
    ``now`` count, or ``None`` if missing, malformed, or negative (Issue #153).

    Deliberately duplicated from
    `adapters.ai_grading._http.parse_retry_after_seconds` rather than shared,
    for the same reason `_CONVERTIBLE_HTTP_ERRORS` above is duplicated: this
    port and the ``AIProvider`` port are kept from importing each other's
    adapter internals. Handles both RFC 9110 §10.2.3 forms (an integer
    delay-seconds count, or an HTTP-date resolved against ``now``, which the
    caller supplies rather than this function reading the clock itself).
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        return float(int(stripped))
    try:
        parsed = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    delta = (parsed - now).total_seconds()
    return delta if delta >= 0 else None


def _to_ocr_result(body: Any) -> OcrResult:
    """Translate one ``:process`` response into the port's `OcrResult`.

    Every Document AI-specific shape stays inside this function (section 3.1
    (A): "Document AI のレスポンス形式・Bounding Box 座標系への依存は
    ``OCRProvider`` 実装の内側に閉じ、座標変換・後処理へ漏らさない").

    A response that does not have the shape below is an
    `OCRResponseSchemaError`, not a silently empty reading: "the provider
    answered and found no text" and "we could not understand the answer" must
    not collapse into the same result, since only the first one is a real
    recognition.
    """
    try:
        document = body["document"]
        text = str(document.get("text", ""))
        tokens = tuple(
            _to_token(token, text)
            for page in document.get("pages", ())
            for token in page.get("tokens", ())
        )
    except (AttributeError, TypeError, KeyError, ValueError, IndexError) as exc:
        # No value from the body reaches the message -- it would be the
        # recognized answer text.
        raise OCRResponseSchemaError(
            f"Document AI returned an unexpected response shape ({type(exc).__name__})"
        ) from None
    return OcrResult(text=text, tokens=tokens, provider=PROVIDER_NAME)


def _to_token(token: Any, document_text: str) -> OcrToken:
    layout = token["layout"]
    confidence = _unit(float(layout.get("confidence", 0.0)))
    return OcrToken(
        text=_segment_text(layout.get("textAnchor", {}), document_text),
        bounding_box=_to_bounding_box(layout.get("boundingPoly", {})),
        confidence=confidence,
        band=band_for(confidence),
    )


def _segment_text(text_anchor: Any, document_text: str) -> str:
    """The token's own characters, sliced out of ``document.text``.

    Document AI returns the whole page's text once and points every token at
    a span of it. ``startIndex`` is omitted when it is 0, and both indices
    arrive as JSON strings (they are int64 in the protobuf), which is why
    they are parsed rather than used directly.

    Indices are character offsets into ``document.text`` -- the slicing the
    published Document AI samples do. Japanese text is entirely inside the
    BMP, so a code-point slice and a UTF-16 slice agree here; a script that
    needs surrogate pairs would need this revisited.
    """
    spans = text_anchor.get("textSegments", ())
    return "".join(
        document_text[int(span.get("startIndex", 0)) : int(span["endIndex"])] for span in spans
    )


def _to_bounding_box(bounding_poly: Any) -> BoundingBox:
    """The axis-aligned box around Document AI's normalized vertices.

    ``normalizedVertices`` are already 0..1 relative to the image that was
    sent -- which is the answer-area crop, not the page -- so no scaling by a
    page dimension is needed or wanted here.

    A rotated token comes back as four corners of a rotated quadrilateral;
    the port's `domain.ocr.BoundingBox` is axis-aligned, so this takes the
    enclosing rectangle. A vertex's ``x``/``y`` is omitted when it is 0.

    An empty or missing polygon becomes the whole image rather than an
    error: some processors omit the polygon for a token they still read, and
    losing a real reading over a missing box would be the wrong trade.
    """
    vertices = bounding_poly.get("normalizedVertices", ())
    if not vertices:
        return BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)
    xs = [_unit(float(vertex.get("x", 0.0))) for vertex in vertices]
    ys = [_unit(float(vertex.get("y", 0.0))) for vertex in vertices]
    left, top = min(xs), min(ys)
    return BoundingBox(x=left, y=top, width=max(xs) - left, height=max(ys) - top)


def _unit(value: float) -> float:
    """Clamp into 0..1.

    `domain.ocr.BoundingBox` and `OcrToken` both reject anything outside it,
    and a provider is free to return 1.0000000001 for a token touching the
    edge of the crop. Failing a whole question's recognition over a rounding
    error at the boundary would be the wrong trade -- the same defensive
    clamp `jobs.recognition_processor._to_domain_boxes` already applies one
    layer further in.
    """
    return min(1.0, max(0.0, value))
