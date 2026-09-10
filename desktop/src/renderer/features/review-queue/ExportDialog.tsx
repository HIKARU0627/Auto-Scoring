import { useCallback, useEffect, useRef, useState, type JSX } from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  ExportDataError,
  listExports,
  requestSubmissionExport,
  retryJob,
  getJob,
} from "../../api/export-data.js";
import {
  ExportConflictError,
  refusalDetail,
  refusalHeadline,
} from "../../core/export-conflict.js";

export interface ExportDialogProps {
  readonly submissionId: string;
  readonly onClose: () => void;
  readonly pollIntervalMs?: number;
}

type DialogStage = "running" | "succeeded" | "refused" | "failed";

type RetryStrategy = "retryJob" | "requestNew";

const MAX_TRANSIENT_POLL_FAILURES = 5;

export function ExportDialog({
  submissionId,
  onClose,
  pollIntervalMs = 1000,
}: ExportDialogProps): JSX.Element {
  const client = useSidecarClient();
  const [stage, setStage] = useState<DialogStage>("running");
  const [filePath, setFilePath] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refusalCode, setRefusalCode] = useState<string | null>(null);
  const [refusedQuestionIds, setRefusedQuestionIds] = useState<
    readonly string[]
  >([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastObservedJobState, setLastObservedJobState] = useState<
    string | null
  >(null);
  const transientPollFailuresRef = useRef(0);
  const cancelledRef = useRef(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const retryStrategy: RetryStrategy =
    lastObservedJobState === "failed" ? "retryJob" : "requestNew";

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const loadExportedFile = useCallback(
    async (activeJobId: string): Promise<boolean> => {
      try {
        const exports = await listExports(client, submissionId);
        if (cancelledRef.current) {
          return true;
        }
        transientPollFailuresRef.current = 0;
        const match = exports.filter((row) => row.job_id === activeJobId);
        setStage("succeeded");
        setFilePath(
          match.length > 0 ? match[match.length - 1]!.file_path : null,
        );
        return true;
      } catch (error) {
        if (cancelledRef.current) {
          return true;
        }
        transientPollFailuresRef.current += 1;
        if (transientPollFailuresRef.current < MAX_TRANSIENT_POLL_FAILURES) {
          return false;
        }
        setStage("failed");
        setLastObservedJobState(null);
        const message =
          error instanceof ExportDataError
            ? error.message
            : error instanceof Error
              ? error.message
              : String(error);
        setErrorMessage(`出力結果の取得に失敗しました: ${message}`);
        return true;
      }
    },
    [client, submissionId],
  );

  const checkJob = useCallback(
    async (activeJobId: string): Promise<void> => {
      try {
        const job = await getJob(client, activeJobId);
        if (cancelledRef.current) {
          return;
        }
        switch (job.state) {
          case "succeeded": {
            const finished = await loadExportedFile(activeJobId);
            if (!finished) {
              pollTimerRef.current = setTimeout(() => {
                void checkJob(activeJobId);
              }, pollIntervalMs);
            }
            return;
          }
          case "failed":
            transientPollFailuresRef.current = 0;
            setStage("failed");
            setLastObservedJobState("failed");
            setErrorMessage(job.last_error ?? "出力に失敗しました");
            return;
          case "cancelled":
            transientPollFailuresRef.current = 0;
            setStage("failed");
            setLastObservedJobState("cancelled");
            setErrorMessage("出力がキャンセルされました");
            return;
          default:
            transientPollFailuresRef.current = 0;
            pollTimerRef.current = setTimeout(() => {
              void checkJob(activeJobId);
            }, pollIntervalMs);
        }
      } catch (error) {
        if (cancelledRef.current) {
          return;
        }
        transientPollFailuresRef.current += 1;
        if (transientPollFailuresRef.current < MAX_TRANSIENT_POLL_FAILURES) {
          pollTimerRef.current = setTimeout(() => {
            void checkJob(activeJobId);
          }, pollIntervalMs);
          return;
        }
        setStage("failed");
        setLastObservedJobState(null);
        const message =
          error instanceof ExportDataError
            ? error.message
            : error instanceof Error
              ? error.message
              : String(error);
        setErrorMessage(`進捗の取得に失敗しました: ${message}`);
      }
    },
    [client, loadExportedFile, pollIntervalMs],
  );

  const startExport = useCallback(async () => {
    clearPollTimer();
    transientPollFailuresRef.current = 0;
    setStage("running");
    setErrorMessage(null);
    setRefusalCode(null);
    setRefusedQuestionIds([]);
    setJobId(null);
    setLastObservedJobState(null);
    setFilePath(null);

    try {
      const result = await requestSubmissionExport(client, submissionId);
      if (cancelledRef.current) {
        return;
      }

      const existing = result.export;
      if (existing !== undefined && existing !== null) {
        setStage("succeeded");
        setFilePath(existing.file_path);
        return;
      }

      const nextJobId = result.job_id;
      if (nextJobId === undefined || nextJobId === null) {
        setStage("failed");
        setErrorMessage("sidecar は job_id を返しませんでした");
        return;
      }

      setJobId(nextJobId);
      pollTimerRef.current = setTimeout(() => {
        void checkJob(nextJobId);
      }, pollIntervalMs);
    } catch (error) {
      if (cancelledRef.current) {
        return;
      }
      if (error instanceof ExportConflictError) {
        setStage("refused");
        setRefusalCode(error.conflictCode);
        setRefusedQuestionIds(error.conflictQuestionIds);
        setErrorMessage(error.message);
        return;
      }
      const message =
        error instanceof ExportDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setStage("failed");
      setErrorMessage(message);
    }
  }, [checkJob, clearPollTimer, client, pollIntervalMs, submissionId]);

  useEffect(() => {
    cancelledRef.current = false;
    void startExport();
    return () => {
      cancelledRef.current = true;
      clearPollTimer();
    };
  }, [clearPollTimer, startExport]);

  const handleRetry = useCallback(async () => {
    if (retryStrategy === "requestNew") {
      await startExport();
      return;
    }
    const activeJobId = jobId;
    if (activeJobId === null) {
      return;
    }
    setStage("running");
    setErrorMessage(null);
    try {
      await retryJob(client, activeJobId);
      pollTimerRef.current = setTimeout(() => {
        void checkJob(activeJobId);
      }, pollIntervalMs);
    } catch (error) {
      const message =
        error instanceof ExportDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setStage("failed");
      setErrorMessage(message);
    }
  }, [checkJob, client, jobId, pollIntervalMs, retryStrategy, startExport]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-md"
    >
      <div className="w-full max-w-md rounded-lg border border-outline bg-surface p-lg shadow-elevation-2 text-on-surface">
        <h2 className="text-title-medium font-medium mb-md">PDF出力</h2>

        {stage === "running" ? (
          <div
            data-testid="export-dialog-progress"
            className="py-md text-body-medium text-on-surface-variant"
          >
            <p>出力しています…</p>
          </div>
        ) : null}

        {stage === "succeeded" ? (
          <div data-testid="export-dialog-success" className="py-md">
            <p className="text-body-medium text-success font-medium mb-xs">
              PDFを出力しました
            </p>
            <p className="text-body-small text-on-surface-variant">
              保存先: {filePath ?? "出力が完了しました"}
            </p>
          </div>
        ) : null}

        {stage === "refused" ? (
          <div data-testid="export-dialog-refused" className="py-md">
            <p className="text-body-medium font-medium mb-xs">
              {refusalHeadline(refusalCode)}
            </p>
            <ul className="text-body-small text-on-surface-variant mb-xs">
              {refusedQuestionIds.map((questionId) => (
                <li key={questionId}>・{questionId}</li>
              ))}
            </ul>
            {refusalDetail(refusalCode, errorMessage ?? "") !== null ? (
              <p className="text-body-small text-on-surface-variant">
                {refusalDetail(refusalCode, errorMessage ?? "")}
              </p>
            ) : null}
          </div>
        ) : null}

        {stage === "failed" ? (
          <div data-testid="export-dialog-error" className="py-md">
            <p className="text-body-medium text-error font-medium mb-xs">
              PDF出力エラー
            </p>
            <p className="text-body-small text-on-surface-variant">
              {errorMessage ?? "出力に失敗しました"}
            </p>
          </div>
        ) : null}

        <div className="mt-md flex justify-end gap-sm">
          {stage === "failed" ? (
            <button
              type="button"
              data-testid="export-dialog-retry-button"
              className="rounded-md border border-primary bg-primary px-md py-xs text-ui-label text-on-primary"
              onClick={() => {
                void handleRetry();
              }}
            >
              再試行
            </button>
          ) : null}
          <button
            type="button"
            data-testid="export-dialog-close-button"
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
