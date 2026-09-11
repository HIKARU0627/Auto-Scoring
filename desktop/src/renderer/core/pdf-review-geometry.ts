import type { components } from "../api/generated/schema.js";
import {
  normalizedToLayoutPoint,
  type PixelSize,
} from "./normalized-coordinates.js";

export type NormalizedRect = components["schemas"]["NormalizedRectResponse"];
export type AnnotationResponse = components["schemas"]["AnnotationResponse"];
export type RecognitionResponse = components["schemas"]["RecognitionResponse"];
export type BoundingBoxResponse = components["schemas"]["BoundingBoxResponse"];

export interface LayoutRect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

const FULL_PAGE_AREA: NormalizedRect = {
  x: 0,
  y: 0,
  width: 1,
  height: 1,
};

/** Maps a normalized rect to layout pixels via image pixel dimensions (§7). */
export function normalizedRectToLayout(
  rect: NormalizedRect,
  renderSize: PixelSize,
  imagePixelSize: PixelSize,
): LayoutRect {
  const topLeft = normalizedToLayoutPoint(
    rect.x,
    rect.y,
    renderSize,
    imagePixelSize,
  );
  const bottomRight = normalizedToLayoutPoint(
    rect.x + rect.width,
    rect.y + rect.height,
    renderSize,
    imagePixelSize,
  );
  return {
    left: topLeft.x,
    top: topLeft.y,
    width: bottomRight.x - topLeft.x,
    height: bottomRight.y - topLeft.y,
  };
}

export function resolveAnnotationRects(input: {
  annotation: AnnotationResponse;
  questionAnswerArea: NormalizedRect | null | undefined;
  recognitions: readonly RecognitionResponse[];
}): readonly NormalizedRect[] | null {
  const { annotation, questionAnswerArea, recognitions } = input;
  if (annotation.rect != null) {
    return [annotation.rect];
  }
  const anchorText = annotation.anchor_text;
  if (anchorText != null && anchorText.length > 0) {
    const matched = findAnchorTextRects(
      anchorText,
      recognitions,
      effectiveAnswerArea(questionAnswerArea),
      annotation.kind,
    );
    if (matched != null) {
      return matched;
    }
  }
  return null;
}

export function resolveAnnotationRect(input: {
  annotation: AnnotationResponse;
  questionAnswerArea: NormalizedRect | null | undefined;
  recognitions: readonly RecognitionResponse[];
}): NormalizedRect | null {
  const rects = resolveAnnotationRects(input);
  if (rects == null || rects.length !== 1) {
    return null;
  }
  return rects[0] ?? null;
}

function effectiveAnswerArea(
  answerArea: NormalizedRect | null | undefined,
): NormalizedRect {
  if (answerArea == null || answerArea.width <= 0 || answerArea.height <= 0) {
    return FULL_PAGE_AREA;
  }
  return answerArea;
}

function findAnchorTextRects(
  anchorText: string,
  recognitions: readonly RecognitionResponse[],
  answerArea: NormalizedRect,
  kind?: string | null,
): readonly NormalizedRect[] | null {
  const needle = normalizedForAnchor(anchorText);
  if (needle.length === 0) {
    return null;
  }
  for (let i = recognitions.length - 1; i >= 0; i -= 1) {
    const recognition = recognitions[i];
    if (recognition == null) {
      continue;
    }
    const matched = shortestBoxRun(needle, recognition.boxes, kind);
    if (matched != null) {
      return matched.map((rect) => cropRelativeToPage(rect, answerArea));
    }
  }
  return null;
}

function groupBoxesByLine(
  boxes: readonly BoundingBoxResponse[],
): BoundingBoxResponse[][] {
  if (boxes.length === 0) {
    return [];
  }
  const groups: BoundingBoxResponse[][] = [[boxes[0]!]];
  for (let index = 1; index < boxes.length; index += 1) {
    const previous = boxes[index - 1]!;
    const current = boxes[index]!;
    if (isSameLine(previous, current)) {
      groups[groups.length - 1]!.push(current);
    } else {
      groups.push([current]);
    }
  }
  return groups;
}

