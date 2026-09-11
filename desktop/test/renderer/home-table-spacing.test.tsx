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
 * Regression tests for the Issue #372 recent-tests table (parent Issue 333).
 *
 * The measured values come from the mock `UI_Home.png` and the 1536x1024 /
 * 700x1900 screenshots. jsdom lays out no pixels, so each test pins the value
 * the implementation must produce rather than a rendered size:
 *   1. the column widths and the answer column's left alignment
 *   2. the name has no fixed cap (covered in `home-table-row.test.tsx`)
 *   3. the 700px layout is one block per test, not a clipped table
 *   4. the status pill's `px-lg` horizontal padding, 25px height
 *   5. the header rule uses the lighter `border-chart-axis` token
 *   6. the quick actions are folded into the body flow as `lg` tiles
 *   7. no `overflow-x-auto` (the bright native scrollbar) anywhere in the card
 *   8. there is no fixed-width right rail left behind
 *
 * The PR's mutation table breaks each value and names the test that goes red.
 */

function tableHandlers() {
  return {
    listTestRegistrations: async () => [
      buildTest({ id: "t1", name: "物理_添削模擬課題" }),
    ],
    listSubmissions: async () => [
      buildSubmission({ id: "s1", testId: "t1", state: "needs_review" }),
    ],
    listReviewProgress: async () => [
      buildProgress({ id: "s1", total: 4, confirmed: 1 }),
    ],
  };
}

/** Pins the window to `width` and restores it (plus any listener) after. */
function withViewport(width: number, height: number): () => void {
  const originalWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");
  const originalHeight = Object.getOwnPropertyDescriptor(window, "innerHeight");
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: width,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: height,
  });
  window.dispatchEvent(new Event("resize"));
  return () => {
    if (originalWidth !== undefined) {
      Object.defineProperty(window, "innerWidth", originalWidth);
    }
    if (originalHeight !== undefined) {
      Object.defineProperty(window, "innerHeight", originalHeight);
    }
    window.dispatchEvent(new Event("resize"));
  };
}

describe("home recent-tests columns (Issue #372 §1)", () => {
  it("stays within a 100% split and no longer uses the content-column widths", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-card-t1");

    const headers = Array.from(
      screen
        .getByTestId("home-recent-tests")
        .querySelectorAll<HTMLTableCellElement>("thead th"),
    );
    expect(headers.map((th) => th.style.width)).toEqual([
      "21%",
      "23%",
      "11%",
      "22%",
      "16%",
      "7%",
    ]);
    // The old content-column classes are gone (`w-1/6` / `w-16` / `w-1/3` /
    // `w-20` / `w-10`), which were the source of the 380px 進捗 gap.
    const headerClasses = headers.map((th) => th.className).join(" ");
    for (const stale of ["w-1/6", "w-16", "w-1/3", "w-20", "w-10"]) {
      expect(headerClasses).not.toContain(stale);
    }
  });

  it("left-aligns 答案数 so its header is not 50px from 進捗", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-card-t1");

    const headers = Array.from(
      screen
        .getByTestId("home-recent-tests")
        .querySelectorAll<HTMLTableCellElement>("thead th"),
    );
    const answerHeader = headers[2];
    expect(answerHeader?.textContent).toBe("答案数");
    expect(answerHeader?.className).toContain("text-left");
    expect(answerHeader?.className).not.toContain("text-right");

    const answerCell = screen.getByTestId("home-test-card-t1").children[2];
    expect(answerCell?.className).toContain("text-left");
    expect(answerCell?.className).not.toContain("text-right");
  });
});

describe("home recent-tests status pill (Issue #372 §4)", () => {
  it("uses the mock's 73px pill padding while keeping the 25px height", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-status-t1");

    const pill = screen.getByTestId("home-test-status-t1");
    // `px-sm` (8px) rendered 58px wide against the mock's 73px; `px-lg` (16px)
    // is the token that lands on the measured ~14px side padding.
    expect(pill.className).toContain("px-lg");
    expect(pill.className).not.toContain("px-sm");
    expect(pill.style.height).toBe("25px");
  });
});

describe("home recent-tests header rule (Issue #372 §5)", () => {
  it("draws the header rule with the lighter chart-axis token", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-card-t1");

    const row = screen.getByTestId("home-test-card-t1");
    // The mock's rule is (49,56,78) = `--color-chart-axis`; `outline-variant`
    // measured (61,70,94) and read too heavy.
    expect(row.className).toContain("border-chart-axis");
    expect(row.className).not.toContain("border-outline-variant");
  });
});

describe("home recent-tests narrow layout (Issue #372 §3/§7)", () => {
  it("switches to one block per test so nothing is hidden or collides at 700px", async () => {
    const restore = withViewport(700, 720);
    try {
      renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
      await screen.findByTestId("home-test-card-t1");

      const card = screen.getByTestId("home-test-card-t1");
      // A table row would be `TR`; the block layout is `LI`.
      expect(card.tagName).toBe("LI");
      // No table and no horizontal scroller: at 700px the table hid ~150px of
      // columns (including 最終更新) behind the page's brightest scrollbar.
      const region = screen.getByTestId("home-recent-tests");
      expect(region.querySelector("table")).toBeNull();
      expect(region.querySelector(".overflow-x-auto")).toBeNull();
      // Every column the table shows stays visible, 最終更新 included.
      expect(screen.getByTestId("home-test-status-t1")).toBeDefined();
      expect(screen.getByTestId("home-test-answer-t1")).toBeDefined();
      expect(screen.getByTestId("home-test-updated-t1").textContent).toContain(
        "最終更新",
      );
      // The queue / resume entry points the E2E probes use survive the switch.
      expect(screen.getByTestId("home-open-queue-t1")).toBeDefined();
      expect(screen.getByTestId("home-resume-review-t1")).toBeDefined();
    } finally {
      restore();
    }
  });

  it("goes back to the table when the window is widened", async () => {
    const restore = withViewport(700, 720);
    try {
      renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
      await screen.findByTestId("home-test-card-t1");
      expect(screen.getByTestId("home-test-card-t1").tagName).toBe("LI");
    } finally {
      restore();
    }

    await waitFor(() => {
      expect(screen.getByTestId("home-test-card-t1").tagName).toBe("TR");
    });
  });
});

describe("home dashboard quick actions (Issue #372 §6/§8)", () => {
  it("folds the quick actions into the main flow as lg tiles", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-card-t1");

    const quickActions = screen.getByTestId("home-quick-actions");
    const wrapper = quickActions.parentElement;
    expect(wrapper?.className).toContain("[&>section>div]:grid");
    expect(wrapper?.className).toContain("lg:[&>section>div]:grid-cols-3");
  });

  it("leaves no fixed-width right rail behind", async () => {
    renderAppAt(AppRoutes.home, { handlers: tableHandlers() });
    await screen.findByTestId("home-test-card-t1");

    const quickActions = screen.getByTestId("home-quick-actions");
    // The old rail wrapper carried `lg:w-90`; folding it is what removes the
    // 360x279px bare-surface hole under a stranded quick-action card.
    for (
      let node: HTMLElement | null = quickActions.parentElement;
      node !== null;
      node = node.parentElement
    ) {
      expect(node.className).not.toContain("lg:w-90");
    }
    // It sits in the same column as the hero, above the table in the flow.
    expect(quickActions.parentElement?.parentElement).toBe(
      screen.getByTestId("home-next-up").parentElement,
    );
  });
});
