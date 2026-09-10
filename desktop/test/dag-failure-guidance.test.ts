import { describe, expect, it } from "vitest";

import {
  DagFailureGuidance,
  dagFailureGuidance,
} from "../src/renderer/core/dag-failure-guidance.js";
import { NOT_THE_ANSWER_CROP_REASON } from "../src/renderer/core/grading-failure-reason.js";

const realisticLastError =
  "gemini AI provider returned a malformed response " +
  "[vertex-ai/gemini-2.5-pro SchemaViolation, https://aiplatform.googleapis.com 400]";

describe("dagFailureGuidance (INV-165, INV-166)", () => {
  it("INV-163: classification changes the next step", () => {
    expect(dagFailureGuidance({ errorCode: "rate_limited" })).toBe(
      DagFailureGuidance.rateLimited,
    );
    expect(dagFailureGuidance({ errorCode: "timeout" })).toBe(
      DagFailureGuidance.temporary,
    );
    expect(dagFailureGuidance({ errorCode: "permanent" })).toBe(
      DagFailureGuidance.permanent,
    );
  });

  it("INV-166: crop_not_the_answer is checked before permanent", () => {
    const guidance = dagFailureGuidance({
      errorCode: "permanent",
      lastError: `provider reported (${NOT_THE_ANSWER_CROP_REASON})`,
    });
    expect(guidance).toBe(DagFailureGuidance.answerAreaWrong);
    expect(guidance.nextStep).toContain("回答欄");
    expect(guidance.nextStep).not.toContain("もう一度");
  });

  it("INV-164: last_error fragments never appear in guidance", () => {
    for (const code of [
      null,
      "timeout",
      "rate_limited",
      "server_error",
      "permanent",
    ]) {
      const guidance = dagFailureGuidance({
        errorCode: code,
        lastError: realisticLastError,
      });
      const shown = `${guidance.cause}${guidance.nextStep}`;
      for (const fragment of [
        "gemini",
        "vertex-ai",
        "SchemaViolation",
        "https://",
        "400",
      ]) {
        expect(shown).not.toContain(fragment);
      }
    }
  });

  it("INV-165: every classification has cause and actionable nextStep", () => {
    for (const guidance of Object.values(DagFailureGuidance)) {
      expect(guidance.cause.length).toBeGreaterThan(0);
      expect(guidance.nextStep.length).toBeGreaterThan(0);
      expect(
        ["再判定", "点数を入力", "回答欄", "設定"].some((word) =>
          guidance.nextStep.includes(word),
        ),
      ).toBe(true);
    }
  });
});
