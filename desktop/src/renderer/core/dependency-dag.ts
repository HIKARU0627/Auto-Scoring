import type { components } from "../api/generated/schema.js";
import {
  dagFailureGuidance,
  type DagFailureGuidanceText,
} from "./dag-failure-guidance.js";
import {
  deriveQuestionStatus,
  labelWaitingFor,
  resolveQuestionWait,
  type QuestionStatusKey,
  type QuestionWait,
  type ReviewResponse,
} from "./question-status.js";

export type DependencyEdge = components["schemas"]["DependencyEdgeModel"];
export type JobResponse = components["schemas"]["JobResponse"];

export type DagNodeProgress =
  "waiting" | "running" | "needsCheck" | "failed" | "settled";

export const DagNodeProgressMeta: Record<
  DagNodeProgress,
  { label: string; meaning: string; needsAPerson: boolean }
> = {
  waiting: { label: "待機", meaning: "これから動くもの", needsAPerson: false },
  running: {
    label: "実行中",
    meaning: "いまAIが処理しているもの",
    needsAPerson: false,
  },
  needsCheck: {
    label: "要確認",
    meaning: "人が確認するまで下流が進まないもの",
    needsAPerson: true,
  },
  failed: {
    label: "失敗",
    meaning: "人が対応するまで進まないもの",
    needsAPerson: true,
  },
  settled: {
    label: "完了",
    meaning: "AI処理が終わり、人を待っていないもの",
    needsAPerson: false,
  },
};

const PROGRESS_ORDER: readonly DagNodeProgress[] = [
  "running",
  "waiting",
  "needsCheck",
  "failed",
  "settled",
];

export function dagNodeProgressOf(status: QuestionStatusKey): DagNodeProgress {
  switch (status) {
    case "pending":
    case "blocked":
    case "queued":
    case "regradeRequested":
      return "waiting";
    case "running":
      return "running";
    case "needsCheck":
      return "needsCheck";
    case "failed":
      return "failed";
    default:
      return "settled";
  }
}

export function releasesDependents(
  job: JobResponse | null | undefined,
): boolean {
  return job?.usable ?? false;
}

export function dependencyExecutionLayers(
  questionIds: readonly string[],
  edges: readonly DependencyEdge[],
): string[][] | null {
  const remainingInDegree = new Map<string, number>(
    questionIds.map((id) => [id, 0]),
  );
  const adjacency = new Map(
    questionIds.map((id) => [id, [] as string[]] as const),
  );
  for (const edge of edges) {
    const from = adjacency.get(edge.from_question_id);
    if (from == null || !remainingInDegree.has(edge.to_question_id)) {
      continue;
    }
    from.push(edge.to_question_id);
    remainingInDegree.set(
      edge.to_question_id,
      (remainingInDegree.get(edge.to_question_id) ?? 0) + 1,
    );
  }

  const placed = new Set<string>();
  const layers: string[][] = [];
  while (placed.size < questionIds.length) {
    const layer = questionIds
      .filter((id) => !placed.has(id) && remainingInDegree.get(id) === 0)
      .sort();
    if (layer.length === 0) {
      return null;
    }
    for (const id of layer) {
      placed.add(id);
    }
    for (const id of layer) {
      for (const neighbor of adjacency.get(id) ?? []) {
        remainingInDegree.set(
          neighbor,
          (remainingInDegree.get(neighbor) ?? 0) - 1,
        );
      }
    }
    layers.push(layer);
  }
  return layers;
}

export interface DagQuestion {
  readonly id: string;
  readonly label: string;
  readonly status: QuestionStatusKey;
  readonly blockedOnQuestionId?: string | null;
  readonly failure?: DagFailureGuidanceText | null;
}

