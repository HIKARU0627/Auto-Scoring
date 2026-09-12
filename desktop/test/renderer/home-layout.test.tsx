import * as fs from "node:fs";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue #360 home layout.
 *
 * The five acceptance points each get a positive assertion that names the
 * value the implementation must produce, so one deliberate mutation per point
 * turns exactly one of them red (the mutation list is in the PR):
 *   1. the main column is two side-by-side cards (全体の進捗 | テストの進捗)
 *   2. the 進捗 cell is a single row, not a two-line stack
 *   3. the row ends in the mock's `›` chevron
 *   4. the 最近のテスト heading carries すべて見る
 *   5. the KPI number resolves larger than the panel heading
 */

function readFontTokens(): Record<string, number> {
  const css = fs.readFileSync(
    path.resolve(
      import.meta.dirname,
      "../../src/renderer/styles/design-tokens.css",
    ),
    "utf8",
  );
  const tokens: Record<string, number> = {};
  for (const match of css.matchAll(/--font-size-([a-z-]+):\s*(\d+)px/g)) {
    tokens[`--font-size-${match[1]}`] = Number(match[2]);
  }
  return tokens;
}

/** Resolve a `calc(var(--token) * n)` inline font-size to px. */
function calcFontPx(
  styleValue: string,
  tokens: Record<string, number>,
): number {
  const varMatch = /var\((--font-size-[a-z-]+)\)/.exec(styleValue);
  const multiplier = /([0-9.]+)/.exec(styleValue.replace(/.*\*\s*/, ""));
  const token = varMatch?.[1];
  const factor = multiplier?.[1];
  if (token === undefined || factor === undefined) {
    throw new Error(`unparsable font-size: ${styleValue}`);
  }
  const base = tokens[token];
  if (base === undefined) {
    throw new Error(`unknown token: ${token}`);
  }
  return base * Number(factor);
}

function renderDashboard() {
  return renderAppAt(AppRoutes.home, {
    handlers: {
      listTestRegistrations: async () => [
        buildTest({ id: "t1", name: "国語 第1回" }),
      ],
      listSubmissions: async () => [
        buildSubmission({ id: "s1", testId: "t1", state: "needs_review" }),
        buildSubmission({ id: "s2", testId: "t1", state: "ai_processed" }),
      ],
      listReviewProgress: async () => [
        buildProgress({ id: "s1", total: 5, confirmed: 3 }),
        buildProgress({ id: "s2", total: 3, confirmed: 0 }),
      ],
    },
  });
}

describe("home layout (Issue #360)", () => {
  it("puts 全体の進捗 and テストの進捗 side by side in one grid", async () => {
    renderDashboard();

    await screen.findByTestId("home-test-card-t1");
    const progressPanel = screen.getByTestId("home-progress-panel");
    const donutPanel = screen.getByTestId("home-tests-panel");
    const progressCell = progressPanel.parentElement;
    const donutCell = donutPanel.parentElement;

    // Same grid, different cells: the single 784px column is gone.
    expect(progressCell).not.toBeNull();
    expect(donutCell).not.toBeNull();
    expect(progressCell).not.toBe(donutCell);
    expect(progressCell?.parentElement).toBe(donutCell?.parentElement);
    const grid = progressCell?.parentElement;
    // Issue 375 item 12: an even split narrows the progress card enough that
    // its four KPI columns approach the mock's 128px pitch (was 3:2).
    expect(grid?.className).toContain("lg:grid-cols-2");
  });

  it("keeps the 進捗 cell on one row: link, bar and % share a parent", async () => {
    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByTestId("home-test-progress-percent-t1").textContent,
      ).toBe("38%");
    });
    const queue = screen.getByTestId("home-open-queue-t1");
    const row = queue.parentElement;
    expect(row).not.toBeNull();
    // A two-line stack is exactly the `flex-col` the old cell used.
    expect(row?.className).not.toContain("flex-col");
    expect(row?.className).toContain("whitespace-nowrap");
    expect(row?.contains(screen.getByTestId("home-test-progress-t1"))).toBe(
      true,
    );
    expect(
      row?.contains(screen.getByTestId("home-test-progress-percent-t1")),
    ).toBe(true);
  });

  it("ends every recent-test row with a chevron", async () => {
    renderDashboard();

    const row = await screen.findByTestId("home-test-card-t1");
    expect(row.querySelector(".lucide-chevron-right")).not.toBeNull();
    // The chevron doubles as the "continue" entry point kept from #336.
    expect(screen.getByTestId("home-resume-review-t1")).toBeDefined();
  });

  it("shows すべて見る next to the 最近のテスト heading", async () => {
    renderDashboard();

    await screen.findByTestId("home-test-card-t1");
    const seeAll = screen.getByTestId("home-open-all-tests");
    expect(seeAll.textContent).toBe("すべて見る");
  });

  it("renders the KPI number larger than the 全体の進捗 heading", async () => {
    renderDashboard();

    const kpi = await screen.findByTestId("home-bucket-needsReview");
    const heading = screen
      .getByTestId("home-progress-panel")
      .querySelector("h2");
    expect(heading).not.toBeNull();

    const tokens = readFontTokens();
    const kpiPx = calcFontPx(kpi.style.fontSize, tokens);
    const headingPx = calcFontPx(heading?.style.fontSize ?? "", tokens);
    expect(kpiPx).toBeGreaterThan(headingPx);
  });
});
