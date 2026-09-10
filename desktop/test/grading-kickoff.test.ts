import { describe, expect, it } from "vitest";

import { gradingKickoffFailureFromStatus } from "../src/renderer/core/grading-kickoff.js";

describe("grading kickoff failures (INV-167)", () => {
  it("INV-167: 409 mentions both dependency and conflict without asserting which", () => {
    const failure = gradingKickoffFailureFromStatus(409);
    expect(failure.message).toContain("設問依存関係が確定していない");
    expect(failure.message).toContain("競合");
    expect(failure.retryable).toBe(true);
  });

  it("INV-167: 404 is non-retryable and says the submission is missing", () => {
    const failure = gradingKickoffFailureFromStatus(404);
    expect(failure.message).toContain("見つかりません");
    expect(failure.retryable).toBe(false);
  });
});