export function buildDagQuestion(input: {
  id: string;
  label: string;
  status: QuestionStatusKey;
  blockedOnQuestionId?: string | null;
  lastError?: string | null;
  errorCode?: string | null;
}): DagQuestion {
  const failure =
    input.status === "failed"
      ? dagFailureGuidance({
          errorCode: input.errorCode ?? null,
          lastError: input.lastError ?? null,
        })
      : null;
  return {
    id: input.id,
    label: input.label,
    status: input.status,
    ...(input.blockedOnQuestionId !== undefined
      ? { blockedOnQuestionId: input.blockedOnQuestionId }
      : {}),
    failure,
  };
}

export interface LayoutRect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

export interface DagNode {
  readonly question: DagQuestion;
  readonly layer: number;
  readonly rect: LayoutRect;
  readonly waitingOn: QuestionWait | null;
  readonly statusLabel: string;
}

export interface DagEdgeLine {
  readonly fromQuestionId: string;
  readonly toQuestionId: string;
  readonly satisfied: boolean;
  readonly key: string;
}

export interface DagFailure {
  readonly openQuestionId: string;
  readonly questionLabels: readonly string[];
  readonly guidance: DagFailureGuidanceText;
  readonly stalledQuestionLabels: readonly string[];
  readonly headline: string;
}

export interface DependencyDagLayout {
  readonly nodes: readonly DagNode[];
  readonly edges: readonly DagEdgeLine[];
  readonly progressCounts: Readonly<Record<DagNodeProgress, number>>;
  readonly progressSummary: string;
  readonly failures: readonly DagFailure[];
  readonly statusById: Readonly<Record<string, QuestionStatusKey>>;
}

export interface DagMetrics {
  readonly nodeWidth: number;
  readonly nodeHeight: number;
  readonly columnGap: number;
  readonly rowGap: number;
  readonly padding: number;
}

export const DEFAULT_DAG_METRICS: DagMetrics = {
  nodeWidth: 120,
  nodeHeight: 56,
  columnGap: 48,
  rowGap: 16,
  padding: 16,
};

function rectAt(metrics: DagMetrics, layer: number, row: number): LayoutRect {
  return {
    left: metrics.padding + layer * (metrics.nodeWidth + metrics.columnGap),
    top: metrics.padding + row * (metrics.nodeHeight + metrics.rowGap),
    width: metrics.nodeWidth,
    height: metrics.nodeHeight,
  };
}

function formatQuestionNames(labels: readonly string[]): string {
  if (labels.length === 0) {
    return "";
  }
  const shown = 5;
  const named = labels
    .slice(0, shown)
    .map((n) => `問${n}`)
    .join("・");
  const rest = labels.length - shown;
  return rest > 0 ? `${named} ほか${rest}件` : named;
}

function buildFailures(nodes: readonly DagNode[]): DagFailure[] {
  const grouped = new Map<DagFailureGuidanceText, DagNode[]>();
  for (const node of nodes) {
    if (node.question.failure != null) {
      const list = grouped.get(node.question.failure) ?? [];
      list.push(node);
      grouped.set(node.question.failure, list);
    }
  }
  return [...grouped.entries()].map(([guidance, failed]) => ({
    openQuestionId: failed[0]!.question.id,
    questionLabels: failed.map((n) => n.question.label),
    guidance,
    stalledQuestionLabels: nodes
      .filter(
        (other) =>
          other.question.status === "blocked" &&
          failed.some((n) => n.question.id === other.waitingOn?.questionId),
      )
      .map((n) => n.question.label),
    headline: (() => {
      const failedName = formatQuestionNames(
        failed.map((n) => n.question.label),
      );
      const stalledName = formatQuestionNames(
        nodes
          .filter(
            (other) =>
              other.question.status === "blocked" &&
              failed.some((n) => n.question.id === other.waitingOn?.questionId),
          )
          .map((n) => n.question.label),
      );
      return stalledName.length === 0
        ? `${failedName} が失敗しました。`
        : `${failedName} が失敗し、${stalledName} は人が対応するまで進みません。`;
    })(),
  }));
}

