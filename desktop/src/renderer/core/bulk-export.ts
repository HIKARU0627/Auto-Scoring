/**
 * Bulk PDF export plan and runner (Issue #142 / INV-188..189).
 */

import type { SidecarClient } from "../api/client.js";
import type { ExportResponse } from "./export-data.js";
import {
  cancelJob,
  ExportDataError,
  getExportFile,
  getJob,
  listExports,
  requestBulkExport,
} from "./export-data.js";
import { bulkExportRefusalReason } from "./export-conflict.js";
import {
  bulkExportFileName,
  type BulkExportStorage,
  writeBulkExportFile,
} from "./bulk-export-writer.js";
import type { ReviewQueue } from "./review-queue.js";
import type { SubmissionResponse } from "./review-queue.js";

export interface BulkExportTarget {
  readonly submissionId: string;
  readonly label: string;
}

export interface BulkExportExclusion {
  readonly submissionId: string;
  readonly label: string;
  readonly reason: string;
}

export class BulkExportPlan {
  constructor(
    public readonly targets: readonly BulkExportTarget[],
    public readonly excluded: readonly BulkExportExclusion[],
  ) {}

  static from(queue: ReviewQueue): BulkExportPlan {
    const targets: BulkExportTarget[] = [];
    const excluded: BulkExportExclusion[] = [];
    for (const entry of queue.entries) {
      const label = bulkExportLabel(entry.submission);
      if (entry.isFullyConfirmed) {
        targets.push({ submissionId: entry.id, label });
        continue;
      }
      excluded.push({
        submissionId: entry.id,
        label,
        reason:
          entry.totalQuestions === 0
            ? "設問ごとの確定状況が取れていません"
            : `未確認の設問が${entry.totalQuestions - entry.confirmedQuestions}問あります`,
      });
    }
    return new BulkExportPlan(targets, excluded);
  }

  get hasTargets(): boolean {
    return this.targets.length > 0;
  }
}

export function bulkExportLabel(submission: SubmissionResponse): string {
  return (
    submission.student_label ?? submission.original_filename ?? submission.id
  );
}

export type BulkExportItemState =
  "pending" | "written" | "failed" | "cancelled";

export interface BulkExportItemResult {
  readonly target: BulkExportTarget;
  readonly state: BulkExportItemState;
  readonly savedPath?: string;
  readonly failureReason?: string;
}

export class BulkExportProgress {
  constructor(
    public readonly items: readonly BulkExportItemResult[],
    public readonly currentLabel: string | null,
  ) {}

  get totalCount(): number {
    return this.items.length;
  }

  get settledCount(): number {
    return this.items.filter((item) => item.state !== "pending").length;
  }

  get writtenCount(): number {
    return this.items.filter((item) => item.state === "written").length;
  }

  get failures(): readonly BulkExportItemResult[] {
    return this.items.filter((item) => item.state === "failed");
  }

  get cancelled(): readonly BulkExportItemResult[] {
    return this.items.filter((item) => item.state === "cancelled");
  }

  get retryableTargets(): readonly BulkExportTarget[] {
    return this.items
      .filter((item) => item.state === "failed" || item.state === "cancelled")
      .map((item) => item.target);
  }
}

export interface BulkExportRunOptions {
  readonly client: SidecarClient;
  readonly testId: string;
  readonly targets: readonly BulkExportTarget[];
  readonly storage: BulkExportStorage;
  readonly destinationLabel: string;
  readonly pollIntervalMs?: number;
  readonly maxTransientPollFailures?: number;
  readonly onProgress?: (progress: BulkExportProgress) => void;
}

export class BulkExportRunner {
  private cancelled = false;

  cancel(): void {
    this.cancelled = true;
  }

