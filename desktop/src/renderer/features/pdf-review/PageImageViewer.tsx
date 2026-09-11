import { useMemo, type JSX } from "react";

import {
  normalizedRectToLayout,
  resolveAnnotationRects,
  type AnnotationResponse,
  type NormalizedRect,
} from "../../core/pdf-review-geometry.js";
import type { RecognitionResponse } from "../../core/pdf-review-data.js";
import type { PageImageState } from "../answer-area-editor/answer-area-types.js";

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
  const aspect = displayedWidth / displayedHeight;
  const renderWidth = Math.min(640 * zoom, 1200);
  const renderHeight = renderWidth / aspect;
  const renderSize = { width: renderWidth, height: renderHeight };
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
    <div data-testid="review-page-viewer" className="flex flex-col gap-sm">
      <div
        data-testid="review-page-surface"
        className="relative mx-auto border border-outline-variant bg-surface-container-lowest"
        style={{ width: renderWidth, height: renderHeight }}
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
          <h3 className="text-title-small font-medium">設問コメント</h3>
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
