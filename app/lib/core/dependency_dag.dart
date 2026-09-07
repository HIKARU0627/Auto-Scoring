/// Reading the 設問依存DAG as "how far the AI has got" (Issue #64).
///
/// The graph itself, its parallel-execution layers, and the job queue that
/// walks them all exist already (Issue #26 `docs/dependency-graph.md`,
/// Issue #18 `docs/job-queue.md`). What was missing was a way for a reviewer
/// waiting on 答案 processing to see *what is running, what is waiting on
/// what, and what starts next* -- the 添削レビュー screen showed job progress
/// as a single Navigation Rail icon, with the dependency structure nowhere on
/// screen.
///
/// Everything here is deliberately free of widgets so it can be unit-tested
/// without a render tree (same split as `core/pdf_review_geometry.dart`):
/// layer assignment, the derivation of one node's state from its `Job` and
/// its `Review`, and the pixel geometry of the node/edge diagram. The
/// `features` side only paints what this produces.
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// Groups [questionIds] into parallel-execution layers via Kahn's algorithm
/// over [edges] -- every question whose prerequisites are all in an earlier
/// layer lands in the same layer, mirroring
/// `domain.dependency_graph._kahn_layers` on the backend (which sorts each
/// layer by id for determinism over a `frozenset`; kept identical here so
/// the two never disagree about *which* layer something is in).
///
/// Recomputed from a caller's *current* edge set rather than read off
/// `DependencyGraphResponse.layers`, which is a snapshot from the last
/// analyze/confirm response and goes stale the moment a reviewer edits an
/// edge in テスト設定 (Issue #16 review round 3).
///
/// Returns `null` if the edge set is not a DAG. A cycle only ever appears
/// mid-edit in テスト設定 -- `/dependency-graph/confirm` rejects one -- so
/// every caller treats `null` as "can't show a plan yet", not an error.
List<List<String>>? dependencyExecutionLayers(
  List<String> questionIds,
  List<DependencyEdgeModel> edges,
) {
  final remainingInDegree = {for (final id in questionIds) id: 0};
  final adjacency = {for (final id in questionIds) id: <String>[]};
  for (final edge in edges) {
    final from = adjacency[edge.fromQuestionId];
    if (from == null || !remainingInDegree.containsKey(edge.toQuestionId)) {
      continue;
    }
    from.add(edge.toQuestionId);
    remainingInDegree[edge.toQuestionId] =
        remainingInDegree[edge.toQuestionId]! + 1;
  }

  final placed = <String>{};
  final layers = <List<String>>[];
  while (placed.length < questionIds.length) {
    final layer =
        questionIds
            .where((id) => !placed.contains(id) && remainingInDegree[id] == 0)
            .toList()
          ..sort();
    if (layer.isEmpty) return null;
    placed.addAll(layer);
    for (final id in layer) {
      for (final neighbor in adjacency[id]!) {
        remainingInDegree[neighbor] = remainingInDegree[neighbor]! - 1;
      }
    }
    layers.add(layer);
  }
  return layers;
}

/// Where one question stands in the pipeline, as a reviewer needs to read it.
///
/// This is *not* `Job.state` renamed: the queue's six states and the four
/// review actions describe two different halves of the same question's life,
/// and a reviewer watching the graph wants one answer per node. See
/// [deriveDagNodeStatus] for how the two are combined.
///
/// Every value carries its own icon and Japanese label as well as a tone, so
/// the diagram survives being read without colour (Issue #25's rule, restated
/// in `docs/design-tokens.md` §3.4).
enum DagNodeStatus {
  /// No `Job` exists for this question yet -- 答案 has been taken in but its
  /// per-question jobs have not been enqueued (Issue #18: jobs are only ever
  /// created by an explicit `POST .../jobs`, never implicitly).
  pending('未処理', Icons.radio_button_unchecked, AppStatusTone.neutral),

  /// `BLOCKED`: a prerequisite has not released this question yet. The node
  /// names *which* prerequisite (`Job.blocked_on_question_id`) rather than
  /// just saying "waiting" -- that name is the whole point of drawing the
  /// graph (`docs/job-queue.md` §「`BLOCKED`を…両方に使う」).
  blocked('前提待ち', Icons.lock_clock, AppStatusTone.neutral),

  /// `QUEUED`: every prerequisite is satisfied and the worker will pick this
  /// up next. This is the state the 「上流が完了して下流が解ける瞬間」
  /// transition lands in.
  queued('実行待ち', Icons.schedule, AppStatusTone.neutral),

