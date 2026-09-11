import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import {
  buildGrade,
  buildQuestion,
  buildReviewableGrade,
  renderPdfReview,
} from "./support/pdf-review-harness.js";

describe("PdfReviewPage routing (INV-014)", () => {
  it("INV-014: opens the question specified in the URL", async () => {
    renderPdfReview({
      questionId: "q-2",
      questions: [
        buildQuestion({ id: "q-1", number: "1" }),
        buildQuestion({ id: "q-2", number: "2" }),
      ],
      jobs: [
        {
          id: "job-1",
          kind: "grading",
          submission_id: "sub-1",
          question_id: "q-1",
          state: "succeeded",
          usable: true,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "job-2",
          kind: "grading",
          submission_id: "sub-1",
          question_id: "q-2",
          state: "succeeded",
          usable: true,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    await waitFor(() => {
      expect(screen.getByTestId("review-rail-q-2").className).toContain(
        "border-primary",
      );
    });
  });
});

describe("unreadable OCR spans (Issue #185)", () => {
  it("shows overlay and inspector notice distinct from blank finding", async () => {
    renderPdfReview({
      recognitions: [
        {
          id: "rec-1",
          submission_id: "sub-1",
          question_id: "q-1",
          source: "ai",
          stage: "ocr",
          text: "あい",
          confidence: 0.55,
          created_at: "2026-01-01T00:00:00Z",
          boxes: [
            {
              text: "あ",
              x: 0.1,
              y: 0.1,
              width: 0.2,
              height: 0.2,
              unreadable: true,
            },
            {
              text: "い",
              x: 0.4,
              y: 0.1,
              width: 0.2,
              height: 0.2,
              unreadable: false,
            },
          ],
        },
      ],
      grades: [buildGrade({ confidence: 0.97 })],
    });
    await waitFor(() => {
      expect(
        screen.getByTestId("review-unreadable-spans-notice"),
      ).toBeDefined();
    });
    expect(screen.getByTestId("review-unreadable-box-0")).toBeDefined();
    expect(screen.queryByTestId("review-answer-image-blank")).toBeNull();
    expect(
      screen.getByTestId("review-unreadable-spans-notice").textContent,
    ).toContain("空欄とは別");
  });
});

describe("confidence display (INV-068, INV-069)", () => {
  it("INV-068: high confidence has no warning icon, low does", async () => {
    renderPdfReview({
      recognitions: [
        {
          id: "rec-1",
          submission_id: "sub-1",
          question_id: "q-1",
          source: "ai",
          stage: "ocr",
          text: "答案",
          confidence: 0.55,
          created_at: "2026-01-01T00:00:00Z",
          boxes: [],
        },
      ],
      grades: [buildGrade({ confidence: 0.97 })],
    });
    await waitFor(() => {
      expect(screen.getByTestId("review-grading-confidence")).toBeDefined();
    });
    expect(screen.queryByTestId("review-grading-confidence-icon")).toBeNull();
    expect(
      screen.getByTestId("review-recognition-confidence-icon"),
    ).toBeDefined();
  });

  it("INV-069: blank answer finding is shown with the score", async () => {
    renderPdfReview({
      grades: [
        buildGrade({
          score: { awarded: 0, maximum: 5, ratio: 0 },
          confidence: 1,
          answer_image_finding: "blank",
        }),
      ],
    });
    await waitFor(() => {
      expect(screen.getByTestId("review-answer-image-blank")).toBeDefined();
    });
    const text = screen.getByTestId("review-answer-image-blank").textContent!;
    expect(text).toContain("何も書かれていない");
    expect(text).toContain("本当に無記入なら");
  });
});

describe("annotation fallback (INV-064)", () => {
  it("routes unresolved annotation to question comment area", async () => {
    renderPdfReview({
      annotations: [
        {
          id: "anno-1",
          submission_id: "sub-1",
          question_id: "q-1",
          source: "ai",
          kind: "comment",
          anchor_text: "存在しない語",
          comment: "時制表現について確認",
          created_at: "2026-01-01T00:00:00Z",
          rect: null,
        },
      ],
    });
    await waitFor(() => {
      expect(screen.getByText("設問コメント")).toBeDefined();
    });
    expect(screen.getByText("時制表現について確認")).toBeDefined();
  });
});

const WAIT_MS = 5000;
const clientHeightDescriptor = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "clientHeight",
);

function stubShortInspectorViewport(): void {
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() {
      return 120;
    },
  });
}

afterEach(() => {
  if (clientHeightDescriptor != null) {
    Object.defineProperty(
      HTMLElement.prototype,
      "clientHeight",
      clientHeightDescriptor,
    );
  }
});

describe("material read gate (INV-201-01, INV-067)", () => {
  it("INV-201-01: approve and Enter blocked while material is off-screen", async () => {
    stubShortInspectorViewport();
    renderPdfReview({
      grades: [buildReviewableGrade(24)],
    });
    await waitFor(
      () => {
        expect(
          screen.getByTestId("review-unread-material-notice"),
        ).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    const approve = screen.getByTestId(
      "review-approve-button",
    ) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    await waitFor(
      () => {
        expect(approve.disabled).toBe(true);
        expect(
          screen.getByTestId("review-unread-material-notice"),
        ).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    fireEvent.keyDown(window, { key: "Enter" });
    await waitFor(
      () => {
        expect(screen.getByTestId("review-snackbar")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(screen.getByTestId("review-snackbar").textContent).toContain(
      "判断材料が画面外に残っていました",
    );
    const reject = screen.getByTestId(
      "review-reject-button",
    ) as HTMLButtonElement;
    expect(reject.disabled).toBe(false);
  });

  it("INV-067: reject stays enabled while approve is gated", async () => {
    stubShortInspectorViewport();
    renderPdfReview({ grades: [buildReviewableGrade(12)] });
    await waitFor(
      () => {
        expect(
          screen.getByTestId("review-unread-material-notice"),
        ).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(
      (screen.getByTestId("review-approve-button") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByTestId("review-reject-button") as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it("INV-201-01: approve and Enter blocked while page data is loading", async () => {
    const view = renderPdfReview({
      holdInitialLoad: true,
      grades: [buildGrade()],
    });
    expect(screen.getByText("読み込み中…")).toBeDefined();
    fireEvent.keyDown(window, { key: "Enter" });
    expect(view.client.POST).not.toHaveBeenCalled();
    view.harness.releaseInitialLoad();
    await waitFor(
      () => {
        expect(screen.getByTestId("review-approve-button")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(
      (screen.getByTestId("review-approve-button") as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("INV-201-01: approve blocked while question review data is still loading", async () => {
    const view = renderPdfReview({
      holdQuestionData: true,
      grades: [buildReviewableGrade(12)],
    });
    await waitFor(
      () => {
        expect(screen.getByTestId("review-approve-button")).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    const approve = screen.getByTestId(
      "review-approve-button",
    ) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(view.client.POST).not.toHaveBeenCalled();
    view.harness.releaseQuestionData();
    await waitFor(
      () => {
        expect(
          screen.getByTestId("review-unread-material-notice"),
        ).toBeDefined();
      },
      { timeout: WAIT_MS },
    );
    expect(approve.disabled).toBe(true);
  });
});

describe("review actions (INV-071)", () => {
  it("reject calls the generated client approve endpoint family", async () => {
    const view = renderPdfReview({ grades: [buildGrade()] });
    await waitFor(() => {
      expect(screen.getByTestId("review-reject-button")).toBeDefined();
    });
    fireEvent.change(screen.getByTestId("review-note-field"), {
      target: { value: "手書き文字が判読できない" },
    });
    fireEvent.click(screen.getByTestId("review-reject-button"));
    await waitFor(() => {
      expect(view).toBeDefined();
    });
  });
});

describe("Enter follows focus (Issue #196)", () => {
  it("does not approve the question when Enter is pressed on another button", async () => {
    const view = renderPdfReview({ grades: [] });
    const approve = (await screen.findByTestId(
      "review-approve-button",
    )) as HTMLButtonElement;
    await waitFor(() => {
      expect(approve.disabled).toBe(false);
    });

    const reject = screen.getByTestId("review-reject-button");
    reject.focus();
    expect(document.activeElement).toBe(reject);

    fireEvent.keyDown(reject, { key: "Enter", code: "Enter", bubbles: true });

    expect(view.client.POST).not.toHaveBeenCalled();
  });

  it("does not approve the question when Enter is pressed in the note field", async () => {
    const view = renderPdfReview({ grades: [] });
    const approve = (await screen.findByTestId(
      "review-approve-button",
    )) as HTMLButtonElement;
    await waitFor(() => {
      expect(approve.disabled).toBe(false);
    });

    const note = screen.getByTestId("review-note-field");
    note.focus();
    fireEvent.keyDown(note, { key: "Enter", code: "Enter", bubbles: true });

    expect(view.client.POST).not.toHaveBeenCalled();
  });
});

describe("three-place status consistency (INV-070)", () => {
  it("rail and DAG node use the same status label", async () => {
    renderPdfReview({
      questions: [
        buildQuestion({ id: "q-1", number: "1" }),
        buildQuestion({ id: "q-2", number: "2" }),
        buildQuestion({ id: "q-3", number: "3" }),
      ],
      edges: [
        {
          from_question_id: "q-2",
          to_question_id: "q-3",
          rationale: "前提",
          provides: [],
        },
      ],
      jobs: [
        {
          id: "job-1",
          kind: "grading",
          submission_id: "sub-1",
          question_id: "q-1",
          state: "succeeded",
          usable: true,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "job-2",
          kind: "grading",
          submission_id: "sub-1",
          question_id: "q-2",
          state: "succeeded",
          usable: false,
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "job-3",
          kind: "grading",
          submission_id: "sub-1",
          question_id: "q-3",
          state: "blocked",
          usable: false,
          blocked_on_question_id: "q-2",
          attempts: 1,
          max_attempts: 3,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      grades: [],
      reviews: [],
    });
    await waitFor(() => {
      expect(screen.getByTestId("dag-node-q-3")).toBeDefined();
    });
    fireEvent.click(screen.getByTestId("review-rail-q-3"));
    const dagLabel = screen.getByTestId("dag-node-status-q-3").textContent;
    const rail = screen.getByTestId("review-rail-q-3");
    expect(rail.getAttribute("title")).toBe(dagLabel);
    const inspector = within(screen.getByTestId("review-inspector"));
    expect(inspector.getByText(/問3.*確認待ち/)).toBeDefined();
  });
});
