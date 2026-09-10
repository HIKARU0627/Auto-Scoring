import { describe, expect, it } from "vitest";

import { AppRoutes } from "../src/renderer/core/app-routes.js";
import { HomeDashboard } from "../src/renderer/core/home-dashboard.js";
import { HomeWorkBucket } from "../src/renderer/core/submission-work-bucket.js";
import {
  buildSubmission,
  buildTest,
} from "./renderer/support/mock-sidecar-client.js";

function buildDashboard(
  work: Record<string, ReturnType<typeof buildSubmission>[]>,
  tests: ReturnType<typeof buildTest>[],
): HomeDashboard {
  const submissionsByTestId: Record<
    string,
    ReturnType<typeof buildSubmission>[]
  > = {};
  for (const test of tests) {
    submissionsByTestId[test.id] = work[test.id] ?? [];
  }
  return HomeDashboard.from({ tests, submissionsByTestId });
}

describe("HomeTestProgress", () => {
  it("counts only human-reviewed answers as done (INV-147)", () => {
    const progress = buildDashboard(
      {
        t1: [
          buildSubmission({
            id: "done",
            testId: "t1",
            state: "reviewed",
            createdDay: 1,
          }),
          buildSubmission({
            id: "not-done",
            testId: "t1",
            state: "ai_processed",
            createdDay: 2,
          }),
        ],
      },
      [buildTest({ id: "t1" })],
    ).tests[0];

    expect(progress?.doneCount).toBe(1);
    expect(progress?.countOf(HomeWorkBucket.intakeDone)).toBe(1);
    expect(progress?.resumableSubmission?.id).toBe("not-done");
  });

  it("picks the oldest needs_review submission for resume (INV-148)", () => {
    const progress = buildDashboard(
      {
        t1: [
          buildSubmission({
            id: "old-processed",
            testId: "t1",
            state: "ai_processed",
            createdDay: 1,
          }),
          buildSubmission({
            id: "new-flagged",
            testId: "t1",
            state: "needs_review",
            createdDay: 5,
          }),
          buildSubmission({
            id: "old-flagged",
            testId: "t1",
            state: "needs_review",
            createdDay: 3,
          }),
        ],
      },
      [buildTest({ id: "t1" })],
    ).tests[0];

    expect(progress?.resumableSubmission?.id).toBe("old-flagged");
  });
});

describe("HomeDashboard card filtering (INV-150)", () => {
  it("keeps flagged overflow tests visible and counts them in next action", () => {
    const flagged = [
      buildTest({ id: "flagged-0", name: "化学", createdDay: 1 }),
      buildTest({ id: "flagged-1", name: "古漢", createdDay: 2 }),
    ];
    const settled = Array.from({ length: 9 }, (_, index) =>
      buildTest({
        id: `settled-${index}`,
        name: `テスト${index}`,
        createdDay: index + 10,
      }),
    );
    const tests = [...settled, ...flagged];
    const work: Record<string, ReturnType<typeof buildSubmission>[]> = {};
    for (const test of flagged) {
      work[test.id] = [
        buildSubmission({
          id: `s-${test.id}`,
          testId: test.id,
          state: "needs_review",
        }),
      ];
    }
    for (const test of settled) {
      work[test.id] = [
        buildSubmission({
          id: `s-${test.id}`,
          testId: test.id,
          state: "exported",
        }),
      ];
    }

    const dashboard = buildDashboard(work, tests);
    for (const test of flagged) {
      expect(
        dashboard.visibleTests.some((entry) => entry.test.id === test.id),
      ).toBe(true);
    }
    expect(dashboard.nextAction.headline).toBe("要確認の答案が2件あります");
  });
});

describe("HomeDashboard next action", () => {
  it("routes empty state to intake without deprecated copy (INV-128/INV-129)", () => {
    const dashboard = buildDashboard({}, []);
    expect(dashboard.nextAction.route).toBe(AppRoutes.intake);
    expect(dashboard.nextAction.detail).not.toContain("模範解答");
    expect(dashboard.nextAction.detail).not.toContain("採点マニュアル");
  });
});
