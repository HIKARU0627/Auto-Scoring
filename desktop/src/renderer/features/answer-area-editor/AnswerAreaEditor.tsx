import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type PointerEvent as ReactPointerEvent,
} from "react";

import { ActionRequirements } from "../../core/action-requirements.js";
import {
  MAX_PAGE_WIDTH_PX,
  UNASSIGNED_QUESTION_DISPLAY_LABEL,
  UNASSIGNED_QUESTION_LABEL,
} from "../../core/answer-area-constants.js";
import {
  layoutPointToNormalized,
  normalizedToLayoutPoint,
  type PixelSize,
} from "../../core/normalized-coordinates.js";
import type { PageImageState, RegionModel } from "./answer-area-types.js";
import {
  bboxFromPoints,
  freeRegionId,
  nudgeRegion,
  regionKindLabel,
} from "./region-helpers.js";

export interface AnswerAreaEditorProps {
  readonly pages: readonly { width_pt: number; height_pt: number }[];
  readonly pageImages: readonly PageImageState[];
  readonly regions: readonly RegionModel[];
  readonly questionNumbers: readonly string[];
  readonly undetectedQuestionNumbers: readonly string[];
  readonly absentQuestionNumbers: readonly string[];
  readonly readingOrderConflicts: readonly (readonly [string, string])[];
  readonly readOnly: boolean;
  readonly onRegionsChanged: (regions: RegionModel[]) => void;
  readonly onEditNumerically?: (index: number) => void;
}

interface DraftState {
  pageIndex: number;
  start: { x: number; y: number };
  end: { x: number; y: number };
}

/** How far one arrow keypress moves or resizes a region, in rendered pixels. */
const KEYBOARD_NUDGE_PX = 2;

/** Upper bound on the undo history, so a long editing session stays bounded. */
const UNDO_HISTORY_LIMIT = 100;

