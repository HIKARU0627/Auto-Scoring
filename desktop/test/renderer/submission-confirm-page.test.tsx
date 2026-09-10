import { describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderAppAt } from "./support/app-harness.js";
import { buildSubmission, buildTest } from "./support/mock-sidecar-client.js";
import {
  createSubmissionConfirmClient,
  renderSubmissionConfirm,
} from "./support/submission-confirm-harness.js";

function mockLayout(params: {
  containerHeight?: number;
  rowHeight?: number;
  rowGap?: number;
  fitAll?: boolean;
}): () => void {
  const containerHeight =
    params.containerHeight ?? (params.fitAll ? 5000 : 400);
  const rowHeight = params.rowHeight ?? 200;
  const rowGap = params.rowGap ?? 16;
  const original = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function () {
    const element = this as HTMLElement;
    const list = element.closest('[data-testid="confirm-question-list"]');
    const scrollTop =
      list instanceof HTMLElement
        ? list.scrollTop
        : element.dataset["testid"] === "confirm-question-list"
          ? element.scrollTop
          : 0;
    if (element.dataset["testid"] === "confirm-question-list") {
      return rect(0, 0, 800, containerHeight);
    }
    const card = element.closest("article");
    if (card instanceof HTMLElement) {
      const cards = Array.from(
        document.querySelectorAll('[data-testid^="confirm-question-"]'),
      );
      const index = cards.indexOf(card);
      const top = index * (rowHeight + rowGap) - scrollTop;
      if (element.dataset["testid"]?.startsWith("confirm-reach-")) {
        return rect(0, top + rowHeight / 2, 800, 20);
      }
      if (element.classList.contains("h-0")) {
        const siblings = Array.from(card.querySelectorAll(".h-0"));
        const markerIndex = siblings.indexOf(element);
        const y = markerIndex === 0 ? top : top + rowHeight;
        return rect(0, y, 0, 0);
      }
    }
    return original.call(this);
  };
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() {
      if ((this as HTMLElement).dataset["testid"] === "confirm-question-list") {
        return containerHeight;
      }
      return 400;
    },
  });
  return () => {
    HTMLElement.prototype.getBoundingClientRect = original;
  };
}

function rect(
  left: number,
  top: number,
  width: number,
  height: number,
): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

