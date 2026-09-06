"""Prompt text and image-format sniffing shared by every ``AIProvider``
adapter in this package (Issue #44) -- kept in one place so OpenRouter and
Codex app-server cannot silently drift onto different wording."""

from __future__ import annotations

from auto_scoring.domain.ai_provider import GradingRequest

_JPEG_MAGIC = b"\xff\xd8\xff"


def sniff_image_format(data: bytes) -> str:
    """Returns ``"jpeg"`` or ``"png"`` (default -- this project's own crop
    pipeline, ``adapters.image.opencv_preprocessor``, writes PNG)."""
    return "jpeg" if data.startswith(_JPEG_MAGIC) else "png"


def build_grading_prompt(request: GradingRequest) -> str:
    return (
        "You are grading one student's answer to a single exam question. "
        "Respond with ONLY a JSON object matching the provided schema -- no "
        "prose, no markdown fences.\n\n"
        f"Question:\n{request.prompt_text}\n\n"
        f"Model answer:\n{request.model_answer}\n\n"
        f"Rubric:\n{request.rubric_text}\n\n"
        f"Max score: {request.max_score}\n\n"
        f"OCR reading of the student's answer (may contain misreadings; the "
        f"attached image is authoritative):\n{request.ocr_text}\n\n"
        f'The questionId in your response must be exactly "{request.question_id}".'
    )
