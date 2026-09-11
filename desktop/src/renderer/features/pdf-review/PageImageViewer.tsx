import { useLayoutEffect, useMemo, useRef, useState, type JSX } from "react";

import {
  normalizedRectToLayout,
  resolveAnnotationRects,
  type AnnotationResponse,
  type NormalizedRect,
} from "../../core/pdf-review-geometry.js";
import type { RecognitionResponse } from "../../core/pdf-review-data.js";
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
  readonly zoom: number;
}

export function PageImageViewer({
  pageImage,
  displayedWidth,
  displayedHeight,
  annotations,
  recognitions,
  questionAnswerArea,
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

  const resolved = useMemo(() => {
    const placed: ResolvedAnnotation[] = [];
    const unresolved: AnnotationResponse[] = [];
    for (const annotation of annotations) {
      const rects = resolveAnnotationRects({
        annotation,
        questionAnswerArea,
        recognitions,
      });
      if (rects == null || rects.length === 0) {
        unresolved.push(annotation);
      } else {
        placed.push({ annotation, rects });
      }
    }
    return { placed, unresolved };
  }, [annotations, questionAnswerArea, recognitions]);

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
        {resolved.placed.flatMap(({ annotation, rects }) =>
          rects.map((rect, index) => {
            const layout = normalizedRectToLayout(
              rect,
              renderSize,
              imagePixelSize,
            );
            return (
              <div
                key={`${annotation.id}-${index}`}
                data-testid={`annotation-${annotation.id}-${index}`}
                className="pointer-events-none absolute border-2 border-error"
                style={{
                  left: layout.left,
                  top: layout.top,
                  width: layout.width,
                  height: layout.height,
                }}
                aria-hidden
              />
            );
          }),
        )}
      </div>
      {resolved.unresolved.length > 0 ? (
        <section data-testid="review-question-comments">
          <h3 className="text-ui-label font-semibold text-on-surface">
            設問コメント
          </h3>
          <ul className="list-disc pl-lg">
            {resolved.unresolved.map((annotation) => (
              <li key={annotation.id} className="text-body-medium">
                {annotation.comment ??
                  annotation.anchor_text ??
                  annotation.kind}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
