import { useCallback, useEffect, useMemo, useState, type JSX } from "react";

import {
  useSidecarClient,
  useSidecarConnection,
} from "../../api/SidecarApiProvider.js";
import {
  analyzeDependencyGraph,
  buildQuestionTextOverrides,
  completeRegistration,
  confirmCriteria,
  confirmDependencyGraph,
  confirmProfile,
  detectAnswerAreas,
  emptyCriteriaQuestion,
  estimateCriteriaExtract,
  extractCriteria,
  loadTestSettingsSnapshot,
  manualAnswerAreaRegion,
  reloadAnswerAreaEditor,
  TestRegistrationDataError,
  updateCriteria,
  updateProfile,
  uploadAnswerLayout,
  type CriteriaQuestionModel,
  type CriteriaResponse,
  type DependencyEdgeModel,
  type DependencyGraphResponse,
  type ProfileResponse,
  type TestResponse,
} from "../../api/test-registration-data.js";
import {
  answerProfileConfirmRequirements,
  answerProfileSaveRequirements,
  completeRegistrationRequirements,
  dependencyGraphConfirmRequirements,
  gradingStartRequirements,
} from "../../core/action-requirements.js";
import {
  missingAnswerAreas,
  mustSeeAnswerSheetFirst,
  unassignedAnswerAreas,
} from "../../core/answer-area-review.js";
import {
  criteriaBlockingReason,
  criteriaTotals,
  dependencyGraphDescribesQuestions,
} from "../../core/criteria-totals.js";
import { dependencyExecutionLayers } from "../../core/dependency-dag.js";
import { AnswerAreaEditor } from "../answer-area-editor/AnswerAreaEditor.js";
import type {
  PageImageState,
  RegionModel,
} from "../answer-area-editor/answer-area-types.js";
import { freeRegionId } from "../answer-area-editor/region-helpers.js";
import type { components } from "../../api/generated/schema.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";

type PageGeometryResponse = components["schemas"]["PageGeometryResponse"];

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      test: TestResponse;
      profile: ProfileResponse | null;
      criteria: CriteriaResponse | null;
      dependencyGraph: DependencyGraphResponse | null;
      editableCriteria: CriteriaQuestionModel[];
      declaredTotalPoints: number | null;
      editableRegions: RegionModel[] | null;
      editableEdges: DependencyEdgeModel[] | null;
      questionNumbers: readonly string[];
      pageImages: readonly PageImageState[];
      layoutPages: readonly PageGeometryResponse[];
      answerLayoutPageCount: number | null;
      answerLayoutDetectionAvailable: boolean;
      answerLayoutDetectionReason: string | null;
    };

function criteriaConfirmed(criteria: CriteriaResponse | null): boolean {
  return criteria?.status === "confirmed";
}

function profileConfirmed(profile: ProfileResponse | null): boolean {
  return profile?.status === "confirmed";
}

function graphConfirmed(graph: DependencyGraphResponse | null): boolean {
  return graph?.status === "confirmed";
}

function answerSheetVisible(pageImages: readonly PageImageState[]): boolean {
  return pageImages.some((page) => page.objectUrl !== null);
}

function initialEditableRegions(
  profile: ProfileResponse | null,
  answerLayoutPageCount: number | null,
): RegionModel[] | null {
  if (profile !== null) {
    return profile.regions.map((region) => ({
      ...region,
      bbox: { ...region.bbox },
    }));
  }
  if (answerLayoutPageCount !== null) {
    return [];
  }
  return null;
}

function editorPages(
  profile: ProfileResponse | null,
  layoutPages: readonly PageGeometryResponse[],
): readonly { width_pt: number; height_pt: number }[] {
  if (profile !== null) {
    return profile.pages;
  }
  return layoutPages.map((page) => ({
    width_pt: page.displayed_width,
    height_pt: page.displayed_height,
  }));
}

