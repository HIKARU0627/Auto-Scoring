import { useCallback, useEffect, useState, type JSX } from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  loadSubmissionQueueData,
  SubmissionQueueDataError,
  type SubmissionQueueData,
  type SubmissionResponse,
} from "../../core/submission-queue-data.js";
import { submissionConfirm } from "../../core/app-routes.js";
import { describeReviewReason } from "../../core/submission-review-reason.js";
import { submissionStatusVisualOf } from "../../core/submission-status.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import { BulkExportDialog } from "./BulkExportDialog.js";
import { ExportDialog } from "./ExportDialog.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: SubmissionQueueData };

function answerName(submission: SubmissionResponse): string {
  return (
    submission.student_label ?? submission.original_filename ?? submission.id
  );
}

function toneTextClass(
  tone: "attention" | "neutral" | "danger" | "success",
): string {
  switch (tone) {
    case "attention":
      return "text-attention";
    case "danger":
      return "text-error";
    case "success":
      return "text-success";
    default:
      return "text-on-surface-variant";
  }
}

export function SubmissionQueuePage(): JSX.Element {
  const client = useSidecarClient();
  const { params, push } = useRouter();
  const testId = params.testId ?? "";

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [exportingSubmissionId, setExportingSubmissionId] = useState<
    string | null
  >(null);
  const [bulkExportOpen, setBulkExportOpen] = useState(false);

  const reload = useCallback(async () => {
    if (testId.length === 0) {
      setLoadState({ status: "error", message: "テスト ID がありません" });
      return;
    }

    setLoadState({ status: "loading" });
    try {
      const data = await loadSubmissionQueueData(client, testId);
      setLoadState({ status: "ready", data });
    } catch (error) {
      const message =
        error instanceof SubmissionQueueDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setLoadState({ status: "error", message });
    }
  }, [client, testId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onOpenSubmission = useCallback(
    (submissionId: string) => {
      // Tap row navigates to submission confirm screen (INV-021)
      push(submissionConfirm(testId, submissionId));
    },
    [push, testId],
  );

  return (
    <ShellScreen title="答案キュー">
      {/* Hidden testId details for accessibility and compatibility */}
      {testId.length > 0 ? (
        <span className="sr-only">testId={testId}</span>
      ) : null}

      {loadState.status === "loading" ? (
        <p className="text-body-medium text-on-surface-variant">読み込み中…</p>
      ) : null}

      {loadState.status === "error" ? (
        <div
          data-testid="queue-error"
          className="rounded-md border border-error bg-error-container p-lg text-on-error-container"
        >
          <p className="text-body-medium">
            答案の一覧を取得できません: {loadState.message}
          </p>
          <button
            type="button"
            className="mt-md rounded-md border border-outline px-md py-xs text-ui-label text-on-surface bg-surface"
            onClick={() => {
              void reload();
            }}
          >
            再読み込み
          </button>
        </div>
      ) : null}

      {loadState.status === "ready" && loadState.data.queue.isEmpty ? (
        <div
          data-testid="queue-empty"
          className="rounded-md border border-outline-variant bg-surface p-xl text-center text-on-surface-variant"
        >
          <p className="text-body-medium">
            このテストにはまだ答案が取り込まれていません。
          </p>
          <button
            type="button"
            className="mt-md rounded-md border border-outline px-md py-xs text-ui-label text-on-surface bg-surface"
            onClick={() => {
              void reload();
            }}
          >
            再読み込み
          </button>
        </div>
      ) : null}

      {loadState.status === "ready" && !loadState.data.queue.isEmpty ? (
        <div className="mx-auto max-w-[960px] flex flex-col gap-lg">
          {/* Header */}
          <div className="rounded-lg border border-outline-variant bg-surface-container p-lg">
            <h2 className="text-title-medium font-medium text-on-surface">
              {loadState.data.test.name}
            </h2>
            <p className="mt-xs text-body-medium text-on-surface-variant">
              確認済み {loadState.data.queue.doneCount} /{" "}
              {loadState.data.queue.total}
            </p>
            <div className="mt-sm h-2 w-full overflow-hidden rounded-full bg-surface-container-highest">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{
                  width: `${(loadState.data.queue.doneCount / loadState.data.queue.total) * 100}%`,
                }}
              />
            </div>
            <div className="mt-md flex justify-end">
              <button
                type="button"
                data-testid="queue-bulk-export-button"
                className="rounded-md border border-outline px-md py-xs text-ui-label text-on-surface bg-surface"
                onClick={() => {
                  setBulkExportOpen(true);
                }}
              >
                まとめてPDF出力
              </button>
            </div>
          </div>

          {/* Submissions List */}
          <div className="flex flex-col divide-y divide-outline-variant rounded-lg border border-outline-variant bg-surface">
            {loadState.data.queue.entries.map((entry, index) => {
              const visual = submissionStatusVisualOf(entry.submission.state);
              const reasonSummary = describeReviewReason(
                entry.submission.review_reason,
              );

              return (
                <div
                  key={entry.id}
                  data-testid={`queue-row-${entry.id}`}
                  role="button"
                  tabIndex={0}
                  className="flex items-center justify-between p-md hover:bg-surface-container-low cursor-pointer transition-colors"
                  onClick={() => onOpenSubmission(entry.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onOpenSubmission(entry.id);
                    }
                  }}
                >
                  <div className="flex flex-col gap-xs">
                    <div className="flex items-center gap-sm">
                      <span className="text-body-large font-medium text-on-surface">
                        {answerName(entry.submission)}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-md text-ui-label text-on-surface-variant">
                      <span>
                        {index + 1} / {loadState.data.queue.total}
                      </span>
                      <span className={toneTextClass(visual.tone)}>
                        {visual.label}
                      </span>

                      {/* Question progress chip (INV-144) */}
                      {entry.totalQuestions > 0 ? (
                        <span
                          data-testid={`queue-progress-${entry.id}`}
                          className={`rounded px-xs py-0.5 text-ui-label border ${
                            entry.isDone
                              ? "border-success text-success"
                              : entry.isPartiallyReviewed
                                ? "border-attention text-attention"
                                : "border-outline text-on-surface-variant"
                          }`}
                        >
                          {entry.confirmedQuestions} / {entry.totalQuestions} 問
                          確定
                        </span>
                      ) : null}

                      {/* Manual grading marker (INV-144) */}
                      {entry.needsManualGrading ? (
                        <span
                          data-testid={`queue-manual-grade-${entry.id}`}
                          className="text-attention font-medium"
                        >
                          AIが採点できなかった設問があります
                        </span>
                      ) : null}
                    </div>

                    {/* Review reason summary (INV-158 / INV-159) */}
                    {reasonSummary !== null ? (
                      <p className="text-ui-label text-on-surface-variant mt-xs">
                        {reasonSummary}
                      </p>
                    ) : null}
                  </div>

                  {/* PDF Export action button (INV-145) */}
                  {entry.isFullyConfirmed ? (
                    <button
                      type="button"
                      data-testid={`queue-export-${entry.id}`}
                      title="PDF出力"
                      aria-label="PDF出力"
                      className="rounded border border-outline px-sm py-xs text-ui-label text-on-surface hover:bg-surface-container"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExportingSubmissionId(entry.id);
                      }}
                    >
                      PDF出力
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {bulkExportOpen && loadState.status === "ready" ? (
        <BulkExportDialog
          testId={testId}
          queue={loadState.data.queue}
          onClose={() => {
            setBulkExportOpen(false);
            void reload();
          }}
        />
      ) : null}

      {exportingSubmissionId !== null ? (
        <ExportDialog
          submissionId={exportingSubmissionId}
          onClose={() => {
            setExportingSubmissionId(null);
            void reload();
          }}
        />
      ) : null}
    </ShellScreen>
  );
}
