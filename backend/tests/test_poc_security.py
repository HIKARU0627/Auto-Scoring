"""Security checks for PoC report generation."""

from auto_scoring.domain.ai_provider import (
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
)
from poc.evaluate import _grade_one, render_json
from poc.metrics import HumanLabel, aggregate


class _FailingProvider:
    descriptor = ProviderDescriptor(
        provider="failing",
        model="test",
        version="1",
        temperature=0,
        structured_output_mode="json_schema",
        prompt_id="test-v1",
    )

    def grade(self, request: GradingRequest) -> GradingResponse:
        raise ProviderUnavailable(f"secret-token; answer={request.ocr_text}")


def test_provider_error_details_do_not_reach_report() -> None:
    request = GradingRequest(
        question_id="q",
        question_text="question",
        max_score=5,
        rubric=[{"id": "c1", "description": "criterion", "points": 5}],  # type: ignore[list-item]
        reference_answer="reference",
        ocr_text="student-answer",
    )
    human = HumanLabel(question_id="q", score=4, max_score=5, criteria={"c1": "pass"})
    outcome = _grade_one(_FailingProvider(), request, "case", "clean", human)
    rendered = render_json({"failing": aggregate("failing", [outcome], tolerance_points=1.0)})
    assert outcome.error == "provider_unavailable"
    assert "secret-token" not in rendered
    assert "student-answer" not in rendered
