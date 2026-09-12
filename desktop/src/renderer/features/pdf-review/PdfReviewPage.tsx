import {
  useCallback,
  useEffect,
  useLayoutEffect,
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
} from "../../core/pdf-review-data.js";
import { useSidecarClient } from "../../api/SidecarApiProvider.js";
import {
  buildDependencyDagLayout,
  deriveStatusesFromJobs,
  releasesDependents,
} from "../../core/dependency-dag.js";
import { sortQuestionsForReview } from "../../core/question-order.js";
import {
  ActionRequirements,
  reviewApproveRequirements,
} from "../../core/action-requirements.js";
import {
  deriveQuestionStatus,
  jobIsInProgress,
  labelWaitingFor,
  latestJobFor,
  resolveQuestionWait,
} from "../../core/question-status.js";
import { QuestionStatusBadge } from "../../core/QuestionStatusBadge.js";
import {
  annotationsForDisplayedAttempt,
  displayGrade,
  expectedReviewVersion,
  recognitionsForDisplayedAttempt,
} from "../../core/question-review-state.js";
import {
  hasNoRoomForScore,
  scoreOverlay as buildScoreOverlay,
} from "../../core/export-parity.js";
import {
  unreadableBoxesFromOcr,
  latestOcrRecognition,
} from "../../core/unreadable-spans.js";
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
  type MaterialRowsInput,
} from "./use-material-read-tracking.js";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      pages: readonly SubmissionPageState[];
      questionData: Map<string, QuestionReviewData>;
    };

const ENTER_ACTIVATES_LOCALLY =
  'button, a[href], input, textarea, select, [role="button"], [contenteditable="true"]';

const CARD_CLASS = "min-w-0 rounded-xl bg-surface-container p-lg";

const BUTTON_PRIMARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-primary px-md py-sm text-ui-label font-medium text-on-primary hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

const BUTTON_SECONDARY_CLASS =
  "inline-flex items-center gap-xs rounded-md bg-surface-container-high px-md py-sm text-ui-label font-medium text-on-surface hover:bg-surface-container-highest focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary active:opacity-80 disabled:opacity-50";

/**
 * Enter on a focused control belongs to that control, not the page (Issue #196).
 *
 * The page-wide listener below runs wherever focus is, so without this guard
 * Tab-ing to 却下/再判定/取り消し/続きを表示/戻る and pressing Enter would approve
 * the question instead of running the button the reviewer actually reached.
 * Returning early leaves the key to the browser's own activation.
 */
function enterActivatesLocally(target: EventTarget | null): boolean {
  return (
    target instanceof Element && target.closest(ENTER_ACTIVATES_LOCALLY) != null
  );
}

/**
 * How often the review screen re-reads the job list while grading is still in
 * flight (Issue #319).
 *
 * 2s is fast enough that a reviewer sees the approval unlock "by itself" as
 * soon as the job lands (the live run measured a 32s job), and slow enough
 * that it does not flood the single-worker sidecar. See
 * `docs/pdf-review-overlay.md` §2.16 for why these values.
 */
export const JOB_POLL_INTERVAL_MS = 2000;

/**
 * Stop following automatically after this many polls -- 5 minutes at
 * {@link JOB_POLL_INTERVAL_MS} -- and tell the reviewer to reload instead.
 */
export const JOB_POLL_MAX_ATTEMPTS = 150;

/**
 * Space below the review workspace: the app shell's `p-xl` plus this screen's
 * `main` `pb-xl` (2 x `--spacing-xl`, 48px). Subtracting it when fitting the
 * workspace to the viewport leaves the document with no window scrollbar, so
 * the 設問レール and 採点パネル stay on screen when the answer is zoomed
 * (Issue #401).
 */
const REVIEW_WORKSPACE_BOTTOM_INSET = 48;

/**
 * The width at which the three review panes sit side by side. This is
 * Tailwind's `lg` (64rem at the 16px root), matching the `lg:flex-row` below.
 * Below it the panes stack and the viewport fit is not applied (Issue #401).
 */
const REVIEW_WORKSPACE_SIDE_BY_SIDE = "(min-width: 1024px)";

