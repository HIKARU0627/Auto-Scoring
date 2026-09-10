import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
} from "react";

import {
  PdfReviewDataError,
  loadDependencyGraph,
  loadJobs,
  loadQuestionReviewData,
  loadQuestions,
  loadSubmission,
  loadSubmissionPages,
  loadAnswerImageUrl,
  type QuestionReviewData,
  type SubmissionPageState,
} from "../../api/pdf-review-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  buildDependencyDagLayout,
  deriveStatusesFromJobs,
  releasesDependents,
} from "../../core/dependency-dag.js";
import { sortQuestionsForReview } from "../../core/question-order.js";
import {
  deriveQuestionStatus,
  labelWaitingFor,
  QuestionStatus,
  resolveQuestionWait,
  type QuestionStatusKey,
} from "../../core/question-status.js";
import {
  annotationsForDisplayedAttempt,
  displayGrade,
  expectedReviewVersion,
  recognitionsForDisplayedAttempt,
} from "../../core/question-review-state.js";
import { BackOrHomeButton } from "../../navigation/BackOrHomeButton.js";
import { ShellScreen } from "../../navigation/ShellScreen.js";
import { useRouter } from "../../navigation/router.js";
import { AnswerCropView } from "./AnswerCropView.js";
import { ConfidenceBadge } from "./ConfidenceBadge.js";
import { DependencyDagPanel } from "./DependencyDagPanel.js";
import { PageImageViewer } from "./PageImageViewer.js";
import { setStateIfMounted, useMountedRef } from "./use-mounted-ref.js";
import {
  useMaterialReadTracking,
  type MaterialRow,
} from "./use-material-read-tracking.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      pages: readonly SubmissionPageState[];
      questionData: Map<string, QuestionReviewData>;
    };

function statusIcon(status: QuestionStatusKey): string {
  return QuestionStatus[status].icon;
}

