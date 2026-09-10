"""`CriteriaExtractor` over one image-carrying provider call (Issue #103).

The call itself -- which vendor, how the pages are encoded, how the strict
JSON Schema is sent, and what happens to a response that is not a usable
completion envelope -- is `adapters.ai.image_call`, shared with the
answer-area and classification adapters (Issue #125). What stays here is the
part that is about 採点基準 and nothing else: which prompt and schema go out,
and which parser the answer has to satisfy.

Why an image call and not the whole grading chain: ``codex_app_server`` has
no image input at all, and 6 of the 11 measured criteria documents have no
text layer.
"""

from __future__ import annotations

from auto_scoring.adapters.ai.image_call import ImageJsonCall, parse_or_violate
from auto_scoring.adapters.criteria_extraction._prompt import (
    CRITERIA_SYSTEM_INSTRUCTIONS,
    build_criteria_user_content,
    strict_criteria_extraction_schema,
)
from auto_scoring.domain.ai_provider import ProviderUnavailable
from auto_scoring.domain.criteria_extraction import (
    CriteriaExtractionOutput,
    CriteriaExtractionRequest,
    parse_criteria_extraction,
)

#: Longer than the grading adapters' 120s: a criteria document is up to
#: several full pages of dense Japanese read in one call, where a grading
#: call reads one cropped answer. Measured material runs 1-8 pages.
DEFAULT_TIMEOUT_SECONDS = 300.0

#: The name the OpenAI-compatible ``response_format`` gives this schema.
SCHEMA_NAME = "criteria_extraction"


class StructuredCriteriaExtractor:
    """Reads one 採点基準 document per ``extract()``.

    A response that does not satisfy
    :class:`~auto_scoring.domain.criteria_extraction.CriteriaExtractionOutput`
    is discarded (`adapters.ai.image_call.discard_response`) -- never turned
    into a best-effort reading, which is what would put an invented 配点 in
    front of a teacher (Issue #103 acceptance 6).
    """

    def __init__(self, call: ImageJsonCall) -> None:
        self._call = call

    @property
    def name(self) -> str:
        return self._call.provider

    def extract(self, request: CriteriaExtractionRequest) -> CriteriaExtractionOutput:
        text, _ = self._call.call(
            system=CRITERIA_SYSTEM_INSTRUCTIONS,
            user_text=build_criteria_user_content(request),
            images=request.page_images,
            schema=strict_criteria_extraction_schema(),
        )
        return parse_or_violate(
            text,
            parse_criteria_extraction,
            label=self._call.label,
            schema_name="CriteriaExtractionOutput",
        )


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
