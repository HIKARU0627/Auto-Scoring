import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  buildPlan,
  createIntakeBridge,
  createIntakeMockClient,
  plannedFile,
} from "./support/intake-harness.js";
import { buildTest } from "./support/mock-sidecar-client.js";
import { renderAppAt } from "./support/app-harness.js";

/**
 * Issue #384 (2): the heading used to ask "このバッチはどのテストの答案ですか".
 * The owner asked "バッチとは？ これを選択すると何が起きるのか？". The screen now
 * names the folder being imported and spells out both outcomes: picking one
 * test routes without AI, not picking makes the AI decide per answer.
 *
 * The exact retired heading is also barred by `retired-copy.test.ts`.
 */

const RULE_MATCHED = [
  plannedFile("subject-a/01_answers.pdf", { role: "student_answer" }),
  plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
];

const PATHS = ["subject-a/01_answers.pdf", "subject-a/02_criteria.pdf"];

async function openReview(): Promise<void> {
  renderAppAt(AppRoutes.intake, {
    client: createIntakeMockClient({
      planIntake: async () => buildPlan(RULE_MATCHED),
      listTestRegistrations: async () => [
        buildTest({ id: "test-1", name: "subject-a" }),
      ],
    }),
    bridge: createIntakeBridge({ folderPaths: PATHS }),
  });
  await screen.findByTestId("intake-template-picker");
  fireEvent.click(screen.getByTestId("intake-choose-folder"));
  await screen.findByTestId("intake-narrowing");
}

describe("Issue #384 (2): the narrowing copy names the folder", () => {
  it("does not use the word バッチ", async () => {
    await openReview();
    expect(screen.queryByText(/バッチ/)).toBeNull();
  });

  it("names the folder as the thing being routed", async () => {
    await openReview();
    expect(
      screen.getByText("このフォルダの答案は、どのテストのものですか"),
    ).toBeDefined();
  });

  it("explains what happens both when a test is picked and when it is not", async () => {
    await openReview();
    const benefit = screen.getByTestId("intake-narrowing-benefit").textContent;
    expect(benefit).toContain("AIに問い合わせず");
    expect(benefit).toContain("選ばない場合");
    expect(benefit).toContain("費用");
  });
});
