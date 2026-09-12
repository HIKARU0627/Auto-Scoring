import { describe, expect, it } from "vitest";

import {
  INTAKE_JOURNEY,
  IntakeJourneyStage,
  journeyLabel,
  journeyRoute,
  journeyStageForTest,
  journeyStepIndex,
  journeySteps,
} from "../src/renderer/core/intake-journey.js";

/**
 * Issue #450: the path from 資料の取込 to PDF出力 was only in the operator's
 * head. These fix the one definition every screen points at: which step a test
 * is on, and which route that step opens.
 */
describe("intake journey (Issue #450)", () => {
  it("names the five steps in the order the operator walks them", () => {
    expect(INTAKE_JOURNEY.map((step) => step.id)).toEqual([
      "materials",
      "settings",
      "answers",
      "review",
      "export",
    ]);
    expect(INTAKE_JOURNEY.map((step) => step.label)).toEqual([
      "資料の取込",
      "テスト設定",
      "答案の取込",
      "採点の確認",
      "PDF出力",
    ]);
  });

  it("a draft's next step is テスト設定", () => {
    expect(
      journeyStageForTest({
        isDraft: true,
        answerCount: 0,
        doneCount: 0,
        total: 0,
      }),
    ).toBe(IntakeJourneyStage.settings);
  });

  it("a ready test with no answers' next step is 答案の取込", () => {
    expect(
      journeyStageForTest({
        isDraft: false,
        answerCount: 0,
        doneCount: 0,
        total: 0,
      }),
    ).toBe(IntakeJourneyStage.answers);
  });

  it("a ready test with unconfirmed answers' next step is 採点の確認", () => {
    expect(
      journeyStageForTest({
        isDraft: false,
        answerCount: 3,
        doneCount: 1,
        total: 3,
      }),
    ).toBe(IntakeJourneyStage.review);
  });

  it("a ready test with every answer confirmed is at PDF出力", () => {
    expect(
      journeyStageForTest({
        isDraft: false,
        answerCount: 2,
        doneCount: 2,
        total: 2,
      }),
    ).toBe(IntakeJourneyStage.export);
  });

  it("an answer list that could not be read has no stage to claim", () => {
    // `null` means the submissions request failed; guessing a step would send
    // the operator to the wrong screen, so the row shows no next action.
    expect(
      journeyStageForTest({
        isDraft: false,
        answerCount: null,
        doneCount: 0,
        total: 0,
      }),
    ).toBeNull();
  });

  it("routes each stage to the screen that does that work", () => {
    expect(journeyRoute(IntakeJourneyStage.materials, "t1")).toBe(
      "/intake?targetTestId=t1",
    );
    expect(journeyRoute(IntakeJourneyStage.settings, "t1")).toBe(
      "/tests/t1/settings",
    );
    expect(journeyRoute(IntakeJourneyStage.answers, "t1")).toBe(
      "/intake?targetTestId=t1",
    );
    expect(journeyRoute(IntakeJourneyStage.review, "t1")).toBe(
      "/tests/t1/submissions",
    );
    expect(journeyRoute(IntakeJourneyStage.export, "t1")).toBe(
      "/tests/t1/submissions",
    );
  });

  it("marks only the stages before the current one complete", () => {
    expect(journeySteps(IntakeJourneyStage.review)).toEqual([
      { id: "materials", label: "資料の取込", complete: true },
      { id: "settings", label: "テスト設定", complete: true },
      { id: "answers", label: "答案の取込", complete: true },
      { id: "review", label: "採点の確認", complete: false },
      { id: "export", label: "PDF出力", complete: false },
    ]);
  });

  it("gives every step a label and a position", () => {
    INTAKE_JOURNEY.forEach((step, index) => {
      expect(journeyStepIndex(step.id)).toBe(index);
      expect(journeyLabel(step.id)).toBe(step.label);
    });
  });
});
