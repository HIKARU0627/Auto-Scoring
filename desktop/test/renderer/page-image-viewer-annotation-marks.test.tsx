import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ANNOTATION_SHAPE_KINDS,
  annotationShapePath,
} from "../../src/renderer/core/annotation-mark.js";
import type { AnnotationResponse } from "../../src/renderer/core/pdf-review-geometry.js";
import { PageImageViewer } from "../../src/renderer/features/pdf-review/PageImageViewer.js";

/**
 * Issue #403: every `AnnotationKind` gets its own mark on the answer page.
 * Before this, `PageImageViewer` drew one `border-error` rectangle for all of
 * them, so the screen never showed the ○×△ or the red text the exported PDF
 * does.
 *
 * These tests render the real viewer (not a mock) and read the SVG/text it
 * produces, because that is what "the screen draws a circle for circle" means.
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
      zoom={zoom}
    />,
  );
}

describe("PageImageViewer annotation marks (Issue #403)", () => {
  it("draws each of the seven kinds with its own shape or text, never one shared rectangle", () => {
    const { getByTestId } = renderViewer(SEVEN_KINDS);

    for (const kind of ANNOTATION_SHAPE_KINDS) {
      const mark = getByTestId(`annotation-${kind}-0`);
      expect(mark.getAttribute("data-kind")).toBe(kind);
      const path = mark.querySelector("path");
      expect(path, `${kind} must be drawn as a shape`).not.toBeNull();
      expect(path!.getAttribute("d")).toBe(annotationShapePath(kind));
    }

    for (const [kind, text] of [
      ["score", "3/5"],
      ["comment", COMMENT_TEXT],
    ] as const) {
      const mark = getByTestId(`annotation-${kind}-0`);
      expect(mark.getAttribute("data-kind")).toBe(kind);
      expect(
        mark.querySelector("path"),
        `${kind} is a text kind, not a shape`,
      ).toBeNull();
      expect(mark.textContent).toContain(text);
    }
  });

  it("paints every mark with the annotation-mark token, not the error border", () => {
    const { getByTestId, container } = renderViewer(SEVEN_KINDS);

    for (const kind of [...ANNOTATION_SHAPE_KINDS, "score", "comment"]) {
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

  it("names each mark by its kind label and comment so colour is not the only cue", () => {
    const { getByTestId } = renderViewer(SEVEN_KINDS);

    expect(
      getByTestId("annotation-circle-0").getAttribute("aria-label"),
    ).toContain("○");
    expect(
      getByTestId("annotation-triangle-0").getAttribute("aria-label"),
    ).toContain("△");
    const comment = getByTestId("annotation-comment-0");
    expect(comment.getAttribute("aria-label")).toContain("コメント");
    expect(comment.getAttribute("aria-label")).toContain(COMMENT_TEXT);
  });

  it("shows the kind label for a text mark that carries no comment", () => {
    const { getByTestId } = renderViewer([
      buildAnnotation({ id: "score", kind: "score", comment: null }),
    ]);
    expect(getByTestId("annotation-score-0").textContent).toContain("点数");
  });
});
