/**
 * Shape and label definitions for the seven `AnnotationKind` values the review
 * screen overlays on the answer page (Issue #403).
 *
 * The geometry lives here, separate from the component that draws it, so each
 * kind's mark can be tested on its own and `PageImageViewer` stays a thin
 * renderer. The five shape kinds are SVG paths in a fixed `0 0 100 100` box,
 * stretched onto the annotation's resolved rect with
 * `preserveAspectRatio="none"`. That reproduces the strokes the exported PDF
 * draws in `adapters/pdf/pdfium_pypdf_engine._draw_mark`: an ellipse, two
 * diagonals, an apex-up triangle, a bottom-edge line, and a rectangle.
 *
 * `SCORE` and `COMMENT` have no shape. They are also **not drawn as marks at
 * all** (Issue #406): the exported PDF takes the score from the confirmed grade
 * and sends comment prose to the trailing note page, so `PageImageViewer` only
 * draws shapes here and shows `score`/`comment` through
 * `core/export-parity.ts`'s output preview instead.
 */

/** The five kinds drawn as a stroked shape. */
export const ANNOTATION_SHAPE_KINDS = [
  "circle",
  "cross",
  "triangle",
  "underline",
  "box",
] as const;

export type AnnotationShapeKind = (typeof ANNOTATION_SHAPE_KINDS)[number];

/** The coordinate box every shape path below is written in. */
export const ANNOTATION_SHAPE_VIEW_BOX = "0 0 100 100";

const SHAPE_PATHS: Record<AnnotationShapeKind, string> = {
  // Drawn as an ellipse under `preserveAspectRatio="none"`, exactly like
  // `pdf_canvas.ellipse(x0, y0, x1, y1)`: a circle only when the rect is square.
  circle: "M 50 0 A 50 50 0 1 0 50 100 A 50 50 0 1 0 50 0",
  // `_draw_mark`'s CROSS: both diagonals of the rect.
  cross: "M 0 0 L 100 100 M 100 0 L 0 100",
  // Apex at the top edge's midpoint, base along the bottom edge.
  triangle: "M 50 0 L 100 100 L 0 100 Z",
  // A line along the bottom edge -- where `_draw_mark` strokes UNDERLINE.
  underline: "M 0 100 L 100 100",
  box: "M 0 0 L 100 0 L 100 100 L 0 100 Z",
};

const KIND_LABELS: Record<string, string> = {
  circle: "○",
  cross: "×",
  triangle: "△",
  underline: "下線",
  box: "囲み",
  score: "点数",
  comment: "コメント",
};

/**
 * The SVG path for ``kind`` in {@link ANNOTATION_SHAPE_VIEW_BOX}, or ``null``
 * when the kind is text (`score`/`comment`) or unknown.
 *
 * An unknown kind returns ``null`` so the caller falls back to showing its name
 * rather than drawing a shape that would misrepresent it.
 */
export function annotationShapePath(kind: string): string | null {
  return (SHAPE_PATHS as Record<string, string>)[kind] ?? null;
}

/**
 * A short Japanese label for ``kind``, used for the accessible name and as the
 * visible text of a text-kind mark that has no comment. Colour is never the
 * only cue (Issue #25): a mark is either a distinct shape or carries this text.
 */
export function annotationKindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}
