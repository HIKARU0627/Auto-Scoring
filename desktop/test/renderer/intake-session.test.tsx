import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { buildReviewState } from "../../src/renderer/core/intake-review.js";
import { saveIntakeSession } from "../../src/renderer/core/intake-data.js";
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
 * Issue #384 (3): the intake screen must keep the chosen folder, files, roles
 * and targets when the user leaves the screen and comes back.
 *
 * Reproduced on the real app: importing, opening テスト設定 and pressing back
 * unmounts `IntakePage`, so the router rebuilds it from scratch and every
 * choice is gone. The fix keeps the session in module memory (never on disk)
 * and restores it, with a visible notice and a やり直す escape hatch.
 */

const RULE_MATCHED = [
  plannedFile("subject-a/01_answers.pdf", { role: "student_answer" }),
  plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
];

const PATHS = ["subject-a/01_answers.pdf", "subject-a/02_criteria.pdf"];

const READY_TEST = () => [buildTest({ id: "test-1", name: "subject-a" })];

function intakeClient(
  options: {
    unitCost?: number | null;
    plan?: ReturnType<typeof buildPlan>;
    listTestRegistrations?: () => Promise<ReturnType<typeof buildTest>[]>;
  } = {},
) {
  return createIntakeMockClient({
    intakeCost: async () => options.unitCost ?? null,
    planIntake: async () => options.plan ?? buildPlan(RULE_MATCHED),
    listTestRegistrations: options.listTestRegistrations ?? (async () => []),
  });
}

async function openReview(
  options: {
    client?: ReturnType<typeof intakeClient>;
    bridge?: ReturnType<typeof createIntakeBridge>;
  } = {},
): Promise<void> {
  renderAppAt(AppRoutes.intake, {
    client: options.client ?? intakeClient(),
    bridge: options.bridge ?? createIntakeBridge({ folderPaths: PATHS }),
  });
  await screen.findByTestId("intake-template-picker");
  fireEvent.click(screen.getByTestId("intake-choose-folder"));
  await screen.findByTestId("intake-review-summary");
}

async function leaveToTestList(): Promise<void> {
  fireEvent.click(screen.getByTestId("sidebar-nav-tests"));
  await screen.findByText("テスト一覧", {
    selector: '[data-testid="page-title"]',
  });
}

async function returnToIntake(): Promise<void> {
  fireEvent.click(screen.getByTestId("sidebar-nav-intake"));
}

describe("Issue #384 (3): the intake selection survives leaving the screen", () => {
  it("restores folder, files, roles and targets and tells the user", async () => {
    await openReview({
      client: intakeClient({ listTestRegistrations: async () => READY_TEST() }),
    });

    fireEvent.change(screen.getByTestId("intake-target-subject-a"), {
      target: { value: "__new__" },
    });
    fireEvent.change(screen.getByTestId("intake-name-subject-a"), {
      target: { value: "restored-name" },
    });
    fireEvent.change(
      screen.getByTestId("intake-role-subject-a/01_answers.pdf"),
      { target: { value: "reference" } },
    );
    fireEvent.click(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    );
    fireEvent.click(screen.getByTestId("intake-narrow-test-1"));

    await leaveToTestList();
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();
    await returnToIntake();

    await screen.findByTestId("intake-review-summary");
    expect(await screen.findByTestId("intake-restore-notice")).toBeDefined();
    expect(screen.getByTestId("intake-target-subject-a")).toHaveProperty(
      "value",
      "__new__",
    );
    expect(screen.getByTestId("intake-name-subject-a")).toHaveProperty(
      "value",
      "restored-name",
    );
    expect(
      screen.getByTestId("intake-role-subject-a/01_answers.pdf"),
    ).toHaveProperty("value", "reference");
    expect(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    ).toHaveProperty("checked", false);
    expect(
      screen.getByTestId("intake-narrow-test-1").getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("やり直す drops the restored selection and stays empty afterwards", async () => {
    await openReview();
    await leaveToTestList();
    await returnToIntake();
    await screen.findByTestId("intake-restore-notice");

    fireEvent.click(screen.getByTestId("intake-restore-discard"));

    expect(screen.getByTestId("intake-choose-folder")).toBeDefined();
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();
    expect(screen.queryByTestId("intake-restore-notice")).toBeNull();

    await leaveToTestList();
    await returnToIntake();
    expect(await screen.findByTestId("intake-choose-folder")).toBeDefined();
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();
  });

  it("a fully successful import clears the session", async () => {
    await openReview();
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-done-heading");

    await leaveToTestList();
    await returnToIntake();

    expect(await screen.findByTestId("intake-choose-folder")).toBeDefined();
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();
    expect(screen.queryByTestId("intake-restore-notice")).toBeNull();
  });

  it("a failed import keeps the session so it can be retried", async () => {
    await openReview({
      bridge: createIntakeBridge({
        folderPaths: PATHS,
        createSubmission: async () => {
          throw new Error("simulated disk failure");
        },
      }),
      client: intakeClient({ listTestRegistrations: async () => READY_TEST() }),
    });
    fireEvent.click(screen.getByTestId("intake-import"));
    await screen.findByTestId("intake-done-heading");

    await leaveToTestList();
    await returnToIntake();

    expect(await screen.findByTestId("intake-restore-notice")).toBeDefined();
    expect(screen.getByTestId("intake-done-heading")).toBeDefined();
  });

  it("does not restore when the folder changed on disk, and says why", async () => {
    let onDisk = scannedFolder(PATHS);
    const base = createIntakeBridge({ folderPaths: PATHS });
    const bridge = {
      ...base,
      scanFolder: vi.fn(async () => onDisk),
    };
    await openReview({ bridge });
    await leaveToTestList();

    onDisk = { name: "batch", entries: [] };
    await returnToIntake();

    expect(await screen.findByTestId("intake-restore-stale")).toBeDefined();
    expect(screen.getByTestId("intake-choose-folder")).toBeDefined();
    expect(screen.queryByTestId("intake-review-summary")).toBeNull();
  });

  it("picking a folder again does not carry the previous narrowing over", async () => {
    const base = createIntakeBridge({ folderPaths: PATHS });
    saveIntakeSession({
      step: "choose",
      templateId: "serial-number-prefix",
      chosenFolderName: "subject-a",
      chosenFolderPath: "/tmp/batch",
      review: buildReviewState({
        plan: buildPlan(RULE_MATCHED),
        folder: scannedFolder(PATHS),
        requiredRoles: ["grading_criteria"],
        unitCost: null,
      }),
      narrowedTestIds: ["test-1"],
      outcomes: [],
    });

    renderAppAt(AppRoutes.intake, {
      client: intakeClient({ listTestRegistrations: async () => READY_TEST() }),
      bridge: base,
    });
    await screen.findByTestId("intake-choose-folder");
    fireEvent.click(screen.getByTestId("intake-choose-folder"));
    await screen.findByTestId("intake-narrow-test-1");

    expect(
      screen.getByTestId("intake-narrow-test-1").getAttribute("aria-pressed"),
    ).toBe("false");
  });
});

describe("Issue #384 (3): the session is memory only", () => {
  it("only the theme is ever written to storage during an intake visit", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    await openReview();
    await leaveToTestList();
    await returnToIntake();
    await screen.findByTestId("intake-restore-notice");

    const writtenKeys = setItem.mock.calls.map((call) => String(call[0]));
    expect(writtenKeys.every((key) => key === "auto-scoring-theme")).toBe(true);
    setItem.mockRestore();
  });
});
