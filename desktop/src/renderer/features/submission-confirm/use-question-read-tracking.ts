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

export interface QuestionReadTracking {
  readonly isReached: (questionId: string) => boolean;
  readonly unreadIsAbove: boolean;
  readonly revealNext: () => void;
  readonly registerRowMarkers: (
    questionId: string,
    top: HTMLElement,
    bottom: HTMLElement,
  ) => void;
  readonly resetQuestion: (questionId: string) => void;
  readonly resetAll: () => void;
}

export function useQuestionReadTracking(
  questionIds: readonly string[],
  scrollContainerRef: RefObject<HTMLElement | null>,
): QuestionReadTracking {
  const [rangesByQuestion, setRangesByQuestion] = useState<
    Readonly<Record<string, MaterialRange[]>>
  >({});
  const rowRefs = useRef(
    new Map<string, { top: HTMLElement; bottom: HTMLElement }>(),
  );

  const recordVisible = useCallback(
    (questionId: string, start: number, end: number) => {
      setRangesByQuestion((current) => {
        const previous = current[questionId] ?? [];
        const merged = mergeMaterialRange(previous, start, end);
        if (sameMaterialRanges(previous, merged)) {
          return current;
        }
        return { ...current, [questionId]: merged };
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
    for (const questionId of questionIds) {
      const markers = rowRefs.current.get(questionId);
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
      recordVisible(questionId, start, end);
    }
  }, [questionIds, recordVisible, scrollContainerRef]);

  const registerRowMarkers = useCallback(
    (questionId: string, top: HTMLElement, bottom: HTMLElement) => {
      rowRefs.current.set(questionId, { top, bottom });
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

  const isReached = useCallback(
    (questionId: string) => materialRowIsCovered(rangesByQuestion[questionId]),
    [rangesByQuestion],
  );

  const unreadIsAbove = useMemo(() => {
    for (const questionId of questionIds) {
      if (isReached(questionId)) {
        continue;
      }
      const markers = rowRefs.current.get(questionId);
      const container = scrollContainerRef.current;
      if (markers == null || container == null) {
        continue;
      }
      const rowTop = markers.top.getBoundingClientRect().top;
      const containerTop = container.getBoundingClientRect().top;
      return rowTop < containerTop;
    }
    return false;
  }, [isReached, questionIds, rangesByQuestion, scrollContainerRef]);

  const revealNext = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container == null) {
      return;
    }
    const viewport = container.clientHeight * 0.9;
    const delta = unreadIsAbove ? -viewport : viewport;
    if (typeof container.scrollBy === "function") {
      container.scrollBy({ top: delta, behavior: "smooth" });
    } else {
      container.scrollTop += delta;
    }
    window.setTimeout(measure, 300);
  }, [measure, scrollContainerRef, unreadIsAbove]);

  const resetQuestion = useCallback((questionId: string) => {
    setRangesByQuestion((current) => {
      if (!(questionId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[questionId];
      return next;
    });
  }, []);

  const resetAll = useCallback(() => {
    setRangesByQuestion({});
  }, []);

  return {
    isReached,
    unreadIsAbove,
    revealNext,
    registerRowMarkers,
    resetQuestion,
    resetAll,
  };
}
