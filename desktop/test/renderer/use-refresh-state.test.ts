import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  formatRefreshClockTime,
  useRefreshState,
} from "../../src/renderer/core/use-refresh-state.js";

/**
 * Issue #383: the shared refresh feedback. The clock and both delays are
 * injected, so every timing assertion below is driven by fake timers; nothing
 * here waits in real time.
 */
afterEach(() => {
  vi.useRealTimers();
});

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("formatRefreshClockTime", () => {
  it("renders 24-hour HH:MM:SS with zero padding", () => {
    expect(formatRefreshClockTime(new Date(2026, 8, 12, 4, 5, 6))).toBe(
      "04:05:06",
    );
  });

  it("renders a placeholder before the first success", () => {
    expect(formatRefreshClockTime(null)).toBe("--:--:--");
  });
});

describe("useRefreshState", () => {
  it("never shows the loading treatment for a refresh shorter than the delay", async () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRefreshState({ now: () => new Date() }));

    await act(async () => {
      await view.result.current.run(async () => "ok");
    });

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(view.result.current.showLoading).toBe(false);
  });

  it("shows the loading treatment only after the delay elapses", () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRefreshState({ now: () => new Date() }));
    const operation = deferred<string>();

    act(() => {
      void view.result.current.run(() => operation.promise);
    });

    act(() => {
      vi.advanceTimersByTime(149);
    });
    expect(view.result.current.showLoading).toBe(false);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(view.result.current.showLoading).toBe(true);

    act(() => {
      operation.resolve("ok");
    });
  });

  it("holds the loading treatment for the minimum visible time once shown", async () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRefreshState({ now: () => new Date() }));
    const operation = deferred<string>();

    act(() => {
      void view.result.current.run(() => operation.promise);
    });
    // Appears at 150ms.
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(view.result.current.showLoading).toBe(true);

    // The operation finishes at 200ms, only 50ms after the treatment appeared.
    act(() => {
      vi.advanceTimersByTime(50);
    });
    await act(async () => {
      operation.resolve("ok");
      await Promise.resolve();
    });

    // Show was at 150ms, so the minimum runs until 550ms. At 549ms it is
    // still held; at 550ms it is released.
    act(() => {
      vi.advanceTimersByTime(349);
    });
    expect(view.result.current.showLoading).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(view.result.current.showLoading).toBe(false);
  });

  it("hides immediately when the refresh outlasted the minimum visible time", async () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRefreshState({ now: () => new Date() }));
    const operation = deferred<string>();

    act(() => {
      void view.result.current.run(() => operation.promise);
    });
    // Shown at 150ms, minimum elapses at 550ms; the operation runs to 600ms.
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(view.result.current.showLoading).toBe(true);

    await act(async () => {
      operation.resolve("ok");
      await Promise.resolve();
    });
    expect(view.result.current.showLoading).toBe(false);
  });

  it("does not update the last-updated time when the refresh fails", async () => {
    const first = new Date(2026, 8, 12, 1, 2, 3);
    const second = new Date(2026, 8, 12, 4, 5, 6);
    let clock = first;
    const view = renderHook(() => useRefreshState({ now: () => clock }));

    await act(async () => {
      await view.result.current.run(async () => "ok");
    });
    expect(formatRefreshClockTime(view.result.current.lastUpdatedAt)).toBe(
      "01:02:03",
    );

    clock = second;
    await act(async () => {
      await expect(
        view.result.current.run(async () => {
          throw new Error("boom");
        }),
      ).rejects.toThrow("boom");
    });

    // The failure keeps the previous success time; the caller's own error
    // state is what tells the reviewer it failed.
    expect(formatRefreshClockTime(view.result.current.lastUpdatedAt)).toBe(
      "01:02:03",
    );
  });

  it("updates the last-updated time on every success", async () => {
    const clock = { value: new Date(2026, 8, 12, 1, 2, 3) };
    const view = renderHook(() => useRefreshState({ now: () => clock.value }));

    await act(async () => {
      await view.result.current.run(async () => "ok");
    });
    expect(formatRefreshClockTime(view.result.current.lastUpdatedAt)).toBe(
      "01:02:03",
    );

    clock.value = new Date(2026, 8, 12, 4, 5, 6);
    await act(async () => {
      await view.result.current.run(async () => "ok");
    });
    expect(formatRefreshClockTime(view.result.current.lastUpdatedAt)).toBe(
      "04:05:06",
    );
  });

  it("ignores a second run while one is already in flight", () => {
    vi.useFakeTimers();
    const view = renderHook(() => useRefreshState({ now: () => new Date() }));
    const first = deferred<string>();
    const second = deferred<string>();
    let firstCalls = 0;
    let secondCalls = 0;

    act(() => {
      void view.result.current.run(() => {
        firstCalls += 1;
        return first.promise;
      });
      void view.result.current.run(() => {
        secondCalls += 1;
        return second.promise;
      });
    });

    expect(firstCalls).toBe(1);
    expect(secondCalls).toBe(0);

    act(() => {
      first.resolve("ok");
      second.resolve("ok");
    });
  });
});
