import { useCallback, useEffect, useMemo, useState, type JSX } from "react";

import {
  AnswerAreaDataError,
  loadAnswerAreaEditorData,
  type ProfileResponse,
} from "../../api/answer-area-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import { missingAnswerAreas } from "../../core/answer-area-review.js";
import { AnswerAreaEditor } from "../answer-area-editor/AnswerAreaEditor.js";
import type {
  PageImageState,
  RegionModel,
} from "../answer-area-editor/answer-area-types.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      profile: ProfileResponse | null;
      pageImages: readonly PageImageState[];
      regions: RegionModel[];
    };

export function TestSettingsPage(): JSX.Element {
  const client = useSidecarClient();
  const { params } = useRouter();
  const testId = params.testId ?? "";
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  const reload = useCallback(async () => {
    if (testId.length === 0) {
      setLoadState({ status: "error", message: "テスト ID がありません" });
      return;
    }
    setLoadState({ status: "loading" });
    try {
      const data = await loadAnswerAreaEditorData(client, testId);
      setLoadState({
        status: "ready",
        profile: data.profile,
        pageImages: data.pageImages,
        regions: data.profile?.regions ?? [],
      });
    } catch (error) {
      const message =
        error instanceof AnswerAreaDataError
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

  const onRegionsChanged = useCallback((regions: RegionModel[]) => {
    setLoadState((current) => {
      if (current.status !== "ready") {
        return current;
      }
      return { ...current, regions };
    });
  }, []);

  const editorProps = useMemo(() => {
    if (loadState.status !== "ready" || loadState.profile === null) {
      return null;
    }
    const profile = loadState.profile;
    const reportedAbsent = new Set(profile.absent_question_numbers);
    const missing = missingAnswerAreas({
      regions: loadState.regions,
      questionNumbers: profile.question_numbers,
      reportedAbsent,
    });
    const conflicts = profile.reading_order_conflicts.map(
      (pair) => [pair[0], pair[1]] as [string, string],
    );
    const readOnly = profile.status === "confirmed";
    return {
      pages: profile.pages,
      pageImages: loadState.pageImages,
      regions: loadState.regions,
      questionNumbers: profile.question_numbers,
      undetectedQuestionNumbers: missing.undetected,
      absentQuestionNumbers: missing.absent,
      readingOrderConflicts: conflicts,
      readOnly,
    };
  }, [loadState]);

  return (
    <ShellScreen title="テスト設定">
      {loadState.status === "loading" ? (
        <p className="text-body-medium text-on-surface-variant">読み込み中…</p>
      ) : null}

      {loadState.status === "error" ? (
        <div
          data-testid="test-settings-error"
          className="rounded-md border border-error bg-error-container p-lg text-on-error-container"
        >
          <p className="text-body-medium">{loadState.message}</p>
          <button
            type="button"
            className="mt-md rounded-md border border-outline px-md py-xs text-ui-label"
            onClick={() => {
              void reload();
            }}
          >
            再試行
          </button>
        </div>
      ) : null}

      {loadState.status === "ready" && loadState.profile === null ? (
        <p className="text-body-medium text-on-surface-variant">
          まだ回答欄がありません。答案を取り込んで「回答欄を自動検出」するか、「領域を手動追加」で引いてください。
        </p>
      ) : null}

      {editorProps !== null ? (
        <section data-testid="answer-area-editor">
          <h2 className="mb-md text-title-medium font-medium">
            テストプロファイル（設問・回答欄・添削記号領域の位置）
          </h2>
          <AnswerAreaEditor
            {...editorProps}
            onRegionsChanged={onRegionsChanged}
          />
        </section>
      ) : null}
    </ShellScreen>
  );
}
