import { describe, expect, it } from "vitest";

import {
  buildDagQuestion,
  buildDependencyDagLayout,
  deriveStatusesFromJobs,
  type DagQuestion,
} from "../src/renderer/core/dependency-dag.js";
import type { components } from "../src/renderer/api/generated/schema.js";

type DependencyEdge = components["schemas"]["DependencyEdgeModel"];
type JobResponse = components["schemas"]["JobResponse"];
type ReviewResponse = components["schemas"]["ReviewResponse"];

function jobAt(
  id: string,
  createdAt: string,
  overrides: Partial<JobResponse> = {},
): JobResponse {
  return {
    id,
    kind: "grading",
    submission_id: "sub-1",
    question_id: "q-1",
    state: "succeeded",
    usable: true,
    attempts: 1,
    max_attempts: 3,
    created_at: createdAt,
    updated_at: createdAt,
    ...overrides,
  };
}

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

  it("returns no layout (empty state) when there are no questions", () => {
    expect(
      buildDependencyDagLayout({
        questions: [],
        edges: [],
        releasedQuestionIds: new Set(),
      }),
    ).toBeNull();
  });
});

describe("deriveStatusesFromJobs (Issue #402)", () => {
  const regradeRequest: ReviewResponse = {
    id: "review-regrade",
    submission_id: "sub-1",
    question_id: "q-1",
    action: "regrade_requested",
    version: 1,
    regrade_job_id: "job-regrade",
    created_at: "2026-01-01T00:00:01Z",
  };

  it("derives the DAG node status from the newest job per question", () => {
    const oldJob = jobAt("job-old", "2026-01-01T00:00:00Z");
    const regradeJob = jobAt("job-regrade", "2026-01-01T00:00:02Z", {
      state: "running",
      usable: null,
    });

    const statuses = deriveStatusesFromJobs({
      questions: [{ id: "q-1", label: "1" }],
      jobs: [oldJob, regradeJob],
      reviewsByQuestion: { "q-1": regradeRequest },
    });

    // With the oldest job this would read 再判定待ち forever.
    expect(statuses[0]!.status).toBe("running");
  });
});
