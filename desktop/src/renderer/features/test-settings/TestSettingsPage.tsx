import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  analyzeDependencyGraph,
  AnswerDetectionRateLimitedError,
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
  ActionRequirements,
  answerCoverageRequirements,
  answerDetectRequirements,
  answerDetectionOutcomeRequirements,
  answerProfileConfirmRequirements,
  answerProfileSaveRequirements,
  answerProfileUndetectedConfirmRequirements,
  answerRegionAddRequirements,
  completeRegistrationRequirements,
  dependencyGraphConfirmRequirements,
  gradingStartRequirements,
} from "../../core/action-requirements.js";
import {
  classifyAnswerDetectionOutcome,
  type AnswerDetectionOutcome,
} from "../../core/answer-detection-outcome.js";
import {
  answerAreaCoverage,
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
import { intakeTarget } from "../../core/app-routes.js";
import { AppErrorBanner } from "../../core/AppErrorBanner.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";
import {
  BusyNotice,
  Caption,
  Card,
  CardHeading,
  ErrorNotice,
  ProgressMeter,
  ScreenSkeleton,
  StatusPill,
  StepProgress,
  primaryButtonClass,
  secondaryButtonClass,
} from "../ui/screen-ui.js";

type PageGeometryResponse = components["schemas"]["PageGeometryResponse"];

interface RunningWork {
  readonly title: string;
  readonly detail: string;
}

/**
 * What each long-running button is doing, and roughly how long it takes
 * (Issue #346). The measured waits are 14-21s for answer-area detection and
 * 9-63s for criteria extraction, so a bare "処理中…" would leave the reviewer
 * staring at a frozen screen.
 */
const WORK = {
  extractEstimate: {
    title: "採点基準を確認しています",
    detail: "AIへ送るページ数と概算費用を計算しています。",
  },
  extract: {
    title: "採点基準PDFから抽出しています",
    detail: "AIが設問と配点を読み取っています。9〜63秒ほどかかります。",
  },
  saveCriteria: {
    title: "配点と採点基準を保存しています",
    detail: "保存が終わると内容が最新の状態に更新されます。",
  },
  confirmCriteria: {
    title: "配点と採点基準を確定しています",
    detail: "確定すると「回答欄を自動検出」ができるようになります。",
  },
  uploadLayout: {
    title: "答案を取り込んでいます",
    detail: "答案のページを読み込んでいます。",
  },
  detect: {
    title: "回答欄を検出しています",
    detail: "AIが答案を見ています。通常14〜21秒ほどかかります。",
  },
  saveProfile: {
    title: "回答欄を保存しています",
    detail: "保存が終わると内容が最新の状態に更新されます。",
  },
  confirmProfile: {
    title: "プロファイルを確定しています",
    detail: "回答欄の位置を確定しています。",
  },
  analyzeGraph: {
    title: "設問の依存関係を分析しています",
    detail: "AIが設問どうしの関係を読んでいます。数十秒かかることがあります。",
  },
  confirmGraph: {
    title: "依存関係グラフを確定しています",
    detail: "分析した依存関係を確定しています。",
  },
  complete: {
    title: "登録を完了しています",
    detail: "登録が終わると答案を取り込んで採点を始められます。",
  },
} as const satisfies Record<string, RunningWork>;

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
      detectionOutcome: AnswerDetectionOutcome;
      detectionRetryAfterSeconds: number | null;
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

function profileRegions(profile: ProfileResponse | null): RegionModel[] {
  if (profile === null) {
    return [];
  }
  return profile.regions.map((region) => ({
    ...region,
    bbox: { ...region.bbox },
  }));
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

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function useModalDialogBehavior(
  open: boolean,
  onClose: () => void,
): RefObject<HTMLDivElement | null> {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const panel = panelRef.current;
    if (!open || panel === null) {
      return;
    }

    const focusables = (): HTMLElement[] =>
      Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));

    (focusables()[0] ?? panel).focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const list = focusables();
      if (list.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const activeElement = document.activeElement;
      if (event.shiftKey) {
        if (activeElement === first || !panel.contains(activeElement)) {
          event.preventDefault();
          last?.focus();
        }
      } else if (activeElement === last || !panel.contains(activeElement)) {
        event.preventDefault();
        first?.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  return panelRef;
}

export function TestSettingsPage(): JSX.Element {
  const client = useSidecarClient();
  const { params, push } = useRouter();
  const testId = params.testId ?? "";
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [runningWork, setRunningWork] = useState<RunningWork | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [extractEstimateOpen, setExtractEstimateOpen] = useState(false);
  const [undetectedConfirmOpen, setUndetectedConfirmOpen] = useState(false);
  const [extractEstimate, setExtractEstimate] = useState<{
    pageCount: number;
    maxPages: number;
    estimatedCost: number | null;
    unitCost: number | null;
  } | null>(null);

  const closeExtractEstimate = useCallback(() => {
    setExtractEstimateOpen(false);
    setExtractEstimate(null);
  }, []);
  const closeUndetectedConfirm = useCallback(() => {
    setUndetectedConfirmOpen(false);
  }, []);
  const extractDialogRef = useModalDialogBehavior(
    extractEstimateOpen,
    closeExtractEstimate,
  );
  const undetectedDialogRef = useModalDialogBehavior(
    undetectedConfirmOpen,
    closeUndetectedConfirm,
  );

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
        detectionOutcome: "none",
        detectionRetryAfterSeconds: null,
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

  const runGuarded = useCallback(
    async (work: RunningWork, action: () => Promise<void>) => {
      setBusy(true);
      setRunningWork(work);
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
        setRunningWork(null);
      }
    },
    [],
  );

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
          detectionOutcome: current.detectionOutcome,
          detectionRetryAfterSeconds: current.detectionRetryAfterSeconds,
        };
      });
    },
    [client, testId],
  );

  const ready = loadState.status === "ready" ? loadState : null;
  const answerSheetRegistered = (ready?.answerLayoutPageCount ?? null) !== null;
  const regions =
    ready?.editableRegions ??
    (answerSheetRegistered ? ([] as RegionModel[]) : null);
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

  const coverage = answerAreaCoverage({
    questionNumbers: ready?.questionNumbers ?? [],
    regions: workingRegions,
  });
  const coverageReqs = answerCoverageRequirements({
    expected: coverage.expected,
    covered: coverage.covered,
  });
  const undetectedConfirmReqs = answerProfileUndetectedConfirmRequirements({
    undetectedQuestionCount: missing.undetected.length,
  });

  const answerAreaRegionCount = workingRegions.filter(
    (region) => region.kind === "answer_area",
  ).length;
  const saveProfileReqs = answerProfileSaveRequirements({
    busy,
    hasRegions: answerAreaRegionCount > 0,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
  });
  const confirmProfileReqs = answerProfileConfirmRequirements({
    busy,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
    regionCount: answerAreaRegionCount,
    unassignedRegionCount: unassigned.length,
    mustSeeAnswerSheetFirst: mustSeeSheet,
    answerSheetRegistered,
  });
  const addRegionReqs = answerRegionAddRequirements({
    busy,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
    answerSheetRegistered,
  });
  const detectReqs = answerDetectRequirements({
    busy,
    alreadyConfirmed: profileConfirmed(ready?.profile ?? null),
    answerSheetRegistered,
    detectionAvailable: ready?.answerLayoutDetectionAvailable ?? false,
    criteriaConfirmed: criteriaConfirmed(ready?.criteria ?? null),
  });
  const detectionOutcomeReqs = answerDetectionOutcomeRequirements({
    outcome: ready?.detectionOutcome ?? "none",
    retryAfterSeconds: ready?.detectionRetryAfterSeconds ?? null,
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

  const registrationSteps = [
    {
      id: "criteria",
      label: "配点・採点基準",
      complete: criteriaConfirmed(ready?.criteria ?? null),
    },
    {
      id: "profile",
      label: "回答欄の確認",
      complete: profileConfirmed(ready?.profile ?? null),
    },
    {
      id: "dependency",
      label: "依存関係",
      complete: graphConfirmed(ready?.dependencyGraph ?? null),
    },
  ];
  const currentRegistrationStep =
    registrationSteps.find((step) => !step.complete)?.id ?? null;

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

  const runConfirmProfile = useCallback(() => {
    if (regions === null) {
      return;
    }
    void runGuarded(WORK.confirmProfile, async () => {
      const saved = await updateProfile(client, testId, regions);
      const confirmed = await confirmProfile(client, testId, saved.revision);
      const snapshot = await loadTestSettingsSnapshot(client, testId);
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
  }, [client, regions, runGuarded, testId]);

  const confirmProfileWithGuard = useCallback(() => {
    if (undetectedConfirmReqs.length > 0) {
      setUndetectedConfirmOpen(true);
      return;
    }
    runConfirmProfile();
  }, [runConfirmProfile, undetectedConfirmReqs.length]);

  return (
    <ShellScreen title={ready?.test.name ?? "テスト設定"}>
      {loadState.status === "loading" ? (
        <ScreenSkeleton testId="test-settings-loading" />
      ) : null}

      {loadState.status === "error" ? (
        <AppErrorBanner
          testId="test-settings-error"
          message={loadState.message}
          onRetry={() => {
            void reload();
          }}
        />
      ) : null}

      {ready !== null ? (
        <div className="flex flex-col gap-xl">
          <Card testId="test-settings-status">
            <CardHeading
              title="登録の確認ステップ"
              description="3つの確認を済ませると登録完了になります。"
              aside={
                <StatusPill
                  tone={ready.test.status === "ready" ? "success" : "attention"}
                >
                  {ready.test.status === "ready" ? "登録完了" : "下書き"}
                </StatusPill>
              }
            />
            <div className="mt-lg">
              <StepProgress
                testId="test-settings-steps"
                steps={registrationSteps}
                currentId={currentRegistrationStep}
              />
            </div>
            <div className="mt-lg">
              <ProgressMeter
                testId="test-settings-progress"
                label="確認済みのステップ"
                value={registrationSteps.filter((step) => step.complete).length}
                max={registrationSteps.length}
              />
            </div>
            <div data-testid="test-status-label" className="mt-md">
              <Caption>
                {ready.test.status === "ready"
                  ? "テスト状態: 登録完了"
                  : "テスト状態: 下書き"}
              </Caption>
            </div>
            <div className="mt-lg flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="test-settings-open-materials-button"
                className={secondaryButtonClass()}
                onClick={() => {
                  void window.autoScoring?.openMaterialWindow({ testId });
                }}
              >
                資料を開く
              </button>
            </div>
          </Card>

          {actionError !== null ? (
            <ErrorNotice testId="test-settings-action-error">
              {actionError}
            </ErrorNotice>
          ) : null}

          {busy ? (
            <BusyNotice
              testId="test-settings-busy"
              title={runningWork?.title ?? "処理しています"}
              detail={runningWork?.detail ?? "完了すると表示が更新されます。"}
            />
          ) : null}

          <Card testId="criteria-section">
            <CardHeading
              title="配点と採点基準"
              description="設問ごとの配点と模範解答を確認します。"
              aside={
                <StatusPill
                  tone={
                    criteriaConfirmed(ready.criteria) ? "success" : "attention"
                  }
                >
                  {criteriaConfirmed(ready.criteria) ? "確認済み" : "未確認"}
                </StatusPill>
              }
            />
            <div className="mt-lg flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="extract-criteria-button"
                className={primaryButtonClass()}
                disabled={busy || criteriaConfirmed(ready.criteria)}
                onClick={() => {
                  void runGuarded(WORK.extractEstimate, async () => {
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
                className={secondaryButtonClass()}
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

            {totals !== null && ready.editableCriteria.length > 0 ? (
              <p
                data-testid="criteria-totals-label"
                className="mt-md tabular-nums text-body-medium text-on-surface"
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
                className="mt-md text-body-medium text-attention"
              >
                {criteriaBlock}
              </p>
            ) : null}

            <div className="mt-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="save-criteria-button"
                className={secondaryButtonClass()}
                disabled={busy || criteriaConfirmed(ready.criteria)}
                onClick={() => {
                  void runGuarded(WORK.saveCriteria, async () => {
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
                className={primaryButtonClass()}
                disabled={
                  busy ||
                  criteriaConfirmed(ready.criteria) ||
                  criteriaBlock !== null ||
                  ready.editableCriteria.length === 0
                }
                onClick={() => {
                  void runGuarded(WORK.confirmCriteria, async () => {
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
          </Card>

          <Card testId="profile-section">
            <CardHeading
              title="テストプロファイル（設問・回答欄・添削記号領域の位置）"
              description="答案の上で回答欄の位置を確認します。"
              aside={
                <StatusPill
                  tone={
                    profileConfirmed(ready.profile) ? "success" : "attention"
                  }
                >
                  {profileConfirmed(ready.profile) ? "確認済み" : "未確認"}
                </StatusPill>
              }
            />

            <div className="mt-lg flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="upload-answer-layout-button"
                className={secondaryButtonClass()}
                disabled={busy || profileConfirmed(ready.profile)}
                onClick={() => {
                  void runGuarded(WORK.uploadLayout, async () => {
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
                    await uploadAnswerLayout(testId, filePath);
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
                        detectionOutcome: "none",
                        detectionRetryAfterSeconds: null,
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
                className={primaryButtonClass()}
                disabled={detectReqs.length > 0}
                onClick={() => {
                  void runGuarded(WORK.detect, async () => {
                    let profile: ProfileResponse;
                    try {
                      profile = await detectAnswerAreas(client, testId);
                    } catch (error) {
                      if (error instanceof AnswerDetectionRateLimitedError) {
                        // The provider refused the call. Nothing was detected
                        // *because of the rate limit*, which is a different
                        // fact from "detection found no boxes" -- show the
                        // single-source wording that says to wait and press
                        // again, with the server's own seconds when it gave
                        // one (Issue #304).
                        setLoadState((current) => {
                          if (current.status !== "ready") {
                            return current;
                          }
                          return {
                            ...current,
                            detectionOutcome: "rate-limited",
                            detectionRetryAfterSeconds: error.retryAfterSeconds,
                          };
                        });
                        return;
                      }
                      throw error;
                    }
                    const nextRegions = profileRegions(profile);
                    const detectionOutcome = classifyAnswerDetectionOutcome({
                      questionNumbers: ready.questionNumbers,
                      regions: nextRegions,
                      absentQuestionNumbers: profile.absent_question_numbers,
                    });
                    await applyEditorReload(profile);
                    setLoadState((current) => {
                      if (current.status !== "ready") {
                        return current;
                      }
                      return {
                        ...current,
                        profile,
                        editableRegions: nextRegions,
                        detectionOutcome,
                        detectionRetryAfterSeconds: null,
                      };
                    });
                  });
                }}
              >
                回答欄を自動検出
              </button>
              <button
                type="button"
                data-testid="add-region-button"
                className={secondaryButtonClass()}
                disabled={addRegionReqs.length > 0}
                onClick={() => {
                  setLoadState((current) => {
                    if (current.status !== "ready") {
                      return current;
                    }
                    const working =
                      current.editableRegions ??
                      (current.answerLayoutPageCount !== null ? [] : null);
                    if (working === null) {
                      return current;
                    }
                    const label = current.questionNumbers[0] ?? "問1";
                    return {
                      ...current,
                      editableRegions: [
                        ...working,
                        manualAnswerAreaRegion({
                          regionId: freeRegionId(working),
                          label,
                        }),
                      ],
                      detectionOutcome: "none",
                      detectionRetryAfterSeconds: null,
                    };
                  });
                }}
              >
                領域を手動追加
              </button>
            </div>
            <DisabledActionReason requirements={detectReqs} />

            {ready.answerLayoutPageCount === null ? (
              <p
                data-testid="answer-layout-missing"
                className="mb-md text-body-medium text-on-surface-variant"
              >
                回答欄は答案そのものの上で決めます。この様式の答案を1枚選んでください。
              </p>
            ) : null}

            {detectionOutcomeReqs.length > 0 ? (
              <div data-testid="answer-detection-outcome" className="mb-md">
                <DisabledActionReason requirements={detectionOutcomeReqs} />
              </div>
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

            {coverageReqs.length > 0 ? (
              <p
                data-testid="answer-area-coverage"
                className="mt-md text-body-medium text-on-surface-variant"
              >
                {coverageReqs[0]?.message}
              </p>
            ) : null}

            <div className="mt-md flex flex-wrap gap-sm">
              <button
                type="button"
                data-testid="save-profile-button"
                className={secondaryButtonClass()}
                disabled={saveProfileReqs.length > 0}
                onClick={() => {
                  if (regions === null) {
                    return;
                  }
                  void runGuarded(WORK.saveProfile, async () => {
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
                className={primaryButtonClass()}
                disabled={confirmProfileReqs.length > 0}
                onClick={confirmProfileWithGuard}
              >
                プロファイルを確定
              </button>
            </div>
            <DisabledActionReason requirements={addRegionReqs} />
            <DisabledActionReason requirements={confirmProfileReqs} />
          </Card>

          <Card testId="dependency-graph-section">
            <CardHeading
              title="設問依存関係グラフ"
              description="設問どうしの依存関係を確認します。"
              aside={
                <StatusPill
                  tone={
                    graphConfirmed(ready.dependencyGraph)
                      ? "success"
                      : "attention"
                  }
                >
                  {graphConfirmed(ready.dependencyGraph)
                    ? "確認済み"
                    : "未確認"}
                </StatusPill>
              }
            />
            <button
              type="button"
              data-testid="analyze-dependency-graph-button"
              className={primaryButtonClass()}
              disabled={busy || !profileConfirmed(ready.profile)}
              onClick={() => {
                void runGuarded(WORK.analyzeGraph, async () => {
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
                    <p className="text-recognized font-medium text-on-surface">
                      並列実行可能な層
                    </p>
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
                void runGuarded(WORK.confirmGraph, async () => {
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
          </Card>

          <Card testId="complete-registration-section">
            <CardHeading
              title="登録完了"
              description="3つの確認が済むと登録を完了できます。"
              aside={
                <StatusPill
                  tone={ready.test.status === "ready" ? "success" : "attention"}
                >
                  {ready.test.status === "ready" ? "登録完了" : "未完了"}
                </StatusPill>
              }
            />
            <div className="mt-lg">
              <button
                type="button"
                data-testid="complete-registration-button"
                className={primaryButtonClass()}
                disabled={completeReqs.length > 0}
                onClick={() => {
                  void runGuarded(WORK.complete, async () => {
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
              <div
                data-testid="remaining-work-label"
                className="mt-md flex flex-col gap-xs"
              >
                <p
                  data-testid="remaining-work-count"
                  className="text-body-medium font-medium text-on-surface"
                >
                  {remainingWork.length === 0
                    ? "残りの確認はありません"
                    : `残りの確認 ${remainingWork.length}件`}
                </p>
                {remainingWork.length === 0 ? (
                  <p className="text-body-medium text-on-surface-variant">
                    「登録完了」を押すと採点を開始できる状態になります。
                  </p>
                ) : (
                  remainingWork.map((item) => (
                    <p
                      key={item.id}
                      data-testid={`remaining-work-${item.id}`}
                      className="text-body-medium text-on-surface-variant"
                    >
                      {item.message}
                    </p>
                  ))
                )}
              </div>
              <DisabledActionReason requirements={completeReqs} />
            </div>
          </Card>

          <Card testId="answers-intake-section">
            <CardHeading
              title="答案の取り込み"
              description="答案を取り込むとAI採点が始まります。取り込み先にはこのテストが選ばれた状態で開きます。"
              aside={
                <StatusPill
                  tone={ready.test.status === "ready" ? "success" : "attention"}
                >
                  {ready.test.status === "ready" ? "取り込めます" : "登録待ち"}
                </StatusPill>
              }
            />
            <div className="mt-lg">
              <button
                type="button"
                data-testid="open-answers-intake-button"
                className={primaryButtonClass()}
                disabled={busy || ready.test.status !== "ready"}
                onClick={() => {
                  push(intakeTarget(testId));
                }}
              >
                答案を取り込む
              </button>
              {ready.test.status === "ready" ? null : (
                <p
                  data-testid="answers-intake-waiting"
                  className="mt-md text-body-medium text-on-surface-variant"
                >
                  配点・回答欄・依存関係の確認が済むと、答案を取り込めます。上の各セクションで確認を完了してください。
                </p>
              )}
            </div>
          </Card>
        </div>
      ) : null}

      {extractEstimateOpen && extractEstimate !== null
        ? createPortal(
            <div
              data-testid="extract-confirm-dialog"
              className="fixed inset-0 z-50 overflow-y-auto bg-overlay-scrim"
              role="dialog"
              aria-modal="true"
            >
              <div className="flex min-h-full items-center justify-center p-lg">
                <div
                  ref={extractDialogRef}
                  className="grid w-full max-w-112 max-h-dialog-viewport grid-dialog-body-footer overflow-hidden rounded-xl bg-surface-container-high shadow-lg"
                >
                  <div className="overflow-y-auto p-lg">
                    <h3 className="text-recognized font-medium leading-ui text-on-surface">
                      採点基準PDFから抽出
                    </h3>
                    <p data-testid="extract-page-count" className="mt-sm">
                      {extractEstimate.pageCount} ページを AI provider
                      に送信します。
                    </p>
                    <p
                      data-testid="extract-cost"
                      className="mt-xs text-body-medium"
                    >
                      {extractEstimate.estimatedCost === null
                        ? "概算費用: 1ページあたりの単価が未設定です（設定画面で入力できます）"
                        : `概算費用: 約${extractEstimate.estimatedCost.toFixed(2)}`}
                    </p>
                    {extractEstimate.pageCount > extractEstimate.maxPages ? (
                      <p
                        data-testid="extract-over-limit"
                        className="mt-sm text-body-medium text-attention"
                      >
                        一度に読めるのは {extractEstimate.maxPages}{" "}
                        ページまでです。このまま実行しても失敗します。ファイルを分割してください。
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-row flex-nowrap items-center justify-end gap-sm border-t border-outline-variant p-lg pt-md">
                    <button
                      type="button"
                      data-testid="extract-cancel-button"
                      className={secondaryButtonClass(
                        "shrink-0 whitespace-nowrap",
                      )}
                      onClick={closeExtractEstimate}
                    >
                      キャンセル
                    </button>
                    <button
                      type="button"
                      data-testid="extract-confirm-button"
                      className={primaryButtonClass(
                        "shrink-0 whitespace-nowrap",
                      )}
                      disabled={
                        extractEstimate.pageCount > extractEstimate.maxPages
                      }
                      onClick={() => {
                        closeExtractEstimate();
                        void runGuarded(WORK.extract, async () => {
                          const criteria = await extractCriteria(
                            client,
                            testId,
                          );
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
            </div>,
            document.body,
          )
        : null}

      {undetectedConfirmOpen && missing.undetected.length > 0
        ? createPortal(
            <div
              data-testid="profile-confirm-undetected-dialog"
              className="fixed inset-0 z-50 overflow-y-auto bg-overlay-scrim"
              role="dialog"
              aria-modal="true"
            >
              <div className="flex min-h-full items-center justify-center p-lg">
                <div
                  ref={undetectedDialogRef}
                  className="grid w-full max-w-112 max-h-dialog-viewport grid-dialog-body-footer overflow-hidden rounded-xl bg-surface-container-high shadow-lg"
                >
                  <div className="overflow-y-auto p-lg">
                    <h3 className="text-recognized font-medium leading-ui text-on-surface">
                      回答欄が見つかっていない設問があります
                    </h3>
                    <p
                      data-testid="profile-confirm-undetected-count"
                      className="mt-sm text-body-medium"
                    >
                      {
                        ActionRequirements.profileConfirmUndetected(
                          missing.undetected.length,
                        ).message
                      }
                    </p>
                    <p className="mt-sm text-body-medium text-on-surface-variant">
                      {
                        ActionRequirements.profileConfirmUndetectedAction
                          .message
                      }
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-row flex-nowrap items-center justify-end gap-sm border-t border-outline-variant p-lg pt-md">
                    <button
                      type="button"
                      data-testid="profile-confirm-undetected-cancel"
                      className={secondaryButtonClass(
                        "shrink-0 whitespace-nowrap",
                      )}
                      onClick={closeUndetectedConfirm}
                    >
                      戻って直す
                    </button>
                    <button
                      type="button"
                      data-testid="profile-confirm-undetected-proceed"
                      className={primaryButtonClass(
                        "shrink-0 whitespace-nowrap",
                      )}
                      onClick={() => {
                        setUndetectedConfirmOpen(false);
                        runConfirmProfile();
                      }}
                    >
                      このまま確定
                    </button>
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
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
      className="rounded-lg bg-surface-container-high p-md"
    >
      <div className="grid gap-sm md:grid-cols-2">
        <label className="flex flex-col gap-xs">
          <Caption>設問番号</Caption>
          <input
            data-testid={`criteria-number-${index}`}
            className="rounded-md bg-surface-container px-sm py-xs text-on-surface"
            value={question.number}
            readOnly={readOnly}
            onChange={(event) => {
              onChange({ ...question, number: event.target.value });
            }}
          />
        </label>
        <label className="flex flex-col gap-xs">
          <Caption>配点</Caption>
          <input
            data-testid={`criteria-points-${index}`}
            className="rounded-md bg-surface-container px-sm py-xs text-on-surface"
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
      <label className="mt-sm flex flex-col gap-xs">
        <Caption>模範解答</Caption>
        <textarea
          data-testid={`criteria-model-answer-${index}`}
          className="min-h-20 rounded-md bg-surface-container px-sm py-xs text-on-surface"
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
          className="mt-sm w-fit rounded-md bg-surface-container-high px-sm py-xs text-ui-label text-on-surface"
          onClick={onRemove}
        >
          削除
        </button>
      ) : null}
    </div>
  );
}