/**
 * The height the three-pane workspace should take, or `null` when it must size
 * to its content instead (Issue #401).
 *
 * Side by side, the workspace fills the viewport from its own top (in document
 * coordinates) down to {@link REVIEW_WORKSPACE_BOTTOM_INSET}, which is what
 * keeps the 設問レール and 採点パネル on screen while the page region scrolls.
 * When the panes stack, there is no single row to fit, so the caller leaves the
 * height unset.
 */
export function resolveWorkspaceHeight(input: {
  readonly viewportHeight: number;
  /**
   * The workspace's top from `getBoundingClientRect()`, i.e. relative to the
   * viewport. Pass the page scroll as {@link scrollY} too so the two cancel
   * out: measuring against the viewport alone reads the workspace as one
   * scroll-offset taller than it is once the document has scrolled (Issue
   * #422).
   */
  readonly workspaceTop: number;
  readonly scrollY?: number;
  readonly sideBySide: boolean;
}): number | null {
  if (!input.sideBySide) {
    return null;
  }
  const workspaceTop = input.workspaceTop + (input.scrollY ?? 0);
  const available =
    input.viewportHeight - workspaceTop - REVIEW_WORKSPACE_BOTTOM_INSET;
  return available > 0 ? available : null;
}

/**
 * The bare question number (`1`) whether the stored value is `1` or `問1`.
 *
 * Question numbers are stored with their prefix (`問1`), but some callers and
 * tests use the bare form (`1`). Display sites add `問` themselves and
 * `labelWaitingFor` adds it too, so an unconditional prepend produced `問問1`
 * on screen. Stripping here keeps every path at one prefix.
 */
function questionNumberValue(number: string | null | undefined): string {
  if (number == null || number.length === 0) {
    return "";
  }
  return number.startsWith("問") ? number.slice(1) : number;
}

