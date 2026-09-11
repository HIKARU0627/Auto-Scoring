import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import {
  buildDagQuestion,
  buildDependencyDagLayout,
} from "../../src/renderer/core/dependency-dag.js";
import { DependencyDagPanel } from "../../src/renderer/features/pdf-review/DependencyDagPanel.js";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider.js";
import type { components } from "../../src/renderer/api/generated/schema.js";

type DependencyEdge = components["schemas"]["DependencyEdgeModel"];

function edge(from: string, to: string): DependencyEdge {
  return {
    from_question_id: from,
    to_question_id: to,
    rationale: "前提",
    provides: [],
  };
}

function stalledLayout(q2Status: "needsCheck" | "failed") {
  return buildDependencyDagLayout({
    questions: [
      buildDagQuestion({ id: "q1", label: "1", status: "approved" }),
      buildDagQuestion({
        id: "q2",
        label: "2",
        status: q2Status,
        errorCode: q2Status === "failed" ? "server_error" : null,
      }),
      buildDagQuestion({
        id: "q3",
        label: "3",
        status: "blocked",
        blockedOnQuestionId: "q2",
      }),
      buildDagQuestion({ id: "q4", label: "4", status: "graded" }),
      buildDagQuestion({
        id: "q5",
        label: "5",
        status: "blocked",
        blockedOnQuestionId: "q3",
      }),
    ],
    edges: [edge("q1", "q3"), edge("q2", "q3"), edge("q3", "q5")],
    releasedQuestionIds: new Set(["q1"]),
  })!;
}

describe("DependencyDagPanel (INV-160–161, INV-201-03)", () => {
  it("INV-160: header summary differs for needsCheck vs failed", () => {
    const { rerender } = render(
      <ThemeProvider>
        <DependencyDagPanel
          layout={stalledLayout("needsCheck")}
          selectedQuestionId={null}
          onQuestionSelected={() => {}}
        />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("dag-progress-summary").textContent).toBe(
      "実行中 0 ・ 待機 2 ・ 要確認 1 ・ 完了 2",
    );
    rerender(
      <ThemeProvider>
        <DependencyDagPanel
          layout={stalledLayout("failed")}
          selectedQuestionId={null}
          onQuestionSelected={() => {}}
        />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("dag-progress-summary").textContent).toBe(
      "実行中 0 ・ 待機 2 ・ 失敗 1 ・ 完了 2",
    );
  });

  it("INV-161: failure notice remains when panel is collapsed", () => {
    const onSelect = vi.fn();
    render(
      <ThemeProvider>
        <DependencyDagPanel
          layout={stalledLayout("failed")}
          selectedQuestionId={null}
          onQuestionSelected={onSelect}
        />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByTestId("dag-toggle-button"));
    expect(screen.queryByTestId("dag-node-q2")).toBeNull();
    expect(screen.getByTestId("dag-progress-summary").textContent).toContain(
      "失敗 1",
    );
    expect(screen.getByTestId("dag-failure-q2")).toBeDefined();
    expect(screen.getByTestId("dag-failure-headline-q2").textContent).toContain(
      "問2 が失敗し",
    );
    fireEvent.click(screen.getByTestId("dag-failure-open-q2"));
    expect(onSelect).toHaveBeenCalledWith("q2");
  });
});

describe("DependencyDagPanel React Flow regression (Issue #337)", () => {
  function renderPanel(
    layout: ReturnType<typeof buildDependencyDagLayout>,
    onSelect: (questionId: string) => void = () => {},
  ): ReturnType<typeof render> {
    expect(layout).not.toBeNull();
    return render(
      <ThemeProvider>
        <DependencyDagPanel
          layout={layout!}
          selectedQuestionId={null}
          onQuestionSelected={onSelect}
        />
      </ThemeProvider>,
    );
  }

  it("① renders one flow node per question", async () => {
    const { container } = renderPanel(stalledLayout("failed"));
    await waitFor(() => {
      expect(container.querySelectorAll(".react-flow__node")).toHaveLength(5);
    });
    for (const id of ["q1", "q2", "q3", "q4", "q5"]) {
      expect(screen.getByTestId(`dag-node-${id}`)).toBeDefined();
    }
  });

  it("② renders one flow edge per dependency", async () => {
    const { container } = renderPanel(stalledLayout("failed"));
    const edges = () =>
      container.querySelectorAll('[data-testid^="rf__edge-"]');
    await waitFor(() => {
      expect(edges()).toHaveLength(3);
    });
    expect(
      [...edges()].map((edge) => edge.getAttribute("data-id")).sort(),
    ).toEqual(["q1>q3", "q2>q3", "q3>q5"]);
  });

  it("③ shows the empty state when there are no dependencies", async () => {
    const noDependencies = buildDependencyDagLayout({
      questions: [
        buildDagQuestion({ id: "q1", label: "1", status: "approved" }),
        buildDagQuestion({ id: "q2", label: "2", status: "graded" }),
      ],
      edges: [],
      releasedQuestionIds: new Set(),
    });
    const { container } = renderPanel(noDependencies);
    expect(screen.getByTestId("dag-empty")).toBeDefined();
    await waitFor(() => {
      expect(container.querySelectorAll(".react-flow__edge")).toHaveLength(0);
    });
  });

  it("④ renders the failure guidance of a failed question", () => {
    renderPanel(stalledLayout("failed"));
    expect(screen.getByTestId("dag-failure-headline-q2").textContent).toContain(
      "問2 が失敗し",
    );
    expect(
      screen.getByTestId("dag-failure-next-q2").textContent?.length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("dag-failure-q2")).toBeDefined();
  });

  it("keeps node click selection working", async () => {
    const onSelect = vi.fn();
    const { container } = renderPanel(stalledLayout("failed"), onSelect);
    await waitFor(() => {
      expect(container.querySelectorAll(".react-flow__node")).toHaveLength(5);
    });
    fireEvent.click(screen.getByTestId("dag-node-q3"));
    expect(onSelect).toHaveBeenCalledWith("q3");
  });
});
