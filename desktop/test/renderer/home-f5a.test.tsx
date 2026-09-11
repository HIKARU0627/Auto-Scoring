import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import {
  SIDEBAR_PRODUCT_NAME,
  SIDEBAR_TEST_ID,
} from "../../src/renderer/navigation/Sidebar.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue #371 (stage F5A, parent #333) text hierarchy,
 * accent contrast, glyph unification and 1px rules.
 *
 * jsdom cannot lay out pixels, so the pixel-measured values (50px rule, donut
 * placement, brand size) are pinned by the token/class the build must produce;
 * `theme-contrast-f5a.test.ts` pins the ratios numerically.
 */

function handlers(): MockSidecarHandlers {
  return {
    listTestRegistrations: async () => [
      buildTest({ id: "t1", name: "国語 第1回" }),
    ],
    listSubmissions: async () => [
      buildSubmission({ id: "s1", testId: "t1", state: "needs_review" }),
    ],
    listReviewProgress: async () => [
      buildProgress({ id: "s1", total: 5, confirmed: 3 }),
    ],
  };
}

async function renderHome() {
  const result = renderAppAt(AppRoutes.home, { handlers: handlers() });
  await screen.findByTestId("home-test-card-t1");
  return result;
}

function glyphD(testId: string): string | null {
  return (
    screen.getByTestId(testId).querySelector("svg path")?.getAttribute("d") ??
    null
  );
}

describe("home F5A: accent text token (Issue #371 item 1)", () => {
  it("paints 次の一手 with the accent-text token, not the fill", async () => {
    await renderHome();
    const accent = screen.getByText("次の一手");
    expect(accent.classList.contains("text-primary-text")).toBe(true);
    expect(accent.classList.contains("text-primary")).toBe(false);
  });
});

describe("home F5A: secondary text and headings (Issue #371 items 2-3)", () => {
  it("uses the strong tier for the hero body and the muted tier for axis labels", async () => {
    const { container } = await renderHome();
    await waitFor(() => {
      expect(
        container.querySelector(".recharts-cartesian-axis-tick-value"),
      ).not.toBeNull();
    });

    const hero = screen.getByTestId("home-next-up");
    const body = hero.querySelector("p.text-on-surface-strong");
    expect(
      body,
      `hero body must use the strong secondary tier: ${hero.innerHTML}`,
    ).not.toBeNull();

    const ticks = Array.from(
      container.querySelectorAll(".recharts-cartesian-axis-tick-value"),
    );
    expect(ticks.length).toBeGreaterThan(0);
    for (const tick of ticks) {
      expect(tick.getAttribute("fill")).toBe("var(--color-on-surface-muted)");
    }
  });

  it("paints every card heading with the heading token", async () => {
    await renderHome();
    for (const testId of [
      "home-progress-panel",
      "home-tests-panel",
      "home-quick-actions",
    ]) {
      const heading = screen.getByTestId(testId).querySelector("h2");
      expect(
        heading?.classList.contains("text-heading"),
        `${testId} heading must use text-heading`,
      ).toBe(true);
    }
  });
});

describe("home F5A: one glyph per destination (Issue #371 item 5)", () => {
  it("renders the quick actions and hero with the sidebar silhouettes", async () => {
    await renderHome();
    expect(glyphD("home-open-intake")).toBe(glyphD("sidebar-nav-intake"));
    expect(glyphD("home-open-test-list-footer")).toBe(
      glyphD("sidebar-nav-tests"),
    );
    expect(glyphD("home-open-settings")).toBe(glyphD("sidebar-nav-settings"));
    // The hero tile repeats the document glyph, as the mock draws it.
    expect(
      screen
        .getByTestId("home-next-up")
        .querySelector("svg path")
        ?.getAttribute("d"),
    ).toBe(glyphD("sidebar-nav-intake"));
  });

  it("keeps the quick-action glyphs filled silhouettes", async () => {
    await renderHome();
    for (const testId of [
      "home-open-intake",
      "home-open-test-list-footer",
      "home-open-settings",
    ]) {
      const svg = screen.getByTestId(testId).querySelector("svg");
      expect(svg?.getAttribute("fill")).toBe("currentColor");
      expect(svg?.getAttribute("stroke")).toBeNull();
    }
  });
});

describe("home F5A: brand size (Issue #371 item 6)", () => {
  it("drops the wordmark to the mock's 15-17px band", async () => {
    await renderHome();
    const brand = within(screen.getByTestId(SIDEBAR_TEST_ID)).getByText(
      SIDEBAR_PRODUCT_NAME,
    );
    expect(brand.className).toContain(
      "text-[length:var(--font-size-title-medium)]",
    );
    expect(brand.className).not.toContain(
      "text-[length:var(--font-size-title-large)]",
    );
  });
});

describe("home F5A: 1px chart rules (Issue #371 item 7)", () => {
  it("snaps the grid and baseline strokes to integer pixels", async () => {
    const { container } = await renderHome();
    await waitFor(() => {
      expect(
        container.querySelectorAll(".recharts-cartesian-grid-horizontal line")
          .length,
      ).toBeGreaterThanOrEqual(2);
    });

    const gridLines = Array.from(
      container.querySelectorAll(".recharts-cartesian-grid-horizontal line"),
    );
    for (const line of gridLines) {
      expect(line.getAttribute("shape-rendering")).toBe("crispEdges");
    }
    const axisLine = container.querySelector(".recharts-cartesian-axis-line");
    expect(axisLine?.getAttribute("shape-rendering")).toBe("crispEdges");
  });
});

describe("home F5A: donut card header parity (Issue #371 item 9)", () => {
  it("gives the donut the same static label treatment as the progress card", async () => {
    await renderHome();
    const donutHeader = screen
      .getByTestId("home-tests-panel")
      .querySelector("h2")?.parentElement;
    const progressHeader = screen
      .getByTestId("home-progress-panel")
      .querySelector("h2")?.parentElement;
    expect(progressHeader?.className).toContain("justify-between");
    expect(donutHeader?.className).toContain("justify-between");

    const donutLabel = Array.from(
      screen.getByTestId("home-tests-panel").querySelectorAll("span"),
    ).find((node) => node.textContent === "全テスト");
    expect(
      donutLabel,
      "donut card must carry a static 全テスト label",
    ).toBeDefined();
    expect(donutLabel?.className).toContain("text-on-surface-variant");
    // No dropdown affordance: the label is text, not a chevron-bearing control.
    expect(
      screen.getByTestId("home-tests-panel").querySelectorAll("button"),
    ).toHaveLength(0);
  });
});

describe("home F5A: narrow-width donut and quick actions (Issue #371 items 10-11)", () => {
  it("moves the donut legend beside the ring below lg", async () => {
    await renderHome();
    const chart = screen.getByTestId("home-phase-chart");
    expect(chart.className).toContain("max-lg:flex-row");
    expect(chart.className).toContain("max-lg:items-center");
    expect(screen.getByTestId("home-phase-legend").className).toContain(
      "max-lg:flex-1",
    );
  });

  it("folds the quick-action rows into two columns while the card is wide", async () => {
    await renderHome();
    const list = screen.getByTestId("home-quick-actions").querySelector("div");
    expect(list?.className).toContain("sm:grid-cols-2");
    expect(list?.className).toContain("lg:grid-cols-1");
  });
});