  /// `RUNNING`: an OCR/AI provider call is in flight for this question.
  running('AI処理中', Icons.play_circle_outline, AppStatusTone.neutral),

  /// `SUCCEEDED` but `usable == false`: the pipeline finished and decided its
  /// own result is not trustworthy enough to release the questions that
  /// depend on it (low Confidence -- `docs/job-queue.md` §「依存の解放は
  /// 「usable」を…」). Nothing downstream moves until a person looks, which is
  /// exactly what [AppStatusTone.attention] is reserved for.
  needsCheck('要確認', Icons.help_outline, AppStatusTone.attention),

  /// `FAILED`: the job did not complete. Distinct from [needsCheck] -- there
  /// is no result to judge here.
  failed('失敗', Icons.error_outline, AppStatusTone.danger),

  /// `CANCELLED`: a person or a re-submission stopped this job.
  cancelled('中止', Icons.block, AppStatusTone.neutral),

  /// The AI is done and usable, and no human decision has been recorded yet.
  /// Deliberately [AppStatusTone.neutral]: on this screen "waiting to be
  /// reviewed" is the *normal* state, and colouring it would leave the whole
  /// diagram shouting (same reasoning as the Navigation Rail's icons).
  graded('レビュー待ち', Icons.rate_review_outlined, AppStatusTone.neutral),

  /// A reviewer asked for a re-grade and the replacement job has not been
  /// created yet -- a brief interim, since `regradeReview` enqueues one.
  regradeRequested('再判定待ち', Icons.autorenew, AppStatusTone.neutral),

  /// A reviewer rejected the AI's grade. A decision, not a failure, so it
  /// stays neutral.
  rejected('却下', Icons.cancel_outlined, AppStatusTone.neutral),

  /// A reviewer approved (or edited and thereby confirmed) the grade.
  approved('承認済み', Icons.check_circle, AppStatusTone.success);

  const DagNodeStatus(this.label, this.icon, this.tone);

  /// The Japanese label shown inside the node. Short enough to fit a node at
  /// [AppLayout.dagNodeWidth] without wrapping.
  final String label;

  /// The shape half of the state, so the diagram reads with colour removed.
  final IconData icon;

  final AppStatusTone tone;

  /// Whether the pipeline may still change this node on its own. The panel
  /// uses it to decide whether anything is worth animating, and the running
  /// indicator to decide whether to move at all.
  bool get isInFlight => switch (this) {
    DagNodeStatus.blocked ||
    DagNodeStatus.queued ||
    DagNodeStatus.running ||
    DagNodeStatus.regradeRequested => true,
    _ => false,
  };
}

/// Collapses one question's `Job` and `Review` into the single state a node
/// shows.
///
/// The precedence is "the queue first, the human second", because a live job
/// always describes a *newer* attempt than any review can: a re-submission
/// under a newer confirmed graph version, or a 再判定 request, creates a fresh
/// `Job` while the append-only review history still holds the previous
/// attempt's decision (Issue #18, and the same reasoning behind
/// `_isAwaitingGrade` on the 添削レビュー screen). Showing 承認済み over a
/// job that is running again would tell the reviewer the opposite of what is
/// happening.
///
/// [reviewAction] is the *effective* review action (post-Undo) or `null` when
/// none exists -- or when this screen has simply not fetched this question's
/// reviews yet, which is the common case for a question the reviewer has not
/// visited. Both read as "no human decision recorded", which is the right
/// thing to draw: the node then shows how far the *pipeline* got, and gains
/// the human half as soon as that question is opened.
DagNodeStatus deriveDagNodeStatus({
  required JobResponse? job,
  required String? reviewAction,
}) {
  if (job == null) {
    // A review with no job at all is not something the backend produces, but
    // if it ever appears, the human decision is the only fact available.
    return _reviewStatus(reviewAction) ?? DagNodeStatus.pending;
  }
  return switch (job.state) {
    'blocked' => DagNodeStatus.blocked,
    'queued' => DagNodeStatus.queued,
    'running' => DagNodeStatus.running,
    'failed' => DagNodeStatus.failed,
    'cancelled' => DagNodeStatus.cancelled,
    // `usable` is only ever set on a terminal transition, and `false` means
    // the queue itself judged the result not good enough to release anything
    // downstream -- a stronger statement than "nobody has reviewed it yet",
    // so it outranks the review overlay.
    'succeeded' when job.usable == false => DagNodeStatus.needsCheck,
    'succeeded' => _reviewStatus(reviewAction) ?? DagNodeStatus.graded,
    // An unknown state from a newer backend: say nothing rather than guess.
    _ => DagNodeStatus.pending,
  };
}

