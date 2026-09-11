import { describe, expect, it } from "vitest";

import type { components } from "../src/renderer/api/generated/schema.js";
import {
  latestOcrRecognition,
  unreadableBoxesFromOcr,
} from "../src/renderer/core/unreadable-spans.js";

type RecognitionResponse = components["schemas"]["RecognitionResponse"];

function recognition(
  input: Partial<RecognitionResponse> &
    Pick<RecognitionResponse, "id" | "stage">,
): RecognitionResponse {
  return {
    submission_id: "sub-1",
    question_id: "q-1",
    source: "ai",
    text: "答案",
    confidence: 0.5,
    created_at: "2026-01-01T00:00:00Z",
    boxes: [],
    ...input,
  };
}

describe("unreadable-spans", () => {
  it("picks the newest OCR row when grading and OCR both exist", () => {
    const rows = [
      recognition({
        id: "ocr-1",
        stage: "ocr",
        created_at: "2026-01-01T00:00:00Z",
      }),
      recognition({
        id: "grade-1",
        stage: "grading",
        created_at: "2026-01-01T00:00:01Z",
      }),
    ];
    expect(latestOcrRecognition(rows)?.id).toBe("ocr-1");
  });

  it("returns only boxes flagged unreadable on the OCR row", () => {
    const rows = [
      recognition({
        id: "ocr-1",
        stage: "ocr",
        boxes: [
          {
            text: "読",
            x: 0.1,
            y: 0.1,
            width: 0.1,
            height: 0.1,
            unreadable: true,
          },
          {
            text: "め",
            x: 0.2,
            y: 0.1,
            width: 0.1,
            height: 0.1,
            unreadable: false,
          },
        ],
      }),
    ];
    expect(unreadableBoxesFromOcr(rows)).toHaveLength(1);
    expect(unreadableBoxesFromOcr(rows)[0]?.text).toBe("読");
  });
});