function normalizedForAnchor(text: string): string {
  const folded = Array.from(text)
    .map((char) => {
      const code = char.codePointAt(0) ?? 0;
      if (code >= 0xff01 && code <= 0xff5e) {
        return String.fromCodePoint(code - 0xfee0);
      }
      return char;
    })
    .join("");
  return folded.replace(/\s+/g, "");
}

function isSameLine(b1: BoundingBoxResponse, b2: BoundingBoxResponse): boolean {
  if (b1.text.includes("\n")) {
    return false;
  }
  const minH = Math.min(b1.height, b2.height);
  const yOverlap =
    Math.min(b1.y + b1.height, b2.y + b2.height) - Math.max(b1.y, b2.y);
  const isHoriz =
    minH > 0 && yOverlap > 0.5 * minH && b2.x >= b1.x - b1.width * 0.1;

  const minW = Math.min(b1.width, b2.width);
  const xOverlap =
    Math.min(b1.x + b1.width, b2.x + b2.width) - Math.max(b1.x, b2.x);
  const isVert =
    minW > 0 && xOverlap > 0.5 * minW && b2.y >= b1.y - b1.height * 0.1;

  return isHoriz || isVert;
}

function shortestBoxRun(
  needle: string,
  boxesIn: readonly BoundingBoxResponse[],
  kind?: string | null,
): readonly NormalizedRect[] | null {
  const boxes = [...boxesIn];
  const texts = boxes.map((box) => normalizedForAnchor(box.text));
  const limit = runLengthLimit(needle);
  let bestStart: number | null = null;
  let bestEnd: number | null = null;
  for (let start = 0; start < boxes.length; start += 1) {
    let joined = "";
    for (let end = start; end < boxes.length; end += 1) {
      joined += texts[end];
      if (joined.length > limit) {
        break;
      }
      if (joined.includes(needle)) {
        if (bestStart == null || end - start < bestEnd! - bestStart) {
          bestStart = start;
          bestEnd = end;
        }
        break;
      }
    }
  }
  if (bestStart == null || bestEnd == null) {
    return null;
  }

  const matchedBoxes = boxes.slice(bestStart, bestEnd + 1);
  const lineGroups = groupBoxesByLine(matchedBoxes);
  if (lineGroups.length === 1) {
    return [unionOfBoxes(matchedBoxes)];
  }

  const isCross = kind?.toLowerCase() === "cross";
  if (isCross) {
    return [unionOfBoxes(lineGroups[0]!)];
  }

  const kindLower = kind?.toLowerCase();
  if (kindLower === "underline" || kindLower === "box") {
    return lineGroups.map((group) => unionOfBoxes(group));
  }
  return null;
}

function runLengthLimit(needle: string): number {
  return 2 * needle.length + 2;
}

function unionOfBoxes(boxes: readonly BoundingBoxResponse[]): NormalizedRect {
  const first = boxes[0];
  if (first == null) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }
  let left = first.x;
  let top = first.y;
  let right = first.x + first.width;
  let bottom = first.y + first.height;
  for (const box of boxes.slice(1)) {
    left = Math.min(left, box.x);
    top = Math.min(top, box.y);
    right = Math.max(right, box.x + box.width);
    bottom = Math.max(bottom, box.y + box.height);
  }
  return {
    x: left,
    y: top,
    width: boxes.length === 1 ? first.width : right - left,
    height: boxes.length === 1 ? first.height : bottom - top,
  };
}

function cropRelativeToPage(
  rect: NormalizedRect,
  answerArea: NormalizedRect,
): NormalizedRect {
  return {
    x: answerArea.x + rect.x * answerArea.width,
    y: answerArea.y + rect.y * answerArea.height,
    width: rect.width * answerArea.width,
    height: rect.height * answerArea.height,
  };
}
