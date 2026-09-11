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

interface RowGeometry {
  readonly id: string;
  readonly top: number;
  readonly bottom: number;
}

/**
 * Several rows at fixed content offsets inside one scroll container, for the
 * multi-row shape measured in Issue #328 (container 608px, content 2224px,
 * every material row off-screen at rest).
 *
 * `scrollBy` deliberately reproduces what the real container did: a relative
 * page scroll reached one page (`clientHeight * 0.9`) and then stopped moving
 * no matter how often it was pressed. A regression back to viewport paging
 * therefore keeps failing here, while the fixed code aims `scrollTop` at the
 * unread row directly and does not depend on this at all.
 */
function buildMultiRowHarness(input: {
  viewport: number;
  contentHeight: number;
  rows: readonly RowGeometry[];
}): {
  container: HTMLDivElement;
  markers: Map<string, { top: HTMLSpanElement; bottom: HTMLSpanElement }>;
  scrollTop: () => number;
} {
  const { viewport, contentHeight, rows } = input;
  const maxScroll = Math.max(0, contentHeight - viewport);
  let scrollTop = 0;
  const container = document.createElement("div");
  Object.defineProperty(container, "clientHeight", {
    configurable: true,
    get: () => viewport,
  });
  Object.defineProperty(container, "scrollHeight", {
    configurable: true,
    get: () => contentHeight,
  });
  Object.defineProperty(container, "scrollTop", {
    configurable: true,
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = Math.min(Math.max(value, 0), maxScroll);
    },
  });
  container.getBoundingClientRect = () => rect(0, viewport);
  container.scrollBy = ((_options: ScrollToOptions) => {
    scrollTop = Math.min(Math.max(scrollTop, viewport * 0.9), maxScroll);
  }) as typeof container.scrollBy;
  const markers = new Map<
    string,
    { top: HTMLSpanElement; bottom: HTMLSpanElement }
  >();
  for (const row of rows) {
    const top = document.createElement("span");
    top.getBoundingClientRect = () =>
      rect(row.top - scrollTop, row.top - scrollTop);
    const bottom = document.createElement("span");
    bottom.getBoundingClientRect = () =>
      rect(row.bottom - scrollTop, row.bottom - scrollTop);
    markers.set(row.id, { top, bottom });
  }
  document.body.appendChild(container);
  return { container, markers, scrollTop: () => scrollTop };
}

function renderMultiRowTracking(
  harness: {
    container: HTMLDivElement;
    markers: Map<string, { top: HTMLSpanElement; bottom: HTMLSpanElement }>;
  },
  rowIds: readonly string[],
) {
  const scrollContainerRef = createRef<HTMLElement | null>();
  scrollContainerRef.current = harness.container;
  const input: MaterialRowsInput = {
    status: "known",
    rows: rowIds.map((id) => ({ id })),
  };
  const view = renderHook(() =>
    useMaterialReadTracking(input, scrollContainerRef),
  );
  act(() => {
    for (const id of rowIds) {
      const markers = harness.markers.get(id);
      if (markers != null) {
        view.result.current.registerRowMarkers(id, markers.top, markers.bottom);
      }
    }
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

  it("revealRest reports that it could not move when the container is null", () => {
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
    // The old text claimed the material had been revealed even when there was
    // nothing to scroll (Issue #328, decision 2).
    expect(result.current.snackbarMessage).toContain("進めませんでした");
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

  it("covers off-screen material by revealing to the first unread row (Issue #328)", () => {
    vi.useFakeTimers();
    // The measured shape: 608px container, 2224px content, two material rows
    // that never entered the viewport under viewport paging.
    const harness = buildMultiRowHarness({
      viewport: 608,
      contentHeight: 2224,
      rows: [
        { id: "grade:test", top: 1160, bottom: 1240 },
        { id: "criterion:c-0", top: 1900, bottom: 1980 },
      ],
    });
    const view = renderMultiRowTracking(harness, [
      "grade:test",
      "criterion:c-0",
    ]);

    expect(view.result.current.allRowsCovered).toBe(false);

    // Finite, not a fixed number of presses: however the material is laid
    // out, repeatedly revealing must end covered.
    let presses = 0;
    while (!view.result.current.allRowsCovered && presses < 50) {
      act(() => {
        view.result.current.revealRest();
        vi.advanceTimersByTime(300);
      });
      presses += 1;
    }

    expect(view.result.current.allRowsCovered).toBe(true);
    expect(presses).toBeGreaterThan(0);
  });

  it("says it could not move when the container has no scroll range (Issue #328)", () => {
    vi.useFakeTimers();
    const harness = buildMultiRowHarness({
      viewport: 608,
      contentHeight: 608,
      rows: [{ id: "grade:test", top: 0, bottom: 700 }],
    });
    const view = renderMultiRowTracking(harness, ["grade:test"]);

    expect(view.result.current.allRowsCovered).toBe(false);

    act(() => {
      view.result.current.revealRest();
      vi.advanceTimersByTime(300);
    });

    expect(view.result.current.snackbarMessage).toContain("進めませんでした");
    expect(view.result.current.allRowsCovered).toBe(false);
  });
});
