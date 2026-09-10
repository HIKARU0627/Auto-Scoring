import { describe, expect, it } from "vitest";

import {
  BulkExportPlan,
  BulkExportRunner,
} from "../src/renderer/core/bulk-export.js";
import { createMemoryBulkExportStorage } from "../src/renderer/core/bulk-export-writer.js";
import { ReviewQueue } from "../src/renderer/core/review-queue.js";
import {
  buildProgress,
  buildSubmission,
  createMockSidecarClient,
} from "./renderer/support/mock-sidecar-client.js";

function buildQueue(
  submissions: ReturnType<typeof buildSubmission>[],
  progress: ReturnType<typeof buildProgress>[],
): ReviewQueue {
  return ReviewQueue.from({ submissions, progress });
}

describe("BulkExportPlan (INV-188)", () => {
  it("includes only fully confirmed submissions and lists exclusions with reasons", () => {
    const plan = BulkExportPlan.from(
      buildQueue(
        [
          buildSubmission({
            id: "sub-1",
            state: "ai_processed",
            studentLabel: "出席1",
          }),
          buildSubmission({
            id: "sub-2",
            state: "ai_processed",
            studentLabel: "出席2",
            createdDay: 2,
          }),
          buildSubmission({
            id: "sub-3",
            state: "ai_processed",
            studentLabel: "出席3",
            createdDay: 3,
          }),
        ],
        [
          buildProgress({ id: "sub-1", total: 2, confirmed: 2 }),
          buildProgress({ id: "sub-2", total: 2, confirmed: 1 }),
          buildProgress({ id: "sub-3", total: 2, confirmed: 2 }),
        ],
      ),
    );

    expect(plan.targets.map((target) => target.submissionId)).toEqual([
      "sub-1",
      "sub-3",
    ]);
    expect(plan.excluded).toHaveLength(1);
    expect(plan.excluded[0]?.submissionId).toBe("sub-2");
    expect(plan.excluded[0]?.reason).toContain("未確認の設問が1問");
  });

  it("excludes submissions with unknown progress instead of assuming confirmed", () => {
    const plan = BulkExportPlan.from(
      buildQueue([buildSubmission({ id: "sub-1", state: "ai_processed" })], []),
    );

    expect(plan.targets).toHaveLength(0);
    expect(plan.excluded[0]?.reason).toContain("取れていません");
  });
});

describe("BulkExportRunner (INV-189)", () => {
  it("continues after one refused submission and records a failure list", async () => {
    const storage = createMemoryBulkExportStorage();
    const client = createMockSidecarClient({
      requestBulkExport: async (_testId, submissionIds) => ({
        test_id: "t1",
        items: submissionIds.map((submissionId) =>
          submissionId === "sub-1"
            ? {
                submission_id: submissionId,
                status: "refused",
                refusal_code: "unconfirmed_questions",
                refusal_question_ids: ["q-1", "q-2"],
              }
            : {
                submission_id: submissionId,
                status: "reused",
                export: {
                  id: `exp-${submissionId}`,
                  job_id: `job-${submissionId}`,
                  submission_id: submissionId,
                  file_path: `exports/${submissionId}_corrected.pdf`,
                  file_sha256: "0".repeat(64),
                  created_at: new Date().toISOString(),
                },
              },
        ),
      }),
      getExportFile: async () => new Uint8Array([1]),
    });

    const result = await new BulkExportRunner().run({
      client,
      testId: "t1",
      targets: [
        { submissionId: "sub-1", label: "出席1" },
        { submissionId: "sub-2", label: "出席2" },
      ],
      storage,
      destinationLabel: "/out",
      pollIntervalMs: 1,
    });

    expect(result.writtenCount).toBe(1);
    expect(result.failures).toHaveLength(1);
    expect(result.failures[0]?.target.submissionId).toBe("sub-1");
    expect(result.failures[0]?.failureReason).toContain("未確認の設問が2問");
    expect(await storage.exists("sub-2_corrected.pdf")).toBe(true);
  });

  it("does not overwrite an existing destination file (UG-09)", async () => {
    const original = new Uint8Array([7, 7, 7]);
    const storage = createMemoryBulkExportStorage({
      "sub-1_corrected.pdf": original,
    });
    const client = createMockSidecarClient({
      requestBulkExport: async (_testId, submissionIds) => ({
        test_id: "t1",
        items: submissionIds.map((submissionId) => ({
          submission_id: submissionId,
          status: "reused",
          export: {
            id: `exp-${submissionId}`,
            job_id: `job-${submissionId}`,
            submission_id: submissionId,
            file_path: `exports/${submissionId}_corrected.pdf`,
            file_sha256: "0".repeat(64),
            created_at: new Date().toISOString(),
          },
        })),
      }),
      getExportFile: async () => new Uint8Array([1, 2, 3]),
    });

    await new BulkExportRunner().run({
      client,
      testId: "t1",
      targets: [{ submissionId: "sub-1", label: "出席1" }],
      storage,
      destinationLabel: "/out",
      pollIntervalMs: 1,
    });

    expect(await storage.read("sub-1_corrected.pdf")).toEqual(original);
    expect(await storage.read("sub-1_corrected_2.pdf")).toEqual(
      new Uint8Array([1, 2, 3]),
    );
  });
});
