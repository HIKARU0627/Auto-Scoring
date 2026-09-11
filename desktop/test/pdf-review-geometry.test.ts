import { describe, expect, it } from "vitest";

import {
  geometryToImagePixelSize,
  normalizedToLayoutPoint,
} from "../src/renderer/core/normalized-coordinates.js";
import {
  normalizedRectToLayout,
  resolveAnnotationRect,
  resolveAnnotationRects,
  type NormalizedRect,
} from "../src/renderer/core/pdf-review-geometry.js";
import type { components } from "../src/renderer/api/generated/schema.js";

type AnnotationResponse = components["schemas"]["AnnotationResponse"];
type RecognitionResponse = components["schemas"]["RecognitionResponse"];

const pocTestPoints = [
  { x: 0.12, y: 0.15 },
  { x: 0.5, y: 0.5 },
  { x: 0.9, y: 0.25 },
  { x: 0.25, y: 0.88 },
  { x: 0.82, y: 0.8 },
];

const a4Portrait = { width: 595, height: 842 };
const a4Rotate90 = { width: 842, height: 595 };

function pointRect(x: number, y: number): NormalizedRect {
  return { x, y, width: 0, height: 0 };
}

function annotation(
  input: Partial<AnnotationResponse> & { kind: string },
): AnnotationResponse {
  return {
    id: "anno-1",
    submission_id: "sub-1",
    question_id: "q-1",
    source: "ai",
    kind: input.kind,
    created_at: "2026-01-01T00:00:00Z",
    anchor_text: input.anchor_text ?? null,
    comment: input.comment ?? null,
    rect: input.rect ?? null,
  };
}

function recognitionWithBoxes(
  boxes: { text: string; rect: NormalizedRect }[],
): RecognitionResponse {
  return {
    id: "rec-1",
    submission_id: "sub-1",
    question_id: "q-1",
    source: "ai",
    stage: "ocr",
    text: "placeholder",
    confidence: 0.9,
    created_at: "2026-01-01T00:00:00Z",
    boxes: boxes.map((box) => ({
      text: box.text,
      x: box.rect.x,
      y: box.rect.y,
      width: box.rect.width,
      height: box.rect.height,
      unreadable: false,
    })),
  };
}

const dummyRect: NormalizedRect = {
  x: 0.01,
  y: 0.01,
  width: 0.01,
  height: 0.01,
};

describe("normalizedRectToLayout (INV-050, INV-051, INV-062, INV-063)", () => {
  for (const point of pocTestPoints) {
    it(`INV-050: places (${point.x}, ${point.y}) on A4 portrait`, () => {
      const imagePixelSize = geometryToImagePixelSize(
        a4Portrait.width,
        a4Portrait.height,
        2,
      );
      const layout = normalizedRectToLayout(
        pointRect(point.x, point.y),
        a4Portrait,
        imagePixelSize,
      );
      expect(layout.left).toBeCloseTo(point.x * a4Portrait.width, 6);
      expect(layout.top).toBeCloseTo(point.y * a4Portrait.height, 6);
    });

    it(`INV-050: places (${point.x}, ${point.y}) on A4 rotated 90°`, () => {
      const imagePixelSize = geometryToImagePixelSize(
        a4Rotate90.width,
        a4Rotate90.height,
        2,
      );
      const layout = normalizedRectToLayout(
        pointRect(point.x, point.y),
        a4Rotate90,
        imagePixelSize,
      );
      expect(layout.left).toBeCloseTo(point.x * a4Rotate90.width, 6);
      expect(layout.top).toBeCloseTo(point.y * a4Rotate90.height, 6);
    });
  }

  it("INV-051: overlay scales 2× when render size doubles (non-divisible dimensions)", () => {
    const rect: NormalizedRect = { x: 0.1, y: 0.2, width: 0.3, height: 0.4 };
    const displayedWidth = 333.7;
    const displayedHeight = 471.3;
    const scale = 2;
    const imagePixelSize = geometryToImagePixelSize(
      displayedWidth,
      displayedHeight,
      scale,
    );
    const render1x = { width: 417, height: 589 };
    const render2x = { width: 834, height: 1178 };
    const at1x = normalizedRectToLayout(rect, render1x, imagePixelSize);
    const at2x = normalizedRectToLayout(rect, render2x, imagePixelSize);
    expect(at2x.left).toBeCloseTo(at1x.left * 2, 6);
    expect(at2x.top).toBeCloseTo(at1x.top * 2, 6);
    expect(at2x.width).toBeCloseTo(at1x.width * 2, 6);
    expect(at2x.height).toBeCloseTo(at1x.height * 2, 6);
  });

  it("INV-062: normalized (0.5, 0.5) maps via image pixel dimensions", () => {
    const imagePixelSize = { width: 1190, height: 1684 };
    const renderSize = { width: 595, height: 842 };
    const layout = normalizedToLayoutPoint(
      0.5,
      0.5,
      renderSize,
      imagePixelSize,
    );
    expect(layout.x).toBeCloseTo(297.5, 6);
    expect(layout.y).toBeCloseTo(421, 6);
  });
});