export function PdfReviewPage(): JSX.Element {
  const client = useSidecarClient();
  const { params } = useRouter();
  const testId = params.testId ?? "";
  const submissionId = params.submissionId ?? "";
  const initialQuestionId = params.questionId;

  const mounted = useMountedRef();
  const inspectorRef = useRef<HTMLDivElement>(null);
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [questions, setQuestions] = useState<
    ReturnType<typeof sortQuestionsForReview>
  >([]);
  const [jobs, setJobs] = useState<Awaited<ReturnType<typeof loadJobs>>>([]);
  const [edges, setEdges] = useState<
    Awaited<ReturnType<typeof loadDependencyGraph>>["edges"]
  >([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [note, setNote] = useState("");
  const [answerImageUrl, setAnswerImageUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [zoom, setZoom] = useState(1);

  const selectedQuestion = questions[selectedIndex] ?? null;

  const materialRows = useMemo((): MaterialRow[] => {
    if (loadState.status !== "ready" || selectedQuestion == null) {
      return [];
    }
    const data = loadState.questionData.get(selectedQuestion.id);
    const grade = displayGrade(data?.grades ?? [], data?.reviews ?? []);
    const rows: MaterialRow[] = [];
    if (grade != null) {
      rows.push({ id: `grade:${grade.id}` });
      for (const criterion of grade.criteria) {
        rows.push({ id: `criterion:${criterion.criterion_id}` });
      }
    }
    return rows;
  }, [loadState, selectedQuestion]);

  const materialRead = useMaterialReadTracking(materialRows, inspectorRef);

  const reload = useCallback(async () => {
    if (testId.length === 0 || submissionId.length === 0) {
      setStateIfMounted(mounted, setLoadState, {
        status: "error",
        message: "テスト ID または答案 ID がありません",
      });
      return;
    }
    setStateIfMounted(mounted, setLoadState, { status: "loading" });
    try {
      await loadSubmission(client, submissionId);
      const [sortedQuestions, jobList, graph, pages] = await Promise.all([
        loadQuestions(client, testId).then(sortQuestionsForReview),
        loadJobs(client, submissionId),
        loadDependencyGraph(client, testId),
        loadSubmissionPages(client, submissionId),
      ]);
      const questionData = new Map<string, QuestionReviewData>();
      setStateIfMounted(mounted, setQuestions, sortedQuestions);
      setStateIfMounted(mounted, setJobs, jobList);
      setStateIfMounted(mounted, setEdges, graph.edges);
      if (initialQuestionId != null) {
        const index = sortedQuestions.findIndex(
          (q) => q.id === initialQuestionId,
        );
        if (index >= 0) {
          setStateIfMounted(mounted, setSelectedIndex, index);
        }
      }
      setStateIfMounted(mounted, setLoadState, {
        status: "ready",
        pages,
        questionData,
      });
    } catch (error) {
      const message =
        error instanceof PdfReviewDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setStateIfMounted(mounted, setLoadState, { status: "error", message });
    }
  }, [client, initialQuestionId, mounted, submissionId, testId]);

  const loadSelectedQuestion = useCallback(async () => {
    if (selectedQuestion == null || loadState.status !== "ready") {
      return;
    }
    if (loadState.questionData.has(selectedQuestion.id)) {
      return;
    }
    try {
      const data = await loadQuestionReviewData(
        client,
        submissionId,
        selectedQuestion.id,
      );
      const imageUrl = await loadAnswerImageUrl(
        client,
        submissionId,
        selectedQuestion.id,
      );
      setStateIfMounted(mounted, setAnswerImageUrl, imageUrl);
      setStateIfMounted(mounted, setLoadState, (current) => {
        if (current.status !== "ready") {
          return current;
        }
        const next = new Map(current.questionData);
        next.set(selectedQuestion.id, data);
        return { ...current, questionData: next };
      });
    } catch (error) {
      const message =
        error instanceof PdfReviewDataError
          ? error.message
          : error instanceof Error
            ? error.message
            : String(error);
      setStateIfMounted(mounted, setLoadState, { status: "error", message });
    }
  }, [client, loadState, mounted, selectedQuestion, submissionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    void loadSelectedQuestion();
  }, [loadSelectedQuestion]);

  const reviewsByQuestion = useMemo(() => {
    if (loadState.status !== "ready") {
      return {};
    }
    const map: Record<string, QuestionReviewData["reviews"][number] | null> =
      {};
    for (const question of questions) {
      const data = loadState.questionData.get(question.id);
      const reviews = data?.reviews ?? [];
      map[question.id] = reviews.findLast((r) => r.action !== "undone") ?? null;
    }
    return map;
  }, [loadState, questions]);

  const dagQuestions = useMemo(
    () =>
      deriveStatusesFromJobs({
        questions: questions.map((q) => ({ id: q.id, label: q.number })),
        jobs,
        reviewsByQuestion,
      }),
    [jobs, questions, reviewsByQuestion],
  );

  const dagLayout = useMemo(() => {
    const released = new Set(
      jobs
        .filter((job) => releasesDependents(job))
        .map((job) => job.question_id!),
    );
    return buildDependencyDagLayout({
      questions: dagQuestions,
      edges,
      releasedQuestionIds: released,
    });
  }, [dagQuestions, edges, jobs]);

  const selectedData =
    loadState.status === "ready" && selectedQuestion != null
      ? loadState.questionData.get(selectedQuestion.id)
      : undefined;

  const selectedGrade = displayGrade(
    selectedData?.grades ?? [],
    selectedData?.reviews ?? [],
  );
  const selectedRecognitions = recognitionsForDisplayedAttempt(
    selectedData?.recognitions ?? [],
    selectedGrade,
  );
  const selectedAnnotations = annotationsForDisplayedAttempt(
    selectedData?.annotations ?? [],
    selectedGrade,
  );

  const selectedJob =
    jobs.find((j) => j.question_id === selectedQuestion?.id) ?? null;
  const selectedReview = selectedQuestion
    ? (reviewsByQuestion[selectedQuestion.id] ?? null)
    : null;
  const selectedStatus = deriveQuestionStatus({
    job: selectedJob,
    review: selectedReview,
    hasWaitingDependents: jobs.some(
      (j) => j.blocked_on_question_id === selectedQuestion?.id,
    ),
  });
  const selectedWait = selectedQuestion
    ? resolveQuestionWait(selectedQuestion.id, {
        blockedOn: (id) =>
          jobs.find((j) => j.question_id === id)?.blocked_on_question_id ??
          null,
        statusOf: (id) => {
          const job = jobs.find((j) => j.question_id === id) ?? null;
          const review = reviewsByQuestion[id] ?? null;
          return deriveQuestionStatus({
            job,
            review,
            hasWaitingDependents: jobs.some(
              (j) => j.blocked_on_question_id === id,
            ),
          });
        },
        numberOf: (id) => questions.find((q) => q.id === id)?.number ?? null,
      })
    : null;

  const canApprove =
    materialRead.allRowsCovered && selectedStatus === "graded" && !busy;
  const blockedOnUnread = !materialRead.allRowsCovered;

  const performAction = useCallback(
    async (action: "approve" | "reject" | "regrade" | "undo") => {
      if (selectedQuestion == null || selectedData == null) {
        return;
      }
      setBusy(true);
      try {
        const version = expectedReviewVersion(selectedData.reviews);
        const pathBase = {
          submission_id: submissionId,
          question_id: selectedQuestion.id,
        };
        if (action === "approve") {
          await client.POST(
            "/submissions/{submission_id}/questions/{question_id}/review/approve",
            {
              params: { path: pathBase },
              body: { expected_version: version },
            },
          );
        } else if (action === "reject") {
          await client.POST(
            "/submissions/{submission_id}/questions/{question_id}/review/reject",
            {
              params: { path: pathBase },
              body: { expected_version: version, reason: note },
            },
          );
        } else if (action === "regrade") {
          await client.POST(
            "/submissions/{submission_id}/questions/{question_id}/review/regrade",
            {
              params: { path: pathBase },
              body: { expected_version: version },
            },
          );
        } else {
          await client.POST(
            "/submissions/{submission_id}/questions/{question_id}/review/undo",
            {
              params: { path: pathBase },
              body: { expected_version: version },
            },
          );
        }
        const refreshed = await loadQuestionReviewData(
          client,
          submissionId,
          selectedQuestion.id,
        );
        setStateIfMounted(mounted, setLoadState, (current) => {
          if (current.status !== "ready") {
            return current;
          }
          const next = new Map(current.questionData);
          next.set(selectedQuestion.id, refreshed);
          return { ...current, questionData: next };
        });
        const refreshedJobs = await loadJobs(client, submissionId);
        setStateIfMounted(mounted, setJobs, refreshedJobs);
      } finally {
        setStateIfMounted(mounted, setBusy, false);
      }
    },
    [client, mounted, note, selectedData, selectedQuestion, submissionId],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Enter" && !event.ctrlKey && !event.metaKey) {
        if (!canApprove) {
          if (blockedOnUnread) {
            materialRead.revealRest();
          }
          event.preventDefault();
          return;
        }
        event.preventDefault();
        void performAction("approve");
      }
      if (event.key === "ArrowUp") {
        setSelectedIndex((index) => Math.max(0, index - 1));
      }
      if (event.key === "ArrowDown") {
        setSelectedIndex((index) => Math.min(questions.length - 1, index + 1));
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "z") {
        void performAction("undo");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [
    blockedOnUnread,
    canApprove,
    materialRead,
    performAction,
    questions.length,
  ]);

  const pageIndex = Math.max(0, (selectedQuestion?.page ?? 1) - 1);
  const pageState =
    loadState.status === "ready" ? loadState.pages[pageIndex] : null;

  return (
    <ShellScreen title="添削レビュー">
      <div className="mb-md">
        <BackOrHomeButton />
      </div>

      {loadState.status === "loading" ? (
        <p className="text-body-medium">読み込み中…</p>
      ) : null}
      {loadState.status === "error" ? (
        <p className="text-body-medium text-error">{loadState.message}</p>
      ) : null}

      {loadState.status === "ready" ? (
        <div className="flex flex-col gap-lg">
          {dagLayout != null ? (
            <DependencyDagPanel
              layout={dagLayout}
              selectedQuestionId={selectedQuestion?.id ?? null}
              onQuestionSelected={(questionId) => {
                const index = questions.findIndex((q) => q.id === questionId);
                if (index >= 0) {
                  setSelectedIndex(index);
                }
              }}
            />
          ) : null}

          <div className="flex gap-lg">
            <nav
              data-testid="review-question-rail"
              className="flex w-40 shrink-0 flex-col gap-xs"
              aria-label="設問一覧"
            >
              {questions.map((question, index) => {
                const job =
                  jobs.find((j) => j.question_id === question.id) ?? null;
                const review = reviewsByQuestion[question.id] ?? null;
                const status = deriveQuestionStatus({
                  job,
                  review,
                  hasWaitingDependents: jobs.some(
                    (j) => j.blocked_on_question_id === question.id,
                  ),
                });
                const wait = resolveQuestionWait(question.id, {
                  blockedOn: (id) =>
                    jobs.find((j) => j.question_id === id)
                      ?.blocked_on_question_id ?? null,
                  statusOf: (id) => {
                    const j =
                      jobs.find((item) => item.question_id === id) ?? null;
                    const r = reviewsByQuestion[id] ?? null;
                    return deriveQuestionStatus({
                      job: j,
                      review: r,
                      hasWaitingDependents: jobs.some(
                        (item) => item.blocked_on_question_id === id,
                      ),
                    });
                  },
                  numberOf: (id) =>
                    questions.find((q) => q.id === id)?.number ?? null,
                });
                const label = labelWaitingFor(status, wait);
                return (
                  <button
                    key={question.id}
                    type="button"
                    data-testid={`review-rail-${question.id}`}
                    className={`rounded-md border px-sm py-xs text-left text-ui-label ${
                      index === selectedIndex
                        ? "border-primary"
                        : "border-outline-variant"
                    }`}
                    aria-label={`問${question.number} ${label}`}
                    title={label}
                    onClick={() => {
                      setSelectedIndex(index);
                    }}
                  >
                    <span aria-hidden>{statusIcon(status)}</span>
                    <span> 問{question.number}</span>
                  </button>
                );
              })}
            </nav>

            <div className="min-w-0 flex-1">
              {pageState != null ? (
                <PageImageViewer
                  pageImage={pageState.image}
                  displayedWidth={pageState.geometry.displayed_width}
                  displayedHeight={pageState.geometry.displayed_height}
                  annotations={selectedAnnotations}
                  recognitions={selectedRecognitions}
                  questionAnswerArea={selectedQuestion?.answer_area}
                  zoom={zoom}
                />
              ) : null}
              <div className="mt-sm flex gap-sm">
                <button
                  type="button"
                  className="rounded-md border border-outline px-md py-xs"
                  onClick={() => {
                    setZoom((value) => Math.max(1, value - 0.5));
                  }}
                >
                  縮小
                </button>
                <button
                  type="button"
                  className="rounded-md border border-outline px-md py-xs"
                  onClick={() => {
                    setZoom((value) => value + 0.5);
                  }}
                >
                  拡大
                </button>
              </div>
            </div>

            <aside
              ref={inspectorRef}
              data-testid="review-inspector"
              className="flex w-80 shrink-0 flex-col gap-md overflow-y-auto max-h-[80vh] border border-outline-variant rounded-md p-md"
            >
              <div data-testid="review-question-state">
                <span className="text-body-medium">
                  問{selectedQuestion?.number ?? ""}{" "}
                  {labelWaitingFor(selectedStatus, selectedWait)}
                </span>
              </div>

              {blockedOnUnread ? (
                <div
                  data-testid="review-unread-material-notice"
                  className="rounded-md border border-attention/40 bg-attention-container/20 p-sm text-body-small"
                >
                  判断材料が画面外に残っています。すべて読んでから承認してください。
                  <button
                    type="button"
                    data-testid="review-reveal-material-button"
                    className="mt-xs block text-ui-label underline"
                    onClick={materialRead.revealRest}
                  >
                    続きを表示
                  </button>
                </div>
              ) : null}

              {selectedGrade != null ? (
                <div
                  data-testid="review-score"
                  className="flex flex-col gap-sm"
                >
                  <p className="text-title-small font-medium">
                    {selectedGrade.score.awarded} /{" "}
                    {selectedGrade.score.maximum} 点
                  </p>
                  {selectedGrade.answer_image_finding === "blank" ? (
                    <p
                      data-testid="review-answer-image-blank"
                      className="text-body-medium"
                    >
                      AIは、解答欄に何も書かれていないと報告しました。本当に無記入ならこの0点は正しく、切り出しがずれている場合はテスト設定の回答欄を見直してください。
                    </p>
                  ) : null}
                  {selectedRecognitions[0] != null ? (
                    <ConfidenceBadge
                      label="OCR文字認識信頼度"
                      confidence={selectedRecognitions[0].confidence}
                      testId="review-recognition-confidence"
                    />
                  ) : null}
                  <ConfidenceBadge
                    label="採点信頼度"
                    confidence={selectedGrade.confidence}
                    testId="review-grading-confidence"
                  />
                  {materialRows.map((row) => (
                    <MaterialRowView
                      key={row.id}
                      row={row}
                      grade={selectedGrade}
                      onRegister={materialRead.registerRowMarkers}
                    />
                  ))}
                </div>
              ) : null}

              <AnswerCropView imageUrl={answerImageUrl} />

              <label className="flex flex-col gap-xs">
                <span className="text-ui-label">メモ</span>
                <textarea
                  data-testid="review-note-field"
                  className="min-h-20 rounded-md border border-outline px-sm py-xs"
                  value={note}
                  onChange={(event) => {
                    setNote(event.target.value);
                  }}
                />
              </label>

              <div className="flex flex-wrap gap-sm">
                <button
                  type="button"
                  data-testid="review-approve-button"
                  className="rounded-md bg-primary px-md py-xs text-on-primary disabled:opacity-50"
                  disabled={!canApprove}
                  onClick={() => {
                    void performAction("approve");
                  }}
                >
                  承認
                </button>
                <button
                  type="button"
                  data-testid="review-reject-button"
                  className="rounded-md border border-outline px-md py-xs"
                  disabled={busy}
                  onClick={() => {
                    void performAction("reject");
                  }}
                >
                  却下
                </button>
                <button
                  type="button"
                  data-testid="review-regrade-button"
                  className="rounded-md border border-outline px-md py-xs"
                  disabled={busy}
                  onClick={() => {
                    void performAction("regrade");
                  }}
                >
                  再判定
                </button>
                <button
                  type="button"
                  data-testid="review-undo-button"
                  className="rounded-md border border-outline px-md py-xs"
                  disabled={busy}
                  onClick={() => {
                    void performAction("undo");
                  }}
                >
                  取り消し
                </button>
              </div>
            </aside>
          </div>

          {materialRead.snackbarMessage != null ? (
            <div
              role="status"
              data-testid="review-snackbar"
              className="fixed bottom-lg left-1/2 -translate-x-1/2 rounded-md bg-inverse-surface px-lg py-md text-inverse-on-surface"
            >
              {materialRead.snackbarMessage}
            </div>
          ) : null}
        </div>
      ) : null}
    </ShellScreen>
  );
}

function MaterialRowView({
  row,
  grade,
  onRegister,
}: {
  row: MaterialRow;
  grade: NonNullable<ReturnType<typeof displayGrade>>;
  onRegister: (rowId: string, top: HTMLElement, bottom: HTMLElement) => void;
}): JSX.Element | null {
  const topRef = useRef<HTMLSpanElement>(null);
  const bottomRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (topRef.current != null && bottomRef.current != null) {
      onRegister(row.id, topRef.current, bottomRef.current);
    }
  }, [onRegister, row.id]);

  if (row.id.startsWith("criterion:")) {
    const criterionId = row.id.slice("criterion:".length);
    const criterion = grade.criteria.find(
      (c) => c.criterion_id === criterionId,
    );
    if (criterion == null) {
      return null;
    }
    return (
      <div data-material-row-id={row.id} className="text-body-small">
        <span ref={topRef} className="block h-0" aria-hidden />
        <p>{criterion.outcome}</p>
        <span ref={bottomRef} className="block h-0" aria-hidden />
      </div>
    );
  }

  return (
    <div data-material-row-id={row.id} className="text-body-small">
      <span ref={topRef} className="block h-0" aria-hidden />
      <p>{grade.rationale ?? grade.comment ?? "採点結果"}</p>
      <span ref={bottomRef} className="block h-0" aria-hidden />
    </div>
  );
}
