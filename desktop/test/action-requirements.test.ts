import { describe, expect, it } from "vitest";

import {
  ActionRequirements,
  answerProfileConfirmRequirements,
  answerProfileSaveRequirements,
  completeRegistrationRequirements,
  dependencyGraphConfirmRequirements,
} from "../src/renderer/core/action-requirements.js";

function expectActionable(requirement: { id: string; message: string }): void {
  expect(requirement.id.length).toBeGreaterThan(0);
  expect(requirement.message.endsWith("。")).toBe(true);
  expect(requirement.message).not.toMatch(/Exception|Error|HTTP|[0-9]{3} /);
}

describe("test settings action requirements", () => {
  it("INV-110: profile confirm reasons cover save reasons", () => {
    for (const busy of [false, true]) {
      for (const confirmed of [false, true]) {
        for (const regionCount of [0, 1]) {
          const save = answerProfileSaveRequirements({
            busy,
            hasRegions: regionCount > 0,
            alreadyConfirmed: confirmed,
          });
          const confirm = answerProfileConfirmRequirements({
            busy,
            alreadyConfirmed: confirmed,
            regionCount,
            unassignedRegionCount: 0,
            mustSeeAnswerSheetFirst: false,
            answerSheetRegistered: true,
          });
          expect(confirm.map((requirement) => requirement.id)).toEqual(
            expect.arrayContaining(save.map((item) => item.id)),
          );
        }
      }
    }
  });

  it("INV-201-04: disabled confirm shows actionable reasons", () => {
    const requirements = answerProfileConfirmRequirements({
      busy: false,
      alreadyConfirmed: false,
      regionCount: 0,
      unassignedRegionCount: 2,
      mustSeeAnswerSheetFirst: true,
      answerSheetRegistered: false,
    });
    expect(requirements.map((item) => item.id)).toEqual([
      "answer-regions-missing",
      "answer-regions-unassigned",
      "answer-sheet-unseen",
    ]);
    requirements.forEach(expectActionable);
  });

  it("complete registration stays blocked until profile and graph are confirmed", () => {
    expect(
      completeRegistrationRequirements({
        busy: false,
        alreadyComplete: false,
        profileConfirmed: false,
        dependencyGraphConfirmed: false,
      }).map((item) => item.id),
    ).toEqual(["profile-unconfirmed", "dependency-graph-unconfirmed"]);
    expect(
      completeRegistrationRequirements({
        busy: false,
        alreadyComplete: false,
        profileConfirmed: true,
        dependencyGraphConfirmed: true,
      }),
    ).toEqual([]);
  });

  it("dependency graph confirm requires an analyzed graph", () => {
    expect(
      dependencyGraphConfirmRequirements({
        busy: false,
        hasGraph: false,
        alreadyConfirmed: false,
      }).map((item) => item.id),
    ).toEqual(["dependency-graph-missing"]);
    expectActionable(ActionRequirements.dependencyGraphMissing);
  });
});
