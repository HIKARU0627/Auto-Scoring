"""Placeholder ``AIProvider`` used until the chosen provider chain is wired up.

business-rules-and-evaluation-data.md section 3 (B): the project owner chose
an **ordered fallback chain** (Gemini API -> Codex App Server -> OpenRouter ->
OpenAI API; Issue #81), not a single vendor. Two of the four have adapters
(Issue #44, `adapters/ai_grading/`), the composite that tries them in order
does not exist yet, and no chain is wired into `create_app` (docs/ai-grading-
pipeline.md "AIモデル: 優先度つきフォールバック"; live probe in Issue #54).

Mirrors `auto_scoring.adapters.ocr.null_provider.NullOCRProvider`: rather
than raising (which `GradingJobProcessor` would have to guess a retry
category for) or fabricating a plausible-looking grade, this always reports
the question as ungraded, at confidence 0.0. That is honest about not being
configured yet, and it composes correctly with the "needs_review, never
auto-confirm" rule (Issue #20 acceptance) by construction -- every question
routes to manual review until a real adapter is injected via
``create_app(ai_provider=...)``.
"""

from __future__ import annotations

from auto_scoring.domain.ai_provider import GradingRequest, GradingResponse, ProviderDescriptor

#: Honest, non-fabricated placeholder text: never a guessed reading, score,
#: or rationale (AGENTS.md "Verification" / Issue #20 acceptance: "読めない
#: 文字や判断不能を推測で補完せず、要確認理由を返す").
_NOT_CONFIGURED_MESSAGE = "AIプロバイダが未設定のため採点していません。"


class NullAIProvider:
    """Always reports "not graded, confidence 0.0"; never calls a network."""

    name = "null"

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider=self.name,
            model="null",
            version=None,
            prompt_version="v0",
            temperature=0.0,
            structured_output_mode="none",
        )

    def grade(self, request: GradingRequest) -> GradingResponse:
        return GradingResponse(
            question_id=request.question_id,
            recognition_text="",
            recognition_confidence=0.0,
            score=0,
            max_score=request.max_score,
            grading_confidence=0.0,
            rationale=_NOT_CONFIGURED_MESSAGE,
            comment=_NOT_CONFIGURED_MESSAGE,
            criteria=(),
            annotations=(),
            descriptor=self.describe(),
            latency_seconds=0.0,
        )
