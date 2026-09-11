import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SidecarApiProvider } from "../../src/renderer/api/SidecarApiProvider.js";
import { BulkExportDialog } from "../../src/renderer/features/review-queue/BulkExportDialog.js";
import { ReviewQueue } from "../../src/renderer/core/review-queue.js";
import { createMemoryBulkExportStorage } from "../../src/renderer/core/bulk-export-writer.js";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider.js";
import {
  buildProgress,
  buildSubmission,
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

function renderBulkDialog(
  handlers: MockSidecarHandlers,
  queue: ReviewQueue,
): ReturnType<typeof createMemoryBulkExportStorage> {
  const storage = createMemoryBulkExportStorage();
  const client = createMockSidecarClient(handlers);
  render(
    <ThemeProvider>
      <SidecarApiProvider client={client}>
        <BulkExportDialog
          testId="t1"
          queue={queue}
          pollIntervalMs={10}
          chooseDestination={async () => ({
            label: "/out",
            storage,
          })}
          onClose={() => undefined}
        />
      </SidecarApiProvider>
    </ThemeProvider>,
  );
  return storage;
}

describe("BulkExportDialog (INV-188..189)", () => {
  it("shows targets, exclusions, progress, and completion", async () => {
    let jobState = "queued";
    const storage = renderBulkDialog(
      {
        requestBulkExport: async (_testId, submissionIds) => ({
          test_id: "t1",
          items: submissionIds.map((submissionId) => ({
            submission_id: submissionId,
            status: "queued",
            job_id: "job-1",
          })),
        }),
        getJob: async () => ({
          id: "job-1",
          kind: "export",
          state: jobState,
          attempts: 0,
          max_attempts: 3,
          submission_id: "sub-1",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
        listExports: async () => [
          {
            id: "export-1",
            job_id: "job-1",
            submission_id: "sub-1",
            file_path: "exports/sub-1_corrected.pdf",
            file_sha256: "0".repeat(64),
            created_at: new Date().toISOString(),
          },
        ],
        getExportFile: async () => new Uint8Array([1]),
      },
      ReviewQueue.from({
        submissions: [
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
        ],
        progress: [
          buildProgress({ id: "sub-1", total: 2, confirmed: 2 }),
          buildProgress({ id: "sub-2", total: 2, confirmed: 0 }),
        ],
      }),
    );

    expect(screen.getByText("対象 1件")).toBeDefined();
    expect(screen.getByText("対象外 1件")).toBeDefined();
    expect(screen.getByText(/出席2: 未確認の設問が2問/)).toBeDefined();

    fireEvent.click(screen.getByTestId("bulk-export-start-button"));
    await waitFor(() => {
      expect(screen.getByTestId("bulk-export-progress")).toBeDefined();
    });
    // 排他: 走っている間に開始ボタンは無い (二重に走らせられない)。中止だけが残る。
    // 「開始ボタンが無い」だけでは、ボタン自体が消えても緑になるので、
    // confirm 段で開始できた事実と中止ボタンの存在を肯定形で併せて固定する。
    expect(screen.queryByTestId("bulk-export-start-button")).toBeNull();
    expect(screen.getByTestId("bulk-export-cancel-button")).toBeDefined();

    jobState = "succeeded";
    await waitFor(() => {
      expect(screen.getByTestId("bulk-export-result")).toBeDefined();
    });
    expect(screen.getByText("1 / 1 件を出力しました。")).toBeDefined();
    expect(await storage.exists("sub-1_corrected.pdf")).toBe(true);
  });

  it("lists refused items and allows retrying only the failures (INV-189)", async () => {
    let attempt = 0;
    const storage = renderBulkDialog(
      {
        requestBulkExport: async (_testId, submissionIds) => {
          attempt += 1;
          if (attempt === 1) {
            return {
              test_id: "t1",
              items: submissionIds.map((submissionId) =>
                submissionId === "sub-1"
                  ? {
                      submission_id: submissionId,
                      status: "reused",
                      export: {
                        id: "export-1",
                        job_id: "job-1",
                        submission_id: submissionId,
                        file_path: "exports/sub-1_corrected.pdf",
                        file_sha256: "0".repeat(64),
                        created_at: new Date().toISOString(),
                      },
                    }
                  : {
                      submission_id: submissionId,
                      status: "refused",
                      refusal_code: "no_room_for_score",
                      refusal_question_ids: ["q-9"],
                    },
              ),
            };
          }
          return {
            test_id: "t1",
            items: submissionIds.map((submissionId) => ({
              submission_id: submissionId,
              status: "reused",
              export: {
                id: `export-${submissionId}`,
                job_id: `job-${submissionId}`,
                submission_id: submissionId,
                file_path: `exports/${submissionId}_corrected.pdf`,
                file_sha256: "0".repeat(64),
                created_at: new Date().toISOString(),
              },
            })),
          };
        },
        getExportFile: async () => new Uint8Array([1]),
      },
      ReviewQueue.from({
        submissions: [
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
        ],
        progress: [
          buildProgress({ id: "sub-1", total: 2, confirmed: 2 }),
          buildProgress({ id: "sub-2", total: 2, confirmed: 2 }),
        ],
      }),
    );

    fireEvent.click(screen.getByTestId("bulk-export-start-button"));
    await waitFor(() => {
      expect(screen.getByTestId("bulk-export-failures")).toBeDefined();
    });
    expect(screen.getByText(/点数を書き込める場所がありません/)).toBeDefined();

    fireEvent.click(screen.getByTestId("bulk-export-retry-button"));
    await waitFor(() => {
      expect(screen.getByText("1 / 1 件を出力しました。")).toBeDefined();
    });
    expect(await storage.exists("sub-2_corrected.pdf")).toBe(true);
  });

  it("does not offer start when there are zero targets (INV-188)", () => {
    renderBulkDialog(
      {},
      ReviewQueue.from({
        submissions: [
          buildSubmission({
            id: "sub-1",
            state: "ai_processed",
            studentLabel: "出席1",
          }),
        ],
        progress: [buildProgress({ id: "sub-1", total: 2, confirmed: 0 })],
      }),
    );

    expect(screen.getByTestId("bulk-export-empty-targets")).toBeDefined();
    expect(screen.queryByTestId("bulk-export-start-button")).toBeNull();
  });
});
