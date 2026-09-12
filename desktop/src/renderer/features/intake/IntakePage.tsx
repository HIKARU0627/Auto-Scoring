import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
} from "react";

import {
  attributeAnswer,
  classifyMaterial,
  importReview,
  intakeBridgeFromWindow,
  loadClassificationAvailability,
  loadIntakeCost,
  loadIntakeSession,
  loadIntakeTemplates,
  listTests,
  planIntake,
  resetIntakeSession,
  saveIntakeSession,
  sessionMatchesScan,
  type ImportOutcome,
  type IntakeBridge,
  type IntakeSession,
  type IntakeStep,
  type TestResponse,
  importedAnything,
} from "../../core/intake-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  ActionRequirements,
  intakeFolderPickRequirements,
  intakeImportRequirements,
} from "../../core/action-requirements.js";
import { testSettings } from "../../core/app-routes.js";
import {
  attributionCandidates,
  dropRoutingOutsideCandidates,
  reviewerChoseOneTest,
} from "../../core/intake-attribution.js";
import {
  IntakeTargetKind,
  buildReviewState,
  canImport,
  classifiableFiles,
  confirmAllProposals,
  confirmableProposals,
  copyIntakeFile,
  copyIntakeGroup,
  effectiveRole,
  importRequirements,
  includedFiles,
  intakeFileName,
  pendingClassification,
  pruneStaleTargets,
  requiredRolesOf,
  targetTestAcceptsAnswers,
  unmetRequirements,
  unroutedAnswers,
  withFile,
  withGroup,
  type IntakeGroupState,
  type IntakeReviewState,
} from "../../core/intake-review.js";
import {
  materialRoleLabel,
  type MaterialRole,
} from "../../core/material-role-labels.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import { DisabledActionReason } from "./DisabledActionReason.js";
import { FilePickerRow } from "./FilePickerRow.js";
import {
  BusyNotice,
  Caption,
  Card,
  CardHeading,
  ErrorNotice,
  ProgressMeter,
  ScreenSkeleton,
  SectionHeading,
  StatusPill,
  StepProgress,
  primaryButtonClass,
  secondaryButtonClass,
} from "../ui/screen-ui.js";

type Step = IntakeStep;

/** 復元の表示。`none` は通常起動、`restored` は復元できた、`stale` は現物と不一致。 */
type RestoreNotice = "none" | "restored" | "stale";

const CLASSIFY_CONCURRENCY = 3;

/** グループ全件の取込状態。`some` がチェックの中間状態。 */
function groupIncludeState(group: IntakeGroupState): "all" | "some" | "none" {
  const total = group.files.length;
  if (total === 0) {
    return "none";
  }
  const included = includedFiles(group).length;
  if (included === 0) {
    return "none";
  }
  return included === total ? "all" : "some";
}

/** グループ全件をまとめて取り込む／外す。個別チェックはこの後で上書きできる。 */
function setGroupFilesIncluded(
  review: IntakeReviewState,
  key: string,
  included: boolean,
): IntakeReviewState {
  return withGroup(review, key, (group) =>
    copyIntakeGroup(group, {
      files: group.files.map((file) =>
        copyIntakeFile(file, { excluded: !included }),
      ),
    }),
  );
}

/** 復元前に、選んだフォルダを読み直してセッションと突き合わせる。読めなければ false。 */
async function folderMatchesSession(
  bridge: IntakeBridge,
  path: string,
  review: IntakeReviewState,
): Promise<boolean> {
  try {
    const folder = await bridge.scanFolder(path);
    return sessionMatchesScan(review, folder.entries);
  } catch {
    return false;
  }
}

const MATERIAL_ROLE_OPTIONS = [
  "student_answer",
  "grading_criteria",
  "annotation_resource",
  "annotation_sample",
  "reference",
  "ignore",
] as const;

interface RunningWork {
  readonly title: string;
  readonly detail: string;
}

export interface IntakePageProps {
  readonly bridge?: IntakeBridge;
}

