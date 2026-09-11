import { describe, expect, it } from "vitest";

import {
  classifyAnswerDetectionOutcome,
  countAnswerAreaRegions,
} from "../src/renderer/core/answer-detection-outcome.js";

describe("classifyAnswerDetectionOutcome", () => {
  it("returns none when answer areas were found", () => {
    expect(
      classifyAnswerDetectionOutcome({
        questionNumbers: ["問1"],
        regions: [{ kind: "answer_area" }],
        absentQuestionNumbers: [],
      }),
    ).toBe("none");
  });

  it("returns zero-results when detection finished with no boxes", () => {
    expect(
      classifyAnswerDetectionOutcome({
        questionNumbers: ["問1", "問2"],
        regions: [],
        absentQuestionNumbers: [],
      }),
    ).toBe("zero-results");
  });

  it("returns role-mismatch when every question was reported absent", () => {
    expect(
      classifyAnswerDetectionOutcome({
        questionNumbers: ["問1", "問2"],
        regions: [],
        absentQuestionNumbers: ["問1", "問2"],
      }),
    ).toBe("role-mismatch");
  });
});

describe("countAnswerAreaRegions", () => {
  it("counts only answer_area regions", () => {
    expect(
      countAnswerAreaRegions([
        { kind: "answer_area" },
        { kind: "score" },
        { kind: "answer_area" },
      ]),
    ).toBe(2);
  });
});