async function waitUntilConfirmReady(): Promise<void> {
  await waitFor(() => {
    expect(
      (screen.getByTestId("confirm-submission-button") as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
}

describe("SubmissionConfirmPage (Issue #245)", () => {
  it("INV-154: unreached question numbers appear on screen", async () => {
    const restore = mockLayout({ containerHeight: 120, rowHeight: 300 });
    renderSubmissionConfirm({ numbers: ["1", "2", "3"] });
    try {
      await screen.findByTestId("confirm-blocked-unreached");
      expect(
        screen.getByTestId("confirm-blocked-unreached").textContent,
      ).toContain("問3");
      expect(
        screen.getByTestId("confirm-blocked-unreached").textContent,
      ).toContain("まだ表示していない設問があります");
      expect(screen.getByTestId("confirm-reach-q-1")).toBeDefined();
      expect(screen.getAllByText("未表示").length).toBeGreaterThan(0);
    } finally {
      restore();
    }
  });

  it("INV-155: one click approves every pending question", async () => {
    const restore = mockLayout({ fitAll: true });
    const approved: string[] = [];
    renderSubmissionConfirm({
      numbers: ["1", "2", "3", "4", "5"],
      approveReview: async (_submissionId, questionId) => {
        approved.push(questionId);
        return {};
      },
    });
    try {
      await screen.findByTestId("confirm-question-list");
      await waitUntilConfirmReady();
      fireEvent.click(screen.getByTestId("confirm-submission-button"));
      await waitFor(() => {
        expect(approved).toEqual(["q-1", "q-2", "q-3", "q-4", "q-5"]);
      });
    } finally {
      restore();
    }
  });

  it("INV-201-08: Enter on defer button does not confirm submission", async () => {
    const restore = mockLayout({ fitAll: true });
    const approved: string[] = [];
    renderSubmissionConfirm({
      numbers: ["1"],
      approveReview: async (_submissionId, questionId) => {
        approved.push(questionId);
        return {};
      },
    });
    try {
      await screen.findByTestId("confirm-question-list");
      await waitUntilConfirmReady();
      const defer = screen.getByTestId("confirm-defer-button");
      defer.focus();
      fireEvent.keyDown(defer, { key: "Enter", code: "Enter", bubbles: true });
      expect(approved).toEqual([]);
      fireEvent.click(defer);
      await waitFor(() => {
        expect(
          screen.getByText("ほかに確認できる答案がありません"),
        ).toBeDefined();
      });
      expect(approved).toEqual([]);
    } finally {
      restore();
    }
  });

  it("INV-201-02: high confidence grades still require explicit confirm", async () => {
    const restore = mockLayout({ fitAll: true });
    const approved: string[] = [];
    renderSubmissionConfirm({
      numbers: ["1"],
      approveReview: async (_submissionId, questionId) => {
        approved.push(questionId);
        return {};
      },
    });
    try {
      await screen.findByTestId("confirm-grade-confidence-q-1");
      expect(
        screen.getByTestId("confirm-grade-confidence-q-1").textContent,
      ).toContain("88%");
      await waitUntilConfirmReady();
      expect(approved).toEqual([]);
      fireEvent.click(screen.getByTestId("confirm-submission-button"));
      await waitFor(() => {
        expect(approved).toEqual(["q-1"]);
      });
    } finally {
      restore();
    }
  });

  it("INV-156: partial failure shows confirmed count, failed number, and remaining", async () => {
    const restore = mockLayout({ fitAll: true });
    let failOnThird = true;
    renderSubmissionConfirm({
      numbers: ["1", "2", "3", "4"],
      approveReview: async (_submissionId, questionId) => {
        if (questionId === "q-3" && failOnThird) {
          throw new Error("他の操作と競合しました");
        }
        return {};
      },
    });
    try {
      await screen.findByTestId("confirm-question-list");
      await waitUntilConfirmReady();
      fireEvent.click(screen.getByTestId("confirm-submission-button"));
      await screen.findByTestId("confirm-outcome-partial");
      const notice =
        screen.getByTestId("confirm-outcome-partial").textContent ?? "";
      expect(notice).toContain("問1・問2 を確定しました");
      expect(notice).toContain("問3 で失敗しました");
      expect(notice).toContain("他の操作と競合しました");
      expect(notice).toContain("残り2問");
      expect(screen.getByText("2問をまとめて確定 (Enter)")).toBeDefined();
    } finally {
      restore();
    }
  });

  it("INV-157: missing AI grade blocks confirmation and names the question", async () => {
    const restore = mockLayout({ fitAll: true });
    renderSubmissionConfirm({
      numbers: ["1", "2"],
      withoutAiGrade: new Set(["q-2"]),
    });
    try {
      await screen.findByTestId("confirm-blocked-human-score");
      expect(
        (screen.getByTestId("confirm-submission-button") as HTMLButtonElement)
          .disabled,
      ).toBe(true);
      expect(
        screen.getByTestId("confirm-blocked-human-score").textContent,
      ).toContain("問2");
      expect(screen.getByText("点数を入力する")).toBeDefined();
    } finally {
      restore();
    }
  });

  it("INV-021 follow-up: queue row opens confirm page", async () => {
    const restore = mockLayout({ fitAll: true });
    renderAppAt("/tests/t1/submissions", {
      handlers: {
        getTest: async () => buildTest({ id: "t1" }),
        listSubmissions: async () => [
          buildSubmission({
            id: "s1",
            testId: "t1",
            state: "ai_processed",
            studentLabel: "答案A",
          }),
        ],
      },
    });
    await screen.findByTestId("queue-row-s1");
    fireEvent.click(screen.getByTestId("queue-row-s1"));
    await screen.findByTestId("confirm-question-list");
    expect(screen.getByTestId("confirm-subtitle")).toBeDefined();
    restore();
  });
});

describe("SubmissionConfirmPage API usage (Acceptance #5)", () => {
  it("uses generated client POST for approve", async () => {
    const restore = mockLayout({ fitAll: true });
    const client = createSubmissionConfirmClient({ numbers: ["1"] });
    renderSubmissionConfirm({ numbers: ["1"], client });
    try {
      await screen.findByTestId("confirm-question-list");
      await waitUntilConfirmReady();
      fireEvent.click(screen.getByTestId("confirm-submission-button"));
      await waitFor(() => {
        expect(client.POST).toHaveBeenCalledWith(
          "/submissions/{submission_id}/questions/{question_id}/review/approve",
          expect.any(Object),
        );
      });
    } finally {
      restore();
    }
  });
});