export function AnswerAreaEditor({
  pages,
  pageImages,
  regions,
  questionNumbers,
  undetectedQuestionNumbers,
  absentQuestionNumbers,
  readingOrderConflicts,
  readOnly,
  onRegionsChanged,
  onEditNumerically,
}: AnswerAreaEditorProps): JSX.Element {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [drawTarget, setDrawTarget] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [undoDepth, setUndoDepth] = useState(0);
  const undoStackRef = useRef<RegionModel[][]>([]);
  const gestureStartRef = useRef<RegionModel[] | null>(null);
  const gesturePushedRef = useRef(false);
  const lastEmittedRef = useRef<readonly RegionModel[] | null>(null);

  useEffect(() => {
    if (selectedIndex !== null && selectedIndex >= regions.length) {
      setSelectedIndex(null);
    }
  }, [regions.length, selectedIndex]);

  useEffect(() => {
    if (lastEmittedRef.current === regions) {
      return;
    }
    undoStackRef.current = [];
    setUndoDepth(0);
    lastEmittedRef.current = regions;
  }, [regions]);

  const effectiveDrawTarget = useMemo(() => {
    if (
      drawTarget !== null &&
      (drawTarget === UNASSIGNED_QUESTION_LABEL ||
        questionNumbers.includes(drawTarget))
    ) {
      return drawTarget;
    }
    if (undetectedQuestionNumbers.length > 0) {
      return undetectedQuestionNumbers[0] ?? UNASSIGNED_QUESTION_LABEL;
    }
    if (absentQuestionNumbers.length > 0) {
      return absentQuestionNumbers[0] ?? UNASSIGNED_QUESTION_LABEL;
    }
    return UNASSIGNED_QUESTION_LABEL;
  }, [
    absentQuestionNumbers,
    drawTarget,
    questionNumbers,
    undetectedQuestionNumbers,
  ]);

  const pushUndo = useCallback((snapshot: RegionModel[]) => {
    const stack = undoStackRef.current;
    stack.push(snapshot);
    if (stack.length > UNDO_HISTORY_LIMIT) {
      stack.shift();
    }
    setUndoDepth(stack.length);
  }, []);

  /**
   * Emits a new region set and records an undo entry. A pointer drag emits on
   * every move, so `onEditStart`/`onEditEnd` bracket a gesture: the snapshot is
   * taken once at press time, not once per pixel.
   */
  const emit = useCallback(
    (next: RegionModel[]) => {
      if (gestureStartRef.current !== null) {
        if (!gesturePushedRef.current) {
          pushUndo(gestureStartRef.current);
          gesturePushedRef.current = true;
        }
      } else {
        pushUndo([...regions]);
      }
      lastEmittedRef.current = next;
      onRegionsChanged(next);
    },
    [onRegionsChanged, pushUndo, regions],
  );

  const onEditStart = useCallback(() => {
    gestureStartRef.current = [...regions];
    gesturePushedRef.current = false;
  }, [regions]);

  const onEditEnd = useCallback(() => {
    gestureStartRef.current = null;
    gesturePushedRef.current = false;
  }, []);

  const undo = useCallback(() => {
    const previous = undoStackRef.current.pop();
    if (previous === undefined) {
      return;
    }
    setUndoDepth(undoStackRef.current.length);
    lastEmittedRef.current = previous;
    onRegionsChanged(previous);
  }, [onRegionsChanged]);

  const replaceRegion = useCallback(
    (index: number, region: RegionModel) => {
      const next = [...regions];
      next[index] = region;
      emit(next);
    },
    [emit, regions],
  );

  const deleteRegion = useCallback(
    (index: number) => {
      setSelectedIndex(null);
      emit(regions.filter((_, regionIndex) => regionIndex !== index));
    },
    [emit, regions],
  );

  const swapLabels = useCallback(
    (first: string, second: string) => {
      emit(
        regions.map((region) => {
          if (region.kind !== "answer_area") {
            return region;
          }
          if (region.label === first) {
            return { ...region, label: second };
          }
          if (region.label === second) {
            return { ...region, label: first };
          }
          return region;
        }),
      );
    },
    [emit, regions],
  );

  const commitDraft = useCallback(() => {
    if (draft === null) {
      return;
    }
    setDraft(null);
    const bbox = bboxFromPoints(draft.start, draft.end);
    if (bbox === null) {
      return;
    }
    const newRegion: RegionModel = {
      region_id: freeRegionId(regions),
      kind: "answer_area",
      page_index: draft.pageIndex,
      label: effectiveDrawTarget,
      confirmed: false,
      bbox,
    };
    emit([...regions, newRegion]);
    setSelectedIndex(regions.length);
  }, [draft, effectiveDrawTarget, emit, regions]);

  const normalizePointer = (
    event: ReactPointerEvent,
    renderSize: PixelSize,
    imagePixelSize: PixelSize,
  ): { x: number; y: number } => {
    const rect = event.currentTarget.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    return layoutPointToNormalized(localX, localY, renderSize, imagePixelSize);
  };

  const regionListOrder = useMemo(() => {
    const indices = regions.map((_, index) => index);
    indices.sort((a, b) => {
      const regionA = regions[a];
      const regionB = regions[b];
      if (regionA === undefined || regionB === undefined) {
        return 0;
      }
      const unassignedA = isUnassigned(regionA, questionNumbers) ? 0 : 1;
      const unassignedB = isUnassigned(regionB, questionNumbers) ? 0 : 1;
      if (unassignedA !== unassignedB) {
        return unassignedA - unassignedB;
      }
      return a - b;
    });
    return indices;
  }, [questionNumbers, regions]);

  return (
    <div
      className="flex flex-col gap-md"
      onKeyDown={(event) => {
        if (
          (event.ctrlKey || event.metaKey) &&
          event.key.toLowerCase() === "z"
        ) {
          event.preventDefault();
          undo();
        }
      }}
    >
      <UndetectedBanner
        questionNumbers={questionNumbers}
        undetected={undetectedQuestionNumbers}
        absent={absentQuestionNumbers}
        readOnly={readOnly}
        onSelectDrawTarget={setDrawTarget}
      />

      {readingOrderConflicts.length > 0 ? (
        <ReadingOrderWarning
          conflicts={readingOrderConflicts}
          readOnly={readOnly}
          onSwap={swapLabels}
        />
      ) : null}

      {!readOnly ? (
        <DrawToolbar
          questionNumbers={questionNumbers}
          drawTarget={effectiveDrawTarget}
          onDrawTargetChange={setDrawTarget}
          canUndo={undoDepth > 0}
          onUndo={undo}
        />
      ) : null}

      {pages.map((page, pageIndex) => (
        <PageCanvas
          key={pageIndex}
          pageIndex={pageIndex}
          page={page}
          pageImage={
            pageImages[pageIndex] ?? {
              objectUrl: null,
              pixelWidth: null,
              pixelHeight: null,
            }
          }
          regions={regions}
          selectedIndex={selectedIndex}
          draft={draft?.pageIndex === pageIndex ? draft : null}
          readOnly={readOnly}
          onSelect={setSelectedIndex}
          onReplace={replaceRegion}
          onDraftStart={(point) => {
            setDraft({ pageIndex, start: point, end: point });
          }}
          onDraftUpdate={(point) => {
            setDraft((current) =>
              current === null ? current : { ...current, end: point },
            );
          }}
          onDraftCommit={commitDraft}
          onClearSelection={() => {
            setSelectedIndex(null);
          }}
          onEditStart={onEditStart}
          onEditEnd={onEditEnd}
          normalizePointer={normalizePointer}
        />
      ))}

      <RegionList
        regions={regions}
        regionListOrder={regionListOrder}
        questionNumbers={questionNumbers}
        readOnly={readOnly}
        onReplace={replaceRegion}
        onDelete={deleteRegion}
        {...(onEditNumerically === undefined ? {} : { onEditNumerically })}
      />
    </div>
  );
}

