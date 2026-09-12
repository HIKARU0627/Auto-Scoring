import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";

import { AppRoutes } from "../../src/renderer/core/app-routes.js";
import { homeBarAxis } from "../../src/renderer/core/home-analytics.js";
import { renderAppAt } from "./support/app-harness.js";
import {
  buildSubmission,
  buildTest,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

/**
 * Issue #382: the home daily bar chart must leave headroom above its tallest
 * bar, and the y-axis labels must be on the same scale as the bars.
 *
 * Recharts draws to SVG, so the bar `height` and the y tick label `y` are real
 * DOM attributes. The plot height is read from the chart's clip rectangle, not
 * from the distance between the top and bottom tick: the latter scales with the
 * axis domain, so a wrong domain would cancel itself out and pass.
 */

const DAY_MS = 86_400_000;

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

/** `count` confirmed submissions dated `daysAgo` days before noon today. */
function submissionsOn(
  count: number,
  daysAgo: number,
): ReturnType<typeof buildSubmission>[] {
  return Array.from({ length: count }, (_, index) =>
    submissionDaysAgo({
      id: `s${daysAgo}-${index}`,
      state: "reviewed",
      daysAgo,
    }),
  );
}

function renderCharts(handlers: MockSidecarHandlers) {
  return renderAppAt(AppRoutes.home, { handlers });
}

function barHeights(container: HTMLElement): number[] {
  return Array.from(
    container.querySelectorAll<SVGElement>("[data-testid='home-daily-bar']"),
  ).map((bar) => Number(bar.getAttribute("height")));
}

/** The drawn plot area: the clip rect that starts after the y-axis labels. */
function plotArea(container: HTMLElement): { top: number; height: number } {
  const rects = Array.from(container.querySelectorAll("clipPath rect")).map(
    (rect) => ({
      x: Number(rect.getAttribute("x")),
      y: Number(rect.getAttribute("y")),
      height: Number(rect.getAttribute("height")),
    }),
  );
  const plot = rects.reduce((best, rect) => (rect.x > best.x ? rect : best));
  return { top: plot.y, height: plot.height };
}

/**
 * The y-axis tick labels are the `<text>` nodes that are not date labels
 * (`M/D`); their `y` is the pixel position of that value on the shared scale.
 */
function yTicks(container: HTMLElement): { value: number; y: number }[] {
  return Array.from(container.querySelectorAll("text"))
    .filter((text) => !(text.textContent ?? "").includes("/"))
    .map((text) => ({
      value: Number(text.textContent),
      y: Number(text.getAttribute("y")),
    }))
    .filter((tick) => Number.isFinite(tick.value) && Number.isFinite(tick.y));
}

describe("home daily bar chart headroom (Issue #382)", () => {
  it("draws the tallest bar at 90% of the plot, below the axis ceiling", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => submissionsOn(9, 0),
    });

    await waitFor(() => {
      expect(barHeights(container)).toHaveLength(7);
    });

    const axis = homeBarAxis(9);
    expect(axis.upper).toBe(10);

    const tallest = Math.max(...barHeights(container));
    const plot = plotArea(container);
    expect(plot.height).toBeGreaterThan(0);
    const drawnRatio = tallest / plot.height;
    // max 9 with upper 10: exactly 90%, and never touching the ceiling.
    expect(drawnRatio).toBeCloseTo(0.9, 2);
    expect(drawnRatio).toBeLessThanOrEqual(0.9);
  });

  it("labels every tick on the same scale as the bar heights", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => submissionsOn(9, 0),
    });

    await waitFor(() => {
      expect(barHeights(container)).toHaveLength(7);
    });

    const axis = homeBarAxis(9);
    const tallest = Math.max(...barHeights(container));
    const plot = plotArea(container);
    const ticks = yTicks(container);
    const zero = ticks.find((tick) => tick.value === 0);
    const top = ticks.find((tick) => tick.value === axis.upper);
    expect(top, "the upper bound must be labeled").toBeDefined();
    expect(zero, "the zero baseline must be labeled").toBeDefined();

    // The top label sits at the plot's top edge and the zero label at its
    // bottom edge: the labels and the clip rect agree on the same domain.
    expect(Math.abs((top?.y ?? 0) - plot.top)).toBeLessThan(1);
    expect(Math.abs((zero?.y ?? 0) - (plot.top + plot.height))).toBeLessThan(1);

    // Each label sits where its value says it should on the plot scale...
    for (const tick of ticks) {
      const expectedY = plot.top + plot.height * (1 - tick.value / axis.upper);
      expect(Math.abs(tick.y - expectedY), `tick ${tick.value}`).toBeLessThan(
        1,
      );
    }
    // ...and the bar height is the same fraction of the plot.
    expect(tallest).toBeCloseTo((9 / axis.upper) * plot.height, 0);
    expect(ticks.length).toBeGreaterThanOrEqual(3);
    expect(ticks.length).toBeLessThanOrEqual(6);
  });

  it("keeps up to 10% headroom for the actual home max (count 10)", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => submissionsOn(10, 0),
    });

    await waitFor(() => {
      expect(barHeights(container)).toHaveLength(7);
    });

    const axis = homeBarAxis(10);
    expect(axis.upper).toBe(12);
    const ticks = yTicks(container);
    expect(ticks.map((tick) => tick.value)).toEqual([...axis.ticks]);
    const drawnRatio =
      Math.max(...barHeights(container)) / plotArea(container).height;
    expect(drawnRatio).toBeCloseTo(10 / 12, 2);
    expect(drawnRatio).toBeLessThanOrEqual(0.9);
    expect(drawnRatio).toBeGreaterThanOrEqual(0.7);
  });

  it("survives an all-zero week without NaN or negative heights", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => [],
    });

    await waitFor(() => {
      expect(barHeights(container)).toHaveLength(7);
    });

    for (const height of barHeights(container)) {
      expect(Number.isNaN(height)).toBe(false);
      expect(Number.isFinite(height)).toBe(true);
      expect(height).toBeGreaterThanOrEqual(0);
    }
    // The degenerate axis still labels a positive ceiling (0 -> 1).
    const ticks = yTicks(container);
    expect(ticks.map((tick) => tick.value)).toEqual([0, 1]);
  });

  it("holds for a single bar holding 1", async () => {
    const { container } = renderCharts({
      listTestRegistrations: async () => [buildTest({ id: "t1" })],
      listSubmissions: async () => submissionsOn(1, 0),
    });

    await waitFor(() => {
      expect(barHeights(container)).toHaveLength(7);
    });

    const axis = homeBarAxis(1);
    expect(axis.upper).toBe(2);
    const tallest = Math.max(...barHeights(container));
    expect(Number.isFinite(tallest)).toBe(true);
    expect(tallest).toBeGreaterThan(0);
    const ticks = yTicks(container);
    expect(ticks.map((tick) => tick.value)).toEqual([0, 1, 2]);
    expect(tallest / plotArea(container).height).toBeCloseTo(0.5, 2);
  });
});
