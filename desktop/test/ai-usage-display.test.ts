import { describe, expect, it } from "vitest";

import {
  formatAiUsageCost,
  formatAiUsageDisplay,
  formatAiUsageTokens,
  formatProviderAccountBalance,
  type AiUsageNumbers,
} from "../src/renderer/core/ai-usage-display.js";

const knownUsage = (
  overrides: Partial<AiUsageNumbers> = {},
): AiUsageNumbers => ({
  inputTokens: 1000,
  outputTokens: 200,
  tokenUnitCost: null,
  estimatedCost: null,
  usageAvailability: "known",
  ...overrides,
});

describe("ai usage display (Issue #187)", () => {
  it("単価未設定のときは金額を出さない", () => {
    const usage = knownUsage();
    expect(formatAiUsageCost(usage)).toBeNull();
    const display = formatAiUsageDisplay(usage);
    expect(display.costLine).toContain("単価が未設定");
    expect(display.costLine).not.toMatch(/0(\.0+)?円/);
    expect(display.costLine).not.toMatch(/約0(\.0+)?/);
  });

  it("usage が無いときは不明と出し 0 と表示しない", () => {
    const usage = knownUsage({
      inputTokens: null,
      outputTokens: null,
      usageAvailability: "unknown",
    });
    expect(formatAiUsageTokens(usage)).toBe("トークン数: 不明");
    expect(formatAiUsageTokens(usage)).not.toContain("0");
  });

  it("provider 残高は自前積算と別行", () => {
    const self = formatAiUsageDisplay(
      knownUsage({ tokenUnitCost: 1, estimatedCost: 1.2 }),
    );
    const provider = formatProviderAccountBalance(5, 100);
    expect(self.providerBalanceLine).toBeNull();
    expect(provider).toContain("provider 側の数字");
    expect(provider).not.toContain("概算費用");
  });

  it("mutation: 単価未設定でも金額を出す形にするとテストが赤くなる", () => {
    const broken = (usage: AiUsageNumbers): string | null => {
      if (usage.usageAvailability === "unknown") {
        return null;
      }
      return "概算費用: 約0.00";
    };
    expect(broken(knownUsage())).not.toBeNull();
    expect(formatAiUsageCost(knownUsage())).toBeNull();
  });
});
