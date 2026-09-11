import { describe, expect, it } from "vitest";

import type { components } from "../src/renderer/api/generated/schema.js";
import {
  answerAreaCoverage,
  missingAnswerAreas,
} from "../src/renderer/core/answer-area-review.js";

type RegionModel = components["schemas"]["RegionModel"];

function region(
  label: string,
  kind: RegionModel["kind"] = "answer_area",
): RegionModel {
  return {
    region_id: `region-${label}`,
    kind,
    page_index: 0,
    label,
    confirmed: false,
    text: null,
    bbox: { x0: 0, y0: 0, x1: 1, y1: 1 },
  };
}

describe("missingAnswerAreas (Issue #164 / #314)", () => {
  it("keeps a declared-absent question apart from an undetected one", () => {
    const result = missingAnswerAreas({
      regions: [region("問1")],
      questionNumbers: ["問1", "問2", "問3"],
      reportedAbsent: new Set(["問3"]),
    });

    expect(result.undetected).toEqual(["問2"]);
    expect(result.absent).toEqual(["問3"]);
  });

  it("counts an undeclared missing question as undetected, never as absent", () => {
    const result = missingAnswerAreas({
      regions: [region("問1")],
      questionNumbers: ["問1", "問2"],
      reportedAbsent: new Set(),
    });

    expect(result.undetected).toEqual(["問2"]);
    expect(result.absent).toEqual([]);
  });

  it("drops a question from both lists once a box covers it", () => {
    const result = missingAnswerAreas({
      regions: [region("問1"), region("問3")],
      questionNumbers: ["問1", "問2", "問3"],
      reportedAbsent: new Set(["問3"]),
    });

    expect(result.undetected).toEqual(["問2"]);
    expect(result.absent).toEqual([]);
  });
});

describe("answerAreaCoverage (Issue #314)", () => {
  it("counts the criteria questions the registered regions do not cover", () => {
    expect(
      answerAreaCoverage({
        questionNumbers: ["問1", "問2", "問3"],
        regions: [region("問1")],
      }),
    ).toEqual({ expected: 3, covered: 1, uncovered: 2 });
  });

  it("ignores non-answer-area regions when counting coverage", () => {
    expect(
      answerAreaCoverage({
        questionNumbers: ["問1", "問2"],
        regions: [region("問1"), region("問2", "question")],
      }),
    ).toEqual({ expected: 2, covered: 1, uncovered: 1 });
  });

  it("reports no uncovered questions when every question has a region", () => {
    expect(
      answerAreaCoverage({
        questionNumbers: ["問1", "問2"],
        regions: [region("問1"), region("問2")],
      }),
    ).toEqual({ expected: 2, covered: 2, uncovered: 0 });
  });
});
