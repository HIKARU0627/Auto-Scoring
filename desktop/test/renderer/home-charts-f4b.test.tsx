import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildSubmission,
  buildTest,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Regression tests for the Issue #366 chart details (parent #333, stage F4B).
 *
 * Every assertion names a value the implementation must produce, so the
 * mutation list in the PR turns the matching test red. Recharts draws SVG, so
 * the grid lines, the two bar series and the donut arcs are real DOM nodes.
 */

const DAY_MS = 86_400_000;

/** A submission dated `daysAgo` days before noon today. */
function submissionDaysAgo(input: {
  id: string;
  state: string;
  daysAgo: number;
}): ReturnType<typeof buildSubmission> {
  const noon = new Date();
  noon.setHours(12, 0, 0, 0);
  return {
    ...buildSubmission({ id: input.id, testId: "t1", state: input.state }),
    created_at: new Date(noon.getTime() - input.daysAgo * DAY_MS).toISOString(),
  };
}

function barElements(container: HTMLElement): Element[] {
  return Array.from(
    container.querySelectorAll("[data-testid='home-daily-bar']"),
  );
}

function renderCharts(handlers: MockSidecarHandlers) {
  return renderAppAt(AppRoutes.home, { handlers });
}

describe("home charts: grid and baseline (Issue #366 item 1)", () => {
  it("draws the dark grid lines and the brighter zero baseline from tokens", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => [
        submissionDaysAgo({ id: "a", state: "reviewed", daysAgo: 0 }),
      ],
    });

    await waitFor(() => {
      expect(barElements(container)).toHaveLength(7);
    });

    const gridLines = Array.from(
      container.querySelectorAll(".recharts-cartesian-grid-horizontal line"),
    );
    // The mock has two dark grid lines under the top of the plot.
    expect(gridLines.length).toBeGreaterThanOrEqual(2);
    for (const line of gridLines) {
      expect(line.getAttribute("stroke")).toBe("var(--color-chart-grid)");
    }
    // The 0 axis is the bright baseline, not one of the dark grid lines.
    const axisLine = container.querySelector(".recharts-cartesian-axis-line");
    expect(axisLine).not.toBeNull();
    expect(axisLine?.getAttribute("stroke")).toBe("var(--color-chart-axis)");
  });
});

describe("home charts: two-layer bar (Issue #366 item 2)", () => {
  it("stacks the confirmed answers over the still-open ones", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => [
        submissionDaysAgo({ id: "a", state: "reviewed", daysAgo: 0 }),
        submissionDaysAgo({ id: "b", state: "exported", daysAgo: 0 }),
        submissionDaysAgo({ id: "c", state: "reviewed", daysAgo: 0 }),
        submissionDaysAgo({ id: "d", state: "needs_review", daysAgo: 0 }),
      ],
    });

    await waitFor(() => {
      expect(barElements(container)).toHaveLength(7);
    });

    const bars = barElements(container);
    const total = bars.find((bar) => bar.getAttribute("data-count") === "4");
    expect(total).toBeDefined();
    expect(total?.getAttribute("data-done-count")).toBe("3");

    const open = container.querySelector("[data-testid='home-daily-bar-open']");
    expect(open).not.toBeNull();
    const totalHeight = Number(total?.getAttribute("height"));
    const openHeight = Number(open?.getAttribute("height"));
    // 3 confirmed / 1 open: the top (open) segment is a quarter of the total.
    expect(openHeight / totalHeight).toBeCloseTo(0.25, 2);
    // The open series sits on top of the confirmed one, not beside it.
    expect(open?.getAttribute("y")).toBe(total?.getAttribute("y"));

    // The split is readable as text too, so colour is not the only carrier.
    expect(screen.getByTestId("home-daily-chart").textContent ?? "").toContain(
      "確認済み3件",
    );
  });
});

describe("home charts: KPI column rules (Issue #366 item 3)", () => {
  it("rules the KPI columns apart with a token stroke", async () => {
    renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => [],
    });

    await screen.findByTestId("home-bucket-done");
    const cells = Array.from(
      screen.getByTestId("home-progress-panel").querySelectorAll("dl > div"),
    );
    expect(cells).toHaveLength(4);
    // The first column has no rule; every column after it does (4-up), and the
    // 2-up narrow layout only rules the right-hand of its two columns.
    expect(cells[0]?.className).toContain("sm:first:border-l-0");
    for (const cell of cells.slice(1)) {
      expect(cell.className).toContain("sm:border-l");
      expect(cell.className).toContain("border-chart-divider");
    }
  });
});

describe("home charts: donut dimensions (Issue #366 item 4)", () => {
  it("uses the mock's 150px / 23px ring and its legend rhythm", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [
        buildTest({ id: "p1", name: "進行" }),
      ],
      listSubmissions: async () => [
        submissionDaysAgo({ id: "s1", state: "ai_processing", daysAgo: 0 }),
      ],
    });

    await waitFor(() => {
      expect(container.querySelector(".recharts-sector")).not.toBeNull();
    });
    const paths = Array.from(container.querySelectorAll(".recharts-sector"));
    const radii = paths.flatMap((path) =>
      [
        ...(path.getAttribute("d") ?? "").matchAll(/A\s*([\d.]+),([\d.]+)/g),
      ].map((match) => Number(match[1])),
    );
    // Outer diameter 150 and 23px ring -> 75 / 52 (was 82 / 58).
    expect(radii).toContain(75);
    expect(radii).toContain(52);

    const dot = screen
      .getByTestId("home-phase-preparing")
      .querySelector("[aria-hidden='true']");
    expect(dot?.className).toContain("size-4");
    expect(screen.getByTestId("home-phase-legend").className).toContain(
      "gap-sm",
    );
    expect(screen.getByTestId("home-phase-preparing").className).toContain(
      "leading-tight",
    );
  });
});

describe("home charts: no dead space under the plot (Issue #366 item 5)", () => {
  it("lets the plot take the card's leftover height", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => [
        submissionDaysAgo({ id: "a", state: "reviewed", daysAgo: 0 }),
      ],
    });

    await waitFor(() => {
      expect(barElements(container)).toHaveLength(7);
    });

    const panel = screen.getByTestId("home-progress-panel");
    expect(panel.classList.contains("flex")).toBe(true);
    expect(panel.classList.contains("flex-col")).toBe(true);
    expect(panel.classList.contains("h-full")).toBe(true);

    const plot = screen.getByTestId("home-daily-plot");
    expect(plot.classList.contains("flex-1")).toBe(true);
    expect(plot.classList.contains("min-h-0")).toBe(true);

    const figure = screen.getByTestId("home-daily-chart");
    expect(figure.classList.contains("h-full")).toBe(true);
    const responsive = figure.querySelector(".recharts-responsive-container");
    expect(responsive?.getAttribute("style") ?? "").toContain("height: 100%");
  });
});
