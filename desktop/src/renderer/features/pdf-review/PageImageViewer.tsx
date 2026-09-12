import { useLayoutEffect, useMemo, useRef, useState, type JSX } from "react";

import {
  ANNOTATION_SHAPE_VIEW_BOX,
  annotationKindLabel,
  annotationShapePath,
} from "../../core/annotation-mark.js";
import {
  normalizedRectToLayout,
  resolveAnnotationRects,
  type AnnotationResponse,
  type LayoutRect,
  type NormalizedRect,
} from "../../core/pdf-review-geometry.js";
import type { RecognitionResponse } from "../../core/pdf-review-data.js";
import {
  annotationNote,
  commentDestination,
  type AnnotationNote,
  type ScoreOverlay,
} from "../../core/export-parity.js";
import type { PageImageState } from "../answer-area-editor/answer-area-types.js";

/** Natural render width of the page at zoom 1, before the column clamps it. */
export const PAGE_BASE_RENDER_WIDTH = 640;

/** Hard ceiling so a zoomed page cannot grow without bound. */
export const PAGE_MAX_RENDER_WIDTH = 1200;

export interface PageRenderSize {
  readonly width: number;
  readonly height: number;
}

/**
 * The pixel size the page surface is drawn at inside its column (Issue #354).
 *
 * The page used to be a fixed `min(640 * zoom, 1200)` wide, so in the two-column
 * review layout its box crossed the boundary into the inspector -- on narrow
 * widths the answer image could sit over the 続きを表示 control and swallow the
 * click (Issue #354). Fitting the natural width to the measured column keeps the
 * image inside its own column while still letting zoom scale past the column and
 * scroll horizontally.
 *
 * `availableWidth` is `null` before the first measurement; the natural width is
 * used then so the surface never collapses.
 */
export function resolvePageRenderSize(input: {
  readonly availableWidth: number | null;
  readonly zoom: number;
  readonly displayedWidth: number;
  readonly displayedHeight: number;
}): PageRenderSize {
  const aspect = input.displayedWidth / input.displayedHeight;
  const columnWidth =
    input.availableWidth != null && input.availableWidth > 0
      ? input.availableWidth
      : PAGE_BASE_RENDER_WIDTH;
  const fittedWidth = Math.min(PAGE_BASE_RENDER_WIDTH, columnWidth);
  const width = Math.min(fittedWidth * input.zoom, PAGE_MAX_RENDER_WIDTH);
  return { width, height: width / aspect };
}

export interface ResolvedAnnotation {
  readonly annotation: AnnotationResponse;
  readonly rects: readonly NormalizedRect[];
}

export interface PageImageViewerProps {
  readonly pageImage: PageImageState;
  readonly displayedWidth: number;
  readonly displayedHeight: number;
  readonly annotations: readonly AnnotationResponse[];
  readonly recognitions: readonly RecognitionResponse[];
  readonly questionAnswerArea: NormalizedRect | null | undefined;
  /**
   * The confirmed grade's score, at the rect the export will draw it on
   * (Issue #406). `null` when there is no grade yet or the export refuses the
   * question (`no_room_for_score`) -- in the latter case the page is called out
   * by `PdfReviewPage`, not here.
   */
  readonly scoreOverlay?: ScoreOverlay | null;
  /**
   * `Question.comment_area`, when a human placed an `ANNOTATION_AREA` region.
   * The export writes the question's comments into this band; the viewer draws
   * its outline so the reviewer can see where they will land. When `null`,
   * they go to an appended note page instead (Issue #161).
   */
  readonly questionCommentArea?: NormalizedRect | null | undefined;
  /** The question's own `page`, used in the note reference `第N頁 問M`. */
  readonly questionPage?: number | undefined;
  /** The question's stored `number`, verbatim, for the same reference. */
  readonly questionNumber?: string | undefined;
  readonly zoom: number;
}