function buildProgressSummary(
  counts: Readonly<Record<DagNodeProgress, number>>,
): string {
  return PROGRESS_ORDER.filter(
    (progress) =>
      !DagNodeProgressMeta[progress].needsAPerson || counts[progress] > 0,
  )
    .map(
      (progress) =>
        `${DagNodeProgressMeta[progress].label} ${counts[progress]}`,
    )
    .join(" ・ ");
}

export function buildDependencyDagLayout(input: {
  questions: readonly DagQuestion[];
  edges: readonly DependencyEdge[];
  releasedQuestionIds: ReadonlySet<string>;
  metrics?: DagMetrics;
}): DependencyDagLayout | null {
  const metrics = input.metrics ?? DEFAULT_DAG_METRICS;
  if (input.questions.length === 0) {
    return null;
  }
  const byId = new Map(input.questions.map((q) => [q.id, q]));
  const drawable = input.edges.filter(
    (edge) => byId.has(edge.from_question_id) && byId.has(edge.to_question_id),
  );
  const layers = dependencyExecutionLayers(
    input.questions.map((q) => q.id),
    drawable,
  );
  if (layers == null) {
    return null;
  }

  const displayOrder = new Map(
    input.questions.map((q, index) => [q.id, index]),
  );
  const nodes: DagNode[] = [];
  for (const [layerIndex, layer] of layers.entries()) {
    const ordered = [...layer].sort(
      (a, b) => (displayOrder.get(a) ?? 0) - (displayOrder.get(b) ?? 0),
    );
    for (const [row, id] of ordered.entries()) {
      const question = byId.get(id)!;
      const waitingOn = resolveQuestionWait(id, {
        blockedOn: (q) => byId.get(q)?.blockedOnQuestionId ?? null,
        statusOf: (q) => byId.get(q)?.status ?? "pending",
        numberOf: (q) => byId.get(q)?.label ?? null,
      });
      nodes.push({
        question,
        layer: layerIndex,
        rect: rectAt(metrics, layerIndex, row),
        waitingOn,
        statusLabel: labelWaitingFor(question.status, waitingOn),
      });
    }
  }

  const edges: DagEdgeLine[] = drawable.map((edge) => ({
    fromQuestionId: edge.from_question_id,
    toQuestionId: edge.to_question_id,
    satisfied: input.releasedQuestionIds.has(edge.from_question_id),
    key: `${edge.from_question_id}>${edge.to_question_id}`,
  }));

  const progressCounts = Object.fromEntries(
    (Object.keys(DagNodeProgressMeta) as DagNodeProgress[]).map((progress) => [
      progress,
      nodes.filter((n) => dagNodeProgressOf(n.question.status) === progress)
        .length,
    ]),
  ) as Record<DagNodeProgress, number>;

  const statusById = Object.fromEntries(
    nodes.map((n) => [n.question.id, n.question.status]),
  ) as Record<string, QuestionStatusKey>;

  return {
    nodes,
    edges,
    progressCounts,
    progressSummary: buildProgressSummary(progressCounts),
    failures: buildFailures(nodes),
    statusById,
  };
}

export function jobHasWaitingDependents(
  questionId: string,
  jobs: readonly JobResponse[],
): boolean {
  return jobs.some((job) => job.blocked_on_question_id === questionId);
}

export function deriveStatusesFromJobs(input: {
  questions: readonly { id: string; label: string }[];
  jobs: readonly JobResponse[];
  reviewsByQuestion: Readonly<Record<string, ReviewResponse | null>>;
}): DagQuestion[] {
  return input.questions.map((question) => {
    const job = input.jobs.find((j) => j.question_id === question.id) ?? null;
    const review = input.reviewsByQuestion[question.id] ?? null;
    const status = deriveQuestionStatus({
      job,
      review,
      hasWaitingDependents: jobHasWaitingDependents(question.id, input.jobs),
    });
    return buildDagQuestion({
      id: question.id,
      label: question.label,
      status,
      blockedOnQuestionId: job?.blocked_on_question_id ?? null,
      lastError: job?.last_error ?? null,
      errorCode: job?.error_code ?? null,
    });
  });
}