function UndetectedBanner({
  questionNumbers,
  undetected,
  absent,
  readOnly,
  onSelectDrawTarget,
}: {
  questionNumbers: readonly string[];
  undetected: readonly string[];
  absent: readonly string[];
  readOnly: boolean;
  onSelectDrawTarget: (target: string) => void;
}): JSX.Element {
  if (questionNumbers.length === 0) {
    return (
      <p
        data-testid="answer-area-no-questions"
        className="text-body-medium text-on-surface"
      >
        配点と採点基準がまだ確定していないので、回答欄を割り当てる設問がありません。
        先に配点と採点基準を確定してください。
      </p>
    );
  }

  if (undetected.length === 0 && absent.length === 0) {
    return (
      <div
        data-testid="answer-area-all-detected"
        className="flex items-start gap-sm text-body-medium"
      >
        <span className="text-success" aria-hidden>
          ✓
        </span>
        <p>{questionNumbers.length}件の設問すべてに回答欄があります。</p>
      </div>
    );
  }

  return (
    <div data-testid="answer-area-undetected" className="flex flex-col gap-md">
      {undetected.length > 0 ? (
        <MissingGroup
          keyPrefix="answer-area-undetected"
          message={
            ActionRequirements.answerAreaUndetected(undetected.length).message
          }
          action={ActionRequirements.answerAreaUndetectedAction.message}
          numbers={undetected}
          readOnly={readOnly}
          onSelect={onSelectDrawTarget}
        />
      ) : null}
      {absent.length > 0 ? (
        <MissingGroup
          keyPrefix="answer-area-absent"
          message={ActionRequirements.answerAreaAbsent(absent.length).message}
          action={ActionRequirements.answerAreaAbsentAction.message}
          numbers={absent}
          readOnly={readOnly}
          onSelect={onSelectDrawTarget}
        />
      ) : null}
    </div>
  );
}

function MissingGroup({
  keyPrefix,
  message,
  action,
  numbers,
  readOnly,
  onSelect,
}: {
  keyPrefix: string;
  message: string;
  action: string;
  numbers: readonly string[];
  readOnly: boolean;
  onSelect: (target: string) => void;
}): JSX.Element {
  return (
    <section
      data-testid={`${keyPrefix}-group`}
      className="flex flex-col gap-sm"
    >
      <p className="text-body-medium text-on-surface">{message}</p>
      <p
        data-testid={`${keyPrefix}-action`}
        className="text-body-medium font-semibold text-on-surface"
      >
        {action}
      </p>
      <div className="flex flex-wrap gap-sm">
        {numbers.map((number) => (
          <button
            key={number}
            type="button"
            data-testid={`${keyPrefix}-${number}`}
            className="rounded-full border border-outline px-md py-xs text-ui-label"
            disabled={readOnly}
            onClick={() => {
              onSelect(number);
            }}
          >
            {number}
          </button>
        ))}
      </div>
    </section>
  );
}

