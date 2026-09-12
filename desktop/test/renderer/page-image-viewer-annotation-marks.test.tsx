import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ANNOTATION_SHAPE_KINDS,
  annotationShapePath,
} from "../../src/renderer/core/annotation-mark.js";
import type { AnnotationResponse } from "../../src/renderer/core/pdf-review-geometry.js";
import { PageImageViewer } from "../../src/renderer/features/pdf-review/PageImageViewer.js";

/**
 * Issue #403: every shape `AnnotationKind` gets its own mark on the answer
 * page, instead of one `border-error` rectangle for all of them.
 *
 * Issue #406 corrected the other half: `score`/`comment` are **not** marks on
 * the answer. The exported PDF draws the confirmed score from the grade (never
 * from a `SCORE` annotation) and sends comment prose to the trailing note page
 * (Issue #161), so drawing those two at their rects was a screen that disagreed
 * with the paper. Their text now appears in the 設問コメント output preview.
 */

const RECT = { x: 0.1, y: 0.1, width: 0.2, height: 0.06 };

const COMMENT_TEXT = "ここは時制が違う";

function buildAnnotation(
  overrides: Partial<AnnotationResponse> & { id: string; kind: string },
): AnnotationResponse {
  return {
    submission_id: "sub-1",
    question_id: "q-1",
    source: "ai",
    rect: RECT,
    anchor_text: null,
    comment: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const SEVEN_KINDS: readonly AnnotationResponse[] = [
  buildAnnotation({ id: "circle", kind: "circle" }),
  buildAnnotation({ id: "cross", kind: "cross" }),
  buildAnnotation({ id: "triangle", kind: "triangle" }),
  buildAnnotation({ id: "underline", kind: "underline" }),
  buildAnnotation({ id: "box", kind: "box" }),
  buildAnnotation({ id: "score", kind: "score", comment: "3/5" }),
  buildAnnotation({
    id: "comment",
    kind: "comment",
    comment: COMMENT_TEXT,
  }),
];

function renderViewer(
  annotations: readonly AnnotationResponse[],
  zoom = 1,
): ReturnType<typeof render> {
  return render(
    <PageImageViewer
      pageImage={{
        objectUrl: "blob:page",
        pixelWidth: 1190,
        pixelHeight: 1684,
      }}
      displayedWidth={595}
      displayedHeight={842}
      annotations={annotations}
      recognitions={[]}
      questionAnswerArea={null}
      questionPage={1}
      questionNumber="問1"
      zoom={zoom}
    />,
  );
}

describe("PageImageViewer annotation marks (Issue #403)", () => {
  it("draws each of the five shape kinds with its own path, never one shared rectangle", () => {
    const { getByTestId, queryByTestId } = renderViewer(SEVEN_KINDS);

    for (const kind of ANNOTATION_SHAPE_KINDS) {
      const mark = getByTestId(`annotation-${kind}-0`);
      expect(mark.getAttribute("data-kind")).toBe(kind);
      const path = mark.querySelector("path");
      expect(path, `${kind} must be drawn as a shape`).not.toBeNull();
      expect(path!.getAttribute("d")).toBe(annotationShapePath(kind));
    }

    // Issue #406: score/comment are not drawn on the answer, so their rects
    // do not produce a mark here.
    expect(queryByTestId("annotation-score-0")).toBeNull();
    expect(queryByTestId("annotation-comment-0")).toBeNull();
  });

  it("paints every shape with the annotation-mark token, not the error border", () => {
    const { getByTestId, container } = renderViewer(SEVEN_KINDS);

    for (const kind of ANNOTATION_SHAPE_KINDS) {
      const mark = getByTestId(`annotation-${kind}-0`);
      expect(mark.className).toContain("text-annotation-mark");
    }
    expect(container.innerHTML).not.toContain("border-error");
  });

  it("uses all five distinct shape paths", () => {
    const { container } = renderViewer(SEVEN_KINDS);
    const drawn = new Set(
      [...container.querySelectorAll("[data-kind] path")].map((path) =>
        path.getAttribute("d"),
      ),
    );
    expect(drawn.size).toBe(ANNOTATION_SHAPE_KINDS.length);
  });

  it("scales the mark with zoom, like the rest of the overlay", () => {
    const zoomedIn = renderViewer(
      [buildAnnotation({ id: "circle", kind: "circle" })],
      3,
    );
    const biggerStroke = zoomedIn
      .getByTestId("annotation-circle-0")
      .querySelector("path")!
      .getAttribute("stroke-width");
    zoomedIn.unmount();

    const zoomedOut = renderViewer(
      [buildAnnotation({ id: "circle", kind: "circle" })],
      1,
    );
    const smallerStroke = zoomedOut
      .getByTestId("annotation-circle-0")
      .querySelector("path")!
      .getAttribute("stroke-width");

    expect(Number(biggerStroke)).toBeGreaterThan(Number(smallerStroke));
  });

  it("names each shape mark by its kind label so colour is not the only cue", () => {
    const { getByTestId } = renderViewer(SEVEN_KINDS);

    expect(
      getByTestId("annotation-circle-0").getAttribute("aria-label"),
    ).toContain("○");
    expect(
      getByTestId("annotation-triangle-0").getAttribute("aria-label"),
    ).toContain("△");
  });

  it("shows a comment-kind annotation as a note, not as text on the answer", () => {
    const { getByTestId, queryByTestId } = renderViewer(SEVEN_KINDS);

    expect(queryByTestId("annotation-comment-0")).toBeNull();
    const notes = getByTestId("review-question-comments");
    expect(notes.textContent).toContain(COMMENT_TEXT);
    // The note names the output line's page and question.
    expect(notes.textContent).toContain("第1頁 問1");
  });
});