DagNodeStatus? _reviewStatus(String? action) => switch (action) {
  'approved' || 'modified' => DagNodeStatus.approved,
  'rejected' => DagNodeStatus.rejected,
  'regrade_requested' => DagNodeStatus.regradeRequested,
  _ => null,
};

/// Whether [job] has released the questions that depend on it.
///
/// Not `state == 'succeeded'`: the queue releases on the explicitly persisted
/// `Job.usable` flag, which a `SUCCEEDED` job can carry as `false` (low
/// Confidence) and a `FAILED` job can carry as `true` once a person marked
/// the question usable to unstick the pipeline
/// (`JobQueueService.mark_question_usable`, `docs/job-queue.md`). Drawing the
/// edge from `state` alone would show a satisfied dependency next to a
/// downstream node that is still, correctly, `BLOCKED`.
bool releasesDependents(JobResponse? job) => job?.usable ?? false;

/// One question as the diagram needs it, before layout: identity, what to
/// print on the node, and the state it is in.
@immutable
class DagQuestion {
  const DagQuestion({
    required this.id,
    required this.label,
    required this.status,
    this.blockedOnQuestionId,
  });

  final String id;

  /// The 設問番号 as shown elsewhere on the screen (`QuestionResponse.number`).
  final String label;

  final DagNodeStatus status;

  /// `Job.blocked_on_question_id` -- which prerequisite this one is waiting
  /// on. A join point has several prerequisites but the queue only records
  /// one, which is enough to answer 「何待ちか」.
  final String? blockedOnQuestionId;
}

/// A laid-out node: a [DagQuestion] plus where it sits on the canvas.
@immutable
class DagNode {
  const DagNode({
    required this.question,
    required this.layer,
    required this.rect,
    this.waitingForLabel,
  });

  final DagQuestion question;

  /// Which parallel-execution layer this question is in (0-based). Same
  /// layer = "may run at the same time".
  final int layer;

  /// Where to draw it, in canvas pixels.
  final Rect rect;

  /// The 設問番号 of [DagQuestion.blockedOnQuestionId], resolved against the
  /// other nodes -- so a node can say 「問2 待ち」 instead of showing an
  /// opaque id, or nothing at all.
  final String? waitingForLabel;

  String get id => question.id;

  DagNodeStatus get status => question.status;

  /// The line of text under the 設問番号 inside the node. A blocked node
  /// names what it is waiting for, since that is the one thing the diagram
  /// exists to answer; every other state just names itself.
  String get statusLabel =>
      status == DagNodeStatus.blocked && waitingForLabel != null
      ? '問$waitingForLabel 待ち'
      : status.label;

  /// What a screen reader announces for this node. Never colour-dependent
  /// and never icon-dependent (Issue #25).
  String get semanticsLabel => '問${question.label} $statusLabel';
}

/// A laid-out dependency edge, with the two points to draw it between.
@immutable
class DagEdgeLine {
  const DagEdgeLine({
    required this.fromQuestionId,
    required this.toQuestionId,
    required this.start,
    required this.end,
    required this.satisfied,
  });

  final String fromQuestionId;
  final String toQuestionId;

  /// The right edge of the prerequisite node, and the left edge of the
  /// dependent one -- layers advance along +x, so an edge always points
  /// rightwards and its direction is legible from the layout itself.
  final Offset start;
  final Offset end;

  /// Whether the prerequisite has released this dependency
  /// ([releasesDependents]). The satisfied/unsatisfied distinction is what
  /// makes 「上流が完了して下流の blocked が解ける瞬間」 visible.
  final bool satisfied;

  /// Stable identity for diffing one frame's edges against the previous
  /// one's, so the panel can animate only the edges that *just* became
  /// satisfied.
  String get key => '$fromQuestionId>$toQuestionId';
}

/// The pixel grid the diagram is drawn on.
///
/// Defaults come from the design tokens; the constructor takes them as
/// parameters purely so the geometry can be unit-tested against numbers a
/// test states itself rather than against whatever the tokens currently say.
@immutable
class DagMetrics {
  const DagMetrics({
    this.nodeWidth = AppLayout.dagNodeWidth,
    this.nodeHeight = AppLayout.dagNodeHeight,
    this.columnGap = AppSpacing.xxl,
    this.rowGap = AppSpacing.md,
    this.padding = AppSpacing.lg,
  });

  final double nodeWidth;
  final double nodeHeight;

  /// Between layers. Wide enough for an arrow to be read as an arrow.
  final double columnGap;