export function IntakePage({ bridge }: IntakePageProps = {}): JSX.Element {
  const client = useSidecarClient();
  const { push } = useRouter();
  const fileBridge = bridge ?? intakeBridgeFromWindow();

  // 画面を離れると unmount して選択が消えるため、前回のセッションを読む
  // (Issue #384)。復元してよいかは loadSettings でフォルダを読み直して確かめる。
  const [initialSession] = useState(() => loadIntakeSession());

  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [step, setStep] = useState<Step>(initialSession?.step ?? "choose");
  const [busy, setBusy] = useState(false);
  const [busyNote, setBusyNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [templates, setTemplates] = useState<
    Awaited<ReturnType<typeof loadIntakeTemplates>>
  >([]);
  const [templateId, setTemplateId] = useState<string | null>(
    initialSession?.templateId ?? null,
  );
  const [unitCost, setUnitCost] = useState<number | null>(null);
  const [existingTests, setExistingTests] = useState<TestResponse[]>([]);
  const [availability, setAvailability] = useState<Awaited<
    ReturnType<typeof loadClassificationAvailability>
  > | null>(null);
  const [review, setReview] = useState<IntakeReviewState | null>(
    initialSession?.review ?? null,
  );
  const [narrowedTestIds, setNarrowedTestIds] = useState<Set<string>>(
    () => new Set(initialSession?.narrowedTestIds ?? []),
  );
  const [classifiedCount, setClassifiedCount] = useState(0);
  const [classificationTotal, setClassificationTotal] = useState(0);
  const [classifying, setClassifying] = useState(false);
  const [runningWork, setRunningWork] = useState<RunningWork | null>(null);
  const [cancelClassification, setCancelClassification] = useState(false);
  const [outcomes, setOutcomes] = useState<readonly ImportOutcome[]>(
    initialSession?.outcomes ?? [],
  );
  const [chosenFolderName, setChosenFolderName] = useState<string | null>(
    initialSession?.chosenFolderName ?? null,
  );
  const [chosenFolderPath, setChosenFolderPath] = useState<string | null>(
    initialSession?.chosenFolderPath ?? null,
  );
  const [restoreNotice, setRestoreNotice] = useState<RestoreNotice>("none");
  /** 取込成功などで「捨てた」あと、unmount 時に保存し直さないためのフラグ。 */
  const skipSaveRef = useRef(false);
  const restoreCheckedRef = useRef(false);
  const sessionSnapshotRef = useRef<IntakeSession | null>(null);
  sessionSnapshotRef.current = {
    step,
    templateId,
    chosenFolderName,
    chosenFolderPath,
    review,
    narrowedTestIds: [...narrowedTestIds],
    outcomes,
  };

  useEffect(
    () => () => {
      const snapshot = sessionSnapshotRef.current;
      if (
        !skipSaveRef.current &&
        snapshot !== null &&
        snapshot.review !== null
      ) {
        saveIntakeSession(snapshot);
      }
    },
    [],
  );

  const applyExistingTests = useCallback((tests: TestResponse[]) => {
    setExistingTests(tests);
    const known = new Set(tests.map((test) => test.id));
    setNarrowedTestIds((current) => {
      const next = new Set([...current].filter((id) => known.has(id)));
      return next;
    });
    setReview((current) =>
      current === null ? current : pruneStaleTargets(current, known),
    );
  }, []);

  /** いまの選択を捨てて最初からやり直す。復元の破棄もこれを使う。 */
  const startOver = useCallback(() => {
    skipSaveRef.current = false;
    resetIntakeSession();
    setStep("choose");
    setReview(null);
    setOutcomes([]);
    setError(null);
    setChosenFolderName(null);
    setChosenFolderPath(null);
    setNarrowedTestIds(new Set());
    setRestoreNotice("none");
  }, []);

  const loadSettings = useCallback(async () => {
    setLoadFailed(false);
    try {
      const [loadedTemplates, cost, tests, loadedAvailability] =
        await Promise.all([
          loadIntakeTemplates(client),
          loadIntakeCost(client),
          listTests(client),
          loadClassificationAvailability(client),
        ]);
      // 復元した選択が実ファイルと合っているかを一度だけ確かめる。合わなければ
      // 復元せず、理由を画面に出して選び直してもらう (Issue #384, 裁定 #5)。
      if (!restoreCheckedRef.current) {
        restoreCheckedRef.current = true;
        const restored = initialSession;
        if (restored?.review != null) {
          const usable =
            restored.chosenFolderPath !== null &&
            (await folderMatchesSession(
              fileBridge,
              restored.chosenFolderPath,
              restored.review,
            ));
          if (usable) {
            setRestoreNotice("restored");
          } else {
            skipSaveRef.current = false;
            resetIntakeSession();
            setStep("choose");
            setReview(null);
            setOutcomes([]);
            setChosenFolderName(null);
            setChosenFolderPath(null);
            setNarrowedTestIds(new Set());
            setRestoreNotice("stale");
          }
        }
      }
      applyExistingTests(tests);
      setTemplates(loadedTemplates);
      setTemplateId((current) =>
        loadedTemplates.some((template) => template.id === current)
          ? current
          : (loadedTemplates[0]?.id ?? null),
      );
      setUnitCost(cost);
      setAvailability(loadedAvailability);
      setReview((current) =>
        current === null ? current : { ...current, unitCost: cost },
      );
    } catch (loadError) {
      setLoadFailed(true);
      setError(
        loadError instanceof Error ? loadError.message : String(loadError),
      );
    } finally {
      setSettingsLoaded(true);
    }
  }, [applyExistingTests, client, fileBridge, initialSession]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  // 答案を振り分けられるのは `ready` のテストだけ。draft は登録の途中で、答案を
  // 上げても 409 になるため候補から外す (Issue #306)。
  const readyTests = useMemo(
    () => existingTests.filter((test) => targetTestAcceptsAnswers(test.status)),
    [existingTests],
  );

  const testStatusById = useMemo(
    () => new Map(existingTests.map((test) => [test.id, test.status])),
    [existingTests],
  );

  const candidates = useMemo(
    () => attributionCandidates(readyTests, narrowedTestIds),
    [readyTests, narrowedTestIds],
  );

  const reviewerChoseOne = reviewerChoseOneTest(
    narrowedTestIds,
    candidates.length,
  );

  const pickFolder = useCallback(async () => {
    if (templateId === null) {
      return;
    }
    setBusy(true);
    setBusyNote(
      "フォルダを読み、取込の型で振り分けを準備しています。ファイル数によって数秒かかります。",
    );
    setError(null);
    try {
      const path = await fileBridge.chooseFolder();
      if (path === null) {
        return;
      }
      // 別のフォルダを選び直したら、前の選択は捨てる (Issue #384, 裁定 #4)。
      skipSaveRef.current = false;
      resetIntakeSession();
      setRestoreNotice("none");
      setOutcomes([]);
      setNarrowedTestIds(new Set());
      const tests = await listTests(client);
      applyExistingTests(tests);
      const folder = await fileBridge.scanFolder(path);
      setChosenFolderName(folder.name);
      setChosenFolderPath(path);
      if (folder.entries.length === 0) {
        setError("このフォルダには取り込めるファイルがありません。");
        return;
      }
      const plan = await planIntake(client, {
        templateId,
        rootName: folder.name,
        entries: folder.entries,
      });
      setReview(
        buildReviewState({
          plan,
          folder,
          requiredRoles: requiredRolesOf(templates, templateId),
          unitCost,
          existingTests: tests,
        }),
      );
      setStep("review");
    } catch (pickError) {
      setError(
        pickError instanceof Error ? pickError.message : String(pickError),
      );
    } finally {
      setBusy(false);
      setBusyNote(null);
    }
  }, [applyExistingTests, client, fileBridge, templateId, templates, unitCost]);

  const runClassification = useCallback(
    async (cachedOnly = false) => {
      if (review === null) {
        return;
      }
      const pending = cachedOnly
        ? classifiableFiles(review).filter((file) => file.cachedClassification)
        : classifiableFiles(review);
      if (pending.length === 0) {
        return;
      }
      setClassifying(true);
      setRunningWork({
        title: "AIが資料の役割を判定しています",
        detail:
          "1件あたり数秒から十数秒かかります。結果は見つかった順に一覧へ反映されます。",
      });
      setClassificationTotal(pending.length);
      setCancelClassification(false);
      setClassifiedCount(0);
      setError(null);

      let nextIndex = 0;
      const worker = async (): Promise<void> => {
        while (true) {
          if (cancelClassification) {
            return;
          }
          const index = nextIndex;
          nextIndex += 1;
          if (index >= pending.length) {
            return;
          }
          const file = pending[index];
          if (file === undefined) {
            return;
          }
          try {
            const proposal = await classifyMaterial(
              fileBridge,
              file.absolutePath,
            );
            setClassifiedCount((count) => count + 1);
            setReview((current) =>
              current === null
                ? current
                : withFile(current, file.relativePath, (entry) =>
                    copyIntakeFile(entry, {
                      proposedRole: proposal.role ?? null,
                      classificationAttempted: true,
                    }),
                  ),
            );
          } catch {
            setClassifiedCount((count) => count + 1);
            setError("AIによる役割判定に失敗しました");
          }
        }
      };

      try {
        await Promise.all(
          Array.from({ length: CLASSIFY_CONCURRENCY }, () => worker()),
        );
      } finally {
        setClassifying(false);
        setRunningWork(null);
      }
    },
    [cancelClassification, fileBridge, review],
  );

  const attributeAnswers = useCallback(
    async (groupKey: string) => {
      if (review === null) {
        return;
      }
      const group = review.groups.find((entry) => entry.key === groupKey);
      if (group === undefined) {
        return;
      }
      if (reviewerChoseOne) {
        const chosen = candidates[0];
        if (chosen === undefined) {
          return;
        }
        setReview((current) => {
          if (current === null) {
            return current;
          }
          let next = current;
          for (const answer of unroutedAnswers(group)) {
            next = withFile(next, answer.relativePath, (file) =>
              copyIntakeFile(file, { answerTestId: chosen.id }),
            );
          }
          return next;
        });
        return;
      }

      const toAsk = unroutedAnswers(group).filter(
        (answer) => !answer.attributionAttempted,
      );
      if (toAsk.length === 0 || candidates.length < 2) {
        return;
      }

      setClassifying(true);
      setRunningWork({
        title: "AIが答案の取り込み先を判定しています",
        detail:
          "答案1件ずつ、どのテストのものかを照合します。十数秒かかることがあります。",
      });
      setClassificationTotal(toAsk.length);
      setCancelClassification(false);
      setClassifiedCount(0);
      setError(null);
      try {
        for (const answer of toAsk) {
          if (cancelClassification) {
            break;
          }
          try {
            const proposal = await attributeAnswer(fileBridge, {
              filePath: answer.absolutePath,
              candidates: candidates.map((test) => ({
                id: test.id,
                label: test.name,
              })),
            });
            setClassifiedCount((count) => count + 1);
            setReview((current) =>
              current === null
                ? current
                : withFile(current, answer.relativePath, (file) =>
                    copyIntakeFile(file, {
                      proposedAnswerTestId: proposal.test_id ?? null,
                      attributionAttempted: true,
                    }),
                  ),
            );
          } catch {
            setClassifiedCount((count) => count + 1);
            setError("AIによる答案振り分けに失敗しました");
          }
        }
      } finally {
        setClassifying(false);
        setRunningWork(null);
      }
    },
    [candidates, fileBridge, review, reviewerChoseOne],
  );

  const runImport = useCallback(async () => {
    if (review === null || !canImport(review)) {
      return;
    }
    setBusy(true);
    setBusyNote(
      "取り込んでいます。ファイルのコピーと、答案の登録・採点の開始を進めています。",
    );
    setError(null);
    const imported: ImportOutcome[] = [];
    try {
      for (const group of review.groups) {
        if (includedFiles(group).length === 0) {
          continue;
        }
        const partial = await importReview(
          { bridge: fileBridge, client, testStatusById },
          {
            ...review,
            groups: [group],
          },
        );
        imported.push(...partial);
        setOutcomes([...imported]);
      }
      setOutcomes(imported);
      setStep("done");
      // 最後まで成功したら保持を捨てる。失敗した分は残して再試行できるようにする
      // (Issue #384, 裁定 #4)。
      if (
        imported.length > 0 &&
        imported.every((outcome) => outcome.error === null)
      ) {
        skipSaveRef.current = true;
        resetIntakeSession();
      }
    } finally {
      setBusy(false);
      setBusyNote(null);
    }
  }, [client, fileBridge, review, testStatusById]);

  const folderPickRequirements = intakeFolderPickRequirements({
    busy,
    templateChosen: templateId !== null,
  });

  const reviewState = review;
  const billable =
    reviewState === null ? 0 : pendingClassification(reviewState).length;
  const classifiable =
    reviewState === null ? 0 : classifiableFiles(reviewState).length;
  const cachedOnly = classifiable - billable;
  const attributionCalls =
    candidates.length >= 2 && reviewState !== null
      ? reviewState.groups
          .filter((group) => group.targetKind === IntakeTargetKind.perAnswer)
          .flatMap((group) =>
            unroutedAnswers(group).filter(
              (answer) => !answer.attributionAttempted,
            ),
          ).length
      : 0;
  const totalCalls = billable + attributionCalls;
  const estimatedCost =
    reviewState === null || reviewState.unitCost === null
      ? null
      : reviewState.unitCost * totalCalls;

  const includedTotal =
    reviewState === null
      ? 0
      : reviewState.groups.reduce(
          (sum, group) => sum + includedFiles(group).length,
          0,
        );
  const confirmableCount =
    reviewState === null ? 0 : confirmableProposals(reviewState).length;
  const blockingRequirements =
    reviewState === null ? [] : importRequirements(reviewState);
  const readyToImport = blockingRequirements.length === 0;

  const failedOutcomeCount = outcomes.filter(
    (outcome) => outcome.error !== null,
  ).length;
  const deferredAnswerCount = outcomes.reduce(
    (sum, outcome) => sum + outcome.answersDeferred,
    0,
  );
  const importedSubmissionCount = outcomes.reduce(
    (sum, outcome) => sum + outcome.submissionCount,
    0,
  );
  const importedMaterialCount = outcomes.reduce(
    (sum, outcome) => sum + outcome.materialCount,
    0,
  );
  const doneHeading =
    failedOutcomeCount === 0
      ? "取込が完了しました"
      : "取込に失敗した項目があります";

  const importReqs = intakeImportRequirements({
    busy,
    classifying,
    folderRequirements: blockingRequirements,
  });

  const steps = [
    { id: "choose", label: "フォルダを選ぶ", complete: step !== "choose" },
    { id: "review", label: "振り分けを確認", complete: step === "done" },
    { id: "done", label: "取り込む", complete: step === "done" },
  ] as const;

  return (
    <ShellScreen title="資料の取込">
      <div className="flex flex-col gap-xl">
        <StepProgress testId="intake-steps" steps={steps} currentId={step} />

        {!settingsLoaded ? (
          <ScreenSkeleton testId="intake-loading" cardCount={2} />
        ) : null}

        {settingsLoaded && error !== null && step === "choose" ? (
          <ErrorNotice
            testId="intake-error"
            action={
              loadFailed ? (
                <button
                  type="button"
                  className={secondaryButtonClass()}
                  onClick={() => {
                    void loadSettings();
                  }}
                >
                  読み込みを再試行
                </button>
              ) : undefined
            }
          >
            {error}
          </ErrorNotice>
        ) : null}

        {busyNote !== null ? (
          <BusyNotice
            testId="intake-busy"
            title="処理しています"
            detail={busyNote}
          />
        ) : null}

        {runningWork !== null ? (
          <Card testId="intake-running" className="bg-surface-container-high">
            <BusyNotice
              testId="intake-running-notice"
              title={runningWork.title}
              detail={runningWork.detail}
            />
            {classificationTotal > 0 ? (
              <div className="mt-md">
                <ProgressMeter
                  testId="intake-running-progress"
                  label="処理したファイル"
                  value={classifiedCount}
                  max={classificationTotal}
                />
              </div>
            ) : null}
          </Card>
        ) : null}

        {settingsLoaded && restoreNotice === "restored" ? (
          <Card
            testId="intake-restore-notice"
            className="bg-surface-container-high"
          >
            <p className="text-body-medium text-on-surface">
              前回の選択を復元しました。フォルダ・ファイルの役割・取込先はそのまま続けられます。
            </p>
            <button
              type="button"
              data-testid="intake-restore-discard"
              className={`mt-md ${secondaryButtonClass()}`}
              onClick={startOver}
            >
              やり直す
            </button>
          </Card>
        ) : null}

        {settingsLoaded && restoreNotice === "stale" ? (
          <Card
            testId="intake-restore-stale"
            className="bg-surface-container-high"
          >
            <p className="text-body-medium text-attention">
              前回選んだフォルダの中身が変わっていたため、前回の選択は復元できませんでした。もう一度フォルダを選んでください。
            </p>
          </Card>
        ) : null}

        {settingsLoaded && step === "choose" ? (
          <div className="flex flex-col gap-lg">
            <Card testId="intake-choose-card">
              <CardHeading
                title="取込の型"
                description="塾から受け取ったフォルダをそのまま選んでください。中身の役割は取込の型で自動的に振り分け、取り込む前に一覧で確認できます。"
              />
              <label className="mt-lg flex flex-col gap-xs">
                <span className="text-ui-label">取込の型</span>
                <select
                  data-testid="intake-template-picker"
                  className="select-themed rounded-md bg-surface-container-high px-md py-sm text-on-surface"
                  value={templateId ?? ""}
                  disabled={busy}
                  onChange={(event) => {
                    setTemplateId(event.target.value);
                  }}
                >
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
              {availability?.available === false ? (
                <p className="mt-md rounded-lg bg-surface-container-high p-md text-body-medium text-on-surface-variant">
                  この端末ではAIによる自動判定を使えません。取込の型で振り分けられなかったファイルは、一覧で役割を選んでください。
                  {availability.reason !== null &&
                  availability.reason !== undefined
                    ? `\n理由: ${availability.reason}`
                    : ""}
                </p>
              ) : null}
            </Card>

            <Card testId="intake-folder-card">
              <CardHeading
                title="フォルダを選ぶ"
                description="取り込むフォルダを1つ選んでください。選んだあと、ファイルごとの振り分けを確認できます。"
              />
              <div className="mt-lg">
                <FilePickerRow
                  buttonTestId="intake-choose-folder"
                  buttonLabel="フォルダを選ぶ"
                  fileName={chosenFolderName}
                  onPressed={
                    folderPickRequirements.length === 0 ? pickFolder : null
                  }
                />
              </div>
              <DisabledActionReason requirements={folderPickRequirements} />
            </Card>
          </div>
        ) : null}

        {settingsLoaded && step === "review" && reviewState !== null ? (
          <div className="flex flex-col gap-lg">
            <Card testId="intake-review-summary">
              <CardHeading
                title="振り分けの確認"
                description="AIの提案を確認し、各フォルダの取り込み先を決めてください。"
                aside={
                  <StatusPill tone={readyToImport ? "success" : "attention"}>
                    {readyToImport ? "取り込めます" : "要確認"}
                  </StatusPill>
                }
              />
              <dl className="mt-lg grid gap-md sm:grid-cols-3">
                <SummaryStat
                  label="取込対象ファイル"
                  value={`${includedTotal}件`}
                  testId="intake-summary-files"
                />
                <SummaryStat
                  label="確認待ちの提案"
                  value={`${confirmableCount}件`}
                  testId="intake-summary-proposals"
                />
                <SummaryStat
                  label="取り込みを止めている項目"
                  value={`${blockingRequirements.length}件`}
                  testId="intake-summary-blocking"
                />
              </dl>
            </Card>

            <Card testId="intake-call-estimate">
              <p className="text-recognized font-medium leading-ui text-on-surface">
                AIに問い合わせる件数: 合計{totalCalls}件
              </p>
              <p
                data-testid="intake-call-breakdown"
                className="mt-sm text-body-medium text-on-surface-variant"
              >
                内訳: 役割の判定 {billable}件 / 答案の振り分け{" "}
                {attributionCalls}件
              </p>
              <p
                data-testid="intake-cost-estimate"
                className="mt-xs text-body-medium text-on-surface-variant"
              >
                {estimatedCost === null || reviewState.unitCost === null
                  ? "概算費用: 1件あたりの単価が未設定です（設定画面で入力できます）"
                  : `概算費用: 約${estimatedCost.toFixed(2)}（1件あたり${reviewState.unitCost.toFixed(2)}）`}
              </p>
            </Card>

            {readyTests.length > 0 ? (
              <Card testId="intake-narrowing">
                <CardHeading title="このフォルダの答案は、どのテストのものですか" />
                <p
                  data-testid="intake-narrowing-benefit"
                  className="mt-xs text-body-medium text-on-surface-variant"
                >
                  テストを1つ選ぶと、AIに問い合わせずにそのテストへ振り分けます。答案のページを送らず、費用もかかりません。選ばない場合は、AIが答案1枚ごとにどのテストのものかを判定します（1枚につき1回、費用がかかります）。
                </p>
                <div className="mt-md flex flex-wrap gap-sm">
                  {readyTests.map((test) => {
                    const selected = narrowedTestIds.has(test.id);
                    return (
                      <button
                        key={test.id}
                        type="button"
                        data-testid={`intake-narrow-${test.id}`}
                        aria-pressed={selected}
                        className={
                          selected
                            ? primaryButtonClass()
                            : secondaryButtonClass()
                        }
                        onClick={() => {
                          setNarrowedTestIds((current) => {
                            const next = new Set(current);
                            if (next.has(test.id)) {
                              next.delete(test.id);
                            } else {
                              next.add(test.id);
                            }
                            setReview((reviewCurrent) =>
                              reviewCurrent === null
                                ? reviewCurrent
                                : dropRoutingOutsideCandidates(
                                    reviewCurrent,
                                    new Set(
                                      attributionCandidates(
                                        readyTests,
                                        next,
                                      ).map((entry) => entry.id),
                                    ),
                                  ),
                            );
                            return next;
                          });
                        }}
                      >
                        {test.name}
                      </button>
                    );
                  })}
                </div>
              </Card>
            ) : null}

            <SectionHeading
              title="フォルダごとの振り分け"
              count={reviewState.groups.length}
            />

            {reviewState.groups.map((group) => {
              const missing = unmetRequirements(group);
              const files = group.files;
              const includeState = groupIncludeState(group);
              return (
                <Card key={group.key} testId={`intake-group-${group.key}`}>
                  <CardHeading
                    title={
                      group.name.length > 0 ? group.name : "（名前未設定）"
                    }
                    description={`${includedFiles(group).length}件のファイル`}
                    aside={
                      <StatusPill
                        tone={missing.length > 0 ? "attention" : "neutral"}
                      >
                        {missing.length > 0 ? "要確認" : group.key}
                      </StatusPill>
                    }
                  />
                  <div className="mt-lg flex flex-col gap-sm">
                    <select
                      data-testid={`intake-target-${group.key}`}
                      aria-label="このフォルダの取り込み先"
                      className="select-themed rounded-md bg-surface-container-high px-md py-sm text-on-surface"
                      value={
                        group.targetKind === IntakeTargetKind.create
                          ? "__new__"
                          : group.targetKind === IntakeTargetKind.perAnswer
                            ? "__per_answer__"
                            : (group.targetTestId ?? "")
                      }
                      disabled={busy}
                      onChange={(event) => {
                        const value = event.target.value;
                        setReview((current) =>
                          current === null
                            ? current
                            : withGroup(current, group.key, (entry) => {
                                if (value === "__new__") {
                                  return copyIntakeGroup(entry, {
                                    targetKind: IntakeTargetKind.create,
                                    targetTestId: null,
                                    targetTestStatus: null,
                                  });
                                }
                                if (value === "__per_answer__") {
                                  return copyIntakeGroup(entry, {
                                    targetKind: IntakeTargetKind.perAnswer,
                                    targetTestId: null,
                                    targetTestStatus: null,
                                  });
                                }
                                const chosen = existingTests.find(
                                  (test) => test.id === value,
                                );
                                return copyIntakeGroup(entry, {
                                  targetKind: IntakeTargetKind.existing,
                                  targetTestId: value,
                                  targetTestStatus: chosen?.status ?? null,
                                });
                              }),
                        );
                      }}
                    >
                      <option value="__new__">
                        新しいテストとして登録する
                      </option>
                      {readyTests.length > 0 ? (
                        <option value="__per_answer__">
                          答案ごとに登録済みのテストへ振り分ける
                        </option>
                      ) : null}
                      {existingTests.map((test) => (
                        <option key={test.id} value={test.id}>
                          登録済み: {test.name}
                          {targetTestAcceptsAnswers(test.status)
                            ? ""
                            : "（登録途中）"}
                        </option>
                      ))}
                    </select>
                    {group.targetKind === IntakeTargetKind.create ? (
                      <label className="flex flex-col gap-xs">
                        <span className="text-ui-label">テスト名</span>
                        <input
                          data-testid={`intake-name-${group.key}`}
                          className="rounded-md bg-surface-container-high px-md py-sm text-on-surface"
                          value={group.name}
                          onChange={(event) => {
                            setReview((current) =>
                              current === null
                                ? current
                                : withGroup(current, group.key, (entry) =>
                                    copyIntakeGroup(entry, {
                                      name: event.target.value,
                                    }),
                                  ),
                            );
                          }}
                        />
                      </label>
                    ) : null}
                    {missing.length > 0 ? (
                      <p
                        data-testid={`intake-unmet-${group.key}`}
                        className="text-body-medium text-attention"
                      >
                        不足: {missing.map(materialRoleLabel).join("、")}
                      </p>
                    ) : null}
                    {group.targetKind !== IntakeTargetKind.unassigned &&
                    group.targetKind !== IntakeTargetKind.perAnswer &&
                    !targetTestAcceptsAnswers(group.targetTestStatus) ? (
                      <p
                        data-testid={`intake-stage-notice-${group.key}`}
                        className="text-body-medium text-on-surface-variant"
                      >
                        {
                          ActionRequirements.answersDeferredUntilRegistered
                            .message
                        }
                      </p>
                    ) : null}
                  </div>
                  <div className="mt-md flex flex-wrap items-center justify-between gap-sm">
                    <label className="flex items-center gap-sm">
                      <input
                        type="checkbox"
                        data-testid={`intake-group-include-${group.key}`}
                        aria-label={`${group.name.length > 0 ? group.name : "（名前未設定）"} のファイルをすべて取り込む`}
                        checked={includeState === "all"}
                        ref={(element) => {
                          if (element !== null) {
                            element.indeterminate = includeState === "some";
                          }
                        }}
                        onChange={(event) => {
                          const included = event.target.checked;
                          setReview((current) =>
                            current === null
                              ? current
                              : setGroupFilesIncluded(
                                  current,
                                  group.key,
                                  included,
                                ),
                          );
                        }}
                      />
                      <span className="text-ui-label">
                        {includeState === "all"
                          ? "すべて外す"
                          : "すべて取り込む"}
                      </span>
                    </label>
                    <span
                      data-testid={`intake-group-include-summary-${group.key}`}
                      className="text-body-medium text-on-surface-variant"
                    >
                      {includedFiles(group).length}/{group.files.length}
                      件を取り込み
                    </span>
                  </div>
                  <ul className="mt-md flex flex-col gap-sm">
                    {files.map((file) => (
                      <li
                        key={file.relativePath}
                        className="flex flex-wrap items-center gap-sm rounded-lg bg-surface-container-high px-md py-sm"
                      >
                        <input
                          type="checkbox"
                          data-testid={`intake-include-${file.relativePath}`}
                          aria-label={`${intakeFileName(file)} を取り込む`}
                          checked={!file.excluded}
                          onChange={(event) => {
                            setReview((current) =>
                              current === null
                                ? current
                                : withFile(
                                    current,
                                    file.relativePath,
                                    (entry) =>
                                      copyIntakeFile(entry, {
                                        excluded: !event.target.checked,
                                      }),
                                  ),
                            );
                          }}
                        />
                        <span className="min-w-0 flex-1 truncate text-body-medium">
                          {intakeFileName(file)}
                        </span>
                        <select
                          data-testid={`intake-role-${file.relativePath}`}
                          aria-label={`${intakeFileName(file)} の役割`}
                          className="select-themed rounded-md bg-surface-container px-sm py-xs text-ui-label"
                          value={effectiveRole(file) ?? ""}
                          onChange={(event) => {
                            const value = event.target.value as MaterialRole;
                            setReview((current) =>
                              current === null
                                ? current
                                : withFile(
                                    current,
                                    file.relativePath,
                                    (entry) =>
                                      copyIntakeFile(entry, {
                                        humanRole: value,
                                        proposalConfirmed: true,
                                      }),
                                  ),
                            );
                          }}
                        >
                          <option value="">未判定</option>
                          {MATERIAL_ROLE_OPTIONS.map((role) => (
                            <option key={role} value={role}>
                              {materialRoleLabel(role)}
                            </option>
                          ))}
                        </select>
                        {file.proposedRole !== null &&
                        !file.proposalConfirmed ? (
                          <button
                            type="button"
                            data-testid={`intake-confirm-${file.relativePath}`}
                            className={secondaryButtonClass()}
                            onClick={() => {
                              setReview((current) =>
                                current === null
                                  ? current
                                  : withFile(
                                      current,
                                      file.relativePath,
                                      (entry) =>
                                        copyIntakeFile(entry, {
                                          proposalConfirmed: true,
                                        }),
                                    ),
                              );
                            }}
                          >
                            この役割でよい
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  {group.targetKind === IntakeTargetKind.perAnswer ? (
                    <button
                      type="button"
                      data-testid={`intake-attribute-${group.key}`}
                      className={`mt-md ${secondaryButtonClass()}`}
                      onClick={() => {
                        void attributeAnswers(group.key);
                      }}
                    >
                      {reviewerChoseOne
                        ? "すべての答案を振り分ける"
                        : "AIで振り分ける"}
                    </button>
                  ) : null}
                </Card>
              );
            })}

            <Card testId="intake-actions" className="bg-surface-container-high">
              <CardHeading
                title="取り込み"
                description="内容を確認したら取り込みます。あとから同じフォルダを取り込むこともできます。"
                aside={
                  <StatusPill tone={readyToImport ? "success" : "attention"}>
                    {readyToImport ? "準備完了" : "未解決あり"}
                  </StatusPill>
                }
              />
              <div className="mt-lg flex flex-wrap gap-md">
                {cachedOnly > 0 ? (
                  <button
                    type="button"
                    data-testid="intake-fetch-cached"
                    className={secondaryButtonClass()}
                    onClick={() => {
                      void runClassification(true);
                    }}
                  >
                    前回の判定を取得する ({cachedOnly}件・無料)
                  </button>
                ) : null}
                {billable > 0 && availability?.available !== false ? (
                  <button
                    type="button"
                    data-testid="intake-run-classification"
                    className={secondaryButtonClass()}
                    onClick={() => {
                      void runClassification(false);
                    }}
                  >
                    AIで判定する ({billable}件)
                  </button>
                ) : null}
                <button
                  type="button"
                  data-testid="intake-import"
                  className={primaryButtonClass()}
                  disabled={importReqs.length > 0}
                  onClick={() => {
                    void runImport();
                  }}
                >
                  この内容で取り込む
                </button>
              </div>
              <DisabledActionReason requirements={importReqs} />

              {reviewState !== null &&
              confirmableProposals(reviewState).length > 0 ? (
                <button
                  type="button"
                  data-testid="intake-confirm-all"
                  className={`mt-md ${secondaryButtonClass()}`}
                  onClick={() => {
                    setReview((current) =>
                      current === null ? current : confirmAllProposals(current),
                    );
                  }}
                >
                  AIの提案 {confirmableProposals(reviewState).length}
                  件をまとめて確認済みにする
                </button>
              ) : null}
            </Card>
          </div>
        ) : null}

        {settingsLoaded && step === "done" ? (
          <div className="flex flex-col gap-lg">
            <Card testId="intake-done-summary">
              <CardHeading
                title={doneHeading}
                titleTestId="intake-done-heading"
                aside={
                  <StatusPill
                    tone={failedOutcomeCount === 0 ? "success" : "attention"}
                  >
                    {failedOutcomeCount === 0 ? "完了" : "一部失敗"}
                  </StatusPill>
                }
              />
              {failedOutcomeCount > 0 ? (
                <p
                  data-testid="intake-failure-summary"
                  className="mt-sm text-body-medium text-attention"
                >
                  {failedOutcomeCount}件のグループで取り込みに失敗しました（全
                  {outcomes.length}件中）。内容は下の一覧で確認できます。
                </p>
              ) : null}
              {deferredAnswerCount > 0 ? (
                <p
                  data-testid="intake-next-step-notice"
                  className="mt-sm text-body-medium text-on-surface-variant"
                >
                  採点にはこのあと配点と採点基準の確定が必要です。下のテストごとの「テスト設定を開く」から入力・確定してください。
                  {ActionRequirements.answersDeferredUntilRegistered.message}
                  登録が済んだら、同じフォルダをもう一度取り込むと答案が入ります。
                </p>
              ) : importedSubmissionCount > 0 ? (
                <p
                  data-testid="intake-next-step-notice"
                  className="mt-sm text-body-medium text-on-surface-variant"
                >
                  答案を取り込みました。AI採点の開始状況は下の一覧で確認できます。
                </p>
              ) : null}
              <dl className="mt-lg grid gap-md sm:grid-cols-3">
                <SummaryStat
                  label="資料"
                  value={`${importedMaterialCount}件`}
                  testId="intake-done-materials"
                />
                <SummaryStat
                  label="答案"
                  value={`${importedSubmissionCount}件`}
                  testId="intake-done-submissions"
                />
                <SummaryStat
                  label="配点確定待ち"
                  value={`${deferredAnswerCount}件`}
                  testId="intake-done-deferred"
                />
              </dl>
            </Card>

            <h2 className="sr-only">取り込み結果</h2>
            {outcomes.map((outcome) => {
              const hadFailure = outcome.error !== null;
              return (
                <Card
                  key={outcome.groupKey}
                  testId={`intake-outcome-${outcome.groupKey}`}
                >
                  <CardHeading
                    title={outcome.name}
                    aside={
                      <StatusPill tone={hadFailure ? "attention" : "success"}>
                        {hadFailure ? "一部失敗" : "完了"}
                      </StatusPill>
                    }
                  />
                  <ul className="mt-sm flex flex-col gap-xs text-body-medium">
                    {outcome.materialCount > 0 ? (
                      <li
                        data-testid={`intake-imported-materials-${outcome.groupKey}`}
                      >
                        資料 {outcome.materialCount}件を取り込みました
                      </li>
                    ) : null}
                    {outcome.submissionCount > 0 ? (
                      <li
                        data-testid={`intake-imported-submissions-${outcome.groupKey}`}
                      >
                        答案 {outcome.submissionCount}件を取り込みました
                      </li>
                    ) : null}
                    {outcome.duplicateCount > 0 ? (
                      <li data-testid={`intake-duplicate-${outcome.groupKey}`}>
                        {ActionRequirements.submissionDuplicate.message}（
                        {outcome.duplicateCount}件）
                      </li>
                    ) : null}
                    {outcome.answersDeferred > 0 ? (
                      <li
                        data-testid={`intake-deferred-${outcome.groupKey}`}
                        className="text-on-surface-variant"
                      >
                        {
                          ActionRequirements.answersDeferredUntilRegistered
                            .message
                        }
                        （{outcome.answersDeferred}件）
                      </li>
                    ) : null}
                    {outcome.gradingStartedCount > 0 ? (
                      <li>
                        うち{outcome.gradingStartedCount}
                        件のAI採点を開始しました
                      </li>
                    ) : null}
                    {outcome.gradingFailure !== null ? (
                      <li className="text-attention">
                        {outcome.gradingFailure}
                      </li>
                    ) : null}
                  </ul>

                  {outcome.error !== null ? (
                    <ErrorNotice testId={`intake-failed-${outcome.groupKey}`}>
                      {importedAnything(outcome)
                        ? `一部を取り込めませんでした: ${outcome.error}`
                        : `取り込めませんでした: ${outcome.error}`}
                      {outcome.failedFiles.length > 0 ? (
                        <>
                          <span className="mt-xs block font-medium">
                            失敗したファイル（{outcome.failedFiles.length}件）
                          </span>
                          <ul
                            data-testid={`intake-failed-files-${outcome.groupKey}`}
                            className="mt-xs flex flex-col gap-xs"
                          >
                            {outcome.failedFiles.map((name) => (
                              <li key={name} className="truncate">
                                {name}
                              </li>
                            ))}
                          </ul>
                        </>
                      ) : null}
                    </ErrorNotice>
                  ) : null}

                  {outcome.testId !== null ? (
                    <button
                      type="button"
                      data-testid={`intake-open-test-settings-${outcome.groupKey}`}
                      className={`mt-md ${secondaryButtonClass()}`}
                      onClick={() => {
                        push(testSettings(outcome.testId!));
                      }}
                    >
                      テスト設定を開く
                    </button>
                  ) : null}
                </Card>
              );
            })}

            <div>
              <button
                type="button"
                data-testid="intake-start-over"
                className={secondaryButtonClass()}
                onClick={startOver}
              >
                別のフォルダを取り込む
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </ShellScreen>
  );
}

function SummaryStat({
  label,
  value,
  testId,
}: {
  label: string;
  value: string;
  testId: string;
}): JSX.Element {
  return (
    <div className="rounded-lg bg-surface-container-high p-md">
      <dt>
        <Caption>{label}</Caption>
      </dt>
      <dd
        data-testid={testId}
        className="mt-xs tabular-nums text-title-large font-medium text-on-surface"
      >
        {value}
      </dd>
    </div>
  );
}