describe("resolveAnnotationRect (INV-052–061)", () => {
  it("INV-052: explicit rect is used as-is", () => {
    const explicit: NormalizedRect = {
      x: 0.1,
      y: 0.1,
      width: 0.2,
      height: 0.2,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "circle", rect: explicit }),
      questionAnswerArea: null,
      recognitions: [],
    });
    expect(resolved).toEqual(explicit);
  });

  it("INV-053: anchor_text resolves to OCR box on full page", () => {
    const wordBox: NormalizedRect = {
      x: 0.4,
      y: 0.5,
      width: 0.05,
      height: 0.03,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "underline", anchor_text: "行く" }),
      questionAnswerArea: null,
      recognitions: [
        recognitionWithBoxes([
          { text: "走る", rect: dummyRect },
          { text: "行く", rect: wordBox },
        ]),
      ],
    });
    expect(resolved).toEqual(wordBox);
  });

  it("INV-054: crop coordinates map to page via answer_area", () => {
    const answerArea: NormalizedRect = {
      x: 0.5,
      y: 0.6,
      width: 0.4,
      height: 0.3,
    };
    const cropBox: NormalizedRect = {
      x: 0.5,
      y: 0.5,
      width: 0.1,
      height: 0.1,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "underline", anchor_text: "酸素" }),
      questionAnswerArea: answerArea,
      recognitions: [recognitionWithBoxes([{ text: "酸素", rect: cropBox }])],
    });
    expect(resolved?.x).toBeCloseTo(0.7, 9);
    expect(resolved?.y).toBeCloseTo(0.75, 9);
    expect(resolved?.width).toBeCloseTo(0.04, 9);
    expect(resolved?.height).toBeCloseTo(0.03, 9);
  });

  it("INV-055: degenerate answer_area is treated as full page", () => {
    const wordBox: NormalizedRect = {
      x: 0.4,
      y: 0.5,
      width: 0.05,
      height: 0.03,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "underline", anchor_text: "酸素" }),
      questionAnswerArea: { x: 0.5, y: 0.6, width: 0, height: 0.3 },
      recognitions: [recognitionWithBoxes([{ text: "酸素", rect: wordBox }])],
    });
    expect(resolved).toEqual(wordBox);
  });

  it("INV-056: OCR line break in box text still matches", () => {
    const wordBox: NormalizedRect = {
      x: 0.1,
      y: 0.2,
      width: 0.3,
      height: 0.1,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "酸素" }),
      questionAnswerArea: null,
      recognitions: [recognitionWithBoxes([{ text: "酸素\n", rect: wordBox }])],
    });
    expect(resolved).toEqual(wordBox);
  });

  it("INV-057: multi-token anchor resolves to union rect", () => {
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "葉緑体で" }),
      questionAnswerArea: null,
      recognitions: [
        recognitionWithBoxes([
          {
            text: "葉緑体",
            rect: { x: 0.1, y: 0.2, width: 0.08, height: 0.04 },
          },
          { text: "で", rect: { x: 0.18, y: 0.21, width: 0.04, height: 0.03 } },
        ]),
      ],
    });
    expect(resolved?.x).toBeCloseTo(0.1, 9);
    expect(resolved?.width).toBeCloseTo(0.12, 9);
  });

  it("INV-057a: cross-line anchor for CROSS restricts to first line (width < 95%)", () => {
    const multiLineBoxes = [
      { text: "春", rect: { x: 0.86, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "は", rect: { x: 0.92, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "あ", rect: { x: 0.01, y: 0.3, width: 0.06, height: 0.04 } },
      { text: "け", rect: { x: 0.07, y: 0.3, width: 0.06, height: 0.04 } },
      { text: "ぼ", rect: { x: 0.13, y: 0.3, width: 0.06, height: 0.04 } },
    ];
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "春はあけぼ" }),
      questionAnswerArea: null,
      recognitions: [recognitionWithBoxes(multiLineBoxes)],
    });
    expect(resolved).not.toBeNull();
    expect(resolved?.x).toBeCloseTo(0.86, 6);
    expect(resolved?.y).toBeCloseTo(0.1, 6);
    expect(resolved?.width).toBeCloseTo(0.12, 6);
    expect(resolved?.height).toBeCloseTo(0.04, 6);
    expect(resolved!.width).toBeLessThan(0.95);
  });

  it("INV-057b: cross-line anchor for UNDERLINE and BOX resolves to per-line rects", () => {
    const multiLineBoxes = [
      { text: "春", rect: { x: 0.86, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "は", rect: { x: 0.92, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "あ", rect: { x: 0.01, y: 0.3, width: 0.06, height: 0.04 } },
      { text: "け", rect: { x: 0.07, y: 0.3, width: 0.06, height: 0.04 } },
      { text: "ぼ", rect: { x: 0.13, y: 0.3, width: 0.06, height: 0.04 } },
    ];
    for (const kind of ["underline", "box"]) {
      const resolved = resolveAnnotationRects({
        annotation: annotation({ kind, anchor_text: "春はあけぼ" }),
        questionAnswerArea: null,
        recognitions: [recognitionWithBoxes(multiLineBoxes)],
      });
      expect(resolved).not.toBeNull();
      expect(resolved).toHaveLength(2);
      expect(resolved![0]!.x).toBeCloseTo(0.86, 6);
      expect(resolved![0]!.y).toBeCloseTo(0.1, 6);
      expect(resolved![0]!.width).toBeCloseTo(0.12, 6);
      expect(resolved![0]!.height).toBeCloseTo(0.04, 6);
      expect(resolved![0]!.width).toBeLessThan(0.95);
      expect(resolved![1]!.x).toBeCloseTo(0.01, 6);
      expect(resolved![1]!.y).toBeCloseTo(0.3, 6);
      expect(resolved![1]!.width).toBeCloseTo(0.18, 6);
      expect(resolved![1]!.height).toBeCloseTo(0.04, 6);
      expect(resolved![1]!.width).toBeLessThan(0.95);
      expect(
        resolveAnnotationRect({
          annotation: annotation({ kind, anchor_text: "春はあけぼ" }),
          questionAnswerArea: null,
          recognitions: [recognitionWithBoxes(multiLineBoxes)],
        }),
      ).toBeNull();
    }
  });

  it("INV-057c: single-line multi-box anchor resolves to union for both cross and underline", () => {
    const singleLineBoxes = [
      { text: "春", rect: { x: 0.2, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "は", rect: { x: 0.26, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "あ", rect: { x: 0.32, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "け", rect: { x: 0.38, y: 0.1, width: 0.06, height: 0.04 } },
      { text: "ぼ", rect: { x: 0.44, y: 0.1, width: 0.06, height: 0.04 } },
    ];
    for (const kind of ["cross", "underline"]) {
      const resolved = resolveAnnotationRect({
        annotation: annotation({ kind, anchor_text: "春はあけぼ" }),
        questionAnswerArea: null,
        recognitions: [recognitionWithBoxes(singleLineBoxes)],
      });
      expect(resolved).not.toBeNull();
      expect(resolved?.x).toBeCloseTo(0.2, 6);
      expect(resolved?.y).toBeCloseTo(0.1, 6);
      expect(resolved?.width).toBeCloseTo(0.3, 6);
      expect(resolved?.height).toBeCloseTo(0.04, 6);
    }
  });

  it("INV-057d: vertical text cross-column anchor handling", () => {
    const verticalBoxes = [
      { text: "春", rect: { x: 0.8, y: 0.86, width: 0.04, height: 0.06 } },
      { text: "は", rect: { x: 0.8, y: 0.92, width: 0.04, height: 0.06 } },
      { text: "あ", rect: { x: 0.6, y: 0.01, width: 0.04, height: 0.06 } },
      { text: "け", rect: { x: 0.6, y: 0.07, width: 0.04, height: 0.06 } },
    ];
    const crossRes = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "春はあけ" }),
      questionAnswerArea: null,
      recognitions: [recognitionWithBoxes(verticalBoxes)],
    });
    expect(crossRes).not.toBeNull();
    expect(crossRes?.x).toBeCloseTo(0.8, 6);
    expect(crossRes?.y).toBeCloseTo(0.86, 6);
    expect(crossRes?.width).toBeCloseTo(0.04, 6);
    expect(crossRes?.height).toBeCloseTo(0.12, 6);
    expect(crossRes!.height).toBeLessThan(0.95);

    const ulineRes = resolveAnnotationRects({
      annotation: annotation({ kind: "underline", anchor_text: "春はあけ" }),
      questionAnswerArea: null,
      recognitions: [recognitionWithBoxes(verticalBoxes)],
    });
    expect(ulineRes).not.toBeNull();
    expect(ulineRes).toHaveLength(2);
    expect(ulineRes![0]!.width).toBeLessThan(0.95);
    expect(ulineRes![1]!.width).toBeLessThan(0.95);
  });

  it("INV-058: shortest run wins", () => {
    const tight: NormalizedRect = {
      x: 0.5,
      y: 0.2,
      width: 0.04,
      height: 0.03,
    };
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "酸素" }),
      questionAnswerArea: null,
      recognitions: [
        recognitionWithBoxes([
          { text: "酸", rect: { x: 0.1, y: 0.2, width: 0.02, height: 0.03 } },
          { text: "素", rect: { x: 0.12, y: 0.2, width: 0.02, height: 0.03 } },
          { text: "酸素", rect: tight },
        ]),
      ],
    });
    expect(resolved?.x).toBe(tight.x);
    expect(resolved?.width).toBe(tight.width);
  });

  it("INV-059: run too long is refused", () => {
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "の" }),
      questionAnswerArea: null,
      recognitions: [
        recognitionWithBoxes([
          {
            text: "光合成は葉緑体で行われる",
            rect: { x: 0.1, y: 0.2, width: 0.8, height: 0.04 },
          },
        ]),
      ],
    });
    expect(resolved).toBeNull();
  });

  it("INV-060: non-consecutive boxes are refused", () => {
    const resolved = resolveAnnotationRect({
      annotation: annotation({ kind: "cross", anchor_text: "水デンプン" }),
      questionAnswerArea: null,
      recognitions: [
        recognitionWithBoxes([
          { text: "水\n", rect: { x: 0.1, y: 0.2, width: 0.04, height: 0.03 } },
          { text: "b\n", rect: { x: 0.1, y: 0.3, width: 0.04, height: 0.03 } },
          {
            text: "デンプン",
            rect: { x: 0.1, y: 0.4, width: 0.08, height: 0.03 },
          },
        ]),
      ],
    });
    expect(resolved).toBeNull();
  });

  it("INV-061: no fallback to score_area when anchor unmatched", () => {
    for (const kind of ["circle", "cross", "triangle", "score"]) {
      const resolved = resolveAnnotationRect({
        annotation: annotation({ kind, anchor_text: "存在しない語" }),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([{ text: "別の語", rect: dummyRect }]),
        ],
      });
      expect(resolved).toBeNull();
    }
  });
});
