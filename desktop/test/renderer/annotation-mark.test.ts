import { describe, expect, it } from "vitest";

import {
  ANNOTATION_SHAPE_KINDS,
  ANNOTATION_SHAPE_VIEW_BOX,
  annotationKindLabel,
  annotationShapePath,
} from "../../src/renderer/core/annotation-mark.js";

/**
 * Issue #403: the seven `AnnotationKind` values must be distinguishable by
 * shape, not by colour alone. The geometry is defined here so this module --
 * not the component -- is what pins each kind to its stroke.
 */

const EXPECTED_PATHS: Record<string, string> = {
  circle: "M 50 0 A 50 50 0 1 0 50 100 A 50 50 0 1 0 50 0",
  cross: "M 0 0 L 100 100 M 100 0 L 0 100",
  triangle: "M 50 0 L 100 100 L 0 100 Z",
  underline: "M 0 100 L 100 100",
  box: "M 0 0 L 100 0 L 100 100 L 0 100 Z",
};

describe("annotationShapePath", () => {
  it("gives every shape kind its own path, so no two kinds draw the same mark", () => {
    const paths = ANNOTATION_SHAPE_KINDS.map((kind) =>
      annotationShapePath(kind),
    );
    expect(paths.every((path) => path != null && path.length > 0)).toBe(true);
    expect(new Set(paths).size).toBe(ANNOTATION_SHAPE_KINDS.length);
  });

  it("pins each shape kind to the stroke the exported PDF draws", () => {
    for (const [kind, path] of Object.entries(EXPECTED_PATHS)) {
      expect(annotationShapePath(kind), kind).toBe(path);
    }
  });

  it("returns null for the text kinds and for an unknown kind", () => {
    expect(annotationShapePath("score")).toBeNull();
    expect(annotationShapePath("comment")).toBeNull();
    expect(annotationShapePath("something-else")).toBeNull();
  });

  it("writes every path in the shared 0..100 box the renderer stretches", () => {
    expect(ANNOTATION_SHAPE_VIEW_BOX).toBe("0 0 100 100");
  });
});

describe("annotationKindLabel", () => {
  it("labels all seven kinds so a mark can be named without relying on colour", () => {
    expect(annotationKindLabel("circle")).toBe("○");
    expect(annotationKindLabel("cross")).toBe("×");
    expect(annotationKindLabel("triangle")).toBe("△");
    expect(annotationKindLabel("underline")).toBe("下線");
    expect(annotationKindLabel("box")).toBe("囲み");
    expect(annotationKindLabel("score")).toBe("点数");
    expect(annotationKindLabel("comment")).toBe("コメント");
  });

  it("falls back to the raw kind for a kind it does not know", () => {
    expect(annotationKindLabel("something-else")).toBe("something-else");
  });
});