  async run(options: BulkExportRunOptions): Promise<BulkExportProgress> {
    this.cancelled = false;
    const pollIntervalMs = options.pollIntervalMs ?? 500;
    const maxTransientPollFailures = options.maxTransientPollFailures ?? 5;
    const order = options.targets.map((target) => target.submissionId);
    const results = new Map<string, BulkExportItemResult>(
      options.targets.map((target) => [
        target.submissionId,
        { target, state: "pending" },
      ]),
    );

    const emit = (currentLabel: string | null): BulkExportProgress => {
      const items = order.map((id) => results.get(id)!);
      const progress = new BulkExportProgress(items, currentLabel);
      options.onProgress?.(progress);
      return progress;
    };

    const settle = (
      submissionId: string,
      state: BulkExportItemState,
      extra?: { savedPath?: string; failureReason?: string },
    ): void => {
      const current = results.get(submissionId);
      if (current === undefined) {
        return;
      }
      results.set(submissionId, {
        target: current.target,
        state,
        ...(extra?.savedPath !== undefined
          ? { savedPath: extra.savedPath }
          : {}),
        ...(extra?.failureReason !== undefined
          ? { failureReason: extra.failureReason }
          : {}),
      });
    };

    emit(
      order
        .map((id) => results.get(id))
        .find((item) => item?.state === "pending")?.target.label ?? null,
    );

    if (options.targets.length === 0) {
      return emit(null);
    }

    let response;
    try {
      response = await requestBulkExport(options.client, options.testId, order);
    } catch (caught) {
      const message =
        caught instanceof ExportDataError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : String(caught);
      for (const submissionId of order) {
        settle(submissionId, "failed", { failureReason: message });
      }
      return emit(null);
    }

    const pendingJobs = new Map<string, string>();
    const readyExports = new Map<string, ExportResponse>();

    for (const item of response.items) {
      if (!results.has(item.submission_id)) {
        continue;
      }
      switch (item.status) {
        case "refused":
          settle(item.submission_id, "failed", {
            failureReason: bulkExportRefusalReason(
              item.refusal_code,
              item.refusal_question_ids ?? [],
            ),
          });
          break;
        case "reused": {
          const exportData = item.export;
          if (exportData === undefined || exportData === null) {
            settle(item.submission_id, "failed", {
              failureReason: "sidecar は出力済みファイルを返しませんでした",
            });
          } else {
            readyExports.set(item.submission_id, exportData);
          }
          break;
        }
        case "queued": {
          const jobId = item.job_id;
          if (jobId === undefined || jobId === null) {
            settle(item.submission_id, "failed", {
              failureReason: "sidecar は job_id を返しませんでした",
            });
          } else {
            pendingJobs.set(item.submission_id, jobId);
          }
          break;
        }
        default:
          settle(item.submission_id, "failed", {
            failureReason: `sidecar が知らない状態を返しました: ${item.status}`,
          });
      }
    }

    for (const submissionId of order) {
      const current = results.get(submissionId);
      if (
        current?.state === "pending" &&
        !pendingJobs.has(submissionId) &&
        !readyExports.has(submissionId)
      ) {
        settle(submissionId, "failed", {
          failureReason: "sidecar の応答にこの答案が含まれていませんでした",
        });
      }
    }

    emit(
      order
        .map((id) => results.get(id))
        .find((item) => item?.state === "pending")?.target.label ?? null,
    );

    const writeExport = async (
      submissionId: string,
      exportData: ExportResponse,
    ): Promise<void> => {
      try {
        const bytes = await getExportFile(options.client, exportData.id);
        const savedName = await writeBulkExportFile(
          options.storage,
          bulkExportFileName(exportData.file_path),
          bytes,
        );
        settle(submissionId, "written", {
          savedPath: `${options.destinationLabel}/${savedName}`,
        });
      } catch (caught) {
        const message =
          caught instanceof ExportDataError
            ? caught.message
            : caught instanceof Error
              ? `ファイルを書き込めませんでした: ${caught.message}`
              : "ファイルを書き込めませんでした";
        settle(submissionId, "failed", { failureReason: message });
      }
    };

    for (const submissionId of order) {
      if (this.cancelled) {
        break;
      }
      const exportData = readyExports.get(submissionId);
      if (exportData !== undefined) {
        await writeExport(submissionId, exportData);
        emit(
          order
            .map((id) => results.get(id))
            .find((item) => item?.state === "pending")?.target.label ?? null,
        );
      }
    }

    const transientFailures = new Map<string, number>();

    while (pendingJobs.size > 0 && !this.cancelled) {
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      for (const submissionId of [...order]) {
        if (this.cancelled) {
          break;
        }
        const jobId = pendingJobs.get(submissionId);
        if (jobId === undefined) {
          continue;
        }
        let job;
        try {
          job = await getJob(options.client, jobId);
        } catch (caught) {
          const failures = (transientFailures.get(submissionId) ?? 0) + 1;
          transientFailures.set(submissionId, failures);
          if (failures >= maxTransientPollFailures) {
            pendingJobs.delete(submissionId);
            const message =
              caught instanceof ExportDataError
                ? caught.message
                : "進捗の取得に失敗しました";
            settle(submissionId, "failed", {
              failureReason: `進捗の取得に失敗しました: ${message}`,
            });
          }
          continue;
        }
        transientFailures.set(submissionId, 0);
        switch (job.state) {
          case "succeeded": {
            pendingJobs.delete(submissionId);
            try {
              const exports = await listExports(options.client, submissionId);
              const match = exports.filter((row) => row.job_id === jobId);
              if (match.length === 0) {
                settle(submissionId, "failed", {
                  failureReason:
                    "出力は終わりましたが、生成されたファイルが見つかりません",
                });
              } else {
                await writeExport(submissionId, match[match.length - 1]!);
              }
            } catch (caught) {
              const message =
                caught instanceof ExportDataError
                  ? caught.message
                  : "出力結果の取得に失敗しました";
              settle(submissionId, "failed", {
                failureReason: `${message}: ${caught instanceof Error ? caught.message : String(caught)}`,
              });
            }
            break;
          }
          case "failed":
            pendingJobs.delete(submissionId);
            settle(submissionId, "failed", {
              failureReason: job.last_error ?? "出力に失敗しました",
            });
            break;
          case "cancelled":
            pendingJobs.delete(submissionId);
            settle(submissionId, "cancelled", {
              failureReason: "出力が取り消されました",
            });
            break;
          default:
            break;
        }
        emit(
          order
            .map((id) => results.get(id))
            .find((item) => item?.state === "pending")?.target.label ?? null,
        );
      }
    }

    if (this.cancelled) {
      for (const [submissionId, jobId] of pendingJobs.entries()) {
        try {
          await cancelJob(options.client, jobId);
        } catch {
          // Cancellation failure is non-actionable for the reviewer.
        }
        settle(submissionId, "cancelled");
      }
      for (const submissionId of order) {
        if (results.get(submissionId)?.state === "pending") {
          settle(submissionId, "cancelled");
        }
      }
      emit(null);
    }

    return emit(null);
  }
}
