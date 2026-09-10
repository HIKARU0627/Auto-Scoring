import { useEffect, useState, type JSX } from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  getJob,
  requestSubmissionExport,
  type ExportResponse,
} from "../../api/submission-queue-data.js";

export interface ExportDialogProps {
  readonly submissionId: string;
  readonly onClose: () => void;
}

type DialogState =
  | { status: "running"; message: string }
  | { status: "succeeded"; exportData: ExportResponse }
  | { status: "failed"; message: string };

export function ExportDialog({
  submissionId,
  onClose,
}: ExportDialogProps): JSX.Element {
  const client = useSidecarClient();
  const [state, setState] = useState<DialogState>({
    status: "running",
    message: "PDF出力を要求中…",
  });

  useEffect(() => {
    let cancelled = false;

    async function runExport(): Promise<void> {
      try {
        const result = await requestSubmissionExport(client, submissionId);
        if (cancelled) return;

        if (result.decision === "reuse_existing" && result.export) {
          setState({ status: "succeeded", exportData: result.export });
          return;
        }

        if (result.job_id) {
          setState({ status: "running", message: "PDF出力中…" });
          const jobId = result.job_id;

          // Poll job status
          for (let attempt = 0; attempt < 30; attempt++) {
            await new Promise((resolve) => setTimeout(resolve, 500));
            if (cancelled) return;

            const job = await getJob(client, jobId);
            if (cancelled) return;

            if (job.state === "succeeded") {
              const exportData = result.export ?? {
                id: jobId,
                job_id: jobId,
                submission_id: submissionId,
                file_path: `exports/submission_${submissionId}.pdf`,
                file_sha256: "",
                created_at: new Date().toISOString(),
              };
              setState({ status: "succeeded", exportData });
              return;
            }

            if (job.state === "failed" || job.state === "cancelled") {
              setState({
                status: "failed",
                message: job.last_error ?? "PDF出力に失敗しました",
              });
              return;
            }
          }

          setState({
            status: "failed",
            message: "PDF出力がタイムアウトしました",
          });
          return;
        }

        setState({
          status: "failed",
          message: "出力結果が得られませんでした",
        });
      } catch (error) {
        if (cancelled) return;
        const msg = error instanceof Error ? error.message : String(error);
        setState({ status: "failed", message: msg });
      }
    }

    void runExport();

    return () => {
      cancelled = true;
    };
  }, [client, submissionId]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-md"
    >
      <div className="w-full max-w-md rounded-lg border border-outline bg-surface p-lg shadow-elevation-2 text-on-surface">
        <h2 className="text-title-medium font-medium mb-md">PDF出力</h2>

        {state.status === "running" ? (
          <div className="py-md text-body-medium text-on-surface-variant">
            <p>{state.message}</p>
          </div>
        ) : null}

        {state.status === "succeeded" ? (
          <div data-testid="export-dialog-success" className="py-md">
            <p className="text-body-medium text-success font-medium mb-xs">
              PDFを出力しました
            </p>
            <p className="text-body-small text-on-surface-variant">
              保存先: {state.exportData.file_path}
            </p>
          </div>
        ) : null}

        {state.status === "failed" ? (
          <div data-testid="export-dialog-error" className="py-md">
            <p className="text-body-medium text-error font-medium mb-xs">
              PDF出力エラー
            </p>
            <p className="text-body-small text-on-surface-variant">
              {state.message}
            </p>
          </div>
        ) : null}

        <div className="mt-md flex justify-end gap-sm">
          <button
            type="button"
            className="rounded-md border border-outline px-md py-xs text-ui-label text-on-surface"
            onClick={onClose}
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
