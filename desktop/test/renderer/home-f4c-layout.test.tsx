import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue #367 (F4C) home layout, parent #333.
 *
 * jsdom does not lay out pixels, so each test pins the literal the mock and
 * the 1536x1024 / 700x720 screenshots measured: the 32px page gutter, the
 * 360px right rail, the 21px main-column card pitch, the ~48px hero CTA and the
 * full-width 最近のテスト row. The PR's mutation table breaks each literal and
 * names the test that goes red.
 *
 * The horizontal-overflow check cannot measure `scrollWidth` in jsdom, so it
 * pins the property that caused the 700px page scroll instead: an absolutely
 * positioned, visually hidden node must be clipped by a *positioned* ancestor.
 * The table's `overflow-x-auto` wrapper is not positioned, which is why the
 * table's `.sr-only` widened the document before this issue.
 */

function renderDashboard() {
  return renderAppAt(AppRoutes.home, {
    handlers: {
      listTestRegistrations: async () => [
        buildTest({ id: "t1", name: "国語 第1回" }),
      ],
      listSubmissions: async () => [
        buildSubmission({ id: "s1", testId: "t1", state: "needs_review" }),
      ],
      listReviewProgress: async () => [
        buildProgress({ id: "s1", total: 5, confirmed: 3 }),
      ],
    },
  });
}

const POSITIONED = new Set(["relative", "absolute", "fixed", "sticky"]);
const CLIPPING = new Set([
  "overflow-clip",
  "overflow-x-clip",
  "overflow-hidden",
  "overflow-x-hidden",
  "overflow-auto",
  "overflow-x-auto",
  "overflow-scroll",
  "overflow-x-scroll",
]);

/** True when a positioned, clipping ancestor contains `node` within `root`. */
function hasPositionedClipAncestor(node: Element, root: Element): boolean {
  let current = node.parentElement;
  while (current !== null && current !== root.parentElement) {
    const classes = new Set(current.className.split(/\s+/));
    const positioned = [...classes].some((name) => POSITIONED.has(name));
    const clips = [...classes].some((name) => CLIPPING.has(name));
    if (positioned && clips) {
      return true;
    }
    current = current.parentElement;
  }
  return false;
}

describe("home F4C layout: page gutter and rail width (Issue #367)", () => {
  it("uses the measured 32px page gutter (px-sm) on the header and main", async () => {
    renderDashboard();
    await screen.findByTestId("home-test-card-t1");

    const board = screen.getByTestId("home-page");
    const header = board.querySelector("header");
    const main = board.querySelector("main");
    for (const region of [header, main]) {
      expect(region?.className).toContain("px-sm");
      expect(region?.className).not.toContain("px-xl");
    }
  });

  it("returns the right rail to the mock's 360px (lg:w-90)", async () => {
    renderDashboard();
    await screen.findByTestId("home-test-card-t1");

    const rail = screen.getByTestId("home-quick-actions").parentElement;
    expect(rail?.className).toContain("lg:w-90");
    expect(rail?.className).not.toContain("lg:max-w-80");
  });
});

describe("home F4C layout: full-width recent tests (Issue #367)", () => {
  it("moves 最近のテスト out of the main column to a row below it", async () => {
    renderDashboard();
    await screen.findByTestId("home-test-card-t1");

    const table = screen.getByTestId("home-recent-tests");
    const leftColumn = screen.getByTestId("home-next-up").parentElement;
    const row = leftColumn?.parentElement;
    expect(leftColumn).not.toBeNull();
    expect(row).not.toBeNull();

    // It is no longer stacked in the main column...
    expect(leftColumn?.contains(table)).toBe(false);
    // ...and not in the quick-action rail either...
    expect(
      screen.getByTestId("home-quick-actions").parentElement?.contains(table),
    ).toBe(false);
    // ...it is the full-width row immediately under the hero + graph row.
    expect(row?.nextElementSibling).toBe(table);
  });

  it("tightens the main-column card pitch to the mock's 21px", async () => {
    renderDashboard();
    await screen.findByTestId("home-test-card-t1");

    const leftColumn = screen.getByTestId("home-next-up").parentElement;
    const dashboardBody = leftColumn?.parentElement?.parentElement;
    expect(leftColumn?.style.gap).toBe("21px");
    expect(dashboardBody?.style.gap).toBe("21px");
  });
});

describe("home F4C layout: hero CTA height (Issue #367)", () => {
  it("raises the hero CTA to the mock's 48px minimum", async () => {
    renderDashboard();
    await screen.findByTestId("home-next-up-action");

    expect(screen.getByTestId("home-next-up-action").className).toContain(
      "min-h-12",
    );
  });
});

describe("home F4C layout: horizontal overflow guard (Issue #367)", () => {
  it("clips visually hidden absolutely positioned nodes inside the content", async () => {
    renderDashboard();
    await screen.findByTestId("home-test-card-t1");

    const board = screen.getByTestId("home-page");
    const main = board.querySelector("main");
    expect(main).not.toBeNull();
    // The guard has to be both the containing block (`relative`) and the
    // clipper (`overflow-x-clip`); either alone leaves the .sr-only free.
    expect(main?.className).toContain("relative");
    expect(main?.className).toContain("overflow-x-clip");

    const srOnly = Array.from(board.querySelectorAll(".sr-only"));
    expect(srOnly.length).toBeGreaterThan(0);
    for (const node of srOnly) {
      expect(
        hasPositionedClipAncestor(node, board),
        `${node.textContent?.trim() || node.tagName} must be clipped by a positioned ancestor`,
      ).toBe(true);
    }
  });
});
