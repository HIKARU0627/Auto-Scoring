import type { SidecarClient } from "../api/client.js";
import type { components } from "../api/generated/schema.js";
import type { AiUsageNumbers, UsageAvailability } from "./ai-usage-display.js";

export type SubmissionAiUsageResponse =
  components["schemas"]["SubmissionAiUsageResponse"];
export type MonthlyAiUsageResponse =
  components["schemas"]["MonthlyAiUsageResponse"];
export type GradingCostModel = components["schemas"]["GradingCostModel"];

export class UsageDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UsageDataError";
  }
}

export function toAiUsageNumbers(
  response: SubmissionAiUsageResponse | MonthlyAiUsageResponse,
): AiUsageNumbers {
  return {
    inputTokens: response.input_tokens ?? null,
    outputTokens: response.output_tokens ?? null,
    tokenUnitCost: response.token_unit_cost ?? null,
    estimatedCost: response.estimated_cost ?? null,
    usageAvailability: response.usage_availability as UsageAvailability,
  };
}

export async function loadSubmissionAiUsage(
  client: SidecarClient,
  submissionId: string,
): Promise<AiUsageNumbers> {
  const response = await client.GET("/submissions/{submission_id}/ai-usage", {
    params: { path: { submission_id: submissionId } },
  });
  if (response.data === undefined) {
    throw new UsageDataError("AI 利用量を取得できません");
  }
  return toAiUsageNumbers(response.data);
}

export async function loadMonthlyAiUsage(
  client: SidecarClient,
): Promise<AiUsageNumbers> {
  const response = await client.GET("/ai-usage/monthly");
  if (response.data === undefined) {
    throw new UsageDataError("月間の AI 利用量を取得できません");
  }
  return toAiUsageNumbers(response.data);
}

export async function loadGradingTokenUnitCost(
  client: SidecarClient,
): Promise<number | null> {
  const response = await client.GET("/grading-cost");
  if (response.data === undefined) {
    throw new UsageDataError("採点の単価を取得できません");
  }
  return response.data.token_unit_cost ?? null;
}

export async function saveGradingTokenUnitCost(
  client: SidecarClient,
  cost: number | null,
): Promise<number | null> {
  const response = await client.PUT("/grading-cost", {
    body: { token_unit_cost: cost },
  });
  if (response.data === undefined) {
    throw new UsageDataError("採点の単価の保存に失敗しました");
  }
  return response.data.token_unit_cost ?? null;
}
