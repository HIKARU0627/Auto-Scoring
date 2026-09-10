import { MINIMUM_BOX_SIZE } from "../../core/answer-area-constants.js";
import type { NormalizedBBox, RegionModel } from "./answer-area-types.js";

export function bboxFromPoints(
  a: { x: number; y: number },
  b: { x: number; y: number },
): NormalizedBBox | null {
  const x0 = Math.min(a.x, b.x);
  const x1 = Math.max(a.x, b.x);
  const y0 = Math.min(a.y, b.y);
  const y1 = Math.max(a.y, b.y);
  if (x1 - x0 < MINIMUM_BOX_SIZE || y1 - y0 < MINIMUM_BOX_SIZE) {
    return null;
  }
  return { x0, y0, x1, y1 };
}

export function freeRegionId(regions: readonly RegionModel[]): string {
  const taken = new Set(regions.map((region) => region.region_id));
  let index = 0;
  while (taken.has(`manual-answer-area-${index}`)) {
    index += 1;
  }
  return `manual-answer-area-${index}`;
}

export function regionKindLabel(kind: RegionModel["kind"]): string {
  switch (kind) {
    case "question":
      return "問題文";
    case "answer_area":
      return "回答欄";
    case "annotation_area":
      return "添削記号領域";
    case "score":
      return "配点";
    case "rubric":
      return "採点基準";
    case "model_answer":
      return "模範解答";
    default:
      return kind;
  }
}

export function nudgeRegion(
  region: RegionModel,
  delta: { x: number; y: number },
  resize: boolean,
): RegionModel {
  const bbox = region.bbox;
  let x0 = bbox.x0;
  let y0 = bbox.y0;
  let x1 = bbox.x1;
  let y1 = bbox.y1;
  if (resize) {
    x1 = Math.min(1, Math.max(x0 + MINIMUM_BOX_SIZE, x1 + delta.x));
    y1 = Math.min(1, Math.max(y0 + MINIMUM_BOX_SIZE, y1 + delta.y));
  } else {
    const width = x1 - x0;
    const height = y1 - y0;
    x0 = Math.min(1 - width, Math.max(0, x0 + delta.x));
    y0 = Math.min(1 - height, Math.max(0, y0 + delta.y));
    x1 = x0 + width;
    y1 = y0 + height;
  }
  return { ...region, bbox: { x0, y0, x1, y1 } };
}
