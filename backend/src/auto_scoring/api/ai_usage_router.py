"""AI token usage and optional cost endpoints (Issue #187)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local.grading_cost_store import GradingCostStore
from auto_scoring.adapters.local.intake_template_store import IntakeTemplateError
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.ai_usage import (
    AiUsageSummary,
    UsageAvailability,
    apply_token_unit_cost,
    summarize_ai_grade_tokens,
)


class GradingCostModel(BaseModel):
    """Per-1000-token unit price, or ``null`` when not set."""

    token_unit_cost: float | None = Field(default=None, ge=0)


class SubmissionAiUsageResponse(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_unit_cost: float | None = None
    estimated_cost: float | None = None
    usage_availability: UsageAvailability


class MonthlyAiUsageResponse(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_unit_cost: float | None = None
    estimated_cost: float | None = None
    usage_availability: UsageAvailability
    month: str


def _to_response(summary: AiUsageSummary) -> dict[str, object]:
    totals = summary.totals
    return {
        "input_tokens": totals.input_tokens if totals is not None else None,
        "output_tokens": totals.output_tokens if totals is not None else None,
        "token_unit_cost": summary.token_unit_cost,
        "estimated_cost": summary.estimated_cost,
        "usage_availability": summary.availability,
    }


def build_ai_usage_router(
    session_factory: sessionmaker[Session],
    grading_costs: GradingCostStore,
) -> APIRouter:
    router = APIRouter(tags=["ai-usage"])

    @router.get("/grading-cost", response_model=GradingCostModel)
    def get_grading_cost() -> GradingCostModel:
        return GradingCostModel(token_unit_cost=grading_costs.load())

    @router.put("/grading-cost", response_model=GradingCostModel)
    def save_grading_cost(request: GradingCostModel) -> GradingCostModel:
        try:
            grading_costs.save(request.token_unit_cost)
        except IntakeTemplateError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return GradingCostModel(token_unit_cost=grading_costs.load())

    @router.get(
        "/submissions/{submission_id}/ai-usage",
        response_model=SubmissionAiUsageResponse,
    )
    def get_submission_ai_usage(submission_id: str) -> SubmissionAiUsageResponse:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            submission = uow.submissions.get(submission_id)
            if submission is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="submission not found")
            grades = uow.grades.list_ai_for_submission(submission_id)
        summary = apply_token_unit_cost(
            summarize_ai_grade_tokens(grades),
            grading_costs.load(),
        )
        return SubmissionAiUsageResponse(**_to_response(summary))

    @router.get("/ai-usage/monthly", response_model=MonthlyAiUsageResponse)
    def get_monthly_ai_usage() -> MonthlyAiUsageResponse:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            grades = uow.grades.list_ai_since(month_start)
        summary = apply_token_unit_cost(
            summarize_ai_grade_tokens(grades),
            grading_costs.load(),
        )
        return MonthlyAiUsageResponse(
            **_to_response(summary),
            month=month_start.strftime("%Y-%m"),
        )

    return router