function ReadingOrderWarning({
  conflicts,
  readOnly,
  onSwap,
}: {
  conflicts: readonly (readonly [string, string])[];
  readOnly: boolean;
  onSwap: (first: string, second: string) => void;
}): JSX.Element {
  return (
    <section
      data-testid="answer-area-reading-order"
      className="flex flex-col gap-sm"
    >
      <p className="text-body-medium text-on-surface">
        設問の並び順と、回答欄の位置の順序が食い違っています。回答欄が入れ替わっていると、それぞれ相手の解答が採点されます。答案を見て、正しければそのまま進んでください。
      </p>
      {conflicts.map(([first, second]) => (
        <div key={`${first}-${second}`} className="flex items-center gap-md">
          <span className="flex-1 text-body-medium font-semibold">
            {first} と {second}
          </span>
          <button
            type="button"
            data-testid={`answer-area-swap-${first}-${second}`}
            className="rounded-md border border-outline px-md py-xs text-ui-label"
            disabled={readOnly}
            onClick={() => {
              onSwap(first, second);
            }}
          >
            回答欄を入れ替える
          </button>
        </div>
      ))}
    </section>
  );
}

function DrawToolbar({
  questionNumbers,
  drawTarget,
  onDrawTargetChange,
  canUndo,
  onUndo,
}: {
  questionNumbers: readonly string[];
  drawTarget: string;
  onDrawTargetChange: (target: string) => void;
  canUndo: boolean;
  onUndo: () => void;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-xs">
      <div className="flex flex-wrap items-center gap-sm text-body-medium">
        <span>次に引く回答欄の設問:</span>
        <select
          data-testid="answer-area-draw-target"
          className="select-themed rounded-md border border-outline px-sm py-xs"
          value={drawTarget}
          onChange={(event) => {
            onDrawTargetChange(event.target.value);
          }}
        >
          {questionNumbers.map((number) => (
            <option key={number} value={number}>
              {number}
            </option>
          ))}
          <option value={UNASSIGNED_QUESTION_LABEL}>
            {UNASSIGNED_QUESTION_DISPLAY_LABEL}
          </option>
        </select>
        <button
          type="button"
          data-testid="answer-area-undo"
          className="rounded-md border border-outline px-sm py-xs text-ui-label"
          disabled={!canUndo}
          onClick={onUndo}
        >
          元に戻す
        </button>
      </div>
      <span className="text-body-small text-on-surface-variant">
        答案の上をドラッグすると回答欄を引けます。枠を選ぶと動かせ、右下のつまみで大きさを変えられます。枠を選んで矢印キーでも動かせ、Shift+矢印で大きさを変えられます（Ctrl+Z
        で元に戻す）。
      </span>
    </div>
  );
}

