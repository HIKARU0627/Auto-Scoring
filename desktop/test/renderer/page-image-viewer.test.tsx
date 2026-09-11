import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  PAGE_BASE_RENDER_WIDTH,
  PAGE_MAX_RENDER_WIDTH,
  PageImageViewer,
  resolvePageRenderSize,
} from "../../src/renderer/features/pdf-review/PageImageViewer.js";

const ASPECT = { displayedWidth: 595, displayedHeight: 842 };

/**
 * jsdom has no layout engine, so the shared `ResizeObserver` mock reports this
 * width for every observed element (test/renderer/setup.ts). The component
 * measures through that observer, which is the column width it sees here.
 */
const MOCKED_COLUMN_WIDTH = 600;

describe("resolvePageRenderSize", () => {
  /**
   * Issue #354: the answer image must never be laid out wider than the column
   * it sits in. It used to be a flat `min(640 * zoom, 1200)`, which crossed the
   * two-column boundary into the inspector on narrow widths and covered the
   * 続きを表示 control.
   *
   * Every width is checked, not a representative one: the clamp has to hold at
   * the exact values the measured layout uses (1536/900/700 windows resolve to
   * columns of 617/485/485) and at the degenerate ones.
   */
  for (const availableWidth of [
    160, 200, 320, 400, 485, 501, 617, 640, 641, 800, 1200, 1600,
  ]) {
    it(`keeps a zoom-1 page within a ${availableWidth}px column`, () => {
      const size = resolvePageRenderSize({
        availableWidth,
        zoom: 1,
        ...ASPECT,
      });
      expect(size.width).toBeLessThanOrEqual(availableWidth);
      expect(size.width).toBe(Math.min(PAGE_BASE_RENDER_WIDTH, availableWidth));
      expect(size.height).toBeCloseTo(
        (size.width * ASPECT.displayedHeight) / ASPECT.displayedWidth,
      );
    });
  }

  it("uses the natural width before the column has been measured", () => {
    const size = resolvePageRenderSize({
      availableWidth: null,
      zoom: 1,
      ...ASPECT,
    });
    expect(size.width).toBe(PAGE_BASE_RENDER_WIDTH);
  });

  it("still lets zoom grow past the column so the image can scroll", () => {
    const size = resolvePageRenderSize({
      availableWidth: 400,
      zoom: 2,
      ...ASPECT,
    });
    expect(size.width).toBe(800);
    expect(size.width).toBeGreaterThan(400);
  });

  it("honours the hard ceiling when zoomed", () => {
    const size = resolvePageRenderSize({
      availableWidth: 1200,
      zoom: 3,
      ...ASPECT,
    });
    expect(size.width).toBe(PAGE_MAX_RENDER_WIDTH);
  });
});

describe("PageImageViewer", () => {
  /**
   * The measured column in jsdom is the ResizeObserver mock's 600px. The
   * surface's inline width is what the browser lays out, so asserting it here
   * pins "the page is drawn inside its column" without a real layout engine.
   */
  it("draws the page no wider than its column", () => {
    render(
      <PageImageViewer
        pageImage={{
          objectUrl: "blob:page",
          pixelWidth: 1190,
          pixelHeight: 1684,
        }}
        displayedWidth={ASPECT.displayedWidth}
        displayedHeight={ASPECT.displayedHeight}
        annotations={[]}
        recognitions={[]}
        questionAnswerArea={null}
        zoom={1}
      />,
    );

    const surface = screen.getByTestId("review-page-surface");
    const surfaceWidth = Number.parseFloat(surface.style.width);

    expect(surfaceWidth).toBeLessThanOrEqual(MOCKED_COLUMN_WIDTH);
    expect(surfaceWidth).toBe(
      Math.min(PAGE_BASE_RENDER_WIDTH, MOCKED_COLUMN_WIDTH),
    );
    expect(Number.parseFloat(surface.style.height)).toBeCloseTo(
      (surfaceWidth * ASPECT.displayedHeight) / ASPECT.displayedWidth,
    );
  });
});
