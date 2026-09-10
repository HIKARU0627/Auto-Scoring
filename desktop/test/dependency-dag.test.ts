import { describe, expect, it } from "vitest";

import {
  buildDagQuestion,
  buildDependencyDagLayout,
  type DagQuestion,
} from "../src/renderer/core/dependency-dag.js";
import type { components } from "../src/renderer/api/generated/schema.js";

type DependencyEdge = components["schemas"]["DependencyEdgeModel"];

function edge(from: string, to: string): DependencyEdge {
  return {
    from_question_id: from,
    to_question_id: to,
    rationale: "前提",
    provides: [],
  };
}

function submission(
  q2Status: DagQuestion["status"],
): ReturnType<typeof buildDependencyDagLayout> {
  return buildDependencyDagLayout({
    questions: [
      buildDagQuestion({ id: "q1", label: "1", status: "approved" }),
      buildDagQuestion({ id: "q2", label: "2", status: q2Status }),
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
  });
}

describe("DependencyDagLayout (INV-160–162, INV-201-03)", () => {
  it("INV-160: needsCheck and failed produce different summaries", () => {
    const blocked = submission("needsCheck")!;
    const failed = submission("failed")!;
    expect(blocked.progressSummary).toBe(
      "実行中 0 ・ 待機 2 ・ 要確認 1 ・ 完了 2",
    );
    expect(failed.progressSummary).toBe(
      "実行中 0 ・ 待機 2 ・ 失敗 1 ・ 完了 2",
    );
    expect(blocked.progressSummary).not.toBe(failed.progressSummary);
  });

  it("omits needsCheck and failed from summary when zero", () => {
    const quiet = buildDependencyDagLayout({
      questions: [
        buildDagQuestion({ id: "q1", label: "1", status: "running" }),
        buildDagQuestion({ id: "q2", label: "2", status: "approved" }),
      ],
      edges: [],
      releasedQuestionIds: new Set(),
    })!;
    expect(quiet.progressSummary).toBe("実行中 1 ・ 待機 0 ・ 完了 1");
  });

  it("INV-162: downstream wait label differs by upstream reason", () => {
    const blocked = submission("needsCheck")!;
    const failed = submission("failed")!;
    const blockedQ3 = blocked.nodes.find((n) => n.question.id === "q3")!;
    const failedQ3 = failed.nodes.find((n) => n.question.id === "q3")!;
    expect(blockedQ3.statusLabel).toBe("問2 確認待ち");
    expect(failedQ3.statusLabel).toBe("問2 失敗で停止");
    expect(blockedQ3.statusLabel).not.toBe(failedQ3.statusLabel);
  });
});
