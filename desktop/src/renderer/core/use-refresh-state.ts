import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared refresh feedback (Issue #383).
 *
 * A reload that finishes faster than the eye can follow used to flash the
 * loading treatment on and off, so the owner could not tell whether anything
 * had happened. This hook removes that flicker and replaces it with a visible
 * answer:
 *
 * 1. the loading treatment is not shown until a refresh has run for longer
 *    than `loadingDelayMs` (default 150ms), so a fast refresh shows nothing;
 * 2. once shown, it stays for at least `minimumVisibleMs` (default 400ms), so
 *    it cannot disappear the frame after it appeared;
 * 3. the caller can render the clock time of the last *successful* refresh,
 *    which changes on every press.
 *
 * The clock and both delays are injected, so tests drive them with fake timers
 * instead of waiting in real time.
 *
 * `run` owns the asynchronous operation: it resolves with the operation's
 * result, rejects on failure (the caller keeps showing its existing error
 * state), and only calls the clock after a success.
 */

/** How long a refresh may run before the loading treatment is shown. */
export const DEFAULT_REFRESH_LOADING_DELAY_MS = 150;

/** How long the loading treatment stays once it has been shown. */
export const DEFAULT_REFRESH_MINIMUM_VISIBLE_MS = 400;

export interface UseRefreshStateOptions {
  /** Injected clock, read once per successful refresh. */
  readonly now: () => Date;
  /** Override the 150ms show delay (tests inject a boundary value). */
  readonly loadingDelayMs?: number;
  /** Override the 400ms minimum visible time (tests inject a boundary value). */
  readonly minimumVisibleMs?: number;
}

export interface RefreshState {
  /** Whether the loading treatment should currently be visible. */
  readonly showLoading: boolean;
  /** Clock time of the last successful refresh, or `null` before the first. */
  readonly lastUpdatedAt: Date | null;
  /**
   * Run one refresh. Resolves with the operation's result; rejects on failure
   * without touching `lastUpdatedAt`.
   */
  readonly run: <T>(operation: () => Promise<T>) => Promise<T>;
}

/** `HH:MM:SS` for the last-updated label; `--:--:--` before the first success. */
export function formatRefreshClockTime(date: Date | null): string {
  if (date === null) {
    return "--:--:--";
  }
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = String(date.getSeconds()).padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
}

interface RefreshTimers {
  show: ReturnType<typeof setTimeout> | null;
  minimum: ReturnType<typeof setTimeout> | null;
}

export function useRefreshState({
  now,
  loadingDelayMs = DEFAULT_REFRESH_LOADING_DELAY_MS,
  minimumVisibleMs = DEFAULT_REFRESH_MINIMUM_VISIBLE_MS,
}: UseRefreshStateOptions): RefreshState {
  const [showLoading, setShowLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const timers = useRef<RefreshTimers>({ show: null, minimum: null });
  /** True while the loading treatment is on screen. */
  const visible = useRef(false);
  /** True once the minimum visible time has elapsed for the current show. */
  const minimumElapsed = useRef(false);
  /** The operation settled while visible, before the minimum had elapsed. */
  const hideWhenMinimumElapses = useRef(false);
  const inFlight = useRef<Promise<unknown> | null>(null);
  const mounted = useRef(true);
  const nowRef = useRef(now);
  nowRef.current = now;

  const clearShowTimer = useCallback(() => {
    if (timers.current.show !== null) {
      clearTimeout(timers.current.show);
      timers.current.show = null;
    }
  }, []);

  const clearMinimumTimer = useCallback(() => {
    if (timers.current.minimum !== null) {
      clearTimeout(timers.current.minimum);
      timers.current.minimum = null;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearShowTimer();
      clearMinimumTimer();
    };
  }, [clearMinimumTimer, clearShowTimer]);

  const startLoadingSequence = useCallback(() => {
    visible.current = false;
    minimumElapsed.current = false;
    hideWhenMinimumElapses.current = false;
    clearShowTimer();
    clearMinimumTimer();

    timers.current.show = setTimeout(() => {
      timers.current.show = null;
      visible.current = true;
      setShowLoading(true);
      timers.current.minimum = setTimeout(() => {
        timers.current.minimum = null;
        minimumElapsed.current = true;
        if (hideWhenMinimumElapses.current) {
          hideWhenMinimumElapses.current = false;
          visible.current = false;
          setShowLoading(false);
        }
      }, minimumVisibleMs);
    }, loadingDelayMs);
  }, [clearMinimumTimer, clearShowTimer, loadingDelayMs, minimumVisibleMs]);

  const settleLoadingSequence = useCallback(() => {
    clearShowTimer();
    if (!visible.current) {
      return;
    }
    if (minimumElapsed.current) {
      visible.current = false;
      setShowLoading(false);
      return;
    }
    // Shown but not for long enough: wait out the remainder in the minimum
    // timer instead of clearing it now.
    hideWhenMinimumElapses.current = true;
  }, [clearShowTimer]);

  const run = useCallback(
    <T>(operation: () => Promise<T>): Promise<T> => {
      const existing = inFlight.current;
      if (existing !== null) {
        return existing as Promise<T>;
      }

      startLoadingSequence();

      const promise = (async (): Promise<T> => {
        try {
          const result = await operation();
          if (mounted.current) {
            setLastUpdatedAt(nowRef.current());
          }
          return result;
        } finally {
          if (mounted.current) {
            settleLoadingSequence();
          } else {
            clearShowTimer();
            clearMinimumTimer();
          }
          inFlight.current = null;
        }
      })();

      inFlight.current = promise;
      return promise;
    },
    [
      clearMinimumTimer,
      clearShowTimer,
      settleLoadingSequence,
      startLoadingSequence,
    ],
  );

  return { showLoading, lastUpdatedAt, run };
}