export function TestSettingsPage(): JSX.Element {
  const client = useSidecarClient();
  const connection = useSidecarConnection();
  const { params } = useRouter();
  const testId = params.testId ?? "";
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [extractEstimateOpen, setExtractEstimateOpen] = useState(false);
  const [extractEstimate, setExtractEstimate] = useState<{
    pageCount: number;
    maxPages: number;
    estimatedCost: number | null;
    unitCost: number | null;
  } | null>(null);

  const reload = useCallback(async () => {
    if (testId.length === 0) {
      setLoadState({ status: "error", message: "テスト ID がありません" });
      return;
    }
    setLoadState({ status: "loading" });
    try {
      const snapshot = await loadTestSettingsSnapshot(client, testId);
      setLoadState({
        status: "ready",
        test: snapshot.test,
        profile: snapshot.profile,
        criteria: snapshot.criteria,
        dependencyGraph: snapshot.dependencyGraph,
        editableCriteria:
          snapshot.criteria?.questions.map((question) => ({ ...question })) ??
          [],
        declaredTotalPoints: snapshot.criteria?.declared_total_points ?? null,
        editableRegions: initialEditableRegions(
          snapshot.profile,
          snapshot.answerLayout?.page_count ?? null,
        ),
        editableEdges:
          snapshot.dependencyGraph?.edges.map((edge) => ({ ...edge })) ?? null,
        questionNumbers: snapshot.questionNumbers,
        pageImages: snapshot.editor.pageImages,
        layoutPages: snapshot.editor.layoutPages,
        answerLayoutPageCount: snapshot.answerLayout?.page_count ?? null,
        answerLayoutDetectionAvailable:
          snapshot.answerLayout?.detection_available ?? false,
        answerLayoutDetectionReason:
          snapshot.answerLayout?.detection_unavailable_reason ?? null,
      });
    } catch (error) {
      const message =
        error instanceof TestRegistrationDataError
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

  const runGuarded = useCallback(async (action: () => Promise<void>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (error) {
      const message =
        error instanceof TestRegistrationDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setActionError(message);
    } finally {
      setBusy(false);
    }
  }, []);

  const applyEditorReload = useCallback(
    async (nextProfile: ProfileResponse | null) => {
      const editor = await reloadAnswerAreaEditor(client, testId);
      setLoadState((current) => {
        if (current.status !== "ready") {
          return current;
        }
        return {
          ...current,
          profile: nextProfile,
          editableRegions:
            initialEditableRegions(
              nextProfile,
              editor.layout?.page_count ?? null,
            ) ?? current.editableRegions,
          pageImages: editor.pageImages,
          layoutPages: editor.layoutPages,
          answerLayoutPageCount: editor.layout?.page_count ?? null,
          answerLayoutDetectionAvailable:
            editor.layout?.detection_available ?? false,
          answerLayoutDetectionReason:
            editor.layout?.detection_unavailable_reason ?? null,
        };
      });
    },
    [client, testId],
  );

  const ready = loadState.status === "ready" ? loadState : null;
  const regions = ready?.editableRegions ?? null;
  const workingRegions = regions ?? [];
  const missing = missingAnswerAreas({
    regions: workingRegions,
    questionNumbers: ready?.questionNumbers ?? [],
    reportedAbsent: new Set(ready?.profile?.absent_question_numbers ?? []),
  });
  const unassigned = unassignedAnswerAreas({
    regions: workingRegions,
    knownQuestionNumbers: new Set(ready?.questionNumbers ?? []),
  });
  const answerSheetSeen = answerSheetVisible(ready?.pageImages ?? []);
  const mustSeeSheet = mustSeeAnswerSheetFirst({
    answerSheetVisible: answerSheetSeen,
    regions: workingRegions,
  });

  const saveProfileReqs = answerProfileSaveRequirements({
    busy,
    hasRegions: regions !== null && regions.length > 0,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
  });
  const confirmProfileReqs = answerProfileConfirmRequirements({
    busy,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
    regionCount: workingRegions.length,
    unassignedRegionCount: unassigned.length,
    mustSeeAnswerSheetFirst: mustSeeSheet,
    answerSheetRegistered: (ready?.answerLayoutPageCount ?? null) !== null,
  });
  const confirmGraphReqs = dependencyGraphConfirmRequirements({
    busy,
    hasGraph: ready?.dependencyGraph !== null,
    alreadyConfirmed: graphConfirmed(ready?.dependencyGraph ?? null),
  });
  const completeReqs = completeRegistrationRequirements({
    busy,
    alreadyComplete: ready?.test.status === "ready",
    profileConfirmed: profileConfirmed(ready?.profile ?? null),
    dependencyGraphConfirmed: graphConfirmed(ready?.dependencyGraph ?? null),
  });

  const criteriaBlock = ready
    ? criteriaBlockingReason(ready.editableCriteria)
    : null;
  const totals = ready
    ? criteriaTotals(ready.editableCriteria, {
        declaredTotalPoints: ready.declaredTotalPoints,
      })
    : null;

  const hasFallbackScoreRegions = workingRegions.some(
    (region) => region.kind === "score",
  );
  const graphStale =
    ready !== null &&
    ready.dependencyGraph !== null &&
    graphConfirmed(ready.dependencyGraph) &&
    !dependencyGraphDescribesQuestions({
      testId,
      graphQuestionIds: ready.dependencyGraph.question_ids,
      criteriaNumbers: criteriaConfirmed(ready.criteria)
        ? ready.editableCriteria.map((question) => question.number)
        : [],
      questionRegionLabels: profileConfirmed(ready.profile)
        ? workingRegions
            .filter((region) => region.kind === "question")
            .map((region) => region.label)
        : [],
    });

  const remainingWork = useMemo(() => {
    if (ready === null) {
      return [];
    }
    const shown = new Map(
      [
        ...completeReqs,
        ...gradingStartRequirements({
          criteriaSettled:
            criteriaConfirmed(ready.criteria) || hasFallbackScoreRegions,
          profileConfirmed: profileConfirmed(ready.profile),
          dependencyGraphConfirmed: graphConfirmed(ready.dependencyGraph),
          dependencyGraphStale: graphStale,
        }),
      ].map((requirement) => [requirement.id, requirement]),
    );
    return [...shown.values()];
  }, [completeReqs, graphStale, hasFallbackScoreRegions, ready]);

  const graphLayers =
    ready === null ||
    ready.dependencyGraph === null ||
    ready.editableEdges === null
      ? null
      : dependencyExecutionLayers(
          ready.dependencyGraph.question_ids,
          ready.editableEdges,
        );

  const editorProps = useMemo(() => {
    if (ready === null || ready.answerLayoutPageCount === null) {
      return null;
    }
    const pages = editorPages(ready.profile, ready.layoutPages);
    if (pages.length === 0) {
      return null;
    }
    return {
      pages,
      pageImages: ready.pageImages,
      regions: workingRegions,
      questionNumbers: [...ready.questionNumbers],
      undetectedQuestionNumbers: missing.undetected,
      absentQuestionNumbers: missing.absent,
      readingOrderConflicts:
        ready.profile?.reading_order_conflicts.map(
          (pair) => [pair[0], pair[1]] as [string, string],
        ) ?? [],
      readOnly: busy || profileConfirmed(ready.profile),
    };
  }, [busy, missing.absent, missing.undetected, ready, workingRegions]);

  return (
    <ShellScreen title={ready?.test.name ?? "テスト設定"}>
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

      {ready !== null ? (
        <div className="flex flex-col gap-xl">
          <section
            data-testid="test-settings-status"
            className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
          >
            <p data-testid="test-status-label" className="text-body-medium">
              {ready.test.status === "ready"
                ? "テスト状態: 登録完了"
                : "テスト状態: 下書き"}
            </p>
          </section>

          {actionError !== null ? (
            <div
              data-testid="test-settings-action-error"
              className="rounded-md border border-error bg-error-container p-md text-on-error-container"
            >
              {actionError}
            </div>
          ) : null}

          {busy ? (
            <p className="text-body-medium text-on-surface-variant">処理中…</p>
          ) : null}

          <section
            data-testid="criteria-section"
            className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
          >
            <div className="mb-md flex items-center justify-between gap-md">
              <h2 className="text-title-medium font-medium">配点と採点基準</h2>
              <span className="text-body-small text-on-surface-variant">
                {criteriaConfirmed(ready.criteria) ? "確認済み" : "未確認"}
              </span>
            </div>
            <div className="mb-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="extract-criteria-button"
                className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
                disabled={busy || criteriaConfirmed(ready.criteria)}
                onClick={() => {
                  void runGuarded(async () => {
                    const estimate = await estimateCriteriaExtract(
                      client,
                      testId,
                    );
                    setExtractEstimate({
                      pageCount: estimate.page_count,
                      maxPages: estimate.max_pages,
                      estimatedCost: estimate.estimated_cost ?? null,
                      unitCost: estimate.unit_cost ?? null,
                    });
                    setExtractEstimateOpen(true);
                  });
                }}
              >
                採点基準PDFから抽出
              </button>
              <button
                type="button"
                data-testid="add-criteria-question-button"
                className="rounded-md border border-outline px-md py-sm text-ui-label disabled:opacity-40"
                disabled={busy || criteriaConfirmed(ready.criteria)}
                onClick={() => {
                  setLoadState((current) => {
                    if (current.status !== "ready") {
                      return current;
                    }
                    return {
                      ...current,
                      editableCriteria: [
                        ...current.editableCriteria,
                        emptyCriteriaQuestion(current.editableCriteria.length),
                      ],
                    };
                  });
                }}
              >
                設問を手で追加
              </button>
            </div>

            {totals !== null ? (
              <p
                data-testid="criteria-totals-label"
                className="text-title-small"
              >
                {totals.unknownCount === 0
                  ? `配点の合計 ${totals.knownPoints} 点`
                  : `配点の合計 ${totals.knownPoints} 点 ・ 配点不明 ${totals.unknownCount} 問`}
              </p>
            ) : null}

            {ready.editableCriteria.length === 0 ? (
              <p
                data-testid="criteria-empty-message"
                className="mt-md text-body-medium text-on-surface-variant"
              >
                まだ抽出されていません。「採点基準PDFから抽出」を実行するか、手で追加してください。
              </p>
            ) : (
              <div className="mt-md flex flex-col gap-md">
                {ready.editableCriteria.map((question, index) => (
                  <CriteriaQuestionEditor
                    key={`criteria-${index}`}
                    index={index}
                    question={question}
                    readOnly={criteriaConfirmed(ready.criteria)}
                    onChange={(updated) => {
                      setLoadState((current) => {
                        if (current.status !== "ready") {
                          return current;
                        }
                        const next = [...current.editableCriteria];
                        next[index] = updated;
                        return { ...current, editableCriteria: next };
                      });
                    }}
                    onRemove={() => {
                      setLoadState((current) => {
                        if (current.status !== "ready") {
                          return current;
                        }
                        return {
                          ...current,
                          editableCriteria: current.editableCriteria.filter(
                            (_, itemIndex) => itemIndex !== index,
                          ),
                        };
                      });
                    }}
                  />
                ))}
              </div>
            )}

            {criteriaBlock !== null && !criteriaConfirmed(ready.criteria) ? (
              <p
                data-testid="criteria-blocking-reason"
                className="mt-md text-body-small text-attention"
              >
                {criteriaBlock}
              </p>
            ) : null}

            <div className="mt-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="save-criteria-button"
                className="rounded-md border border-outline px-md py-sm text-ui-label disabled:opacity-40"
                disabled={busy || criteriaConfirmed(ready.criteria)}
                onClick={() => {
                  void runGuarded(async () => {
                    const saved = await updateCriteria(client, testId, {
                      questions: ready.editableCriteria,
                      declaredTotalPoints: ready.declaredTotalPoints,
                    });
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        criteria: saved,
                        editableCriteria: saved.questions.map((question) => ({
                          ...question,
                        })),
                        declaredTotalPoints:
                          saved.declared_total_points ?? null,
                      };
                    });
                  });
                }}
              >
                修正内容を保存
              </button>
              <button
                type="button"
                data-testid="confirm-criteria-button"
                className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
                disabled={
                  busy ||
                  criteriaConfirmed(ready.criteria) ||
                  criteriaBlock !== null ||
                  ready.editableCriteria.length === 0
                }
                onClick={() => {
                  void runGuarded(async () => {
                    const saved = await updateCriteria(client, testId, {
                      questions: ready.editableCriteria,
                      declaredTotalPoints: ready.declaredTotalPoints,
                    });
                    const confirmed = await confirmCriteria(
                      client,
                      testId,
                      saved.revision,
                    );
                    const snapshot = await loadTestSettingsSnapshot(
                      client,
                      testId,
                    );
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        criteria: confirmed,
                        editableCriteria: confirmed.questions.map(
                          (question) => ({ ...question }),
                        ),
                        declaredTotalPoints:
                          confirmed.declared_total_points ?? null,
                        questionNumbers: snapshot.questionNumbers,
                      };
                    });
                  });
                }}
              >
                確定して設問に反映
              </button>
            </div>
          </section>

          <section
            data-testid="profile-section"
            className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
          >
            <div className="mb-md flex items-center justify-between gap-md">
              <h2 className="text-title-medium font-medium">
                テストプロファイル（設問・回答欄・添削記号領域の位置）
              </h2>
              <span className="text-body-small text-on-surface-variant">
                {profileConfirmed(ready.profile) ? "確認済み" : "未確認"}
              </span>
            </div>

            <div className="mb-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="upload-answer-layout-button"
                className="rounded-md border border-outline px-md py-sm text-ui-label disabled:opacity-40"
                disabled={busy || profileConfirmed(ready.profile)}
                onClick={() => {
                  void runGuarded(async () => {
                    const bridge = window.autoScoring;
                    if (bridge === undefined) {
                      throw new TestRegistrationDataError(
                        "答案ファイルを選べません",
                      );
                    }
                    const filePath = await bridge.choosePdfFile();
                    if (filePath === null) {
                      return;
                    }
                    await uploadAnswerLayout(connection, testId, filePath);
                    const snapshot = await loadTestSettingsSnapshot(
                      client,
                      testId,
                    );
                    await applyEditorReload(snapshot.profile);
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        profile: snapshot.profile,
                        editableRegions: initialEditableRegions(
                          snapshot.profile,
                          snapshot.answerLayout?.page_count ?? null,
                        ),
                        questionNumbers: snapshot.questionNumbers,
                        pageImages: snapshot.editor.pageImages,
                        layoutPages: snapshot.editor.layoutPages,
                        answerLayoutPageCount:
                          snapshot.answerLayout?.page_count ?? null,
                        answerLayoutDetectionAvailable:
                          snapshot.answerLayout?.detection_available ?? false,
                        answerLayoutDetectionReason:
                          snapshot.answerLayout?.detection_unavailable_reason ??
                          null,
                      };
                    });
                  });
                }}
              >
                {ready.answerLayoutPageCount === null
                  ? "回答欄を決める答案を選ぶ"
                  : "別の答案に差し替える"}
              </button>
              <button
                type="button"
                data-testid="detect-answer-areas-button"
                className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
                disabled={
                  busy ||
                  profileConfirmed(ready.profile) ||
                  ready.answerLayoutPageCount === null ||
                  !ready.answerLayoutDetectionAvailable ||
                  ready.questionNumbers.length === 0
                }
                onClick={() => {
                  void runGuarded(async () => {
                    const profile = await detectAnswerAreas(client, testId);
                    await applyEditorReload(profile);
                  });
                }}
              >
                回答欄を自動検出
              </button>
              <button
                type="button"
                data-testid="add-region-button"
                className="rounded-md border border-outline px-md py-sm text-ui-label disabled:opacity-40"
                disabled={
                  busy ||
                  profileConfirmed(ready.profile) ||
                  regions === null ||
                  ready.answerLayoutPageCount === null
                }
                onClick={() => {
                  setLoadState((current) => {
                    if (
                      current.status !== "ready" ||
                      current.editableRegions === null
                    ) {
                      return current;
                    }
                    const label = current.questionNumbers[0] ?? "問1";
                    return {
                      ...current,
                      editableRegions: [
                        ...current.editableRegions,
                        manualAnswerAreaRegion({
                          regionId: freeRegionId(current.editableRegions),
                          label,
                        }),
                      ],
                    };
                  });
                }}
              >
                領域を手動追加
              </button>
            </div>

            {ready.answerLayoutPageCount === null ? (
              <p
                data-testid="answer-layout-missing"
                className="mb-md text-body-small text-on-surface-variant"
              >
                回答欄は答案そのものの上で決めます。この様式の答案を1枚選んでください。
              </p>
            ) : null}

            {!ready.answerLayoutDetectionAvailable &&
            ready.answerLayoutDetectionReason !== null ? (
              <p
                data-testid="answer-layout-detection-unavailable"
                className="mb-md text-body-small text-on-surface-variant"
              >
                {ready.answerLayoutDetectionReason}
              </p>
            ) : null}

            {regions === null ? (
              <p className="text-body-medium text-on-surface-variant">
                まだ回答欄がありません。答案を取り込んで「回答欄を自動検出」するか、「領域を手動追加」で引いてください。
              </p>
            ) : null}

            {editorProps !== null ? (
              <div data-testid="answer-area-editor" className="mt-md">
                <AnswerAreaEditor
                  {...editorProps}
                  onRegionsChanged={(next) => {
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return { ...current, editableRegions: next };
                    });
                  }}
                />
              </div>
            ) : null}

            <div className="mt-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="save-profile-button"
                className="rounded-md border border-outline px-md py-sm text-ui-label disabled:opacity-40"
                disabled={saveProfileReqs.length > 0}
                onClick={() => {
                  if (regions === null) {
                    return;
                  }
                  void runGuarded(async () => {
                    const saved = await updateProfile(client, testId, regions);
                    await applyEditorReload(saved);
                  });
                }}
              >
                修正内容を保存
              </button>
              <button
                type="button"
                data-testid="confirm-profile-button"
                className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
                disabled={confirmProfileReqs.length > 0}
                onClick={() => {
                  if (regions === null) {
                    return;
                  }
                  void runGuarded(async () => {
                    const saved = await updateProfile(client, testId, regions);
                    const confirmed = await confirmProfile(
                      client,
                      testId,
                      saved.revision,
                    );
                    const snapshot = await loadTestSettingsSnapshot(
                      client,
                      testId,
                    );
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        profile: confirmed,
                        editableRegions: confirmed.regions.map((region) => ({
                          ...region,
                          bbox: { ...region.bbox },
                        })),
                        questionNumbers: snapshot.questionNumbers,
                        pageImages: snapshot.editor.pageImages,
                      };
                    });
                  });
                }}
              >
                プロファイルを確定
              </button>
            </div>
            <DisabledActionReason requirements={confirmProfileReqs} />
          </section>

          <section
            data-testid="dependency-graph-section"
            className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
          >
            <div className="mb-md flex items-center justify-between gap-md">
              <h2 className="text-title-medium font-medium">
                設問依存関係グラフ
              </h2>
              <span className="text-body-small text-on-surface-variant">
                {graphConfirmed(ready.dependencyGraph) ? "確認済み" : "未確認"}
              </span>
            </div>
            <button
              type="button"
              data-testid="analyze-dependency-graph-button"
              className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
              disabled={busy || !profileConfirmed(ready.profile)}
              onClick={() => {
                void runGuarded(async () => {
                  const graph = await analyzeDependencyGraph(
                    client,
                    testId,
                    buildQuestionTextOverrides(testId, ready.profile),
                  );
                  setLoadState((current) => {
                    if (current.status !== "ready") {
                      return current;
                    }
                    return {
                      ...current,
                      dependencyGraph: graph,
                      editableEdges: graph.edges.map((edge) => ({ ...edge })),
                    };
                  });
                });
              }}
            >
              依存関係を分析（再実行）
            </button>

            {ready.dependencyGraph === null ? (
              <p className="mt-md text-body-medium text-on-surface-variant">
                まだ分析されていません。「依存関係を分析」を実行してください。
              </p>
            ) : (
              <div className="mt-md">
                {(ready.editableEdges ?? []).length === 0 ? (
                  <p data-testid="dependency-graph-empty">
                    依存関係はありません（すべて独立した設問）。
                  </p>
                ) : (
                  <ul className="flex flex-col gap-sm">
                    {(ready.editableEdges ?? []).map((edge) => (
                      <li
                        key={`${edge.from_question_id}-${edge.to_question_id}`}
                      >
                        {edge.from_question_id} → {edge.to_question_id}:{" "}
                        {edge.rationale}
                      </li>
                    ))}
                  </ul>
                )}
                {graphLayers !== null ? (
                  <div className="mt-md">
                    <p className="text-title-small">並列実行可能な層</p>
                    {graphLayers.map((layer, index) => (
                      <p key={`layer-${index}`}>
                        第{index + 1}層: {layer.join(", ")}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            )}

            <button
              type="button"
              data-testid="confirm-dependency-graph-button"
              className="mt-md rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
              disabled={confirmGraphReqs.length > 0}
              onClick={() => {
                if (
                  ready.dependencyGraph === null ||
                  ready.editableEdges === null
                ) {
                  return;
                }
                void runGuarded(async () => {
                  const confirmed = await confirmDependencyGraph(
                    client,
                    testId,
                    {
                      version: ready.dependencyGraph!.version,
                      edges: ready.editableEdges!,
                    },
                  );
                  setLoadState((current) => {
                    if (current.status !== "ready") {
                      return current;
                    }
                    return {
                      ...current,
                      dependencyGraph: confirmed,
                      editableEdges: confirmed.edges.map((edge) => ({
                        ...edge,
                      })),
                    };
                  });
                });
              }}
            >
              依存関係グラフを確定
            </button>
            <DisabledActionReason requirements={confirmGraphReqs} />
          </section>

          <section data-testid="complete-registration-section">
            <button
              type="button"
              data-testid="complete-registration-button"
              className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
              disabled={completeReqs.length > 0}
              onClick={() => {
                void runGuarded(async () => {
                  const result = await completeRegistration(client, testId);
                  setLoadState((current) => {
                    if (current.status !== "ready") {
                      return current;
                    }
                    return { ...current, test: result.test };
                  });
                });
              }}
            >
              {ready.test.status === "ready" ? "登録完了済み" : "登録完了"}
            </button>
            <div data-testid="remaining-work-label" className="mt-sm">
              {remainingWork.length === 0 ? (
                <p className="text-body-small text-on-surface-variant">
                  「登録完了」を押すと採点を開始できる状態になります。
                </p>
              ) : (
                remainingWork.map((item) => (
                  <p
                    key={item.id}
                    data-testid={`remaining-work-${item.id}`}
                    className="text-body-small text-on-surface-variant"
                  >
                    {item.message}
                  </p>
                ))
              )}
            </div>
            <DisabledActionReason requirements={completeReqs} />
          </section>
        </div>
      ) : null}

      {extractEstimateOpen && extractEstimate !== null ? (
        <div
          data-testid="extract-confirm-dialog"
          className="fixed inset-0 flex items-center justify-center bg-scrim/40 p-lg"
        >
          <div className="max-w-md rounded-lg border border-outline bg-surface p-lg shadow-lg">
            <h3 className="text-title-medium font-medium">
              採点基準PDFから抽出
            </h3>
            <p data-testid="extract-page-count" className="mt-sm">
              {extractEstimate.pageCount} ページを AI provider に送信します。
            </p>
            <p data-testid="extract-cost" className="mt-xs text-body-small">
              {extractEstimate.estimatedCost === null
                ? "概算費用: 1ページあたりの単価が未設定です（設定画面で入力できます）"
                : `概算費用: 約${extractEstimate.estimatedCost.toFixed(2)}`}
            </p>
            <div className="mt-md flex justify-end gap-sm">
              <button
                type="button"
                data-testid="extract-cancel-button"
                className="rounded-md border border-outline px-md py-sm"
                onClick={() => {
                  setExtractEstimateOpen(false);
                  setExtractEstimate(null);
                }}
              >
                キャンセル
              </button>
              <button
                type="button"
                data-testid="extract-confirm-button"
                className="rounded-md bg-primary px-md py-sm text-on-primary disabled:opacity-40"
                disabled={extractEstimate.pageCount > extractEstimate.maxPages}
                onClick={() => {
                  setExtractEstimateOpen(false);
                  setExtractEstimate(null);
                  void runGuarded(async () => {
                    const criteria = await extractCriteria(client, testId);
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        criteria,
                        editableCriteria: criteria.questions.map(
                          (question) => ({ ...question }),
                        ),
                        declaredTotalPoints:
                          criteria.declared_total_points ?? null,
                      };
                    });
                  });
                }}
              >
                実行
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </ShellScreen>
  );
}

