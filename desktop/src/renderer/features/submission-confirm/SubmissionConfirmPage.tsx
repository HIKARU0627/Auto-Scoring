import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type JSX,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  ActionRequirements,
  whileRunningRequirements,
} from "../../core/action-requirements.js";
import {
  loadQuestionReviewData,
  loadAnswerImageUrl,
} from "../../core/pdf-review-data.js";
import {
  approveQuestionReview,
  loadSubmissionConfirmData,
  SubmissionConfirmDataError,
  type QuestionReviewData,
} from "../../core/submission-confirm-data.js";
import {
  loadSubmissionAiUsage,
  UsageDataError,
} from "../../core/usage-data.js";
import {
  formatAiUsageDisplay,
  type AiUsageNumbers,
} from "../../core/ai-usage-display.js";
import type { components } from "../../api/generated/schema.js";
import { pdfReview, submissionConfirm } from "../../core/app-routes.js";
import { deriveQuestionStatus } from "../../core/question-status.js";
import { QuestionStatusBadge } from "../../core/QuestionStatusBadge.js";
import {
  displayGrade,
  effectiveReview,
  expectedReviewVersion,
  isQuestionConfirmed,
  latestAiGrade,
  latestOcrRecognition,
} from "../../core/question-review-state.js";
import { sortQuestionsForReview } from "../../core/question-order.js";
import {
  createSubmissionConfirmation,
  formatQuestionNumbers,
  runSubmissionConfirmation,
  SubmissionConfirmBlock,
  type QuestionConfirmation,
  type SubmissionConfirmationOutcome,
} from "../../core/submission-confirmation.js";
import { hasNearlyBlankCrop } from "../../core/submission-review-reason.js";
import { MaterialSymbolIcon } from "../../core/MaterialSymbolIcon.js";
import {
  submissionStatusToneTextClass,
  submissionStatusVisualOf,
} from "../../core/submission-status.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import { AnswerCropView } from "../pdf-review/AnswerCropView.js";
import { ConfidenceBadge } from "../pdf-review/ConfidenceBadge.js";
import { DisabledActionReason } from "../intake/DisabledActionReason.js";
import { useQuestionReadTracking } from "./use-question-read-tracking.js";

type QuestionResponse = components["schemas"]["QuestionResponse"];
type JobResponse = components["schemas"]["JobResponse"];
type SubmissionResponse = components["schemas"]["SubmissionResponse"];

const NUMERIC_STYLE: CSSProperties = {
  fontVariantNumeric: "var(--font-variant-numeric-score)",
};

const CARD_CLASS = "min-w-0 rounded-xl bg-surface-container p-lg";

const BUTTON_PRIMARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-primary px-md py-sm text-ui-label font-medium text-on-primary hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

const BUTTON_SECONDARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-surface-container-high px-md py-sm text-ui-label font-medium text-on-surface hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

const PILL_SUCCESS_CLASS =
  "inline-flex shrink-0 items-center gap-xs rounded-full bg-success-container px-sm py-xs text-xs text-on-success-container";

const PILL_ATTENTION_CLASS =
  "inline-flex shrink-0 items-center gap-xs rounded-full bg-attention-container px-sm py-xs text-xs text-on-attention-container";

/**
 * The bare question number (`1`) whether the stored value is `1` or `問1`.
 *
 * Question numbers are stored with their prefix (`問1`), so an unconditional
 * `問` prepend produced `問問1` on screen. Stripping here keeps every display
 * site at one prefix; the confirmation logic still receives the raw value.
 */
function questionNumberValue(number: string): string {
  return number.startsWith("問") ? number.slice(1) : number;
}

interface QuestionMaterialState {
  readonly loading: boolean;
  readonly error: string | null;
  readonly data: QuestionReviewData | null;
  readonly answerImageUrl: string | null;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      submission: SubmissionResponse;
      questions: readonly QuestionResponse[];
      jobs: readonly JobResponse[];
      queue: Awaited<ReturnType<typeof loadSubmissionConfirmData>>["queue"];
    };

function EnterActivates({ children }: { children: ReactNode }): JSX.Element {
  return (
    <span
      data-enter-activates-local=""
      onKeyDown={(event: KeyboardEvent) => {
        if (event.key === "Enter") {
          event.stopPropagation();
        }
      }}
    >
      {children}
    </span>
  );
}

