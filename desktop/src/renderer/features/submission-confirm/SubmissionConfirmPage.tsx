import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { useSidecarClient } from "../../api/SidecarApiProvider.js";
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
import type { components } from "../../api/generated/schema.js";
import { pdfReview, submissionConfirm } from "../../core/app-routes.js";
import {
  deriveQuestionStatus,
  QuestionStatus,
} from "../../core/question-status.js";
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
import { submissionStatusVisualOf } from "../../core/submission-status.js";
import { BackOrHomeButton } from "../../navigation/BackOrHomeButton.js";
import { useRouter } from "../../navigation/router.js";
import { AnswerCropView } from "../pdf-review/AnswerCropView.js";
import { ConfidenceBadge } from "../pdf-review/ConfidenceBadge.js";
import { useQuestionReadTracking } from "./use-question-read-tracking.js";

type QuestionResponse = components["schemas"]["QuestionResponse"];
type JobResponse = components["schemas"]["JobResponse"];
type SubmissionResponse = components["schemas"]["SubmissionResponse"];

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

function toneClass(
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
    <p data-testid={testId} className={`text-body-small ${toneClass(tone)}`}>
      {message}
    </p>
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
    <div className="flex min-h-screen flex-col bg-surface text-on-surface">
      <header className="border-b border-outline-variant px-xl py-md">
        <div className="flex items-center gap-md">
          <BackOrHomeButton />
          <div className="min-w-0 flex-1">
            <h1 className="text-title-large font-medium leading-ui">
              {answerName}
            </h1>
            {loadState.status === "ready" ? (
              <p
                data-testid="confirm-subtitle"
                className="text-body-small text-on-surface-variant"
              >
                {subtitle}
              </p>
            ) : null}
          </div>
          {loadState.status === "ready" ? (
            <span className="text-ui-label text-on-surface-variant">
              {submissionStatusVisualOf(loadState.submission.state).label}
            </span>
          ) : null}
          <button
            type="button"
            data-testid="confirm-refresh-button"
            className="rounded-md border border-outline px-md py-xs text-ui-label"
            disabled={confirming}
            onClick={() => {
              void reload();
            }}
          >
            再読み込み
          </button>
        </div>
      </header>

      {loadState.status === "loading" ? (
        <div
          data-testid="confirm-loading"
          className="flex flex-1 items-center justify-center"
        >
          <p className="text-body-medium text-on-surface-variant">
            読み込み中…
          </p>
        </div>
      ) : null}

      {loadState.status === "error" ? (
        <div className="flex flex-1 items-center justify-center p-xl">
          <div className="max-w-lg rounded-md border border-error bg-error-container p-lg text-on-error-container">
            <p data-testid="confirm-error" className="text-body-medium">
              答案を読み込めませんでした: {loadState.message}
            </p>
            <button
              type="button"
              className="mt-md rounded-md border border-outline px-md py-xs text-ui-label"
              onClick={() => {
                void reload();
              }}
            >
              再読み込み
            </button>
          </div>
        </div>
      ) : null}

      {loadState.status === "ready" && questions.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-xl">
          <p
            data-testid="confirm-no-questions"
            className="text-body-medium text-on-surface-variant"
          >
            このテストには設問が登録されていません。
          </p>
        </div>
      ) : null}

      {loadState.status === "ready" && questions.length > 0 ? (
        <div
          className="flex min-h-0 flex-1 flex-col outline-none"
          tabIndex={-1}
          onKeyDown={onPageKeyDown}
        >
          <div
            ref={scrollRef}
            data-testid="confirm-question-list"
            className="min-h-0 flex-1 overflow-y-auto p-xl"
          >
            <div className="mx-auto flex max-w-240 flex-col gap-lg">
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
                    className="rounded-lg border border-outline-variant bg-surface-container p-lg"
                  >
                    <div className="flex items-center gap-sm">
                      <h2 className="flex-1 text-title-medium font-medium">
                        問{question.number}
                      </h2>
                      <span className="text-ui-label">
                        {QuestionStatus[statusKey].label}
                      </span>
                      <span
                        data-testid={`confirm-reach-${question.id}`}
                        className={`text-ui-label ${reached ? "text-success" : "text-attention"}`}
                      >
                        {reached ? "表示済み" : "未表示"}
                      </span>
                    </div>
                    <RowMarkers
                      questionId={question.id}
                      register={readTracking.registerRowMarkers}
                    />
                    {material?.loading ? (
                      <p className="py-lg text-body-medium text-on-surface-variant">
                        読み込み中…
                      </p>
                    ) : null}
                    {material?.error != null ? (
                      <p
                        data-testid={`confirm-question-error-${question.id}`}
                        className="py-lg text-body-small text-error"
                      >
                        判断材料を読み込めませんでした: {material.error}
                      </p>
                    ) : null}
                    {material?.data != null && !material.loading ? (
                      <div className="flex flex-col gap-sm py-sm">
                        <div className="h-45">
                          <AnswerCropView
                            imageUrl={material.answerImageUrl}
                            nearlyBlank={hasNearlyBlankCrop(
                              loadState.submission.review_reason,
                              question.id,
                            )}
                          />
                        </div>
                        <p className="text-label-large">AI認識文字</p>
                        {ocr == null ? (
                          <p>未認識</p>
                        ) : (
                          <>
                            <p
                              data-testid={`confirm-recognition-${question.id}`}
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
                        <p className="text-label-large">採点</p>
                        {aiGrade == null ? (
                          <p data-testid={`confirm-no-grade-${question.id}`}>
                            AIの点数がありません。この設問は自分で点数を入力する必要があります。
                          </p>
                        ) : (
                          <>
                            <p
                              data-testid={`confirm-score-${question.id}`}
                              className="text-score"
                            >
                              {aiGrade.score.awarded} / {aiGrade.score.maximum}{" "}
                              点
                            </p>
                            <ConfidenceBadge
                              label="採点信頼度"
                              confidence={aiGrade.confidence}
                              testId={`confirm-grade-confidence-${question.id}`}
                            />
                            {aiGrade.rationale ? (
                              <p
                                data-testid={`confirm-rationale-${question.id}`}
                              >
                                {aiGrade.rationale}
                              </p>
                            ) : null}
                          </>
                        )}
                        {humanGrade?.source === "human" ? (
                          <p data-testid={`confirm-human-score-${question.id}`}>
                            人による確定: {humanGrade.score.awarded} /{" "}
                            {humanGrade.score.maximum} 点
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="mt-sm flex justify-end">
                      <EnterActivates>
                        <button
                          type="button"
                          data-testid={`confirm-open-${question.id}`}
                          className="rounded-md border border-outline px-md py-xs text-ui-label"
                          onClick={() => {
                            resetQuestionReadTracking(question.id);
                            push(pdfReview(testId, submissionId, question.id));
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

          <footer className="border-t border-outline-variant bg-surface p-lg">
            <div className="mx-auto flex max-w-240 flex-col gap-sm">
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
                    className="rounded-md border border-outline px-md py-sm text-ui-label"
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
                    className="rounded-md border border-outline px-md py-sm text-ui-label"
                    onClick={readTracking.revealNext}
                  >
                    未到達の設問を表示
                  </button>
                ) : null}
                <button
                  type="button"
                  data-testid="confirm-submission-button"
                  className="rounded-md bg-primary px-md py-sm text-ui-label text-on-primary disabled:opacity-50"
                  disabled={!confirmation.canConfirm || confirming}
                  onClick={() => {
                    void confirmSubmission();
                  }}
                >
                  {confirmLabel}
                </button>
              </div>
            </div>
          </footer>
        </div>
      ) : null}

      {snackbar != null ? (
        <div
          role="status"
          className="fixed bottom-lg left-1/2 -translate-x-1/2 rounded-md bg-inverse-surface px-lg py-sm text-body-small text-inverse-on-surface"
        >
          {snackbar}
        </div>
      ) : null}
    </div>
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
        message={`全設問の判断材料を表示しました。${confirmation.pending.length}問をまとめて確定できます。`}
      />
    );
  }
  switch (blocker) {
    case SubmissionConfirmBlock.noQuestions:
      return (
        <Notice
          testId="confirm-blocked-no-questions"
          tone="neutral"
          message="このテストには設問が登録されていません。"
        />
      );
    case SubmissionConfirmBlock.materialUnavailable:
      return (
        <Notice
          testId="confirm-blocked-unavailable"
          tone="danger"
          message={`判断材料を読み込めていない設問があります（${formatQuestionNumbers(confirmation.unloaded)}）。再読み込みしてください。`}
        />
      );
    case SubmissionConfirmBlock.humanScoreRequired:
      return (
        <Notice
          testId="confirm-blocked-human-score"
          tone="attention"
          message={`AIが採点できなかった設問があります（${formatQuestionNumbers(confirmation.needingHumanScore)}）。その設問を開いて点数を入力すると、まとめて確定できます。`}
        />
      );
    case SubmissionConfirmBlock.unreached:
      return (
        <Notice
          testId="confirm-blocked-unreached"
          tone="attention"
          message={`まだ表示していない設問があります（${formatQuestionNumbers(confirmation.unreached)}）。${unreadIsAbove ? "上" : "下"}方向へスクロールすると確定できます。`}
        />
      );
    case SubmissionConfirmBlock.nothingToConfirm:
      return (
        <Notice
          testId="confirm-blocked-nothing"
          tone="success"
          message="この答案は全設問を確定済みです。"
        />
      );
    default:
      return null;
  }
}
