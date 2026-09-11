import type { components } from "../api/generated/schema.js";

export type BoundingBoxResponse = components["schemas"]["BoundingBoxResponse"];
export type RecognitionResponse = components["schemas"]["RecognitionResponse"];

/** The OCR pipeline row whose boxes carry per-span `unreadable` flags. */
export function latestOcrRecognition(
  recognitions: readonly RecognitionResponse[],
): RecognitionResponse | null {
  for (let index = recognitions.length - 1; index >= 0; index -= 1) {
    const row = recognitions[index];
    if (row?.stage === "ocr") {
      return row;
    }
  }
  return null;
}

export function unreadableBoxesFromOcr(
  recognitions: readonly RecognitionResponse[],
): readonly BoundingBoxResponse[] {
  const ocr = latestOcrRecognition(recognitions);
  if (ocr == null) {
    return [];
  }
  return ocr.boxes.filter((box) => box.unreadable);
}
