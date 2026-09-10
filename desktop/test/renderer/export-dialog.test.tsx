import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ExportDialog } from "../../src/renderer/features/review-queue/ExportDialog.js";
import { SidecarApiProvider } from "../../src/renderer/api/SidecarApiProvider.js";
import { ThemeProvider } from "../../src/renderer/theme/ThemeProvider.js";
import {
  createMockSidecarClient,
  type MockSidecarHandlers,
} from "./support/mock-sidecar-client.js";

const CONNECTION = {
  host: "127.0.0.1",
  port: 12345,
  token: "test-token",
};

function renderExportDialog(
  submissionId: string,
  handlers: MockSidecarHandlers,
  pollIntervalMs = 10,
): void {
  const client = createMockSidecarClient(handlers);
  render(
    <ThemeProvider>
      <SidecarApiProvider client={client} connection={CONNECTION}>
        <ExportDialog
          submissionId={submissionId}
          pollIntervalMs={pollIntervalMs}
          onClose={() => undefined}
        />
      </SidecarApiProvider>
    </ThemeProvider>,
  );
}

function buildJob(
  state: string,
  lastError: string | null = null,
): {
  id: string;
  kind: string;
  state: string;
  attempts: number;
  max_attempts: number;
  submission_id: string;
  created_at: string;
  updated_at: string;
  last_error: string | null;
} {
  return {
    id: "job-1",
    kind: "export",
    state,
    attempts: 0,
    max_attempts: 3,
    submission_id: "sub-1",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    last_error: lastError,
  };
}

describe("ExportDialog (INV-180..187)", () => {
  it("shows progress then the saved path once the export job succeeds (INV-180)", async () => {
    let jobCalls = 0;
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        decision: "accept_new",
        job_id: "job-1",
      }),
      getJob: async () => {
        jobCalls += 1;
        return buildJob(jobCalls < 2 ? "running" : "succeeded");
      },
      listExports: async () => [
        {
          id: "export-1",
          job_id: "job-1",
          submission_id: "sub-1",
          file_path: "exports/answer_corrected.pdf",
          file_sha256: "0".repeat(64),
          created_at: new Date().toISOString(),
        },
      ],
    });

    expect(screen.getByTestId("export-dialog-progress")).toBeDefined();
    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-success")).toBeDefined();
    });
    expect(
      screen.getByText("保存先: exports/answer_corrected.pdf"),
    ).toBeDefined();
  });

  it("hands back the existing export immediately for reuse_existing (INV-181)", async () => {
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        decision: "reuse_existing",
        export: {
          id: "export-1",
          job_id: "job-1",
          submission_id: "sub-1",
          file_path: "exports/already.pdf",
          file_sha256: "0".repeat(64),
          created_at: new Date().toISOString(),
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-success")).toBeDefined();
    });
    expect(screen.getByText("保存先: exports/already.pdf")).toBeDefined();
    expect(screen.queryByTestId("export-dialog-progress")).toBeNull();
  });

  it("lists unconfirmed question ids on a 409 refusal (INV-182)", async () => {
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        status: 409,
        body: {
          detail: {
            code: "unconfirmed_questions",
            message: "one or more questions are not yet confirmed",
            question_ids: ["q-1", "q-2"],
          },
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-refused")).toBeDefined();
    });
    expect(
      screen.getByText("未確認の設問があるため出力できません:"),
    ).toBeDefined();
    expect(screen.getByText("・q-1")).toBeDefined();
    expect(screen.getByText("・q-2")).toBeDefined();
  });

  it("shows a distinct message for no_room_for_score (INV-183)", async () => {
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        status: 409,
        body: {
          detail: {
            code: "no_room_for_score",
            message: "one or more questions have no area to write the score in",
            question_ids: ["q-3"],
          },
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-refused")).toBeDefined();
    });
    expect(
      screen.getByText(
        "点数を書き込める場所が無い設問があるため出力できません:",
      ),
    ).toBeDefined();
    expect(screen.getByText("・q-3")).toBeDefined();
    expect(screen.getByText(/確定操作では解消しません/)).toBeDefined();
    expect(screen.queryByText(/未確認の設問/)).toBeNull();
    expect(screen.queryByText(/確定させると出力できます/)).toBeNull();
  });

  it("shows the sidecar message for an unknown conflict code (INV-184)", async () => {
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        status: 409,
        body: {
          detail: {
            code: "a_code_from_a_newer_sidecar",
            message: "some future refusal",
            question_ids: ["q-9"],
          },
        },
      }),
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-refused")).toBeDefined();
    });
    expect(screen.getByText("some future refusal")).toBeDefined();
    expect(screen.getByText("・q-9")).toBeDefined();
    expect(screen.queryByText(/未確認の設問/)).toBeNull();
    expect(screen.queryByText(/確定/)).toBeNull();
  });

  it("retries a failed export by requeueing the job (INV-185)", async () => {
    let state = "running";
    let retried = false;
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        decision: "accept_new",
        job_id: "job-1",
      }),
      getJob: async () =>
        buildJob(state, state === "failed" ? "disk full" : null),
      retryJob: async () => {
        retried = true;
        state = "running";
        return buildJob("running");
      },
      listExports: async () => [
        {
          id: "export-1",
          job_id: "job-1",
          submission_id: "sub-1",
          file_path: "exports/answer_corrected.pdf",
          file_sha256: "0".repeat(64),
          created_at: new Date().toISOString(),
        },
      ],
    });

    state = "failed";
    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-error")).toBeDefined();
    });
    expect(screen.getByText(/disk full/)).toBeDefined();

    fireEvent.click(screen.getByTestId("export-dialog-retry-button"));
    expect(retried).toBe(true);

    state = "succeeded";
    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-success")).toBeDefined();
    });
  });

  it("keeps progress during transient polling failures (INV-186)", async () => {
    let pollAttempts = 0;
    renderExportDialog("sub-1", {
      requestExport: async () => ({
        decision: "accept_new",
        job_id: "job-1",
      }),
      getJob: async () => {
        pollAttempts += 1;
        if (pollAttempts <= 2) {
          throw new Error("timed out");
        }
        return buildJob("succeeded");
      },
      listExports: async () => [
        {
          id: "export-1",
          job_id: "job-1",
          submission_id: "sub-1",
          file_path: "exports/answer_corrected.pdf",
          file_sha256: "0".repeat(64),
          created_at: new Date().toISOString(),
        },
      ],
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("export-dialog-progress")).toBeDefined();
      },
      { timeout: 2000 },
    );
    expect(screen.queryByTestId("export-dialog-error")).toBeNull();

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-success")).toBeDefined();
    });
  });

  it("requests a fresh export when retrying a cancelled job (INV-187)", async () => {
    let requestCount = 0;
    let retryJobCalled = false;
    renderExportDialog("sub-1", {
      requestExport: async () => {
        requestCount += 1;
        return {
          decision: "accept_new",
          job_id: `job-${requestCount}`,
        };
      },
      getJob: async () => buildJob("cancelled"),
      retryJob: async () => {
        retryJobCalled = true;
        return buildJob("running");
      },
    });

    await waitFor(() => {
      expect(screen.getByTestId("export-dialog-error")).toBeDefined();
    });
    expect(requestCount).toBe(1);

    fireEvent.click(screen.getByTestId("export-dialog-retry-button"));
    await waitFor(() => {
      expect(requestCount).toBe(2);
    });
    expect(retryJobCalled).toBe(false);
  });
});
