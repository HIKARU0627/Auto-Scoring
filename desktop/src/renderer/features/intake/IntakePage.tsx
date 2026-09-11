import { useCallback, useEffect, useMemo, useState, type JSX } from "react";

import {
  attributeAnswer,
  classifyMaterial,
  importReview,
  intakeBridgeFromWindow,
  loadClassificationAvailability,
  loadIntakeCost,
  loadIntakeTemplates,
  listTests,
  planIntake,
  type ImportOutcome,
  type IntakeBridge,
  type TestSummary,
  importedAnything,
} from "../../core/intake-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
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
  unmetRequirements,
  unroutedAnswers,
  withFile,
  withGroup,
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

type Step = "choose" | "review" | "done";

const CLASSIFY_CONCURRENCY = 3;

export interface IntakePageProps {
  readonly bridge?: IntakeBridge;
}

export function IntakePage({ bridge }: IntakePageProps = {}): JSX.Element {
  const client = useSidecarClient();
  const { push } = useRouter();
  const fileBridge = bridge ?? intakeBridgeFromWindow();

  const [step, setStep] = useState<Step>("choose");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<
    Awaited<ReturnType<typeof loadIntakeTemplates>>
  >([]);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [unitCost, setUnitCost] = useState<number | null>(null);
  const [existingTests, setExistingTests] = useState<TestSummary[]>([]);
  const [availability, setAvailability] = useState<Awaited<
    ReturnType<typeof loadClassificationAvailability>
  > | null>(null);
  const [review, setReview] = useState<IntakeReviewState | null>(null);
  const [narrowedTestIds, setNarrowedTestIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [, setClassifiedCount] = useState(0);
  const [classifying, setClassifying] = useState(false);
  const [cancelClassification, setCancelClassification] = useState(false);
  const [outcomes, setOutcomes] = useState<readonly ImportOutcome[]>([]);
  const [chosenFolderName, setChosenFolderName] = useState<string | null>(null);

  const applyExistingTests = useCallback((tests: TestSummary[]) => {
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

  const loadSettings = useCallback(async () => {
    try {
      const [loadedTemplates, cost, tests, loadedAvailability] =
        await Promise.all([
          loadIntakeTemplates(client),
          loadIntakeCost(client),
          listTests(client),
          loadClassificationAvailability(client),
        ]);
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
      setError(
        loadError instanceof Error ? loadError.message : String(loadError),
      );
    }
  }, [applyExistingTests, client]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const candidates = useMemo(
    () => attributionCandidates(existingTests, narrowedTestIds),
    [existingTests, narrowedTestIds],
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
    setError(null);
    try {
      const path = await fileBridge.chooseFolder();
      if (path === null) {
        return;
      }
      const tests = await listTests(client);
      applyExistingTests(tests);
      const folder = await fileBridge.scanFolder(path);
      setChosenFolderName(folder.name);
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
        }),
      );
      setStep("review");
    } catch (pickError) {
      setError(
        pickError instanceof Error ? pickError.message : String(pickError),
      );
    } finally {
      setBusy(false);
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
      }
    },
    [candidates, fileBridge, review, reviewerChoseOne],
  );

  const runImport = useCallback(async () => {
    if (review === null || !canImport(review)) {
      return;
    }
    setBusy(true);
    setError(null);
    const imported: ImportOutcome[] = [];
    try {
      for (const group of review.groups) {
        if (includedFiles(group).length === 0) {
          continue;
        }
        const partial = await importReview(
          { bridge: fileBridge, client },
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
    } finally {
      setBusy(false);
    }
  }, [client, fileBridge, review]);

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

  const failedOutcomeCount = outcomes.filter(
    (outcome) => outcome.error !== null,
  ).length;
  const doneHeading =
    failedOutcomeCount === 0
      ? "取込が完了しました"
      : "取込に失敗した項目があります";

  return (
    <ShellScreen title="資料の取込">
      {step === "choose" ? (
        <div className="mx-auto flex max-w-180 flex-col gap-lg">
          <p className="text-body-medium text-on-surface-variant">
            塾から受け取ったフォルダをそのまま選んでください。中身の役割は取込の型で自動的に振り分け、取り込む前に一覧で確認できます。
          </p>
          <label className="flex flex-col gap-xs">
            <span className="text-ui-label">取込の型</span>
            <select
              data-testid="intake-template-picker"
              className="rounded-md border border-outline bg-surface px-md py-sm"
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
            <p className="rounded-md border border-outline-variant bg-surface-container-low p-md text-body-medium">
              この端末ではAIによる自動判定を使えません。取込の型で振り分けられなかったファイルは、一覧で役割を選んでください。
              {availability.reason !== null && availability.reason !== undefined
                ? `\n理由: ${availability.reason}`
                : ""}
            </p>
          ) : null}
          <FilePickerRow
            buttonTestId="intake-choose-folder"
            buttonLabel="フォルダを選ぶ"
            fileName={chosenFolderName}
            onPressed={folderPickRequirements.length === 0 ? pickFolder : null}
          />
          <DisabledActionReason requirements={folderPickRequirements} />
          {error !== null ? (
            <p className="text-body-medium text-error">{error}</p>
          ) : null}
        </div>
      ) : null}

      {step === "review" && reviewState !== null ? (
        <div className="flex flex-col gap-md">
          <section
            data-testid="intake-call-estimate"
            className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
          >
            <p className="text-title-medium font-medium">
              AIに問い合わせる件数: 合計{totalCalls}件
            </p>
            <p
              data-testid="intake-call-breakdown"
              className="mt-xs text-body-medium"
            >
              内訳: 役割の判定 {billable}件 / 答案の振り分け {attributionCalls}
              件
            </p>
            <p
              data-testid="intake-cost-estimate"
              className="mt-xs text-body-medium"
            >
              {estimatedCost === null || reviewState.unitCost === null
                ? "概算費用: 1件あたりの単価が未設定です（設定画面で入力できます）"
                : `概算費用: 約${estimatedCost.toFixed(2)}（1件あたり${reviewState.unitCost.toFixed(2)}）`}
            </p>
          </section>

          {existingTests.length > 0 ? (
            <section>
              <p className="text-body-medium font-medium">
                このバッチはどのテストの答案ですか
              </p>
              <p
                data-testid="intake-narrowing-benefit"
                className="text-body-medium text-on-surface-variant"
              >
                1件だけ選ぶと、AIに問い合わせません。費用が0件になり、答案のページ全体も送りません。
              </p>
              <div className="mt-sm flex flex-wrap gap-sm">
                {existingTests.map((test) => (
                  <button
                    key={test.id}
                    type="button"
                    data-testid={`intake-narrow-${test.id}`}
                    className={`rounded-md border px-md py-xs text-ui-label ${
                      narrowedTestIds.has(test.id)
                        ? "border-primary bg-primary-container"
                        : "border-outline"
                    }`}
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
                                    existingTests,
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
                ))}
              </div>
            </section>
          ) : null}

          {reviewState.groups.map((group) => {
            const missing = unmetRequirements(group);
            return (
              <section
                key={group.key}
                data-testid={`intake-group-${group.key}`}
                className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
              >
                <div className="flex flex-col gap-sm">
                  <select
                    data-testid={`intake-target-${group.key}`}
                    className="rounded-md border border-outline bg-surface px-md py-sm"
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
                                });
                              }
                              if (value === "__per_answer__") {
                                return copyIntakeGroup(entry, {
                                  targetKind: IntakeTargetKind.perAnswer,
                                  targetTestId: null,
                                });
                              }
                              return copyIntakeGroup(entry, {
                                targetKind: IntakeTargetKind.existing,
                                targetTestId: value,
                              });
                            }),
                      );
                    }}
                  >
                    <option value="__new__">新しいテストとして登録する</option>
                    {existingTests.length > 0 ? (
                      <option value="__per_answer__">
                        答案ごとに登録済みのテストへ振り分ける
                      </option>
                    ) : null}
                    {existingTests.map((test) => (
                      <option key={test.id} value={test.id}>
                        登録済み: {test.name}
                      </option>
                    ))}
                  </select>
                  {group.targetKind === IntakeTargetKind.create ? (
                    <input
                      data-testid={`intake-name-${group.key}`}
                      className="rounded-md border border-outline bg-surface px-md py-sm"
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
                  ) : null}
                  {missing.length > 0 ? (
                    <p
                      data-testid={`intake-unmet-${group.key}`}
                      className="text-body-medium text-error"
                    >
                      不足: {missing.map(materialRoleLabel).join("、")}
                    </p>
                  ) : null}
                </div>
                <div className="mt-md flex flex-col gap-sm">
                  {group.files.map((file) => (
                    <div
                      key={file.relativePath}
                      className="flex flex-wrap items-center gap-sm"
                    >
                      <input
                        type="checkbox"
                        data-testid={`intake-include-${file.relativePath}`}
                        checked={!file.excluded}
                        onChange={(event) => {
                          setReview((current) =>
                            current === null
                              ? current
                              : withFile(current, file.relativePath, (entry) =>
                                  copyIntakeFile(entry, {
                                    excluded: !event.target.checked,
                                  }),
                                ),
                          );
                        }}
                      />
                      <span className="min-w-0 flex-1 truncate">
                        {intakeFileName(file)}
                      </span>
                      <select
                        data-testid={`intake-role-${file.relativePath}`}
                        className="rounded-md border border-outline bg-surface px-sm py-xs"
                        value={effectiveRole(file) ?? ""}
                        onChange={(event) => {
                          const value = event.target.value as MaterialRole;
                          setReview((current) =>
                            current === null
                              ? current
                              : withFile(current, file.relativePath, (entry) =>
                                  copyIntakeFile(entry, {
                                    humanRole: value,
                                    proposalConfirmed: true,
                                  }),
                                ),
                          );
                        }}
                      >
                        <option value="">未判定</option>
                        {(
                          [
                            "student_answer",
                            "grading_criteria",
                            "annotation_resource",
                            "annotation_sample",
                            "reference",
                            "ignore",
                          ] as const
                        ).map((role) => (
                          <option key={role} value={role}>
                            {materialRoleLabel(role)}
                          </option>
                        ))}
                      </select>
                      {file.proposedRole !== null && !file.proposalConfirmed ? (
                        <button
                          type="button"
                          data-testid={`intake-confirm-${file.relativePath}`}
                          className="text-ui-label text-primary"
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
                    </div>
                  ))}
                </div>
                {group.targetKind === IntakeTargetKind.perAnswer ? (
                  <button
                    type="button"
                    data-testid={`intake-attribute-${group.key}`}
                    className="mt-md rounded-md border border-outline px-md py-sm text-ui-label"
                    onClick={() => {
                      void attributeAnswers(group.key);
                    }}
                  >
                    {reviewerChoseOne
                      ? "すべての答案を振り分ける"
                      : "AIで振り分ける"}
                  </button>
                ) : null}
              </section>
            );
          })}

          <div className="flex flex-wrap gap-md">
            {cachedOnly > 0 ? (
              <button
                type="button"
                data-testid="intake-fetch-cached"
                className="rounded-md border border-outline px-md py-sm text-ui-label"
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
                className="rounded-md bg-secondary-container px-md py-sm text-ui-label text-on-secondary-container"
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
              className="rounded-md bg-primary px-md py-sm text-ui-label text-on-primary"
              disabled={
                intakeImportRequirements({
                  busy,
                  classifying,
                  folderRequirements: importRequirements(reviewState),
                }).length > 0
              }
              onClick={() => {
                void runImport();
              }}
            >
              この内容で取り込む
            </button>
          </div>
          <DisabledActionReason
            requirements={intakeImportRequirements({
              busy,
              classifying,
              folderRequirements: importRequirements(reviewState),
            })}
          />

          {confirmableProposals(reviewState).length > 0 ? (
            <button
              type="button"
              data-testid="intake-confirm-all"
              className="text-ui-label text-primary"
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
        </div>
      ) : null}

      {step === "done" ? (
        <div className="flex flex-col gap-md">
          <section className="rounded-lg border border-outline-variant bg-surface-container-low p-lg">
            <h2
              data-testid="intake-done-heading"
              className="text-title-large font-medium"
            >
              {doneHeading}
            </h2>
            {failedOutcomeCount > 0 ? (
              <p
                data-testid="intake-failure-summary"
                className="mt-sm text-body-medium text-error"
              >
                {failedOutcomeCount}件のグループで取り込みに失敗しました（全
                {outcomes.length}件中）。内容は下の一覧で確認できます。
              </p>
            ) : null}
            <p
              data-testid="intake-next-step-notice"
              className="mt-sm text-body-medium text-on-surface-variant"
            >
              採点にはこのあと配点と採点基準の確定が必要です。下のテストごとの「テスト設定を開く」から入力・確定してください。それまでは、取り込んだ答案はまだ採点できません。
            </p>
          </section>
          {outcomes.map((outcome) => (
            <section
              key={outcome.groupKey}
              data-testid={`intake-outcome-${outcome.groupKey}`}
              className="rounded-lg border border-outline-variant bg-surface-container-low p-lg"
            >
              <h3 className="text-title-medium font-medium">{outcome.name}</h3>
              {importedAnything(outcome) ? (
                <p data-testid={`intake-imported-${outcome.groupKey}`}>
                  資料 {outcome.materialCount}件 / 答案{" "}
                  {outcome.submissionCount}
                  件を取り込みました
                </p>
              ) : null}
              {outcome.gradingStartedCount > 0 ? (
                <p>うち{outcome.gradingStartedCount}件のAI採点を開始しました</p>
              ) : null}
              {outcome.gradingFailure !== null ? (
                <p className="text-error">{outcome.gradingFailure}</p>
              ) : null}
              {outcome.error !== null ? (
                <p
                  data-testid={`intake-failed-${outcome.groupKey}`}
                  className="text-error"
                >
                  {importedAnything(outcome)
                    ? `一部を取り込めませんでした: ${outcome.error}`
                    : `取り込めませんでした: ${outcome.error}`}
                  {outcome.failedFiles.length > 0
                    ? ` 失敗したファイル: ${outcome.failedFiles.join("、")}`
                    : ""}
                </p>
              ) : null}
              {outcome.testId !== null ? (
                <button
                  type="button"
                  data-testid={`intake-open-test-settings-${outcome.groupKey}`}
                  className="mt-sm rounded-md border border-outline px-md py-sm text-ui-label"
                  onClick={() => {
                    push(testSettings(outcome.testId!));
                  }}
                >
                  テスト設定を開く
                </button>
              ) : null}
            </section>
          ))}
          <button
            type="button"
            data-testid="intake-start-over"
            className="rounded-md border border-outline px-md py-sm text-ui-label"
            onClick={() => {
              setStep("choose");
              setReview(null);
              setOutcomes([]);
              setError(null);
            }}
          >
            別のフォルダを取り込む
          </button>
        </div>
      ) : null}
    </ShellScreen>
  );
}
