import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";

import {
  materialRowIsCovered,
  mergeMaterialRange,
  sameMaterialRanges,
  type MaterialRange,
} from "../../core/material-read-ranges.js";

export interface MaterialRow {
  readonly id: string;
}

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
  rows: readonly MaterialRow[],
  scrollContainerRef: RefObject<HTMLElement | null>,
): MaterialReadState {
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
    if (rows.length === 0) {
      return true;
    }
    return rows.every((row) => materialRowIsCovered(rangesByRow[row.id]));
  }, [rangesByRow, rows]);

  const unreadIsAbove = useMemo(() => {
    for (const row of rows) {
      if (!materialRowIsCovered(rangesByRow[row.id])) {
        const markers = rowRefs.current.get(row.id);
        if (markers == null) {
          continue;
        }
        const container = scrollContainerRef.current;
        if (container == null) {
          return false;
        }
        const rowTop = markers.top.getBoundingClientRect().top;
        const containerTop = container.getBoundingClientRect().top;
        return rowTop < containerTop;
      }
    }
    return false;
  }, [rangesByRow, rows, scrollContainerRef]);

  const revealRest = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container == null) {
      return;
    }
    const viewport = container.clientHeight * 0.9;
    if (typeof container.scrollBy === "function") {
      container.scrollBy({ top: viewport, behavior: "smooth" });
    } else {
      container.scrollTop += viewport;
    }
    setSnackbarMessage(
      "判断材料が画面外に残っていました。続きを表示しました。",
    );
    window.setTimeout(() => {
      measure();
    }, 300);
  }, [measure, scrollContainerRef]);

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