function noticeCardClass(
  tone: "attention" | "neutral" | "danger" | "success",
): string {
  switch (tone) {
    case "attention":
      return "bg-attention-container text-on-attention-container";
    case "danger":
      return "bg-error-container text-on-error-container";
    case "success":
      return "bg-success-container text-on-success-container";
    default:
      return "bg-surface-container-high text-on-surface-variant";
  }
}

function noticeGlyph(
  tone: "attention" | "neutral" | "danger" | "success",
): string {
  switch (tone) {
    case "success":
      return "✓";
    case "attention":
    case "danger":
      return "!";
    default:
      return "−";
  }
}

function Notice({
  testId,
  tone,
  message,
}: {
  testId: string;
  tone: "attention" | "neutral" | "danger" | "success";
  message: string;
}): JSX.Element {
  return (
    <div
      data-testid={testId}
      data-tone={tone}
      role="status"
      className={`flex items-start gap-sm rounded-xl px-lg py-md text-body-medium ${noticeCardClass(tone)}`}
    >
      <span
        aria-hidden
        className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary font-semibold text-on-primary"
      >
        {noticeGlyph(tone)}
      </span>
      <span className="min-w-0 flex-1">{message}</span>
    </div>
  );
}

/**
 * The submission's own state, shown beside its name (Flutter
 * `_SubmissionStateChip`; Issue #84 / Issue #397). The icon comes from
 * `SubmissionStatusVisual` so this screen never grows a third mapping.
 */
function SubmissionStateChip({ state }: { state: string }): JSX.Element {
  const visual = submissionStatusVisualOf(state);
  return (
    <span
      data-testid="confirm-submission-state"
      className={`mt-xs inline-flex items-center gap-xs rounded-full bg-surface-container-high px-sm py-xs text-xs ${submissionStatusToneTextClass(visual.tone)}`}
    >
      <MaterialSymbolIcon
        name={visual.icon}
        label={visual.label}
        testId="confirm-submission-state-icon"
      />
      <span aria-hidden>{visual.label}</span>
    </span>
  );
}

function RowMarkers({
  questionId,
  register,
}: {
  questionId: string;
  register: ReturnType<typeof useQuestionReadTracking>["registerRowMarkers"];
}): JSX.Element {
  const topNode = useRef<HTMLSpanElement | null>(null);
  const bottomNode = useRef<HTMLSpanElement | null>(null);

  const tryRegister = useCallback(() => {
    if (topNode.current != null && bottomNode.current != null) {
      register(questionId, topNode.current, bottomNode.current);
    }
  }, [questionId, register]);

  const topRef = useCallback(
    (node: HTMLSpanElement | null) => {
      topNode.current = node;
      tryRegister();
    },
    [tryRegister],
  );

  const bottomRef = useCallback(
    (node: HTMLSpanElement | null) => {
      bottomNode.current = node;
      tryRegister();
    },
    [tryRegister],
  );

  return (
    <>
      <span ref={topRef} aria-hidden className="block h-0" />
      <span ref={bottomRef} aria-hidden className="block h-0" />
    </>
  );
}

