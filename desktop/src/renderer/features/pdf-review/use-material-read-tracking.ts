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
  planMaterialReveal,
  sameMaterialRanges,
  type MaterialRange,
  type MaterialRevealPlan,
} from "../../core/material-read-ranges.js";

export interface MaterialRow {
  readonly id: string;
}

/** Shown after the unread material was actually brought into view. */
const MATERIAL_REVEALED_MESSAGE =
  "判断材料が画面外に残っていました。続きを表示しました。";

/**
 * Shown when the button could not move the container at all (Issue #328,
 * decision 2). Scrolling is not the only way to read the material -- the gate
 * also opens when the reviewer scrolls by hand -- so point them there instead
 * of leaving a silent no-op.
 */
const MATERIAL_REVEAL_STALLED_MESSAGE =
  "これ以上「続きを表示」では進めませんでした。判断材料を手動でスクロールして確認してください。";

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
    if (container == null) {
      setSnackbarMessage(MATERIAL_REVEAL_STALLED_MESSAGE);
      return;
    }
    // Aim at the first unread row itself instead of paging by whole viewports
    // (Issue #328). Relative viewport paging is not guaranteed to accumulate:
    // on the measured container it reached one page and then stopped, leaving
    // the material off-screen and 承認 disabled forever. The unread point is a
    // fraction of its own row, so a row taller than the viewport still moves.
    const containerTop = container.getBoundingClientRect().top;
    let plan: MaterialRevealPlan | null = null;
    for (const row of rows) {
      const ranges = rangesByRow[row.id];
      if (materialRowIsCovered(ranges)) {
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
      const gapStart = materialRowGapStart(ranges) ?? 0;
      plan = planMaterialReveal({
        scrollTop: container.scrollTop,
        maxScrollTop: Math.max(
          0,
          container.scrollHeight - container.clientHeight,
        ),
        viewportHeight: container.clientHeight,
        unreadTop: rowTop + gapStart * rowHeight,
        containerTop,
      });
      break;
    }
    if (plan == null) {
      setSnackbarMessage(MATERIAL_REVEAL_STALLED_MESSAGE);
      return;
    }
    const before = container.scrollTop;
    container.scrollTop = plan.scrollTop;
    // A stalled smooth scroll used to leave this button silent: the fact that
    // nothing moved must reach the screen (Issue #328, decision 2).
    const moved = container.scrollTop !== before;
    window.setTimeout(() => {
      measure();
    }, 300);
    setSnackbarMessage(
      moved ? MATERIAL_REVEALED_MESSAGE : MATERIAL_REVEAL_STALLED_MESSAGE,
    );
  }, [measure, rangesByRow, rows, scrollContainerRef]);

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
