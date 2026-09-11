import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  BusyNotice,
  ProgressMeter,
  ScreenSkeleton,
  StatusPill,
  StepProgress,
} from "../../src/renderer/features/ui/screen-ui.js";

describe("screen ui primitives (Issue #346)", () => {
  it("marks the current step and derives completed steps from the flags", () => {
    render(
      <StepProgress
        testId="steps"
        currentId="review"
        steps={[
          { id: "choose", label: "選ぶ", complete: true },
          { id: "review", label: "確認", complete: false },
          { id: "done", label: "取込", complete: false },
        ]}
      />,
    );

    const choose = screen.getByTestId("steps-choose");
    const review = screen.getByTestId("steps-review");
    const done = screen.getByTestId("steps-done");

    expect(choose.getAttribute("data-state")).toBe("done");
    expect(review.getAttribute("data-state")).toBe("current");
    expect(review.getAttribute("aria-current")).toBe("step");
    expect(done.getAttribute("data-state")).toBe("upcoming");
  });

  it("renders the progress percentage from value and max", () => {
    render(<ProgressMeter label="進捗" value={1} max={4} />);

    expect(screen.getByText("25%")).toBeDefined();
    const bar = screen.getByRole("progressbar", { name: "進捗" });
    expect(bar.getAttribute("aria-valuenow")).toBe("1");
    expect(bar.getAttribute("aria-valuemax")).toBe("4");
  });

  it("pulls each status pill tone from a design token", () => {
    render(
      <div>
        <StatusPill testId="pill-success" tone="success">
          完了
        </StatusPill>
        <StatusPill testId="pill-attention" tone="attention">
          要確認
        </StatusPill>
      </div>,
    );

    expect(screen.getByTestId("pill-success").className).toContain(
      "bg-success-container",
    );
    expect(screen.getByTestId("pill-attention").className).toContain(
      "bg-attention-container",
    );
  });

  it("announces both what is running and how long it takes", () => {
    render(
      <BusyNotice
        testId="busy"
        title="回答欄を検出しています"
        detail="通常14〜21秒ほどかかります。"
      />,
    );

    const notice = screen.getByTestId("busy");
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice.textContent).toContain("回答欄を検出しています");
    expect(notice.textContent).toContain("通常14〜21秒ほどかかります。");
  });

  it("renders a skeleton with one block per card plus a header", () => {
    render(<ScreenSkeleton testId="loading" cardCount={2} />);

    const skeleton = screen.getByTestId("loading");
    // One header block plus four blocks per card.
    expect(skeleton.querySelectorAll(".animate-pulse")).toHaveLength(1 + 2 * 4);
  });
});