export function PdfReviewPage(): JSX.Element {
  const client = useSidecarClient();
  const { params } = useRouter();
  const testId = params.testId ?? "";
  const submissionId = params.submissionId ?? "";
  const initialQuestionId = params.questionId;

  const mounted = useMountedRef();
  const inspectorRef = useRef<HTMLDivElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const pollAttemptsRef = useRef(0);
  const [workspaceHeight, setWorkspaceHeight] = useState<number | null>(null);
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
  const [regradePending, setRegradePending] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pageIndex, setPageIndex] = useState(0);
  const [jobsRefreshStalled, setJobsRefreshStalled] = useState(false);

  const selectedQuestion = questions[selectedIndex] ?? null;

  const materialCoverage = useMemo((): MaterialRowsInput => {
    if (loadState.status !== "ready" || selectedQuestion == null) {
      return { status: "unknown" };
    }
    const data = loadState.questionData.get(selectedQuestion.id);
    if (data == null) {
      return { status: "unknown" };
    }
    const grade = displayGrade(data.grades ?? [], data.reviews ?? []);
    const rows: MaterialRow[] = [];
    if (grade != null) {
      rows.push({ id: `grade:${grade.id}` });
      for (const criterion of grade.criteria) {
        rows.push({ id: `criterion:${criterion.criterion_id}` });
      }
    }
    return { status: "known", rows };
  }, [loadState, selectedQuestion]);

  const materialRows =
    materialCoverage.status === "known" ? materialCoverage.rows : [];

  const materialRead = useMaterialReadTracking(materialCoverage, inspectorRef);

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

  /**
   * Re-read one question's material and answer crop.
   *
   * `reportError` distinguishes the reviewer opening a question (a failure
   * belongs on screen) from a background refresh after grading finished (a
   * single failed poll must not blank the whole page).
   */
  const fetchQuestionData = useCallback(
    async (questionId: string, reportError: boolean): Promise<void> => {
      try {
        const [data, imageUrl] = await Promise.all([
          loadQuestionReviewData(client, submissionId, questionId),
          loadAnswerImageUrl(client, submissionId, questionId),
        ]);
        setStateIfMounted(mounted, setAnswerImageUrl, imageUrl);
        setStateIfMounted(mounted, setLoadState, (current) => {
          if (current.status !== "ready") {
            return current;
          }
          const next = new Map(current.questionData);
          next.set(questionId, data);
          return { ...current, questionData: next };
        });
      } catch (error) {
        if (!reportError) {
          return;
        }
        const message =
          error instanceof PdfReviewDataError
            ? error.message
            : error instanceof Error
              ? error.message
              : String(error);
        setStateIfMounted(mounted, setLoadState, { status: "error", message });
      }
    },
    [client, mounted, submissionId],
  );

  const loadSelectedQuestion = useCallback(async () => {
    if (selectedQuestion == null || loadState.status !== "ready") {
      return;
    }
    if (loadState.questionData.has(selectedQuestion.id)) {
      return;
    }
    await fetchQuestionData(selectedQuestion.id, true);
  }, [fetchQuestionData, loadState, selectedQuestion]);

  const pollJobs = useCallback(async (): Promise<void> => {
    let refreshed: Awaited<ReturnType<typeof loadJobs>>;
    try {
      refreshed = await loadJobs(client, submissionId);
    } catch {
      // A failed poll is exactly the "we can no longer see the jobs" case the
      // stale notice exists for; keep the last known list on screen.
      setStateIfMounted(mounted, setJobsRefreshStalled, true);
      return;
    }
    const previouslyRunning = new Set(
      jobs.filter(jobIsInProgress).map((job) => job.question_id),
    );
    setStateIfMounted(mounted, setJobs, refreshed);
    const finishedQuestionIds = new Set<string>();
    for (const job of refreshed) {
      if (
        job.question_id != null &&
        !jobIsInProgress(job) &&
        previouslyRunning.has(job.question_id)
      ) {
        finishedQuestionIds.add(job.question_id);
      }
    }
    for (const questionId of finishedQuestionIds) {
      await fetchQuestionData(questionId, false);
    }
  }, [client, fetchQuestionData, jobs, mounted, submissionId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    void loadSelectedQuestion();
  }, [loadSelectedQuestion]);

  /**
   * Jump the page viewer to the selected question's page (Issue #385).
   *
   * The viewer no longer *belongs* to the question: `pageIndex` is its own
   * state so the reviewer can flip pages directly, and the viewer stays on
   * screen when no question is selected. This effect only moves it when the
   * selected question changes, so a manual flip is never reverted by an
   * unrelated re-render.
   */
  useEffect(() => {
    if (selectedQuestion == null) {
      return;
    }
    setPageIndex(Math.max(0, (selectedQuestion.page ?? 1) - 1));
  }, [selectedQuestion?.id, selectedQuestion?.page]);

  const hasJobsInProgress = jobs.some(jobIsInProgress);

  useEffect(() => {
    if (loadState.status !== "ready" || !hasJobsInProgress) {
      pollAttemptsRef.current = 0;
      return undefined;
    }
    if (jobsRefreshStalled) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      pollAttemptsRef.current += 1;
      if (pollAttemptsRef.current >= JOB_POLL_MAX_ATTEMPTS) {
        setStateIfMounted(mounted, setJobsRefreshStalled, true);
        return;
      }
      void pollJobs();
    }, JOB_POLL_INTERVAL_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [
    hasJobsInProgress,
    jobs,
    jobsRefreshStalled,
    loadState.status,
    mounted,
    pollJobs,
  ]);

  /**
   * Fit the three-pane workspace to the rest of the viewport (Issue #401).
   *
   * The page title, question card, and DAG panel sit above the workspace and
   * CSS does not know their combined height, so the workspace is sized to the
   * space left below its own top. This is done in document coordinates: the
   * old viewport-relative `getBoundingClientRect().top` made the workspace look
   * one scroll-offset taller whenever the document was scrolled, which kept the
   * document scrollable and pinned it (Issue #422). `window.scrollY` cancels
   * out as long as both sides are document-absolute.
   *
   * The 採点不可バナー is mounted by an ancestor and changes the frame height
   * with no change to the `document.body` box, so a `ResizeObserver` on the
   * body alone would miss it. A `MutationObserver` on the body re-measures when
   * the band (or anything else) is inserted or removed.
   *
   * The height is applied only when the panes are side by side; when they
   * stack, the page scrolls as before and only the page region reacts to zoom.
   */
  useLayoutEffect(() => {
    if (loadState.status !== "ready") {
      setWorkspaceHeight(null);
      return undefined;
    }
    const workspace = workspaceRef.current;
    if (workspace == null) {
      return undefined;
    }
    let frame = 0;
    const measure = () => {
      const rect = workspace.getBoundingClientRect();
      setWorkspaceHeight(
        resolveWorkspaceHeight({
          viewportHeight: window.innerHeight,
          workspaceTop: rect.top,
          scrollY: window.scrollY,
          sideBySide:
            typeof window.matchMedia === "function" &&
            window.matchMedia(REVIEW_WORKSPACE_SIDE_BY_SIDE).matches,
        }),
      );
    };
    const schedule = () => {
      if (frame !== 0) {
        return;
      }
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        measure();
      });
    };
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(document.body);
    const mutations = new MutationObserver(schedule);
    mutations.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      mutations.disconnect();
      if (frame !== 0) {
        window.cancelAnimationFrame(frame);
      }
      window.removeEventListener("resize", measure);
    };
  }, [loadState.status]);

  const reloadReview = useCallback(async () => {
    pollAttemptsRef.current = 0;
    setJobsRefreshStalled(false);
    await reload();
  }, [reload]);

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
        questions: questions.map((q) => ({
          id: q.id,
          label: questionNumberValue(q.number),
        })),
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
  const selectedPlacement = selectedQuestion?.score_placement ?? null;
  const selectedScoreOverlay = buildScoreOverlay({
    placement: selectedPlacement,
    grade: selectedGrade,
    questionNumber: selectedQuestion?.number ?? "",
  });
  const selectedNoRoomForScore = hasNoRoomForScore(selectedPlacement);
  const unreadableBoxes = unreadableBoxesFromOcr(selectedRecognitions);
  const ocrRecognition = latestOcrRecognition(selectedRecognitions);

  const selectedJob =
    selectedQuestion == null ? null : latestJobFor(jobs, selectedQuestion.id);
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
          latestJobFor(jobs, id)?.blocked_on_question_id ?? null,
        statusOf: (id) => {
          const job = latestJobFor(jobs, id);
          const review = reviewsByQuestion[id] ?? null;
          return deriveQuestionStatus({
            job,
            review,
            hasWaitingDependents: jobs.some(
              (j) => j.blocked_on_question_id === id,
            ),
          });
        },
        numberOf: (id) => {
          const number = questions.find((q) => q.id === id)?.number;
          return number == null ? null : questionNumberValue(number);
        },
      })
    : null;

  const canApprove =
    materialRead.allRowsCovered && selectedStatus === "graded" && !busy;
  const blockedOnUnread = !materialRead.allRowsCovered;
  const gradingInProgress =
    selectedStatus === "queued" ||
    selectedStatus === "running" ||
    selectedStatus === "blocked";
  const approveBlockedReason = canApprove
    ? null
    : (reviewApproveRequirements({ busy, gradingInProgress })[0] ?? null);

  /**
   * Feedback that the 再判定 request is being carried out (Issue #402).
   *
   * A regrade is the one review action whose completion is not a new `Review`
   * row, so the question's own status is the only signal -- and until the
   * replacement job shows up it is easy to read the screen as "nothing
   * happened". `regradePending` covers the moment between the press and the
   * job appearing; the second half covers the whole run, including a fresh
   * visit to the question while it is still going.
   */
  const regradeInFlight =
    regradePending ||
    (selectedReview?.action === "regrade_requested" && gradingInProgress);

  const performAction = useCallback(
    async (action: "approve" | "reject" | "regrade" | "undo") => {
      if (selectedQuestion == null || selectedData == null) {
        return;
      }
      setBusy(true);
      if (action === "regrade") {
        setStateIfMounted(mounted, setRegradePending, true);
      }
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
        setStateIfMounted(mounted, setRegradePending, false);
      }
    },
    [client, mounted, note, selectedData, selectedQuestion, submissionId],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Enter" && !event.ctrlKey && !event.metaKey) {
        if (enterActivatesLocally(event.target)) {
          return;
        }
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

  const pageCount = loadState.status === "ready" ? loadState.pages.length : 0;
  const currentPageIndex =
    pageCount === 0 ? 0 : Math.min(pageIndex, pageCount - 1);
  const pageState =
    loadState.status === "ready"
      ? (loadState.pages[currentPageIndex] ?? null)
      : null;

  return (
    <ShellScreen title="添削レビュー">
      {loadState.status === "loading" ? (
        <section
          aria-busy="true"
          aria-live="polite"
          className={`${CARD_CLASS} animate-pulse`}
        >
          <p className="text-body-medium text-on-surface-variant">
            読み込み中…
          </p>
          <div className="mt-md h-5 w-40 rounded-md bg-surface-container-high" />
          <div className="mt-lg h-40 w-full rounded-md bg-surface-container-high" />
          <div className="mt-md h-4 w-2/3 rounded-md bg-surface-container-high" />
        </section>
      ) : null}
      {loadState.status === "error" ? (
        <section
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
              void reloadReview();
            }}
          >
            再読み込み
          </button>
        </section>
      ) : null}

      {loadState.status === "ready" ? (
        <div className="flex min-w-0 flex-col gap-lg">
          <section
            className={`${CARD_CLASS} flex flex-wrap items-center justify-between gap-md`}
          >
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-on-surface">
                問{questionNumberValue(selectedQuestion?.number)}{" "}
                {labelWaitingFor(selectedStatus, selectedWait)}
              </h2>
              <p className="mt-xs text-body-medium text-on-surface-variant">
                設問ごとに判断材料を確認し、承認します
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-sm">
              {jobsRefreshStalled ? (
                <p
                  data-testid="review-refresh-stale-notice"
                  className="rounded-full bg-attention-container px-sm py-xs text-xs text-on-attention-container"
                >
                  {ActionRequirements.gradingStatusStale.message}
                </p>
              ) : null}
              <button
                type="button"
                data-testid="review-open-materials-button"
                className={BUTTON_SECONDARY_CLASS}
                onClick={() => {
                  void window.autoScoring?.openMaterialWindow({ testId });
                }}
              >
                資料を開く
              </button>
              <button
                type="button"
                data-testid="review-refresh-button"
                className={BUTTON_SECONDARY_CLASS}
                disabled={busy}
                onClick={() => {
                  void reloadReview();
                }}
              >
                再読み込み
              </button>
            </div>
          </section>

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

          <div
            ref={workspaceRef}
            style={
              workspaceHeight == null ? undefined : { height: workspaceHeight }
            }
            className="flex min-w-0 flex-col gap-lg lg:flex-row"
          >
            <nav
              data-testid="review-question-rail"
              className="flex max-h-inspector w-full shrink-0 flex-wrap gap-xs overflow-y-auto rounded-xl bg-surface-container p-sm lg:w-52 lg:flex-col"
              aria-label="設問一覧"
            >
              {questions.map((question, index) => {
                const job = latestJobFor(jobs, question.id);
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
                    latestJobFor(jobs, id)?.blocked_on_question_id ?? null,
                  statusOf: (id) => {
                    const j = latestJobFor(jobs, id);
                    const r = reviewsByQuestion[id] ?? null;
                    return deriveQuestionStatus({
                      job: j,
                      review: r,
                      hasWaitingDependents: jobs.some(
                        (item) => item.blocked_on_question_id === id,
                      ),
                    });
                  },
                  numberOf: (id) => {
                    const number = questions.find((q) => q.id === id)?.number;
                    return number == null ? null : questionNumberValue(number);
                  },
                });
                const label = labelWaitingFor(status, wait);
                const displayNumber = questionNumberValue(question.number);
                const noRoomForScore = hasNoRoomForScore(
                  question.score_placement,
                );
                const railLabel = noRoomForScore
                  ? `問${displayNumber} ${label} 点数の余白なし`
                  : `問${displayNumber} ${label}`;
                return (
                  <button
                    key={question.id}
                    type="button"
                    data-testid={`review-rail-${question.id}`}
                    data-no-room-for-score={noRoomForScore ? "true" : undefined}
                    className={`rounded-lg px-sm py-xs text-left text-ui-label ${
                      index === selectedIndex
                        ? "border border-primary bg-surface-container-high text-on-surface"
                        : "bg-surface-container-high text-on-surface-variant hover:bg-surface-container-highest"
                    }`}
                    aria-label={railLabel}
                    title={label}
                    onClick={() => {
                      setSelectedIndex(index);
                    }}
                  >
                    <QuestionStatusBadge status={status} />
                    <span> 問{displayNumber}</span>
                    {noRoomForScore ? (
                      <span
                        data-testid={`review-rail-no-room-${question.id}`}
                        className="mt-xs block rounded-full bg-attention-container px-sm text-xs text-on-attention-container"
                      >
                        点数の余白なし
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </nav>

            <div className="flex min-w-0 flex-1 flex-col lg:min-h-0">
              <div className="mb-sm flex shrink-0 flex-wrap items-center gap-sm">
                <button
                  type="button"
                  data-testid="review-page-prev"
                  aria-label="前のページ"
                  className={BUTTON_SECONDARY_CLASS}
                  disabled={pageCount === 0 || currentPageIndex <= 0}
                  onClick={() => {
                    setPageIndex((value) => Math.max(0, value - 1));
                  }}
                >
                  前のページ
                </button>
                <span
                  data-testid="review-page-indicator"
                  aria-live="polite"
                  className="text-ui-label text-on-surface-variant"
                >
                  {pageCount === 0
                    ? "0 / 0"
                    : `${currentPageIndex + 1} / ${pageCount}`}
                </span>
                <button
                  type="button"
                  data-testid="review-page-next"
                  aria-label="次のページ"
                  className={BUTTON_SECONDARY_CLASS}
                  disabled={
                    pageCount === 0 || currentPageIndex >= pageCount - 1
                  }
                  onClick={() => {
                    setPageIndex((value) => Math.min(pageCount - 1, value + 1));
                  }}
                >
                  次のページ
                </button>
                <span
                  className="mx-xs h-6 w-px bg-outline-variant"
                  aria-hidden
                />
                <button
                  type="button"
                  data-testid="review-zoom-out"
                  className={BUTTON_SECONDARY_CLASS}
                  onClick={() => {
                    setZoom((value) => Math.max(1, value - 0.5));
                  }}
                >
                  縮小
                </button>
                <button
                  type="button"
                  data-testid="review-zoom-in"
                  className={BUTTON_SECONDARY_CLASS}
                  onClick={() => {
                    setZoom((value) => value + 0.5);
                  }}
                >
                  拡大
                </button>
              </div>
              <div
                data-testid="review-page-region"
                className="max-h-inspector min-w-0 overflow-auto rounded-xl bg-surface-container-low p-sm lg:min-h-0 lg:flex-1"
              >
                {pageState != null ? (
                  <PageImageViewer
                    pageImage={pageState.image}
                    displayedWidth={pageState.geometry.displayed_width}
                    displayedHeight={pageState.geometry.displayed_height}
                    annotations={selectedAnnotations}
                    recognitions={selectedRecognitions}
                    questionAnswerArea={selectedQuestion?.answer_area}
                    scoreOverlay={selectedScoreOverlay}
                    questionCommentArea={selectedQuestion?.comment_area}
                    questionPage={selectedQuestion?.page}
                    questionNumber={selectedQuestion?.number}
                    zoom={zoom}
                  />
                ) : (
                  <div
                    data-testid="review-page-unavailable"
                    role="status"
                    className="flex min-h-40 items-center justify-center px-md py-lg text-center text-body-medium text-on-surface-variant"
                  >
                    {pageCount === 0
                      ? "答案ページがありません。答案の取り込みが完了しているか確認してください。"
                      : "このページを表示できませんでした。前後のページへ移動してください。"}
                  </div>
                )}
              </div>
            </div>

            <aside
              ref={inspectorRef}
              data-testid="review-inspector"
              className="flex w-full shrink-0 flex-col gap-md overflow-y-auto max-h-inspector rounded-xl bg-surface-container p-lg lg:w-80"
            >
              <div
                data-testid="review-question-state"
                className="flex flex-wrap items-center gap-sm"
              >
                <span className="text-base font-semibold text-on-surface">
                  問{questionNumberValue(selectedQuestion?.number)}{" "}
                  {labelWaitingFor(selectedStatus, selectedWait)}
                </span>
              </div>

              {selectedNoRoomForScore ? (
                <div
                  role="alert"
                  data-testid="review-no-room-for-score"
                  className="flex items-start gap-sm rounded-lg bg-attention-container px-md py-sm text-body-medium text-on-attention-container"
                >
                  <span
                    aria-hidden
                    className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary font-semibold text-on-primary"
                  >
                    !
                  </span>
                  <span className="min-w-0 flex-1">
                    この設問の点数を書き込める余白がページにありません。
                    この答案はPDF出力できません（確定しても解消しません）。
                  </span>
                </div>
              ) : null}

              {regradeInFlight ? (
                <p
                  role="status"
                  data-testid="review-regrade-in-progress"
                  className="rounded-lg bg-surface-container-high px-md py-sm text-body-medium text-on-surface-variant"
                >
                  再判定中です。AIの処理が終わると、この画面は自動で更新されます。
                </p>
              ) : null}

              {blockedOnUnread ? (
                <div
                  data-testid="review-unread-material-notice"
                  data-tone="attention"
                  className="flex items-start gap-sm rounded-lg bg-attention-container px-md py-sm text-body-medium text-on-attention-container"
                >
                  <span
                    aria-hidden
                    className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary font-semibold text-on-primary"
                  >
                    !
                  </span>
                  <span className="min-w-0 flex-1">
                    判断材料が画面外に残っています。すべて読んでから承認してください。
                    <button
                      type="button"
                      data-testid="review-reveal-material-button"
                      className="mt-xs block text-ui-label underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                      onClick={materialRead.revealRest}
                    >
                      続きを表示
                    </button>
                  </span>
                </div>
              ) : null}

              {selectedGrade != null ? (
                <div
                  data-testid="review-score"
                  className="flex flex-col gap-sm"
                >
                  <p className="text-role-score font-semibold text-on-surface">
                    {selectedGrade.score.awarded} /{" "}
                    {selectedGrade.score.maximum} 点
                  </p>
                  {selectedGrade.answer_image_finding === "blank" ? (
                    <p
                      data-testid="review-answer-image-blank"
                      className="rounded-lg bg-surface-container-high px-md py-sm text-body-medium text-on-surface-variant"
                    >
                      AIは、解答欄に何も書かれていないと報告しました。本当に無記入ならこの0点は正しく、切り出しがずれている場合はテスト設定の回答欄を見直してください。
                    </p>
                  ) : null}
                  {unreadableBoxes.length > 0 ? (
                    <div
                      data-testid="review-unreadable-spans-notice"
                      className="rounded-lg bg-attention-container px-md py-sm text-body-medium text-on-attention-container"
                    >
                      OCRが読めなかった箇所が {unreadableBoxes.length}{" "}
                      か所あります（空欄とは別です）。切り出し画像のハイライトと、下の一覧で位置を確認してください。
                      <ul className="mt-xs list-disc pl-lg">
                        {unreadableBoxes.map((box, index) => (
                          <li
                            key={`${box.x}-${box.y}-${index}`}
                            data-testid={`review-unreadable-span-${index}`}
                          >
                            {index + 1} 番目の語
                            {box.text.length > 0 ? `（${box.text}）` : ""}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {ocrRecognition != null ? (
                    <ConfidenceBadge
                      label="OCR文字認識信頼度"
                      confidence={ocrRecognition.confidence}
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

              <AnswerCropView
                imageUrl={answerImageUrl}
                unreadableBoxes={unreadableBoxes}
              />

              <label className="flex flex-col gap-xs">
                <span className="text-ui-label font-medium text-on-surface">
                  メモ
                </span>
                <textarea
                  data-testid="review-note-field"
                  className="min-h-20 rounded-md bg-surface-container-high px-sm py-xs text-body-medium text-on-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
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
                  className={BUTTON_PRIMARY_CLASS}
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
                  className={BUTTON_SECONDARY_CLASS}
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
                  className={BUTTON_SECONDARY_CLASS}
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
                  className={BUTTON_SECONDARY_CLASS}
                  disabled={busy}
                  onClick={() => {
                    void performAction("undo");
                  }}
                >
                  取り消し
                </button>
              </div>

              {approveBlockedReason != null ? (
                <p
                  data-testid="review-approve-reason"
                  data-requirement-id={approveBlockedReason.id}
                  className="rounded-lg bg-surface-container-high px-md py-sm text-body-medium text-on-surface-variant"
                >
                  {approveBlockedReason.message}
                </p>
              ) : null}
            </aside>
          </div>

          {materialRead.snackbarMessage != null ? (
            <div
              role="status"
              data-testid="review-snackbar"
              className="fixed bottom-lg left-1/2 -translate-x-1/2 rounded-xl bg-inverse-surface px-lg py-md text-body-medium text-inverse-on-surface"
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
      <div data-material-row-id={row.id} className="text-sm">
        <span ref={topRef} className="block h-0" aria-hidden />
        <p>{criterion.outcome}</p>
        <span ref={bottomRef} className="block h-0" aria-hidden />
      </div>
    );
  }

  return (
    <div data-material-row-id={row.id} className="text-sm">
      <span ref={topRef} className="block h-0" aria-hidden />
      <p>{grade.rationale ?? grade.comment ?? "採点結果"}</p>
      <span ref={bottomRef} className="block h-0" aria-hidden />
    </div>
  );
}
