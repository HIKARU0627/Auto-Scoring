import { describe, expect, it } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  buildPlan,
  createIntakeBridge,
  createIntakeMockClient,
  plannedFile,
} from "./support/intake-harness.js";
import { renderAppAt } from "./support/app-harness.js";

/**
 * Issue #384 (1): フォルダ単位の一括設定。
 *
 * The owner reported that "取り込む / 取り込まない" was one checkbox per file,
 * so a folder of many answers meant one click each. Every folder header now
 * carries a bulk control with an indeterminate state, and the bulk choice must
 * flow into the summary and the cost estimate.
 */

const RULE_MATCHED = [
  plannedFile("subject-a/01_answers.pdf", { role: "student_answer" }),
  plannedFile("subject-a/02_criteria.pdf", { role: "grading_criteria" }),
];

async function openReview(
  options: {
    plan?: ReturnType<typeof buildPlan>;
    paths?: readonly string[];
    unitCost?: number | null;
  } = {},
): Promise<void> {
  const paths = options.paths ?? [
    "subject-a/01_answers.pdf",
    "subject-a/02_criteria.pdf",
  ];
  renderAppAt(AppRoutes.intake, {
    client: createIntakeMockClient({
      intakeCost: async () => options.unitCost ?? null,
      planIntake: async () => options.plan ?? buildPlan(RULE_MATCHED),
    }),
    bridge: createIntakeBridge({ folderPaths: paths }),
  });
  await screen.findByTestId("intake-template-picker");
  fireEvent.click(screen.getByTestId("intake-choose-folder"));
  await screen.findByTestId("intake-review-summary");
}

function groupToggle(): HTMLInputElement {
  return screen.getByTestId(
    "intake-group-include-subject-a",
  ) as HTMLInputElement;
}

describe("Issue #384 (1): folder-level bulk include/exclude", () => {
  it("starts with every file included and the bulk control checked", async () => {
    await openReview();
    const toggle = groupToggle();
    expect(toggle.checked).toBe(true);
    expect(toggle.indeterminate).toBe(false);
    expect(
      screen.getByTestId("intake-group-include-summary-subject-a").textContent,
    ).toContain("2/2件を取り込み");
  });

  it("excluding a whole folder clears every file and the summary", async () => {
    await openReview();
    fireEvent.click(groupToggle());

    expect(groupToggle().checked).toBe(false);
    expect(groupToggle().indeterminate).toBe(false);
    expect(
      screen.getByTestId("intake-include-subject-a/01_answers.pdf"),
    ).toHaveProperty("checked", false);
    expect(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    ).toHaveProperty("checked", false);
    expect(
      screen.getByTestId("intake-group-include-summary-subject-a").textContent,
    ).toContain("0/2件を取り込み");
    expect(screen.getByTestId("intake-summary-files").textContent).toContain(
      "0件",
    );
    expect(screen.getByText("すべて取り込む")).toBeDefined();
  });

  it("shows the indeterminate state when only some files are selected", async () => {
    await openReview();
    fireEvent.click(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    );

    const toggle = groupToggle();
    expect(toggle.checked).toBe(false);
    expect(toggle.indeterminate).toBe(true);
    expect(
      screen.getByTestId("intake-group-include-summary-subject-a").textContent,
    ).toContain("1/2件を取り込み");
  });

  it("re-includes everything from the indeterminate state", async () => {
    await openReview();
    fireEvent.click(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    );
    fireEvent.click(groupToggle());

    expect(groupToggle().checked).toBe(true);
    expect(groupToggle().indeterminate).toBe(false);
    expect(
      screen.getByTestId("intake-include-subject-a/02_criteria.pdf"),
    ).toHaveProperty("checked", true);
    expect(
      screen.getByTestId("intake-group-include-summary-subject-a").textContent,
    ).toContain("2/2件を取り込み");
    expect(screen.getByText("すべて外す")).toBeDefined();
  });

  it("an individual checkbox still overrides the bulk choice", async () => {
    await openReview();
    fireEvent.click(groupToggle());
    fireEvent.click(
      screen.getByTestId("intake-include-subject-a/01_answers.pdf"),
    );

    expect(
      screen.getByTestId("intake-include-subject-a/01_answers.pdf"),
    ).toHaveProperty("checked", true);
    expect(groupToggle().indeterminate).toBe(true);
  });

  it("the bulk exclude flows into the estimated AI cost", async () => {
    await openReview({
      plan: buildPlan(
        [
          ...RULE_MATCHED,
          plannedFile("subject-a/stray.pdf", { classification: "pending" }),
        ],
        1,
      ),
      paths: [
        "subject-a/01_answers.pdf",
        "subject-a/02_criteria.pdf",
        "subject-a/stray.pdf",
      ],
      unitCost: 2.5,
    });
    expect(screen.getByText(/概算費用: 約2\.50/)).toBeDefined();

    fireEvent.click(groupToggle());

    expect(screen.getByText(/概算費用: 約0\.00/)).toBeDefined();
    expect(screen.queryByTestId("intake-run-classification")).toBeNull();
  });
});