export function SubmissionConfirmPage(): JSX.Element {
  const client = useSidecarClient();
  const { params, push, replace } = useRouter();
  const testId = params.testId ?? "";
  const submissionId = params.submissionId ?? "";

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [materialByQuestion, setMaterialByQuestion] = useState<
    Readonly<Record<string, QuestionMaterialState>>
  >({});
  const [confirming, setConfirming] = useState(false);
  const [outcome, setOutcome] = useState<SubmissionConfirmationOutcome | null>(
    null,
  );
  const [snackbar, setSnackbar] = useState<string | null>(null);
  const [aiUsage, setAiUsage] = useState<AiUsageNumbers | null>(null);
  const [aiUsageError, setAiUsageError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const questions =
    loadState.status === "ready"
      ? loadState.questions
      : ([] as QuestionResponse[]);
  const trackedQuestionIds = useMemo(
    () =>
      questions
        .filter((question) => {
          const material = materialByQuestion[question.id];
          return (
            material != null &&
            !material.loading &&
            material.error == null &&
            material.data != null
          );
        })
        .map((question) => question.id),
    [materialByQuestion, questions],
  );

  const readTracking = useQuestionReadTracking(trackedQuestionIds, scrollRef);
  const resetAllReadTracking = readTracking.resetAll;
  const resetQuestionReadTracking = readTracking.resetQuestion;

  const loadMaterial = useCallback(
    async (questionList: readonly QuestionResponse[]) => {
      await Promise.all(
        questionList.map(async (question) => {
          setMaterialByQuestion((current) => ({
            ...current,
            [question.id]: {
              loading: true,
              error: null,
              data: current[question.id]?.data ?? null,
              answerImageUrl: current[question.id]?.answerImageUrl ?? null,
            },
          }));
          try {
            const data = await loadQuestionReviewData(
              client,
              submissionId,
              question.id,
            );
            const answerImageUrl = await loadAnswerImageUrl(
              client,
              submissionId,
              question.id,
            );
            setMaterialByQuestion((current) => ({
              ...current,
              [question.id]: {
                loading: false,
                error: null,
                data,
                answerImageUrl,
              },
            }));
          } catch (error) {
            const message =
              error instanceof Error ? error.message : String(error);
            setMaterialByQuestion((current) => ({
              ...current,
              [question.id]: {
                loading: false,
                error: message,
                data: null,
                answerImageUrl: null,
              },
            }));
          }
        }),
      );
    },
    [client, submissionId],
  );

  const reload = useCallback(async () => {
    if (testId.length === 0 || submissionId.length === 0) {
      setLoadState({ status: "error", message: "答案 ID がありません" });
      return;
    }
    resetAllReadTracking();
    setLoadState({ status: "loading" });
    setOutcome(null);
    try {
      const data = await loadSubmissionConfirmData(
        client,
        testId,
        submissionId,
      );
      const sorted = sortQuestionsForReview(data.questions);
      setLoadState({
        status: "ready",
        submission: data.submission,
        questions: sorted,
        jobs: data.jobs,
        queue: data.queue,
      });
      await loadMaterial(sorted);
    } catch (error) {
      const message =
        error instanceof SubmissionConfirmDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setLoadState({ status: "error", message });
    }
  }, [client, loadMaterial, resetAllReadTracking, submissionId, testId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const confirmationInputs = useMemo(() => {
    return questions.map((question) => {
      const material = materialByQuestion[question.id];
      const reviews = material?.data?.reviews ?? [];
      const grades = material?.data?.grades ?? [];
      const aiGrade = latestAiGrade(grades);
      return {
        questionId: question.id,
        number: question.number,
        materialLoaded:
          material != null &&
          !material.loading &&
          material.error == null &&
          material.data != null,
        isConfirmed: isQuestionConfirmed(reviews),
        aiGradeId: aiGrade?.id ?? null,
        expectedVersion: expectedReviewVersion(reviews),
        isReached: readTracking.isReached(question.id),
      };
    });
  }, [materialByQuestion, questions, readTracking]);

  const confirmation = useMemo(
    () => createSubmissionConfirmation(confirmationInputs),
    [confirmationInputs],
  );

  const gradingFinished = useMemo(() => {
    if (loadState.status !== "ready") {
      return false;
    }
    const active = new Set(["queued", "running", "blocked"]);
    return !loadState.jobs.some(
      (job) => job.kind === "grading" && active.has(job.state),
    );
  }, [loadState]);

  useEffect(() => {
    if (!gradingFinished || submissionId.length === 0) {
      setAiUsage(null);
      setAiUsageError(null);
      return;
    }
    void loadSubmissionAiUsage(client, submissionId)
      .then((usage) => {
        setAiUsage(usage);
        setAiUsageError(null);
      })
      .catch((error: unknown) => {
        setAiUsage(null);
        setAiUsageError(
          error instanceof UsageDataError
            ? error.message
            : error instanceof Error
              ? error.message
              : String(error),
        );
      });
  }, [client, gradingFinished, submissionId]);

  const aiUsageDisplay = aiUsage != null ? formatAiUsageDisplay(aiUsage) : null;

  const latestJobFor = useCallback(
    (questionId: string): JobResponse | null => {
      if (loadState.status !== "ready") {
        return null;
      }
      let latest: JobResponse | null = null;
      for (const job of loadState.jobs) {
        if (job.question_id !== questionId) {
          continue;
        }
        if (
          latest == null ||
          new Date(job.created_at).getTime() >
            new Date(latest.created_at).getTime()
        ) {
          latest = job;
        }
      }
      return latest;
    },
    [loadState],
  );

  const confirmSubmission = useCallback(async () => {
    if (!confirmation.canConfirm || confirming) {
      return;
    }
    setConfirming(true);
    setOutcome(null);
    const result = await runSubmissionConfirmation({
      questions: confirmation.pending,
      approve: async (question: QuestionConfirmation) => {
        await approveQuestionReview(client, submissionId, question);
      },
    });
    if (loadState.status === "ready") {
      await loadMaterial(loadState.questions);
    }
    setConfirming(false);
    setOutcome(result);
    if (result.failedNumber == null) {
      setSnackbar(`${result.confirmed.length}問を確定しました`);
      const next =
        loadState.status === "ready"
          ? loadState.queue?.nextAfter(submissionId)
          : null;
      if (next != null) {
        replace(submissionConfirm(testId, next.id));
      } else if (loadState.status === "ready") {
        setSnackbar(
          loadState.queue == null
            ? "次の答案は取得できませんでした"
            : "このテストの答案はすべて確認しました",
        );
      }
    }
  }, [
    client,
    confirmation,
    confirming,
    loadMaterial,
    loadState,
    replace,
    submissionId,
    testId,
  ]);

  const deferSubmission = useCallback(() => {
    if (loadState.status !== "ready" || loadState.queue == null) {
      setSnackbar("ほかに確認できる答案がありません");
      return;
    }
    const next = loadState.queue.nextAfter(submissionId);
    if (next == null) {
      setSnackbar("ほかに確認できる答案がありません");
      return;
    }
    setSnackbar("後回しにしました。答案キューに残っています");
    replace(submissionConfirm(testId, next.id));
  }, [loadState, replace, submissionId, testId]);

  const onPageKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key !== "Enter" || event.ctrlKey || event.metaKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.closest("[data-enter-activates-local]") != null) {
        return;
      }
      event.preventDefault();
      if (confirmation.blocker === SubmissionConfirmBlock.unreached) {
        readTracking.revealNext();
        return;
      }
      void confirmSubmission();
    },
    [confirmSubmission, confirmation.blocker, readTracking],
  );

  const answerName =
    loadState.status === "ready"
      ? (loadState.submission.student_label ??
        loadState.submission.original_filename ??
        "答案の確定")
      : "答案の確定";

  const position =
    loadState.status === "ready" && loadState.queue != null
      ? loadState.queue.positionOf(submissionId)
      : 0;
  const subtitleProgress = `確定済み ${confirmation.confirmedCount} / ${confirmation.total} 問`;
  const subtitle =
    position > 0
      ? `${position} / ${loadState.status === "ready" ? loadState.queue?.total : 0} 件目 ・ ${subtitleProgress}`
      : subtitleProgress;

  const confirmLabel =
    confirmation.pending.length === 0
      ? "この答案を確定 (Enter)"
      : `${confirmation.pending.length}問をまとめて確定 (Enter)`;

  return (
    <ShellScreen title={answerName}>
      <div className="flex min-w-0 flex-col gap-lg">
        {loadState.status === "ready" ? (
          <section className={CARD_CLASS}>
            <div className="flex flex-wrap items-center justify-between gap-md">
              <div className="min-w-0 flex-1">
                <p
                  data-testid="confirm-subtitle"
                  className="text-body-medium text-on-surface-variant"
                  style={NUMERIC_STYLE}
                >
                  {subtitle}
                </p>
                <SubmissionStateChip state={loadState.submission.state} />
              </div>
              <button
                type="button"
                data-testid="confirm-refresh-button"
                className={BUTTON_SECONDARY_CLASS}
                disabled={confirming}
                onClick={() => {
                  void reload();
                }}
              >
                再読み込み
              </button>
            </div>
          </section>
        ) : null}

        {loadState.status === "loading" ? (
          <section
            data-testid="confirm-loading"
            aria-busy="true"
            aria-live="polite"
            className={`${CARD_CLASS} animate-pulse`}
          >
            <span className="sr-only">答案を読み込んでいます…</span>
            <div className="h-5 w-40 rounded-md bg-surface-container-high" />
            <div className="mt-md h-4 w-3/4 rounded-md bg-surface-container-high" />
            <div className="mt-lg h-40 w-full rounded-md bg-surface-container-high" />
          </section>
        ) : null}

        {loadState.status === "error" ? (
          <section
            data-testid="confirm-error"
            role="alert"
            className="rounded-xl bg-error-container px-lg py-md text-on-error-container"
          >
            <p className="text-body-medium">
              答案を読み込めませんでした: {loadState.message}
            </p>
            <button
              type="button"
              className={`${BUTTON_SECONDARY_CLASS} mt-md`}
              onClick={() => {
                void reload();
              }}
            >
              再読み込み
            </button>
          </section>
        ) : null}

        {loadState.status === "ready" && questions.length === 0 ? (
          <section className={CARD_CLASS}>
            <div className="flex items-start gap-md">
              <span
                aria-hidden
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-container text-on-primary-container"
              >
                ?
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-xl font-semibold leading-ui text-on-surface">
                  設問がありません
                </h2>
                <p
                  data-testid="confirm-no-questions"
                  className="mt-xs text-body-medium text-on-surface-variant"
                >
                  このテストには設問が登録されていません。テスト設定で設問を登録すると、ここで答案を確定できます。
                </p>
              </div>
            </div>
          </section>
        ) : null}

        {loadState.status === "ready" && gradingFinished ? (
          <section data-testid="confirm-ai-usage" className={CARD_CLASS}>
            <h2 className="text-xl font-semibold leading-ui text-on-surface">
              AI 利用量
            </h2>
            {aiUsageError != null ? (
              <p
                data-testid="confirm-ai-usage-error"
                className="mt-xs text-body-medium text-on-surface-variant"
              >
                AI 利用量を取得できませんでした: {aiUsageError}
              </p>
            ) : aiUsageDisplay != null ? (
              <div className="mt-xs flex flex-col gap-xs">
                <p
                  data-testid="confirm-ai-usage-tokens"
                  className="text-body-medium text-on-surface"
                  style={NUMERIC_STYLE}
                >
                  {aiUsageDisplay.tokenLine}
                </p>
                {aiUsageDisplay.costLine != null ? (
                  <p
                    data-testid="confirm-ai-usage-cost"
                    className="text-body-medium text-on-surface"
                    style={NUMERIC_STYLE}
                  >
                    {aiUsageDisplay.costLine}
                  </p>
                ) : null}
              </div>
            ) : (
              <div
                data-testid="confirm-ai-usage-loading"
                className="mt-xs text-body-medium text-on-surface-variant"
              >
                AI 利用量を読み込み中…
              </div>
            )}
          </section>
        ) : null}

        {loadState.status === "ready" && questions.length > 0 ? (
          <div
            className="flex min-h-0 flex-col gap-lg"
            onKeyDown={onPageKeyDown}
          >
            <div
              ref={scrollRef}
              data-testid="confirm-question-list"
              className="min-h-0 max-h-inspector overflow-y-auto rounded-xl"
            >
              <div className="flex flex-col gap-lg">
                {questions.map((question) => {
                  const material = materialByQuestion[question.id];
                  const reviews = material?.data?.reviews ?? [];
                  const grades = material?.data?.grades ?? [];
                  const aiGrade = latestAiGrade(grades);
                  const ocr = latestOcrRecognition(
                    material?.data?.recognitions ?? [],
                  );
                  const humanGrade = displayGrade(grades, reviews);
                  const statusKey = deriveQuestionStatus({
                    job: latestJobFor(question.id),
                    review: effectiveReview(reviews),
                    hasWaitingDependents: loadState.jobs.some(
                      (job) =>
                        job.blocked_on_question_id === question.id &&
                        job.state === "blocked",
                    ),
                  });
                  const reached = readTracking.isReached(question.id);
                  return (
                    <article
                      key={question.id}
                      data-testid={`confirm-question-${question.id}`}
                      className={CARD_CLASS}
                    >
                      <div className="flex flex-wrap items-center gap-sm">
                        <h3 className="flex-1 text-base font-semibold text-on-surface">
                          問{questionNumberValue(question.number)}
                        </h3>
                        <QuestionStatusBadge status={statusKey} />
                        <span
                          data-testid={`confirm-reach-${question.id}`}
                          className={
                            reached ? PILL_SUCCESS_CLASS : PILL_ATTENTION_CLASS
                          }
                        >
                          {reached ? "表示済み" : "未表示"}
                        </span>
                      </div>
                      <RowMarkers
                        questionId={question.id}
                        register={readTracking.registerRowMarkers}
                      />
                      {material?.loading ? (
                        <div className="mt-md h-40 w-full animate-pulse rounded-lg bg-surface-container-high" />
                      ) : null}
                      {material?.error != null ? (
                        <p
                          data-testid={`confirm-question-error-${question.id}`}
                          className="mt-md rounded-lg bg-error-container px-md py-sm text-body-medium text-on-error-container"
                        >
                          判断材料を読み込めませんでした: {material.error}
                        </p>
                      ) : null}
                      {material?.data != null && !material.loading ? (
                        <div className="mt-md grid gap-lg lg:grid-cols-2">
                          <div className="flex flex-col gap-sm">
                            <div className="overflow-hidden rounded-lg bg-surface-container-high p-sm">
                              <AnswerCropView
                                imageUrl={material.answerImageUrl}
                                nearlyBlank={hasNearlyBlankCrop(
                                  loadState.submission.review_reason,
                                  question.id,
                                )}
                              />
                            </div>
                          </div>
                          <div className="flex flex-col gap-sm">
                            <p className="text-ui-label font-medium text-on-surface-variant">
                              AI認識文字
                            </p>
                            {ocr == null ? (
                              <p className="text-body-medium text-on-surface-variant">
                                未認識
                              </p>
                            ) : (
                              <>
                                <p
                                  data-testid={`confirm-recognition-${question.id}`}
                                  className="text-role-recognized rounded-lg bg-surface-container-high p-sm text-on-surface"
                                >
                                  {ocr.text}
                                </p>
                                <ConfidenceBadge
                                  label="OCR文字認識信頼度"
                                  confidence={ocr.confidence}
                                  testId={`confirm-ocr-confidence-${question.id}`}
                                />
                              </>
                            )}
                            <p className="mt-sm text-ui-label font-medium text-on-surface-variant">
                              採点
                            </p>
                            {aiGrade == null ? (
                              <p
                                data-testid={`confirm-no-grade-${question.id}`}
                                className="rounded-lg bg-attention-container px-md py-sm text-body-medium text-on-attention-container"
                              >
                                AIの点数がありません。この設問は自分で点数を入力する必要があります。
                              </p>
                            ) : (
                              <>
                                <p
                                  data-testid={`confirm-score-${question.id}`}
                                  className="text-role-score font-semibold text-on-surface"
                                  style={NUMERIC_STYLE}
                                >
                                  {aiGrade.score.awarded} /{" "}
                                  {aiGrade.score.maximum} 点
                                </p>
                                <ConfidenceBadge
                                  label="採点信頼度"
                                  confidence={aiGrade.confidence}
                                  testId={`confirm-grade-confidence-${question.id}`}
                                />
                                {aiGrade.rationale ? (
                                  <p
                                    data-testid={`confirm-rationale-${question.id}`}
                                    className="text-body-medium text-on-surface-variant"
                                  >
                                    {aiGrade.rationale}
                                  </p>
                                ) : null}
                              </>
                            )}
                            {humanGrade?.source === "human" ? (
                              <p
                                data-testid={`confirm-human-score-${question.id}`}
                                className="rounded-lg bg-success-container px-md py-sm text-body-medium text-on-success-container"
                                style={NUMERIC_STYLE}
                              >
                                人による確定: {humanGrade.score.awarded} /{" "}
                                {humanGrade.score.maximum} 点
                              </p>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                      <div className="mt-md flex justify-end">
                        <EnterActivates>
                          <button
                            type="button"
                            data-testid={`confirm-open-${question.id}`}
                            className={BUTTON_SECONDARY_CLASS}
                            onClick={() => {
                              resetQuestionReadTracking(question.id);
                              push(
                                pdfReview(testId, submissionId, question.id),
                              );
                            }}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.stopPropagation();
                              }
                            }}
                          >
                            {aiGrade == null && !isQuestionConfirmed(reviews)
                              ? "点数を入力する"
                              : "この設問を詳しく見る・直す"}
                          </button>
                        </EnterActivates>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>

            <footer className={`${CARD_CLASS} flex flex-col gap-sm`}>
              {outcome != null ? (
                <Notice
                  testId={
                    outcome.failedNumber == null
                      ? "confirm-outcome-complete"
                      : "confirm-outcome-partial"
                  }
                  tone={outcome.failedNumber == null ? "success" : "danger"}
                  message={
                    outcome.failedNumber == null
                      ? `${outcome.confirmed.length}問を確定しました。`
                      : outcome.confirmed.length === 0
                        ? `確定できた設問はありません。問${outcome.failedNumber} で失敗しました: ${outcome.message ?? "理由は分かりません"}。残り${outcome.remaining.length}問（${outcome.remaining.map((number) => `問${number}`).join("・")}）はそのまま確定し直せます。`
                        : `${outcome.confirmed.map((number) => `問${number}`).join("・")} を確定しました。問${outcome.failedNumber} で失敗しました: ${outcome.message ?? "理由は分かりません"}。残り${outcome.remaining.length}問（${outcome.remaining.map((number) => `問${number}`).join("・")}）はそのまま確定し直せます。`
                  }
                />
              ) : null}
              <BlockerNotice
                confirmation={confirmation}
                unreadIsAbove={readTracking.unreadIsAbove}
              />
              <div className="flex flex-wrap justify-end gap-md">
                <EnterActivates>
                  <button
                    type="button"
                    data-testid="confirm-defer-button"
                    className={BUTTON_SECONDARY_CLASS}
                    disabled={confirming}
                    onClick={deferSubmission}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.stopPropagation();
                      }
                    }}
                  >
                    後回し (S)
                  </button>
                </EnterActivates>
                {confirmation.blocker === SubmissionConfirmBlock.unreached ? (
                  <button
                    type="button"
                    data-testid="confirm-reveal-button"
                    className={BUTTON_SECONDARY_CLASS}
                    onClick={readTracking.revealNext}
                  >
                    未到達の設問を表示
                  </button>
                ) : null}
                <button
                  type="button"
                  data-testid="confirm-submission-button"
                  className={BUTTON_PRIMARY_CLASS}
                  disabled={!confirmation.canConfirm || confirming}
                  onClick={() => {
                    void confirmSubmission();
                  }}
                >
                  {confirming ? "確定中…" : confirmLabel}
                </button>
              </div>
              {confirming ? (
                <DisabledActionReason
                  requirements={whileRunningRequirements({ running: true })}
                />
              ) : null}
            </footer>
          </div>
        ) : null}

        {snackbar != null ? (
          <div
            role="status"
            className="fixed bottom-lg left-1/2 -translate-x-1/2 rounded-xl bg-inverse-surface px-lg py-sm text-body-medium text-inverse-on-surface"
          >
            {snackbar}
          </div>
        ) : null}
      </div>
    </ShellScreen>
  );
}

function BlockerNotice({
  confirmation,
  unreadIsAbove,
}: {
  confirmation: ReturnType<typeof createSubmissionConfirmation>;
  unreadIsAbove: boolean;
}): JSX.Element | null {
  const blocker = confirmation.blocker;
  if (blocker == null) {
    return (
      <Notice
        testId="confirm-ready-notice"
        tone="success"
        message={
          ActionRequirements.submissionConfirmReady(confirmation.pending.length)
            .message
        }
      />
    );
  }
  switch (blocker) {
    case SubmissionConfirmBlock.noQuestions:
      return (
        <Notice
          testId="confirm-blocked-no-questions"
          tone="neutral"
          message={ActionRequirements.submissionConfirmNoQuestions.message}
        />
      );
    case SubmissionConfirmBlock.materialUnavailable:
      return (
        <Notice
          testId="confirm-blocked-unavailable"
          tone="danger"
          message={
            ActionRequirements.submissionConfirmMaterialUnavailable(
              formatQuestionNumbers(confirmation.unloaded),
            ).message
          }
        />
      );
    case SubmissionConfirmBlock.humanScoreRequired:
      return (
        <Notice
          testId="confirm-blocked-human-score"
          tone="attention"
          message={
            ActionRequirements.submissionConfirmHumanScoreRequired(
              formatQuestionNumbers(confirmation.needingHumanScore),
            ).message
          }
        />
      );
    case SubmissionConfirmBlock.unreached:
      return (
        <Notice
          testId="confirm-blocked-unreached"
          tone="attention"
          message={
            ActionRequirements.submissionConfirmUnreached(
              formatQuestionNumbers(confirmation.unreached),
              unreadIsAbove,
            ).message
          }
        />
      );
    case SubmissionConfirmBlock.nothingToConfirm:
      return (
        <Notice
          testId="confirm-blocked-nothing"
          tone="success"
          message={ActionRequirements.submissionConfirmNothingToConfirm.message}
        />
      );
    default:
      return null;
  }
}
