import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildProgress,
  buildSubmission,
  buildTest,
} from "./support/mock-sidecar-client.js";
import { readThemeTokens, tokenHex } from "../support/read-design-tokens";

/**
 * Regression tests for Issue #375 (stage F6, parent #333): the quick actions
 * move back beside the hero so 最近のテスト fits at 1536x1024, and the
 * pixel-diffs the sixth-round evaluation measured are pinned.
 *
 * jsdom lays out no pixels, so each test pins the class/token literal the
 * implementation must produce. The PR's mutation table breaks each literal and
 * names the test that goes red.
 *
 * The pixel-level facts that cannot be asserted here (the table header landing
 * at y=859 < 900, the 95px plot, the 28px integer-placebar bar) are recorded in
 * the PR body from the Electron probe.
 */

function handlers() {
  return {
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
  };
}

const DAY_MS = 86_400_000;

/** A submission dated `daysAgo` days before noon today, so a bar is drawn. */
function submissionDaysAgo(id: string, state: string, daysAgo: number) {
  const noon = new Date();
  noon.setHours(12, 0, 0, 0);
  return {
    ...buildSubmission({ id, testId: "t1", state }),
    created_at: new Date(noon.getTime() - daysAgo * DAY_MS).toISOString(),
  };
}

async function renderHome() {
  const result = renderAppAt(AppRoutes.home, { handlers: handlers() });
  await screen.findByTestId("home-test-card-t1");
  return result;
}

describe("home F6: quick actions return beside the hero (Issue #375 item 1)", () => {
  it("shares one grid row with the hero and leaves the table under both rows", async () => {
    await renderHome();
    const hero = screen.getByTestId("home-next-up");
    const quickActions = screen.getByTestId("home-quick-actions");
    const heroRow = hero.parentElement?.parentElement;
    const content = heroRow?.parentElement;

    // Hero and quick actions are two cells of the same row.
    expect(hero.parentElement).not.toBe(quickActions.parentElement);
    expect(heroRow).toBe(quickActions.parentElement?.parentElement);
    expect(heroRow?.className).toContain("lg:grid-cols-3");
    expect(hero.parentElement?.className).toContain("lg:col-span-2");
    // The graph cards are the next row; the table is the row after both.
    expect(heroRow?.contains(screen.getByTestId("home-progress-panel"))).toBe(
      false,
    );
    expect(content?.nextElementSibling).toBe(
      screen.getByTestId("home-recent-tests"),
    );
  });
});

describe("home F6: page and card heading hierarchy (Issue #375 items 6-8)", () => {
  it("paints the page heading with the heading token at 1.5x the headline scale", async () => {
    await renderHome();
    const title = screen.getByTestId("page-title");
    expect(title.classList.contains("text-heading")).toBe(true);
    expect(title.classList.contains("text-on-surface")).toBe(false);
    expect(title.style.fontSize).toBe(
      "calc(var(--font-size-headline-large) * 1.5)",
    );
  });

  it("paints 最近のテスト with the heading token like the other three cards", async () => {
    await renderHome();
    for (const testId of [
      "home-progress-panel",
      "home-tests-panel",
      "home-quick-actions",
      "home-recent-tests",
    ]) {
      const heading = screen.getByTestId(testId).querySelector("h2");
      expect(
        heading?.classList.contains("text-heading"),
        `${testId} heading must use text-heading`,
      ).toBe(true);
    }
  });
});

describe("home F6: accent link uses the accent-text token (Issue #375 item 5)", () => {
  it("does not put the fill purple on すべて見る or the queue link", async () => {
    await renderHome();
    const seeAll = screen.getByTestId("home-open-all-tests");
    expect(seeAll.classList.contains("text-primary-text")).toBe(true);
    expect(seeAll.classList.contains("text-primary")).toBe(false);

    const queue = screen.getByTestId("home-open-queue-t1");
    expect(queue.classList.contains("text-primary-text")).toBe(true);
    expect(queue.classList.contains("text-primary")).toBe(false);
  });
});

describe("home F6: hero group removes the dead space (Issue #375 item 10)", () => {
  it("keeps the tile and text in one left group with only the CTA pushed right", async () => {
    await renderHome();
    const hero = screen.getByTestId("home-next-up");
    const inner = hero.firstElementChild;
    expect(inner?.className).not.toContain("justify-between");
    expect(inner?.className).not.toContain("md:max-w-112");
    // First child is the icon+text group; the CTA is its sibling.
    const group = inner?.firstElementChild;
    expect(group?.className).toContain("flex-1");
    expect(group?.className).toContain("items-center");
    expect(group?.contains(hero.querySelector("h2"))).toBe(true);
    expect(group?.contains(screen.getByTestId("home-next-up-action"))).toBe(
      false,
    );
  });
});

describe("home F6: KPI number alignment (Issue #375 item 12)", () => {
  it("indents the number to the label text, not the tone dot", async () => {
    await renderHome();
    const number = screen.getByTestId("home-bucket-needsReview");
    expect(number.style.paddingLeft).toBe("var(--spacing-xl)");
  });
});

describe("home F6: daily bars are drawn square (Issue #375 item 13)", () => {
  it("draws every bar rect with rx=0 so the top edge stays flat", async () => {
    const { container } = renderAppAt(AppRoutes.home, {
      handlers: {
        listTestRegistrations: async () => [buildTest({ id: "t1" })],
        listSubmissions: async () => [
          submissionDaysAgo("a", "needs_review", 0),
          submissionDaysAgo("b", "ai_processed", 0),
        ],
      },
    });
    const bars = await waitFor(() => {
      const found = Array.from(
        container.querySelectorAll<SVGRectElement>(
          '[data-testid^="home-daily-bar"]',
        ),
      );
      expect(found.length).toBeGreaterThan(0);
      return found;
    });
    for (const bar of bars) {
      expect(bar.getAttribute("rx")).toBe("0");
    }
  });
});

describe("home F6: plot height is floored at the mock's 95px (Issue #375 item 14)", () => {
  it("uses the min-h-bar-plot utility backed by a 95px token", async () => {
    const { container } = await renderHome();
    const plot = container.querySelector('[data-testid="home-daily-plot"]');
    expect(plot?.className).toContain("min-h-bar-plot");
    expect(plot?.className).not.toContain("min-h-36");
    expect(tokenHex(readThemeTokens("dark"), "--layout-bar-plot-height")).toBe(
      "95px",
    );
  });
});

describe("home F6: sunk 準備中 grey (Issue #375 item 15)", () => {
  it("paints the preparing sector and legend dot with the sunk token", async () => {
    await renderHome();
    const preparing = screen.getByTestId("home-phase-preparing");
    const dot = preparing.querySelector("span");
    expect(dot?.getAttribute("style")).toContain(
      "var(--color-phase-preparing)",
    );
    for (const theme of ["dark", "light"] as const) {
      expect(
        tokenHex(readThemeTokens(theme), "--color-phase-preparing"),
      ).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});

describe("home F6: AppShell frame no longer forces the window height (Issue #375 item 4)", () => {
  it("keeps bg-surface but drops min-h-screen from the shell frame", async () => {
    const { container } = await renderHome();
    const frame = container.firstElementChild;
    expect(frame).not.toBeNull();
    expect(frame?.className).toContain("bg-surface");
    expect(frame?.className).not.toContain("min-h-screen");
    expect(screen.getByTestId("home-page").className).not.toContain(
      "min-h-full",
    );
  });
});