  /// Between two questions that may run at the same time.
  final double rowGap;

  /// Around the whole diagram, so nodes at the edge are not clipped by the
  /// panel's scroll viewport.
  final double padding;

  Rect rectAt(int layer, int row) => Rect.fromLTWH(
    padding + layer * (nodeWidth + columnGap),
    padding + row * (nodeHeight + rowGap),
    nodeWidth,
    nodeHeight,
  );

  Size canvasSize({required int layerCount, required int maxRows}) => Size(
    padding * 2 + layerCount * nodeWidth + (layerCount - 1) * columnGap,
    padding * 2 + maxRows * nodeHeight + (maxRows - 1) * rowGap,
  );
}

/// Everything the 添削レビュー panel needs to paint one submission's progress.
@immutable
class DependencyDagLayout {
  const DependencyDagLayout({
    required this.nodes,
    required this.edges,
    required this.size,
  });

  final List<DagNode> nodes;
  final List<DagEdgeLine> edges;

  /// The canvas the [nodes] are positioned in. Larger than the panel is
  /// allowed to be, in general -- the panel scrolls.
  final Size size;

  /// How many questions are in each of [DagNodeStatus]' values -- the header
  /// summary, so collapsing the panel does not hide whether anything is
  /// still moving.
  int countWhere(bool Function(DagNodeStatus) test) =>
      nodes.where((n) => test(n.status)).length;

  Set<String> get satisfiedEdgeKeys => {
    for (final edge in edges)
      if (edge.satisfied) edge.key,
  };

  Map<String, DagNodeStatus> get statusById => {
    for (final node in nodes) node.id: node.status,
  };
}

/// Lays [questions] out into layers along +x, in the order the screen already
/// lists them within each layer.
///
/// Layer *membership* comes from [dependencyExecutionLayers] (which sorts by
/// id, matching the backend); the order *within* a layer is then re-derived
/// from [questions] so the diagram's rows read in the same order as the
/// Navigation Rail beside it (page, then 設問番号) instead of alphabetically
/// by an id the reviewer never sees.
///
/// Returns `null` if [edges] contain a cycle -- there is no sensible layered
/// drawing of one, and a confirmed graph can never have one.
DependencyDagLayout? buildDependencyDagLayout({
  required List<DagQuestion> questions,
  required List<DependencyEdgeModel> edges,
  required Set<String> releasedQuestionIds,
  DagMetrics metrics = const DagMetrics(),
}) {
  if (questions.isEmpty) return null;
  final byId = {for (final question in questions) question.id: question};
  // Edges whose endpoints are not both on screen cannot be drawn, and would
  // otherwise distort the layering: a graph fetched for the test can name a
  // question this submission's list does not have (a question removed by a
  // later profile confirmation, say).
  final drawable = edges
      .where(
        (e) =>
            byId.containsKey(e.fromQuestionId) &&
            byId.containsKey(e.toQuestionId),
      )
      .toList();
  final layers = dependencyExecutionLayers(
    questions.map((q) => q.id).toList(),
    drawable,
  );
  if (layers == null) return null;

  final displayOrder = {
    for (final (index, question) in questions.indexed) question.id: index,
  };
  final nodes = <DagNode>[];
  final nodeById = <String, DagNode>{};
  var maxRows = 0;
  for (final (layerIndex, layer) in layers.indexed) {
    final ordered = layer.toList()
      ..sort((a, b) => displayOrder[a]!.compareTo(displayOrder[b]!));
    maxRows = maxRows > ordered.length ? maxRows : ordered.length;
    for (final (row, id) in ordered.indexed) {
      final node = DagNode(
        question: byId[id]!,
        layer: layerIndex,
        rect: metrics.rectAt(layerIndex, row),
        waitingForLabel: switch (byId[id]!.blockedOnQuestionId) {
          final blockedOn? => byId[blockedOn]?.label,
          null => null,
        },
      );
      nodes.add(node);
      nodeById[id] = node;
    }
  }

  final lines = [
    for (final edge in drawable)
      DagEdgeLine(
        fromQuestionId: edge.fromQuestionId,
        toQuestionId: edge.toQuestionId,
        start: nodeById[edge.fromQuestionId]!.rect.centerRight,
        end: nodeById[edge.toQuestionId]!.rect.centerLeft,
        satisfied: releasedQuestionIds.contains(edge.fromQuestionId),
      ),
  ];

  return DependencyDagLayout(
    nodes: nodes,
    edges: lines,
    size: metrics.canvasSize(layerCount: layers.length, maxRows: maxRows),
  );
}
