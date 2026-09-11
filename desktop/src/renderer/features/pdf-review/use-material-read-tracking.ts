import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";

import {
  materialRowGapStart,
  materialRowIsCovered,
  mergeMaterialRange,
  sameMaterialRanges,
  type MaterialRange,
} from "../../core/material-read-ranges.js";

export interface MaterialRow {
  readonly id: string;
}

/** Distinguishes "no rows yet" from "confirmed zero material rows". */
export type MaterialRowsInput =
  { status: "unknown" } | { status: "known"; rows: readonly MaterialRow[] };

export interface MaterialReadState {
  readonly allRowsCovered: boolean;
  readonly unreadIsAbove: boolean;
  readonly revealRest: () => void;
  readonly snackbarMessage: string | null;
  readonly clearSnackbar: () => void;
  readonly registerRowMarkers: (
    rowId: string,
    top: HTMLElement,
    bottom: HTMLElement,
  ) => void;
}

export function useMaterialReadTracking(
  input: MaterialRowsInput,
  scrollContainerRef: RefObject<HTMLElement | null>,
): MaterialReadState {
  const rows = input.status === "known" ? input.rows : [];
  const [rangesByRow, setRangesByRow] = useState<
    Readonly<Record<string, MaterialRange[]>>
  >({});
  const [snackbarMessage, setSnackbarMessage] = useState<string | null>(null);
  const rowRefs = useRef(
    new Map<string, { top: HTMLElement; bottom: HTMLElement }>(),
  );

  const recordVisible = useCallback(
    (rowId: string, start: number, end: number) => {
      setRangesByRow((current) => {
        const previous = current[rowId] ?? [];
        const merged = mergeMaterialRange(previous, start, end);
        if (sameMaterialRanges(previous, merged)) {
          return current;
        }
        return { ...current, [rowId]: merged };
      });
    },
    [],
  );

  const measure = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container == null) {
      return;
    }
    const containerRect = container.getBoundingClientRect();
    for (const row of rows) {
      const markers = rowRefs.current.get(row.id);
      if (markers == null) {
        continue;
      }
      const rowTop = markers.top.getBoundingClientRect().top;
      const rowBottom = markers.bottom.getBoundingClientRect().bottom;
      const rowHeight = rowBottom - rowTop;
      if (rowHeight <= 0) {
        continue;
      }
      const visibleTop = Math.max(rowTop, containerRect.top);
      const visibleBottom = Math.min(rowBottom, containerRect.bottom);
      if (visibleBottom <= visibleTop) {
        continue;
      }
      const start = (visibleTop - rowTop) / rowHeight;
      const end = (visibleBottom - rowTop) / rowHeight;
      recordVisible(row.id, start, end);
    }
  }, [recordVisible, rows, scrollContainerRef]);

  const registerRowMarkers = useCallback(
    (rowId: string, top: HTMLElement, bottom: HTMLElement) => {
      rowRefs.current.set(rowId, { top, bottom });
      measure();
    },
    [measure],
  );

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container == null) {
      return undefined;
    }
    const onScroll = () => {
      measure();
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    const observer = new ResizeObserver(() => {
      measure();
    });
    observer.observe(container);
    measure();
    return () => {
      container.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, [measure, scrollContainerRef]);

  const allRowsCovered = useMemo(() => {
    if (input.status === "unknown") {
      return false;
    }
    if (rows.length === 0) {
      return true;
    }
    return rows.every((row) => materialRowIsCovered(rangesByRow[row.id]));
  }, [input.status, rangesByRow, rows]);

  const unreadIsAbove = useMemo(() => {
    const container = scrollContainerRef.current;
    if (container == null) {
      return false;
    }
    const containerTop = container.getBoundingClientRect().top;
    for (const row of rows) {
      const ranges = rangesByRow[row.id];
      const gapStart = materialRowGapStart(ranges);
      if (gapStart == null) {
        continue;
      }
      const markers = rowRefs.current.get(row.id);
      if (markers == null) {
        continue;
      }
      const rowTop = markers.top.getBoundingClientRect().top;
      const rowBottom = markers.bottom.getBoundingClientRect().bottom;
      const rowHeight = rowBottom - rowTop;
      if (rowHeight <= 0) {
        continue;
      }
      return rowTop + gapStart * rowHeight < containerTop;
    }
    return false;
  }, [rangesByRow, rows, scrollContainerRef]);

  const revealRest = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container != null) {
      const viewport = container.clientHeight * 0.9;
      // Towards the unread material, which is not always downwards (Issue
      // #319, ported from `_revealRestOfMaterial`). While parked at the
      // bottom, a row replaced above the fold leaves the gate closed with
      // nowhere to go, and a button that scrolls the wrong way does nothing.
      const delta = unreadIsAbove ? -viewport : viewport;
      if (typeof container.scrollBy === "function") {
        container.scrollBy({ top: delta, behavior: "smooth" });
      } else {
        container.scrollTop += delta;
      }
      window.setTimeout(() => {
        measure();
      }, 300);
    }
    setSnackbarMessage(
      "判断材料が画面外に残っていました。続きを表示しました。",
    );
  }, [measure, scrollContainerRef, unreadIsAbove]);

  const clearSnackbar = useCallback(() => {
    setSnackbarMessage(null);
  }, []);

  return {
    allRowsCovered,
    unreadIsAbove,
    revealRest,
    snackbarMessage,
    clearSnackbar,
    registerRowMarkers,
  };
}
