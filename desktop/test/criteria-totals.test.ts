import { describe, expect, it } from "vitest";

import {
  criteriaBlockingReason,
  criteriaTotals,
  dependencyGraphDescribesQuestions,
} from "../src/renderer/core/criteria-totals.js";

describe("criteria totals", () => {
  it("treats unknown points separately from the sum", () => {
    const totals = criteriaTotals(
      [
        { number: "問1", points: 5, criteria: [], source_pages: [] },
        { number: "問2", points: null, criteria: [], source_pages: [] },
      ],
      { declaredTotalPoints: 5 },
    );
    expect(totals.knownPoints).toBe(5);
    expect(totals.unknownCount).toBe(1);
    expect(totals.declaredDifference).toBeNull();
  });

  it("blocks confirm while points are unknown or missing", () => {
    expect(criteriaBlockingReason([])).toContain("1 件もありません");
    expect(
      criteriaBlockingReason([
        {
          number: "問1",
          points: null,
          criteria: [],
          source_pages: [],
        },
      ]),
    ).toContain("配点が不明");
  });
});

describe("dependencyGraphDescribesQuestions", () => {
  it("detects stale graphs after question set changes", () => {
    expect(
      dependencyGraphDescribesQuestions({
        testId: "t1",
        graphQuestionIds: ["t1:問1"],
        criteriaNumbers: ["問1", "問2"],
        questionRegionLabels: [],
      }),
    ).toBe(false);
  });
});
