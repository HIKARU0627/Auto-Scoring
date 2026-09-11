import { useCallback, useEffect, useRef, useState, type JSX } from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  BulkExportPlan,
  BulkExportProgress,
  BulkExportRunner,
  type BulkExportTarget,
} from "../../core/bulk-export.js";
import {
  createDirectoryHandleStorage,
  type BulkExportStorage,
} from "../../core/bulk-export-writer.js";
import type { ReviewQueue } from "../../core/review-queue.js";

export interface BulkExportDestination {
  readonly label: string;
  readonly storage: BulkExportStorage;
}

export interface BulkExportDialogProps {
  readonly testId: string;
  readonly queue: ReviewQueue;
  readonly onClose: () => void;
  readonly chooseDestination?: () => Promise<BulkExportDestination | null>;
  readonly pollIntervalMs?: number;
}

type DialogStage = "confirm" | "running" | "finished";

async function defaultChooseDestination(): Promise<BulkExportDestination | null> {
  if (typeof window.showDirectoryPicker !== "function") {
    return null;
  }
  const handle = await window.showDirectoryPicker();
  return {
    label: handle.name,
    storage: createDirectoryHandleStorage(handle),
  };
}

export function BulkExportDialog({
  testId,
  queue,
  onClose,
  chooseDestination = defaultChooseDestination,
  pollIntervalMs = 500,
}: BulkExportDialogProps): JSX.Element {
  const client = useSidecarClient();
  const plan = BulkExportPlan.from(queue);
  const [stage, setStage] = useState<DialogStage>("confirm");
  const [targets, setTargets] = useState<readonly BulkExportTarget[]>(
    plan.targets,
  );
  const [destinationLabel, setDestinationLabel] = useState<string | null>(null);
  const [progress, setProgress] = useState<BulkExportProgress | null>(null);
  const runnerRef = useRef<BulkExportRunner | null>(null);
  const storageRef = useRef<BulkExportStorage | null>(null);

  useEffect(() => {
    return () => {
      runnerRef.current?.cancel();
    };
  }, []);

  const runWithDestination = useCallback(
    async (
      runTargets: readonly BulkExportTarget[],
      destination: BulkExportDestination,
    ) => {
      const runner = new BulkExportRunner();
      runnerRef.current = runner;
      storageRef.current = destination.storage;
      setDestinationLabel(destination.label);
      setTargets(runTargets);
      setStage("running");
      setProgress(null);
      const result = await runner.run({
        client,
        testId,
        targets: runTargets,
        storage: destination.storage,
        destinationLabel: destination.label,
        pollIntervalMs,
        onProgress: (next) => {
          setProgress(next);
        },
      });
      setProgress(result);
      setStage("finished");
      runnerRef.current = null;
    },
    [client, pollIntervalMs, testId],
  );

  const handleStart = useCallback(async () => {
    const destination = await chooseDestination();
    if (destination === null) {
      return;
    }
    await runWithDestination(plan.targets, destination);
  }, [chooseDestination, plan.targets, runWithDestination]);

  const handleRetryFailures = useCallback(async () => {
    const retryable = progress?.retryableTargets ?? [];
    if (retryable.length === 0 || storageRef.current === null) {
      return;
    }
    const destination: BulkExportDestination = {
      label: destinationLabel ?? "",
      storage: storageRef.current,
    };
    await runWithDestination(retryable, destination);
  }, [destinationLabel, progress, runWithDestination]);

  const handleCancel = useCallback(() => {
    runnerRef.current?.cancel();
  }, []);

  const queueIsEmpty = queue.isEmpty;
  const hasTargets = targets.length > 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-overlay-scrim p-md"
    >
      <div className="w-full max-w-lg rounded-lg border border-outline bg-surface p-lg shadow-elevation-2 text-on-surface">
        <h2 className="text-title-medium font-medium mb-md">まとめてPDF出力</h2>

        {queueIsEmpty ? (
          <div data-testid="bulk-export-empty" className="py-md">
            <p className="text-body-medium text-on-surface-variant">
              このテストにはまだ答案がありません。
            </p>
          </div>
        ) : null}

        {!queueIsEmpty && stage === "confirm" ? (
          <div data-testid="bulk-export-confirm" className="py-md space-y-sm">
            {hasTargets ? (
              <>
                <p className="text-body-medium">対象 {plan.targets.length}件</p>
                <ul className="text-body-small text-on-surface-variant">
                  {plan.targets.map((target) => (
                    <li key={target.submissionId}>{target.label}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p
                data-testid="bulk-export-empty-targets"
                className="text-body-medium text-on-surface-variant"
              >
                出力できる答案がありません。全設問を確定させると対象になります。
              </p>
            )}
            {plan.excluded.length > 0 ? (
              <div data-testid="bulk-export-excluded">
                <p className="text-body-medium mt-sm">
                  対象外 {plan.excluded.length}件
                </p>
                <ul className="text-body-small text-on-surface-variant">
                  {plan.excluded.map((item) => (
                    <li key={item.submissionId}>
                      {item.label}: {item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}

        {stage === "running" && progress !== null ? (
          <div data-testid="bulk-export-progress" className="py-md space-y-sm">
            <p className="text-body-medium">
              {progress.settledCount} / {progress.totalCount} 件
            </p>
            {progress.currentLabel !== null ? (
              <p className="text-body-small text-on-surface-variant">
                出力中: {progress.currentLabel}
              </p>
            ) : null}
          </div>
        ) : null}

        {stage === "finished" && progress !== null ? (
          <div data-testid="bulk-export-result" className="py-md space-y-sm">
            <p className="text-body-medium">
              {progress.writtenCount} / {progress.totalCount} 件を出力しました。
            </p>
            {destinationLabel !== null ? (
              <p className="text-body-small text-on-surface-variant">
                保存先: {destinationLabel}
              </p>
            ) : null}
            {progress.failures.length > 0 ? (
              <div data-testid="bulk-export-failures">
                <p className="text-body-medium mt-sm">失敗した答案</p>
                <ul className="text-body-small text-on-surface-variant">
                  {progress.failures.map((item) => (
                    <li key={item.target.submissionId}>
                      {item.target.label}: {item.failureReason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-md flex justify-end gap-sm">
          {stage === "confirm" && hasTargets ? (
            <button
              type="button"
              data-testid="bulk-export-start-button"
              className="rounded-md border border-primary bg-primary px-md py-xs text-ui-label text-on-primary"
              onClick={() => {
                void handleStart();
              }}
            >
              出力先を選んで開始
            </button>
          ) : null}
          {stage === "running" ? (
            <button
              type="button"
              data-testid="bulk-export-cancel-button"
              className="rounded-md border border-outline px-md py-xs text-ui-label text-on-surface"
              onClick={handleCancel}
            >
              中止
            </button>
          ) : null}
          {stage === "finished" &&
          (progress?.retryableTargets.length ?? 0) > 0 ? (
            <button
              type="button"
              data-testid="bulk-export-retry-button"
              className="rounded-md border border-primary bg-primary px-md py-xs text-ui-label text-on-primary"
              onClick={() => {
                void handleRetryFailures();
              }}
            >
              失敗した分を再実行
            </button>
          ) : null}
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