function PageCanvas({
  pageIndex,
  page,
  pageImage,
  regions,
  selectedIndex,
  draft,
  readOnly,
  onSelect,
  onReplace,
  onDraftStart,
  onDraftUpdate,
  onDraftCommit,
  onClearSelection,
  onEditStart,
  onEditEnd,
  normalizePointer,
}: {
  pageIndex: number;
  page: { width_pt: number; height_pt: number };
  pageImage: PageImageState;
  regions: readonly RegionModel[];
  selectedIndex: number | null;
  draft: DraftState | null;
  readOnly: boolean;
  onSelect: (index: number) => void;
  onReplace: (index: number, region: RegionModel) => void;
  onDraftStart: (point: { x: number; y: number }) => void;
  onDraftUpdate: (point: { x: number; y: number }) => void;
  onDraftCommit: () => void;
  onClearSelection: () => void;
  onEditStart: () => void;
  onEditEnd: () => void;
  normalizePointer: (
    event: ReactPointerEvent,
    renderSize: PixelSize,
    imagePixelSize: PixelSize,
  ) => { x: number; y: number };
}): JSX.Element {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const [renderSize, setRenderSize] = useState<PixelSize>({
    width: 1,
    height: 1,
  });

  useEffect(() => {
    const element = surfaceRef.current;
    if (element === null) {
      return;
    }
    const syncSize = () => {
      const rect = element.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setRenderSize({ width: rect.width, height: rect.height });
      }
    };
    syncSize();
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry === undefined) {
        return;
      }
      setRenderSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  const aspectRatio = page.height_pt > 0 ? page.width_pt / page.height_pt : 1;
  const imagePixelSize: PixelSize | null =
    pageImage.pixelWidth !== null && pageImage.pixelHeight !== null
      ? { width: pageImage.pixelWidth, height: pageImage.pixelHeight }
      : null;

  const pageRegions = regions
    .map((region, index) => ({ region, index }))
    .filter(({ region }) => region.page_index === pageIndex);

  const draftRect =
    draft !== null && imagePixelSize !== null
      ? layoutRectFromPoints(draft.start, draft.end, renderSize, imagePixelSize)
      : null;

  return (
    <section className="flex flex-col gap-xs">
      <h3 className="text-label-large text-on-surface">
        {pageIndex + 1}ページ
      </h3>
      <div
        className="relative w-full"
        style={{ maxWidth: MAX_PAGE_WIDTH_PX, aspectRatio }}
      >
        <div ref={surfaceRef} className="absolute inset-0">
          {pageImage.objectUrl !== null ? (
            <img
              data-testid={`answer-area-page-${pageIndex}`}
              src={pageImage.objectUrl}
              alt={`${pageIndex + 1}ページ`}
              className="h-full w-full border border-outline-variant object-fill"
            />
          ) : (
            <div
              data-testid={`answer-area-page-placeholder-${pageIndex}`}
              className="h-full w-full border border-outline-variant bg-surface"
            />
          )}

          {!readOnly && imagePixelSize !== null ? (
            <div
              data-testid={`answer-area-draw-surface-${pageIndex}`}
              className="absolute inset-0"
              onPointerDown={(event) => {
                event.currentTarget.setPointerCapture(event.pointerId);
                onDraftStart(
                  normalizePointer(event, renderSize, imagePixelSize),
                );
              }}
              onPointerMove={(event) => {
                if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
                  return;
                }
                onDraftUpdate(
                  normalizePointer(event, renderSize, imagePixelSize),
                );
              }}
              onPointerUp={(event) => {
                if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
                  return;
                }
                event.currentTarget.releasePointerCapture(event.pointerId);
                onDraftCommit();
              }}
              onPointerCancel={(event) => {
                if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
                  return;
                }
                event.currentTarget.releasePointerCapture(event.pointerId);
                onDraftCommit();
              }}
              onClick={onClearSelection}
            />
          ) : null}

          {imagePixelSize !== null
            ? pageRegions.map(({ region, index }) => (
                <RegionOverlay
                  key={region.region_id}
                  index={index}
                  region={region}
                  questionNumbers={[]}
                  selected={index === selectedIndex}
                  readOnly={readOnly}
                  renderSize={renderSize}
                  imagePixelSize={imagePixelSize}
                  onSelect={() => {
                    onSelect(index);
                  }}
                  onMove={(delta) => {
                    onReplace(index, nudgeRegion(region, delta, false));
                  }}
                  onResize={(delta) => {
                    onReplace(index, nudgeRegion(region, delta, true));
                  }}
                  onEditStart={onEditStart}
                  onEditEnd={onEditEnd}
                />
              ))
            : null}

          {draftRect !== null ? (
            <div
              className="pointer-events-none absolute border-2 border-primary"
              style={{
                left: draftRect.left,
                top: draftRect.top,
                width: draftRect.width,
                height: draftRect.height,
              }}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function layoutRectFromPoints(
  start: { x: number; y: number },
  end: { x: number; y: number },
  renderSize: PixelSize,
  imagePixelSize: PixelSize,
): { left: number; top: number; width: number; height: number } {
  const topLeft = normalizedToLayoutPoint(
    Math.min(start.x, end.x),
    Math.min(start.y, end.y),
    renderSize,
    imagePixelSize,
  );
  const bottomRight = normalizedToLayoutPoint(
    Math.max(start.x, end.x),
    Math.max(start.y, end.y),
    renderSize,
    imagePixelSize,
  );
  return {
    left: topLeft.x,
    top: topLeft.y,
    width: Math.max(0, bottomRight.x - topLeft.x),
    height: Math.max(0, bottomRight.y - topLeft.y),
  };
}

function RegionOverlay({
  index,
  region,
  selected,
  readOnly,
  renderSize,
  imagePixelSize,
  onSelect,
  onMove,
  onResize,
  onEditStart,
  onEditEnd,
}: {
  index: number;
  region: RegionModel;
  questionNumbers: readonly string[];
  selected: boolean;
  readOnly: boolean;
  renderSize: PixelSize;
  imagePixelSize: PixelSize;
  onSelect: () => void;
  onMove: (delta: { x: number; y: number }) => void;
  onResize: (delta: { x: number; y: number }) => void;
  onEditStart: () => void;
  onEditEnd: () => void;
}): JSX.Element {
  const topLeft = normalizedToLayoutPoint(
    region.bbox.x0,
    region.bbox.y0,
    renderSize,
    imagePixelSize,
  );
  const bottomRight = normalizedToLayoutPoint(
    region.bbox.x1,
    region.bbox.y1,
    renderSize,
    imagePixelSize,
  );
  const unassigned = region.label === UNASSIGNED_QUESTION_LABEL;
  const borderClass = unassigned ? "border-attention" : "border-primary";
  const label = unassigned
    ? UNASSIGNED_QUESTION_DISPLAY_LABEL
    : region.label.length > 0
      ? region.label
      : regionKindLabel(region.kind);

  const lastPointer = useRef<{ x: number; y: number } | null>(null);
  const resizePointer = useRef<{ x: number; y: number } | null>(null);

  const nudgeWithKeyboard = (
    event: React.KeyboardEvent,
    resize: boolean,
  ): void => {
    const stepX = KEYBOARD_NUDGE_PX / renderSize.width;
    const stepY = KEYBOARD_NUDGE_PX / renderSize.height;
    let dx = 0;
    let dy = 0;
    switch (event.key) {
      case "ArrowLeft":
        dx = -stepX;
        break;
      case "ArrowRight":
        dx = stepX;
        break;
      case "ArrowUp":
        dy = -stepY;
        break;
      case "ArrowDown":
        dy = stepY;
        break;
      default:
        return;
    }
    event.preventDefault();
    if (resize) {
      onResize({ x: dx, y: dy });
    } else {
      onMove({ x: dx, y: dy });
    }
  };

  return (
    <div
      data-testid={`answer-area-box-${index}`}
      role="button"
      tabIndex={readOnly ? -1 : 0}
      aria-label={`回答欄 ${label}。矢印キーで移動、Shift+矢印で大きさ変更`}
      className={`absolute ${borderClass} ${selected ? "border-region-selected" : "border-region"} ${unassigned ? "bg-attention/10" : "bg-primary/10"} ${readOnly ? "" : "cursor-move"}`}
      style={{
        left: topLeft.x,
        top: topLeft.y,
        width: bottomRight.x - topLeft.x,
        height: bottomRight.y - topLeft.y,
      }}
      onPointerDown={(event) => {
        // Only start a move when the press lands on the box itself. A press on
        // the resize handle (or any other child) must not also capture the
        // pointer, or the box moves while the handle resizes.
        if (event.target !== event.currentTarget) {
          return;
        }
        event.stopPropagation();
        onSelect();
        event.currentTarget.setPointerCapture(event.pointerId);
        lastPointer.current = { x: event.clientX, y: event.clientY };
        onEditStart();
      }}
      onPointerMove={(event) => {
        if (!event.currentTarget.hasPointerCapture(event.pointerId)) {
          return;
        }
        const previous = lastPointer.current;
        if (previous === null || readOnly) {
          return;
        }
        const deltaX = (event.clientX - previous.x) / renderSize.width;
        const deltaY = (event.clientY - previous.y) / renderSize.height;
        lastPointer.current = { x: event.clientX, y: event.clientY };
        onMove({ x: deltaX, y: deltaY });
      }}
      onPointerUp={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
        lastPointer.current = null;
        onEditEnd();
      }}
      onPointerCancel={() => {
        lastPointer.current = null;
        onEditEnd();
      }}
      onFocus={onSelect}
      onKeyDown={(event) => {
        if (readOnly || event.target !== event.currentTarget) {
          return;
        }
        nudgeWithKeyboard(event, event.shiftKey);
      }}
    >
      <span className="pointer-events-none absolute left-1 top-1 rounded-sm bg-surface/85 px-xs text-label-small">
        {label}
      </span>
      {selected && !readOnly ? (
        <div
          data-testid={`answer-area-resize-${index}`}
          role="button"
          tabIndex={0}
          aria-label="回答欄の大きさを変える。矢印キーで大きさ変更"
          className={`absolute bottom-0 right-0 h-3.5 w-3.5 cursor-nwse-resize ${unassigned ? "bg-attention" : "bg-primary"}`}
          onPointerDown={(event) => {
            event.stopPropagation();
            event.currentTarget.setPointerCapture(event.pointerId);
            resizePointer.current = {
              x: event.clientX,
              y: event.clientY,
            };
            onEditStart();
          }}
          onPointerMove={(event) => {
            event.stopPropagation();
            if (
              !event.currentTarget.hasPointerCapture(event.pointerId) ||
              readOnly
            ) {
              return;
            }
            const previous = resizePointer.current;
            if (previous === null) {
              return;
            }
            const deltaX = (event.clientX - previous.x) / renderSize.width;
            const deltaY = (event.clientY - previous.y) / renderSize.height;
            resizePointer.current = { x: event.clientX, y: event.clientY };
            onResize({ x: deltaX, y: deltaY });
          }}
          onPointerUp={(event) => {
            event.stopPropagation();
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
            resizePointer.current = null;
            onEditEnd();
          }}
          onPointerCancel={() => {
            resizePointer.current = null;
            onEditEnd();
          }}
          onKeyDown={(event) => {
            if (readOnly || event.target !== event.currentTarget) {
              return;
            }
            nudgeWithKeyboard(event, true);
          }}
        />
      ) : null}
    </div>
  );
}

function RegionList({
  regions,
  regionListOrder,
  questionNumbers,
  readOnly,
  onReplace,
  onDelete,
  onEditNumerically,
}: {
  regions: readonly RegionModel[];
  regionListOrder: readonly number[];
  questionNumbers: readonly string[];
  readOnly: boolean;
  onReplace: (index: number, region: RegionModel) => void;
  onDelete: (index: number) => void;
  onEditNumerically?: (index: number) => void;
}): JSX.Element {
  if (regions.length === 0) {
    return (
      <p data-testid="answer-area-empty" className="text-body-medium">
        領域はまだありません。
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-sm">
      {regionListOrder.map((index) => {
        const region = regions[index];
        if (region === undefined) {
          return null;
        }
        const dropdownValue = questionNumbers.includes(region.label)
          ? region.label
          : UNASSIGNED_QUESTION_LABEL;
        return (
          <article
            key={region.region_id}
            data-testid={`answer-area-row-${index}`}
            className="rounded-lg border border-outline-variant bg-surface-container-low p-md"
          >
            <div className="flex flex-wrap items-center gap-sm">
              <div className="flex-1">
                <p className="text-body-medium">
                  {regionKindLabel(region.kind)}・{region.page_index + 1}ページ
                </p>
                {region.text !== null &&
                region.text !== undefined &&
                region.text.length > 0 ? (
                  <p
                    data-testid={`answer-area-note-${index}`}
                    className="text-body-small text-on-surface-variant"
                  >
                    {region.text}
                  </p>
                ) : null}
              </div>
              {region.kind === "answer_area" ? (
                <select
                  data-testid={`answer-area-question-${index}`}
                  className="select-themed rounded-md border border-outline px-sm py-xs"
                  disabled={readOnly}
                  value={dropdownValue}
                  onChange={(event) => {
                    onReplace(index, { ...region, label: event.target.value });
                  }}
                >
                  {questionNumbers.map((number) => (
                    <option key={number} value={number}>
                      {number}
                    </option>
                  ))}
                  <option value={UNASSIGNED_QUESTION_LABEL}>
                    {UNASSIGNED_QUESTION_DISPLAY_LABEL}
                  </option>
                </select>
              ) : (
                <span className="text-body-medium">{region.label}</span>
              )}
              {onEditNumerically !== undefined ? (
                <button
                  type="button"
                  data-testid={`answer-area-edit-${index}`}
                  className="rounded-md border border-outline px-sm py-xs text-ui-label"
                  disabled={readOnly}
                  onClick={() => {
                    onEditNumerically(index);
                  }}
                >
                  数値で編集
                </button>
              ) : null}
              <button
                type="button"
                data-testid={`answer-area-delete-${index}`}
                className="rounded-md border border-outline px-sm py-xs text-ui-label"
                disabled={readOnly}
                onClick={() => {
                  onDelete(index);
                }}
              >
                削除
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function isUnassigned(
  region: RegionModel,
  questionNumbers: readonly string[],
): boolean {
  return (
    region.kind === "answer_area" && !questionNumbers.includes(region.label)
  );
}
