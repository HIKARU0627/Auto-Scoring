import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AnnotationResponse } from "../../src/renderer/core/pdf-review-geometry.js";
import type { ScoreOverlay } from "../../src/renderer/core/export-parity.js";
import { PageImageViewer } from "../../src/renderer/features/pdf-review/PageImageViewer.js";

/**
 * Issue #406: the review screen shows the score the export will draw, where
 * the export will draw it, and says where the comments go. The placement comes
 * from the sidecar, so this file checks the viewer renders it faithfully rather
 * than recomputing anything.
 */

const DISPLAYED = { displayedWidth: 595, displayedHeight: 842 };

function renderViewer(options: {
  annotations?: readonly AnnotationResponse[];
  scoreOverlay?: ScoreOverlay | null;
  questionCommentArea?: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
}): ReturnType<typeof render> {
  return render(
    <PageImageViewer
      pageImage={{
        objectUrl: "blob:page",
        pixelWidth: 1190,
        pixelHeight: 1684,
      }}
      {...DISPLAYED}
      annotations={options.annotations ?? []}
      recognitions={[]}
      questionAnswerArea={null}
      scoreOverlay={options.scoreOverlay ?? null}
      questionCommentArea={options.questionCommentArea ?? null}
      zoom={1}
    />,
  );
}

const COMMENT: AnnotationResponse = {
  id: "anno-1",
  submission_id: "sub-1",
  question_id: "q-1",
  source: "ai",
  kind: "comment",
  rect: null,
  anchor_text: "存在しない語",
  comment: "時制表現について確認",
  created_at: "2026-01-01T00:00:00Z",
};

describe("PageImageViewer export parity (Issue #406)", () => {
  it("draws the confirmed score at the placement rect, in the annotation mark colour", () => {
    const { getByTestId, queryByTestId } = renderViewer({
      scoreOverlay: {
        rect: { x: 0.8, y: 0.6, width: 0.2, height: 0.05 },
        text: "4/5",
        placement: "own",
      },
    });

    const overlay = getByTestId("review-score-overlay");
    expect(overlay.textContent).toContain("4/5");
    expect(overlay.getAttribute("data-placement")).toBe("own");
    expect(overlay.className).toContain("text-annotation-mark");
    // Not the UI's error colour -- the teacher's red pen (design-tokens §3.4).
    expect(overlay.className).not.toContain("text-error");
    expect(queryByTestId("review-score-overlay")).not.toBeNull();
  });

  it("keeps the margin line's question reference, matching the export's a/m 問N", () => {
    const { getByTestId } = renderViewer({
      scoreOverlay: {
        rect: { x: 0.005, y: 0.05, width: 0.03, height: 0.05 },
        text: "4/5 問2",
        placement: "margin",
      },
    });

    const overlay = getByTestId("review-score-overlay");
    expect(overlay.textContent).toContain("4/5 問2");
    expect(overlay.getAttribute("data-placement")).toBe("margin");
  });

  it("draws no score when the placement is absent", () => {
    const { queryByTestId } = renderViewer({});
    expect(queryByTestId("review-score-overlay")).toBeNull();
  });

  it("marks the comment band and says the comments land there", () => {
    const { getByTestId } = renderViewer({
      annotations: [COMMENT],
      questionCommentArea: { x: 0.7, y: 0.2, width: 0.2, height: 0.1 },
    });

    expect(getByTestId("review-comment-band")).toBeDefined();
    expect(getByTestId("review-comment-destination").textContent).toContain(
      "コメント帯",
    );
  });

  it("says comments leave the answer for the note page when there is no band", () => {
    const { queryByTestId, getByTestId } = renderViewer({
      annotations: [COMMENT],
    });

    expect(queryByTestId("review-comment-band")).toBeNull();
    expect(getByTestId("review-comment-destination").textContent).toContain(
      "末尾の注釈ページ",
    );
  });

  it("shows no comment destination when the question has no comment at all", () => {
    const { queryByTestId } = renderViewer({
      annotations: [
        {
          ...COMMENT,
          kind: "score",
          comment: "3/5",
        },
      ],
    });

    expect(queryByTestId("review-comment-destination")).toBeNull();
  });
});