function CriteriaQuestionEditor({
  index,
  question,
  readOnly,
  onChange,
  onRemove,
}: {
  index: number;
  question: CriteriaQuestionModel;
  readOnly: boolean;
  onChange: (question: CriteriaQuestionModel) => void;
  onRemove: () => void;
}): JSX.Element {
  return (
    <div
      data-testid={`criteria-tile-${index}`}
      className="rounded-md border border-outline-variant p-md"
    >
      <div className="grid gap-sm md:grid-cols-2">
        <label className="flex flex-col gap-xs text-body-small">
          設問番号
          <input
            data-testid={`criteria-number-${index}`}
            className="rounded-md border border-outline px-sm py-xs"
            value={question.number}
            readOnly={readOnly}
            onChange={(event) => {
              onChange({ ...question, number: event.target.value });
            }}
          />
        </label>
        <label className="flex flex-col gap-xs text-body-small">
          配点
          <input
            data-testid={`criteria-points-${index}`}
            className="rounded-md border border-outline px-sm py-xs"
            value={question.points ?? ""}
            readOnly={readOnly}
            inputMode="numeric"
            onChange={(event) => {
              const raw = event.target.value.trim();
              onChange({
                ...question,
                points: raw.length === 0 ? null : Number.parseInt(raw, 10),
              });
            }}
          />
        </label>
      </div>
      <label className="mt-sm flex flex-col gap-xs text-body-small">
        模範解答
        <textarea
          data-testid={`criteria-model-answer-${index}`}
          className="min-h-20 rounded-md border border-outline px-sm py-xs"
          value={question.model_answer ?? ""}
          readOnly={readOnly}
          onChange={(event) => {
            onChange({
              ...question,
              model_answer:
                event.target.value.trim().length === 0
                  ? null
                  : event.target.value,
            });
          }}
        />
      </label>
      {!readOnly ? (
        <button
          type="button"
          data-testid={`remove-criteria-${index}`}
          className="mt-sm rounded-md border border-outline px-sm py-xs text-ui-label"
          onClick={onRemove}
        >
          削除
        </button>
      ) : null}
    </div>
  );
}
