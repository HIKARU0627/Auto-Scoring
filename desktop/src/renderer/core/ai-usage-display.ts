/** Display rules for AI token usage and optional cost (Issue #187). */

export type UsageAvailability = "known" | "partial" | "unknown";

export interface AiUsageNumbers {
  readonly inputTokens: number | null;
  readonly outputTokens: number | null;
  readonly tokenUnitCost: number | null;
  readonly estimatedCost: number | null;
  readonly usageAvailability: UsageAvailability;
}

export interface AiUsageDisplayLines {
  readonly tokenLine: string;
  readonly costLine: string | null;
  readonly providerBalanceLine: string | null;
}

export function formatAiUsageCost(usage: AiUsageNumbers): string | null {
  if (usage.usageAvailability === "unknown") {
    return null;
  }
  if (usage.tokenUnitCost === null) {
    return null;
  }
  if (usage.estimatedCost === null) {
    return null;
  }
  return `概算費用: 約${usage.estimatedCost.toFixed(2)}（1000トークンあたり${usage.tokenUnitCost.toFixed(4)}）`;
}

export function formatAiUsageTokens(usage: AiUsageNumbers): string {
  if (usage.usageAvailability === "unknown") {
    return "トークン数: 不明";
  }
  const input = usage.inputTokens ?? 0;
  const output = usage.outputTokens ?? 0;
  const partial =
    usage.usageAvailability === "partial" ? "（一部の設問は不明）" : "";
  return `トークン数: 入力 ${input.toLocaleString()} / 出力 ${output.toLocaleString()}${partial}`;
}

export function formatAiUsageDisplay(
  usage: AiUsageNumbers,
): AiUsageDisplayLines {
  const tokenLine = formatAiUsageTokens(usage);
  const costLine =
    usage.tokenUnitCost === null
      ? usage.usageAvailability === "unknown"
        ? null
        : "概算費用: 1000トークンあたりの単価が未設定です（設定画面で入力できます）"
      : formatAiUsageCost(usage);
  return {
    tokenLine,
    costLine,
    providerBalanceLine: null,
  };
}

export function formatProviderAccountBalance(
  usage: number | null | undefined,
  limit: number | null | undefined,
): string | null {
  if (usage == null && limit == null) {
    return null;
  }
  const usageText = usage == null ? "不明" : usage.toFixed(2);
  const limitText = limit == null ? "上限なし" : limit.toFixed(2);
  return `provider 側の数字: 利用 ${usageText} / 上限 ${limitText}`;
}
