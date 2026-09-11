import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  useMaterialReadTracking,
  type MaterialRowsInput,
} from "../../src/renderer/features/pdf-review/use-material-read-tracking.js";

afterEach(() => {
  vi.useRealTimers();
});

function rect(top: number, bottom: number): DOMRect {
  return {
    top,
    bottom,
    left: 0,
    right: 100,
    width: 100,
    height: bottom - top,
    x: 0,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

/**
 * A scroll container jsdom cannot lay out, plus one row's two markers.
 *
 * The row starts at content offset 0 and is `rowHeight` tall; the markers'
 * viewport rects move with `scrollTop`, so `measure()` sees a real scroll the
 * way it would in a browser. `scrollBy` is instant (no animation), which is
 * what the hook's recorded range depends on.
 */
function buildHarness(input: { viewport: number; rowHeight: number }): {
  container: HTMLDivElement;
  topMarker: HTMLSpanElement;
  bottomMarker: HTMLSpanElement;
  scrollTop: () => number;
} {
  const { viewport, rowHeight } = input;
  const maxScroll = Math.max(0, rowHeight - viewport);
  let scrollTop = 0;
  const container = document.createElement("div");
  Object.defineProperty(container, "clientHeight", {
    configurable: true,
    get: () => viewport,
  });
  Object.defineProperty(container, "scrollHeight", {
    configurable: true,
    get: () => rowHeight,
  });
  Object.defineProperty(container, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = value;
    },
  });
  container.getBoundingClientRect = () => rect(0, viewport);
  container.scrollBy = ((options: ScrollToOptions) => {
    scrollTop = Math.min(
      Math.max(scrollTop + (options.top ?? 0), 0),
      maxScroll,
    );
  }) as typeof container.scrollBy;
  const topMarker = document.createElement("span");
  topMarker.getBoundingClientRect = () => rect(-scrollTop, -scrollTop);
  const bottomMarker = document.createElement("span");
  bottomMarker.getBoundingClientRect = () =>
    rect(rowHeight - scrollTop, rowHeight - scrollTop);
  document.body.appendChild(container);
  return { container, topMarker, bottomMarker, scrollTop: () => scrollTop };
}

function renderMaterialTracking(harness: {
  container: HTMLDivElement;
  topMarker: HTMLSpanElement;
  bottomMarker: HTMLSpanElement;
}) {
  const scrollContainerRef = createRef<HTMLElement | null>();
  scrollContainerRef.current = harness.container;
  const input: MaterialRowsInput = {
    status: "known",
    rows: [{ id: "grade:test" }],
  };
  const view = renderHook(() =>
    useMaterialReadTracking(input, scrollContainerRef),
  );
  act(() => {
    view.result.current.registerRowMarkers(
      "grade:test",
      harness.topMarker,
      harness.bottomMarker,
    );
  });
  return view;
}

describe("useMaterialReadTracking", () => {
  it("treats unknown material rows as not covered (fail-closed)", () => {
    const scrollContainerRef = createRef<HTMLElement | null>();
    const input: MaterialRowsInput = { status: "unknown" };
    const { result } = renderHook(() =>
      useMaterialReadTracking(input, scrollContainerRef),
    );
    expect(result.current.allRowsCovered).toBe(false);
  });

  it("revealRest shows snackbar when scroll container is null", () => {
    const scrollContainerRef = createRef<HTMLElement | null>();
    const input: MaterialRowsInput = {
      status: "known",
      rows: [{ id: "grade:test" }],
    };
    const { result } = renderHook(() =>
      useMaterialReadTracking(input, scrollContainerRef),
    );
    act(() => {
      result.current.revealRest();
    });
    expect(result.current.snackbarMessage).toContain(
      "判断材料が画面外に残っていました",
    );
  });

  it("reveals a row taller than the viewport by scrolling down (Issue #319)", () => {
    vi.useFakeTimers();
    const harness = buildHarness({ viewport: 300, rowHeight: 900 });
    const view = renderMaterialTracking(harness);

    expect(harness.scrollTop()).toBe(0);
    expect(view.result.current.allRowsCovered).toBe(false);

    for (let press = 0; press < 10; press += 1) {
      if (view.result.current.allRowsCovered) {
        break;
      }
      act(() => {
        view.result.current.revealRest();
        vi.advanceTimersByTime(300);
      });
    }

    expect(harness.scrollTop()).toBeGreaterThan(0);
    expect(view.result.current.allRowsCovered).toBe(true);
  });

  it("reveals upward when the unread material is above the viewport (Issue #319)", () => {
    vi.useFakeTimers();
    const harness = buildHarness({ viewport: 300, rowHeight: 900 });
    // Parked at the bottom with a gap left above, the button used to keep
    // scrolling down -- a no-op -- and the gate never opened.
    harness.container.scrollTop = 600;
    const view = renderMaterialTracking(harness);

    expect(view.result.current.allRowsCovered).toBe(false);
    expect(view.result.current.unreadIsAbove).toBe(true);

    act(() => {
      view.result.current.revealRest();
      vi.advanceTimersByTime(300);
    });
    expect(harness.scrollTop()).toBeLessThan(600);

    for (let press = 0; press < 10; press += 1) {
      if (view.result.current.allRowsCovered) {
        break;
      }
      act(() => {
        view.result.current.revealRest();
        vi.advanceTimersByTime(300);
      });
    }
    expect(view.result.current.allRowsCovered).toBe(true);
  });
});
