"""`AnswerAreaDetector` over one image-carrying provider call (Issue #105).

The call itself -- which vendor, how the pages are encoded, how the strict
JSON Schema is sent, and what happens to a response that is not a usable
completion envelope -- is `adapters.ai.image_call`, shared with the
criteria-extraction and classification adapters (Issue #125). What stays here
is the part that is about 回答欄 and nothing else: which prompt and per-test
schema go out, and which parser the answer has to satisfy.

Why an image call and not the whole grading chain: ``codex_app_server`` has
no image input at all, and the page image is the only input detection has
(all 11 measured 生徒答案 PDFs have an empty text layer).
"""

from __future__ import annotations

from auto_scoring.adapters.ai.image_call import ImageJsonCall, parse_or_violate
from auto_scoring.adapters.answer_area_detection._prompt import (
    ANSWER_AREA_SYSTEM_INSTRUCTIONS,
    build_answer_area_user_content,
    strict_answer_area_detection_schema,
)
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

#: The name the OpenAI-compatible ``response_format`` gives this schema.
SCHEMA_NAME = "answer_area_detection"


class StructuredAnswerAreaDetector:
    """Reads one answer sheet's pages per ``detect()``.

    A response that does not satisfy
    :class:`~auto_scoring.domain.answer_area_detection.AnswerAreaDetectionOutput`
    is discarded (`adapters.ai.image_call.discard_response`) -- never turned
    into a partial reading, which would put boxes on a page the model never
    actually placed there.
    """

    def __init__(self, call: ImageJsonCall) -> None:
        self._call = call

    @property
    def name(self) -> str:
        return self._call.provider

    def detect(self, request: AnswerAreaDetectionRequest) -> AnswerAreaDetectionOutput:
        text, _ = self._call.call(
            system=ANSWER_AREA_SYSTEM_INSTRUCTIONS,
            user_text=build_answer_area_user_content(request),
            images=request.page_images,
            schema=strict_answer_area_detection_schema(request.question_numbers),
        )
        return parse_or_violate(
            text,
            lambda body: parse_answer_area_detection(
                body,
                question_numbers=request.question_numbers,
                page_count=len(request.page_images),
                boxes_per_page=[len(boxes) for boxes in request.page_boxes],
            ),
            label=self._call.label,
            schema_name="AnswerAreaDetectionOutput",
        )