export function PageImageViewer({
  pageImage,
  displayedWidth,
  displayedHeight,
  annotations,
  recognitions,
  questionAnswerArea,
  scoreOverlay,
  questionCommentArea,
  questionPage,
  questionNumber,
  zoom,
}: PageImageViewerProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const [availableWidth, setAvailableWidth] = useState<number | null>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (container == null) {
      return undefined;
    }
    const measure = () => {
      const width = container.getBoundingClientRect().width;
      setAvailableWidth(width > 0 ? width : null);
    };
    measure();
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      const width =
        entry?.contentRect.width ?? container.getBoundingClientRect().width;
      setAvailableWidth(width > 0 ? width : null);
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
    };
  }, []);

  const renderSize = resolvePageRenderSize({
    availableWidth,
    zoom,
    displayedWidth,
    displayedHeight,
  });
  const imagePixelSize = {
    width: pageImage.pixelWidth ?? Math.ceil(displayedWidth * 2),
    height: pageImage.pixelHeight ?? Math.ceil(displayedHeight * 2),
  };

  const destination = commentDestination(questionCommentArea);
  const resolved = useMemo(() => {
    const placed: ResolvedAnnotation[] = [];
    const notes: AnnotationNote[] = [];
    for (const annotation of annotations) {
      const rects = resolveAnnotationRects({
        annotation,
        questionAnswerArea,
        recognitions,
      });
      const isShape = annotationShapePath(annotation.kind) != null;
      if (isShape && rects != null && rects.length > 0) {
        placed.push({ annotation, rects });
      }
      const note = annotationNote({
        kind: annotation.kind,
        comment: annotation.comment,
        placed: rects != null && rects.length > 0,
        page: questionPage ?? 1,
        questionNumber: questionNumber ?? "",
        destination,
      });
      if (note != null) {
        notes.push(note);
      }
    }
    return { placed, notes };
  }, [
    annotations,
    destination,
    questionAnswerArea,
    questionPage,
    questionNumber,
    recognitions,
  ]);
  const scoreLayout =
    scoreOverlay == null
      ? null
      : normalizedRectToLayout(scoreOverlay.rect, renderSize, imagePixelSize);
  const commentBandLayout =
    questionCommentArea == null
      ? null
      : normalizedRectToLayout(questionCommentArea, renderSize, imagePixelSize);

  return (
    <div
      ref={containerRef}
      data-testid="review-page-viewer"
      className="flex min-w-0 flex-col gap-sm"
    >
      <div
        data-testid="review-page-surface"
        className="relative mx-auto bg-surface-container-lowest"
        style={{ width: renderSize.width, height: renderSize.height }}
      >
        {pageImage.objectUrl != null ? (
          <img
            src={pageImage.objectUrl}
            alt="答案ページ"
            className="block h-full w-full object-contain"
            data-testid="review-page-image"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-on-surface-variant">
            ページ画像を読み込めませんでした
          </div>
        )}
        {commentBandLayout != null ? (
          <div
            data-testid="review-comment-band"
            aria-label="コメント帯（出力先）"
            className="pointer-events-none absolute border border-dashed border-annotation-mark"
            style={{
              left: commentBandLayout.left,
              top: commentBandLayout.top,
              width: commentBandLayout.width,
              height: commentBandLayout.height,
            }}
          />
        ) : null}
        {resolved.placed.flatMap(({ annotation, rects }) =>
          rects.map((rect, index) => {
            const layout = normalizedRectToLayout(
              rect,
              renderSize,
              imagePixelSize,
            );
            return (
              <AnnotationMarkView
                key={`${annotation.id}-${index}`}
                annotation={annotation}
                layout={layout}
                pixelsPerPoint={renderSize.width / Math.max(1, displayedWidth)}
                testId={`annotation-${annotation.id}-${index}`}
              />
            );
          }),
        )}
        {scoreLayout != null && scoreOverlay != null ? (
          <div
            data-testid="review-score-overlay"
            data-placement={scoreOverlay.placement}
            role="img"
            aria-label={`出力される点数 ${scoreOverlay.text}`}
            className="pointer-events-none absolute overflow-hidden text-annotation-mark"
            style={{
              left: scoreLayout.left,
              top: scoreLayout.top,
              width: scoreLayout.width,
              height: scoreLayout.height,
              fontSize: Math.min(
                Math.max(
                  scoreLayout.height,
                  MARK_MIN_FONT_PT *
                    (renderSize.width / Math.max(1, displayedWidth)),
                ),
                MARK_MAX_FONT_PT *
                  (renderSize.width / Math.max(1, displayedWidth)),
              ),
            }}
          >
            <span className="block leading-tight break-words whitespace-pre-wrap">
              {scoreOverlay.text}
            </span>
          </div>
        ) : null}
      </div>
      {resolved.notes.length > 0 ? (
        <section data-testid="review-question-comments">
          <h3 className="text-ui-label font-semibold text-on-surface">
            設問コメント
          </h3>
          <p
            data-testid="review-comment-destination"
            className="text-body-small text-on-surface-variant"
          >
            {destination === "band"
              ? "答案の上ではなく、上図の点線の枠（コメント帯）にこのままの順で出力されます。"
              : "答案の上ではなく、末尾の注釈ページにこの行のまま出力されます。"}
          </p>
          <ul className="list-disc pl-lg">
            {resolved.notes.map((note, index) => (
              <li key={`note-${index}`} className="text-body-medium">
                {note.reference != null ? (
                  <span className="text-on-surface-variant">
                    {note.reference}{" "}
                  </span>
                ) : null}
                {note.symbol != null ? <span>{note.symbol} </span> : null}
                {note.text.length > 0 ? <span>{note.text}</span> : null}
                {note.suffix.length > 0 ? <span>{note.suffix}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/**
 * A mark's rendered stroke width, as a fraction of its rect's width.
 *
 * The exported PDF draws every shape at `max(1.0, width_pt * 0.04)`
 * (`adapters/pdf/pdfium_pypdf_engine._draw_mark`); matching the fraction keeps
 * a small `×` from turning into a thick blob and a large `○` from turning into
 * a hairline. `vector-effect: non-scaling-stroke` keeps the SVG's non-uniform
 * stretch from distorting it, and the value is in layout pixels so it scales
 * with zoom.
 */
const MARK_STROKE_FRACTION = 0.04;

/** The PDF's own text-size floor and ceiling, in points (`_draw_text`). */
const MARK_MIN_FONT_PT = 6;
const MARK_MAX_FONT_PT = 14;

/**
 * One annotation drawn on the answer page (Issue #403).
 *
 * Replaces a single `border-error` rectangle that was used for every kind. The
 * shape kinds draw the same strokes the exported PDF does (see
 * `core/annotation-mark.ts`); `score`/`comment` draw text. Colour is always
 * `--color-annotation-mark` -- the teacher's red pen, not `colorScheme.error`
 * (`docs/design-tokens.md` §3.4) -- and never the only cue: a mark is a
 * distinct shape or visible text, with the kind and comment as its accessible
 * name.
 */
function AnnotationMarkView({
  annotation,
  layout,
  pixelsPerPoint,
  testId,
}: {
  annotation: AnnotationResponse;
  layout: LayoutRect;
  pixelsPerPoint: number;
  testId: string;
}): JSX.Element {
  const shapePath = annotationShapePath(annotation.kind);
  const label = annotationKindLabel(annotation.kind);
  const comment = (annotation.comment ?? "").trim();
  const accessibleName =
    comment.length > 0 ? `添削記号 ${label} ${comment}` : `添削記号 ${label}`;
  const position = {
    left: layout.left,
    top: layout.top,
    width: layout.width,
    height: layout.height,
  };

  if (shapePath != null) {
    return (
      <div
        data-testid={testId}
        data-kind={annotation.kind}
        role="img"
        aria-label={accessibleName}
        className="pointer-events-none absolute text-annotation-mark"
        style={position}
      >
        <svg
          viewBox={ANNOTATION_SHAPE_VIEW_BOX}
          preserveAspectRatio="none"
          className="block h-full w-full"
          aria-hidden
        >
          <path
            d={shapePath}
            fill="none"
            stroke="currentColor"
            strokeWidth={Math.max(1, layout.width * MARK_STROKE_FRACTION)}
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
    );
  }

  return (
    <div
      data-testid={testId}
      data-kind={annotation.kind}
      role="img"
      aria-label={accessibleName}
      title={comment.length > 0 ? comment : undefined}
      className="pointer-events-none absolute overflow-hidden text-annotation-mark"
      style={{
        ...position,
        fontSize: Math.min(
          Math.max(layout.height, MARK_MIN_FONT_PT * pixelsPerPoint),
          MARK_MAX_FONT_PT * pixelsPerPoint,
        ),
      }}
    >
      <span className="block leading-tight break-words whitespace-pre-wrap">
        {comment.length > 0 ? comment : label}
      </span>
    </div>
  );
}
