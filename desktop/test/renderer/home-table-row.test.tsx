import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue 365 recent-tests row (parent Issue 333).
 *
 * jsdom does not lay out pixels, so every assertion pins the literal the mock
 * measured at 1536x1024: the 140px progress track, the 25px status pill, the
 * body-weight name and its 9rem cap. The PR's mutation table breaks each
 * literal and names the test that goes red.
 */

function tableHandlers(
  overrides: Partial<MockSidecarHandlers> = {},
): MockSidecarHandlers {
  return {
    listTestRegistrations: async () => [
      buildTest({ id: "t1", name: "国語 第1回" }),
    ],
    listSubmissions: async () => [
      buildSubmission({ id: "s1", testId: "t1", state: "reviewed" }),
      buildSubmission({ id: "s2", testId: "t1", state: "needs_review" }),
    ],
    listReviewProgress: async () => [
      buildProgress({ id: "s1", total: 8, confirmed: 3 }),
    ],
    ...overrides,
  };
}

describe("home recent-tests row: progress track (Issue 365)", () => {
  it("holds the mock's 140px track and keeps 確認済み out of the visible cell", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });

    const track = await screen.findByTestId("home-test-progress-t1");
    expect(track.style.width).toBe("8.75rem");
    expect(track.getAttribute("aria-valuenow")).toBe("3");
    expect(track.getAttribute("aria-valuemax")).toBe("8");
    expect(
      screen.getByTestId("home-test-progress-percent-t1").textContent,
    ).toBe("38%");

    // The queue entry stays reachable: the whole track + percent area is the
    // button and 確認済み N / M is kept as its accessible name, while the old
    // visible cell text (which squeezed the track to 56px) is gone.
    const button = screen.getByTestId("home-open-queue-t1");
    expect(button.getAttribute("aria-label")).toBe("確認済み 1 / 2");
    const clone = button.cloneNode(true) as HTMLElement;
    clone.querySelectorAll(".sr-only").forEach((node) => node.remove());
    expect(clone.textContent?.replace(/\s+/g, "")).toBe("38%");
  });
});

describe("home recent-tests row: one line (Issue 365)", () => {
  it("keeps the status pill at the mock's 25px", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });

    const pill = await screen.findByTestId("home-test-status-t1");
    expect(pill.style.height).toBe("25px");
    expect(pill.className).toContain("items-center");
  });

  it("puts the bucket counts beside the pill instead of under it", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });

    const pill = await screen.findByTestId("home-test-status-t1");
    const statusCell = pill.closest("td");
    expect(statusCell).not.toBeNull();
    // The auxiliary count shares the pill's line, so the row stays one line.
    expect(statusCell?.textContent).toContain("要確認 1件");
    expect(pill.parentElement?.className).toContain("flex");
    expect(pill.parentElement?.className).not.toContain("flex-col");

    // Nothing in the row stacks vertically any more (the old `mt-xs` block
    // under the name is what made the mock's 43px row 57px tall).
    const row = screen.getByTestId("home-test-card-t1");
    expect(row.querySelectorAll(".flex-col, .mt-xs")).toHaveLength(0);
  });

  it("uses the compact vertical padding on every cell so the row stays 43px", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });

    const row = await screen.findByTestId("home-test-card-t1");
    for (const cell of Array.from(row.children)) {
      expect(cell.className, `${cell.tagName} must use py-sm`).toContain(
        "py-sm",
      );
      expect(cell.className).not.toContain("py-md");
    }
  });
});

describe("home recent-tests row: name cell (Issue 365)", () => {
  it("renders the test name at body weight instead of bold", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });

    const name = await screen.findByTestId("home-test-name-t1");
    expect(name.className).toContain("font-normal");
    expect(name.className).not.toContain("font-medium");
  });

  it("caps and ellipsizes the name so it cannot squeeze the status column", async () => {
    const longName =
      "とても長いテスト名がここに入り、狭い画面でもレイアウトを壊さないことを確かめるための名前";
    renderAppAt(AppRoutes.home, {
      handlers: tableHandlers({
        listTestRegistrations: async () => [
          buildTest({ id: "t1", name: longName }),
        ],
      }),
    });

    const name = await screen.findByTestId("home-test-name-t1");
    expect(name.className).toContain("truncate");
    expect(name.style.maxWidth).toBe("9rem");
    expect(name.getAttribute("title")).toBe(longName);
  });
});
