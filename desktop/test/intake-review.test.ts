import { describe, expect, it } from "vitest";

import {
  IntakeTargetKind,
  canImport,
  importRequirements,
  unmetRequirements,
  type IntakeFileState,
  type IntakeGroupState,
} from "../src/renderer/core/intake-review.js";

function file(
  relativePath: string,
  patch: Partial<IntakeFileState> = {},
): IntakeFileState {
  return {
    relativePath,
    absolutePath: `/tmp/${relativePath}`,
    sha256: "0".repeat(64),
    sizeBytes: 1,
    ruleRole: null,
    needsClassification: false,
    cachedClassification: false,
    classificationAttempted: false,
    proposedRole: null,
    proposalConfirmed: false,
    humanRole: null,
    excluded: false,
    answerTestId: null,
    proposedAnswerTestId: null,
    attributionAttempted: false,
    ...patch,
  };
}

function group(
  files: IntakeFileState[],
  patch: Partial<IntakeGroupState> = {},
): IntakeGroupState {
  return {
    key: "subject-a",
    name: "国語",
    files,
    requiredRoles: ["grading_criteria"],
    targetKind: IntakeTargetKind.create,
    targetTestId: null,
    targetTestStatus: null,
    ...patch,
  };
}

describe("intake review core (INV-120–123)", () => {
  const complete = [
    file("subject-a/01_answers.pdf", { ruleRole: "student_answer" }),
    file("subject-a/02_criteria.pdf", { ruleRole: "grading_criteria" }),
  ];

  it("INV-120: blocks import while an AI proposal is unconfirmed", () => {
    const review = {
      groups: [
        group([
          ...complete,
          file("subject-a/stray.pdf", { proposedRole: "reference" }),
        ]),
      ],
      unitCost: null,
    };
    expect(canImport(review)).toBe(false);
    expect(
      importRequirements(review).some(
        (req) => req.id === "intake-proposal-unconfirmed",
      ),
    ).toBe(true);
  });

  it("INV-121: rule-matched files do not require confirmation", () => {
    const review = { groups: [group(complete)], unitCost: null };
    expect(canImport(review)).toBe(true);
  });

  it("INV-122: existing test target does not require grading criteria in batch", () => {
    const review = {
      groups: [
        group(
          [file("subject-a/01_answers.pdf", { ruleRole: "student_answer" })],
          {
            targetKind: IntakeTargetKind.existing,
            targetTestId: "test-1",
          },
        ),
      ],
      unitCost: null,
    };
    expect(unmetRequirements(review.groups[0]!)).toEqual([]);
    expect(canImport(review)).toBe(true);
  });

  it("INV-123: new test requires grading criteria", () => {
    const review = {
      groups: [
        group([
          file("subject-a/01_answers.pdf", { ruleRole: "student_answer" }),
        ]),
      ],
      unitCost: null,
    };
    expect(unmetRequirements(review.groups[0]!)).toEqual(["grading_criteria"]);
    expect(canImport(review)).toBe(false);
  });
});
