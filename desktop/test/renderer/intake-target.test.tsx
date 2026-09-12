import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  intakeTarget,
  readIntakeTarget,
} from "../../src/renderer/core/app-routes.js";
import { buildReviewState } from "../../src/renderer/core/intake-review.js";
import {
  resetIntakeSession,
  saveIntakeSession,
} from "../../src/renderer/core/intake-data.js";
import {
  buildPlan,
  createIntakeBridge,
  createIntakeMockClient,
  plannedFile,
  scannedFolder,
} from "./support/intake-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";
import { renderAppAt } from "./support/app-harness.js";

/**
 * Issue #414: the three "答案を取り込む" entries open the intake screen with the
 * test already chosen as the destination. The owner's report was that the path
 * existed but was invisible; a jump that lands on an empty intake screen and
 * makes the operator find the same test again is not a fix.
 *
 * These cover the three states the screen can be in when it opens with a target:
 * no session (apply silently), a restorable session (ask before discarding), and
 * a draft target (say what is still missing and link to テスト設定).
 */

const RULE_MATCHED = [
  plannedFile("subject-a/01_answers.pdf", { role: "student_answer" }),
  plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
];
const PATHS = ["subject-a/01_answers.pdf", "subject-a/02_criteria.pdf"];

function clientWith(tests: ReturnType<typeof buildTest>[]) {
  return createIntakeMockClient({
    listTestRegistrations: async () => tests,
    planIntake: async () => buildPlan(RULE_MATCHED),
  });
}

async function pickFolder(): Promise<void> {
  fireEvent.click(screen.getByTestId("intake-choose-folder"));
  await screen.findByTestId("intake-review-summary");
}

beforeEach(() => {
  resetIntakeSession();
});

describe("intakeTarget route helper (Issue #414)", () => {
  it("round-trips a test id through the query string", () => {
    const url = intakeTarget("t/1 2%");
    expect(url.startsWith("/intake?targetTestId=")).toBe(true);
    expect(readIntakeTarget(url)).toBe("t/1 2%");
  });

  it("has no target for a plain intake path", () => {
    expect(readIntakeTarget("/intake")).toBeNull();
  });
});

describe("IntakePage target preselection (Issue #414)", () => {
  it("applies the specified test when there is no session to restore", async () => {
    renderAppAt(intakeTarget("test-1"), {
      client: clientWith([
        buildTest({ id: "test-1", name: "国語 第1回", status: "ready" }),
      ]),
      bridge: createIntakeBridge({ folderPaths: PATHS }),
    });

    await screen.findByTestId("intake-template-picker");
    await pickFolder();

    expect(screen.queryByTestId("intake-target-conflict")).toBeNull();
    expect(screen.getByTestId("intake-target-subject-a")).toHaveProperty(
      "value",
      "test-1",
    );
    expect(
      screen.getByTestId("intake-narrow-test-1").getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("asks before discarding a restorable session, and lets the user continue it", async () => {
    saveIntakeSession({
      step: "review",
      templateId: "serial-number-prefix",
      chosenFolderName: "batch",
      chosenFolderPath: "/tmp/batch",
      review: buildReviewState({
        plan: buildPlan(RULE_MATCHED),
        folder: scannedFolder(PATHS),
        requiredRoles: ["grading_criteria"],
        unitCost: null,
      }),
      narrowedTestIds: [],
      outcomes: [],
    });

    renderAppAt(intakeTarget("test-1"), {
      client: clientWith([
        buildTest({ id: "test-1", name: "国語 第1回", status: "ready" }),
      ]),
      bridge: createIntakeBridge({ folderPaths: PATHS }),
    });

    // Neither choice is taken silently: the review is not shown yet.
    await screen.findByTestId("intake-target-conflict");
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();

    fireEvent.click(screen.getByTestId("intake-target-continue"));

    await screen.findByTestId("intake-restore-notice");
    expect(screen.getByTestId("intake-review-summary")).toBeDefined();
    // The ignored request is named, not hidden.
    expect(
      screen.getByTestId("intake-restore-target-ignored").textContent,
    ).toContain("国語 第1回");
    // Continuing keeps the previous target; the requested test was not applied.
    expect(screen.getByTestId("intake-target-subject-a")).toHaveProperty(
      "value",
      "__new__",
    );
  });

  it("discards the session and applies the specified test on request", async () => {
    saveIntakeSession({
      step: "review",
      templateId: "serial-number-prefix",
      chosenFolderName: "batch",
      chosenFolderPath: "/tmp/batch",
      review: buildReviewState({
        plan: buildPlan(RULE_MATCHED),
        folder: scannedFolder(PATHS),
        requiredRoles: ["grading_criteria"],
        unitCost: null,
      }),
      narrowedTestIds: [],
      outcomes: [],
    });

    renderAppAt(intakeTarget("test-1"), {
      client: clientWith([
        buildTest({ id: "test-1", name: "国語 第1回", status: "ready" }),
      ]),
      bridge: createIntakeBridge({ folderPaths: PATHS }),
    });

    await screen.findByTestId("intake-target-conflict");
    fireEvent.click(screen.getByTestId("intake-target-discard"));

    // The previous selection is gone and the folder must be chosen again...
    await screen.findByTestId("intake-choose-folder");
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();

    // ...and the chosen folder routes to the requested test.
    await pickFolder();
    expect(screen.getByTestId("intake-target-subject-a")).toHaveProperty(
      "value",
      "test-1",
    );
  });

  it("explains why a draft test cannot receive answers and links to テスト設定", async () => {
    renderAppAt(intakeTarget("draft-1"), {
      client: clientWith([
        buildTest({ id: "draft-1", name: "数学 第1回", status: "draft" }),
      ]),
      bridge: createIntakeBridge({ folderPaths: PATHS }),
    });

    await screen.findByTestId("intake-template-picker");
    await pickFolder();

    expect(screen.getByTestId("intake-target-subject-a")).toHaveProperty(
      "value",
      "draft-1",
    );
    expect(
      screen.getByTestId("intake-draft-reason-subject-a").textContent,
    ).toContain("配点・回答欄・依存関係");

    fireEvent.click(screen.getByTestId("intake-open-draft-settings-subject-a"));
    await waitFor(() => {
      expect(screen.getByTestId("page-title").textContent).toBe("テスト設定");
    });
  });
});
