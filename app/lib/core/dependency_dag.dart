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
/// layer assignment and the pixel geometry of the node/edge diagram. The
/// `features` side only paints what this produces.
///
/// What a node *says* is not decided here. [QuestionStatus] and
/// [deriveQuestionStatus] live in `core/question_status.dart` because the
/// left rail and the inspector show the state of the same question too, and
/// the three of them disagreeing was Issue #84.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/question_status.dart';

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

/// The three buckets the panel header summarises a submission into, so that
/// collapsing the diagram still answers 「まだ動いているのか」.
///
/// Coarser than [QuestionStatus] on purpose: the header is one line, and the
/// node itself carries the precise state.
enum DagNodeProgress {
  /// Nothing has started, or something has to happen elsewhere first:
  /// 未処理・前提待ち・実行待ち, and a 再判定 request no job has answered yet.
  waiting('待機'),

  /// An OCR/AI provider call is in flight.
  running('実行中'),

  /// The pipeline is done with this question, whatever the outcome --
  /// including 失敗 and 要確認, which are finished results a human now has to
  /// deal with rather than work still in progress.
  settled('完了');

  const DagNodeProgress(this.label);

  final String label;
}

/// Which of the three buckets the collapsed header counts a status in.
///
/// An extension rather than a member of [QuestionStatus]: the buckets exist
/// for this panel's one-line header, and the vocabulary in
/// `core/question_status.dart` is shared with the rail and the inspector,
/// which have no use for them.
extension DagNodeProgressOf on QuestionStatus {
  DagNodeProgress get progress => switch (this) {
    // 未処理 belongs here, not in [DagNodeProgress.settled]: a submission
    // whose per-question jobs have not been enqueued yet has *nothing*
    // finished, and reporting it as 完了 in the header was exactly the lie
    // a collapsed panel left standing (review round 1, P2).
    QuestionStatus.pending ||
    QuestionStatus.blocked ||
    QuestionStatus.queued ||
    QuestionStatus.regradeRequested => DagNodeProgress.waiting,
    QuestionStatus.running => DagNodeProgress.running,
    QuestionStatus.needsCheck ||
    QuestionStatus.failed ||
    QuestionStatus.cancelled ||
    QuestionStatus.graded ||
    QuestionStatus.rejected ||
    QuestionStatus.approved => DagNodeProgress.settled,
  };
}

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

  final QuestionStatus status;

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

  QuestionStatus get status => question.status;

  /// The line of text under the 設問番号 inside the node. Shared with the
  /// rail and the Inspector through [QuestionStatus.labelWaitingFor], so the
  /// three never name the same state differently (Issue #84).
  String get statusLabel => status.labelWaitingFor(waitingForLabel);

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
    this.detour,
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

  /// The free lane this edge has to be routed through, or `null` for an edge
  /// that can go straight from [start] to [end]. See [DagEdgeDetour].
  final DagEdgeDetour? detour;

  /// Stable identity for diffing one frame's edges against the previous
  /// one's, so the panel can animate only the edges that *just* became
  /// satisfied.
  String get key => '$fromQuestionId>$toQuestionId';
}

/// The route around the cards that stand between an edge's two endpoints.
///
/// A dependency may skip layers (`A -> B`, `B -> C` *and* `A -> C` is a
/// perfectly ordinary graph), and a skipping edge whose endpoints sit in the
/// same row would otherwise run straight through the opaque card of every
/// node in between -- taking the direct dependency, and whether it is
/// satisfied, off the screen entirely (review round 1, P2).
///
/// The way around is a lane below every node row: the edge drops into it,
/// runs along it, and climbs back out. Only edges a card is actually standing
/// in the way of get one; a skipping edge with a clear line keeps it.
@immutable
class DagEdgeDetour {
  const DagEdgeDetour({required this.y, required this.shoulder});

  /// The y the lane runs along -- below the bottom of the last node row, so
  /// the flat middle of the route cannot cross a card whatever it passes.
  final double y;

  /// How far the drop and the climb extend horizontally at each end.
  ///
  /// Never more than half a column gap ([DagMetrics.detourShoulder]), so both
  /// of them finish inside the empty column between two layers: the *lane* is
  /// what clears the cards, and this is what keeps the parts of the route
  /// that are not yet down in the lane away from them too.
  final double shoulder;
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
    this.laneGap = AppSpacing.md,
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

  /// Between the node rows and the first detour lane, and between lanes.
  /// See [DagEdgeLine.detourY].
  final double laneGap;

  Rect rectAt(int layer, int row) => Rect.fromLTWH(
    padding + layer * (nodeWidth + columnGap),
    padding + row * (nodeHeight + rowGap),
    nodeWidth,
    nodeHeight,
  );

  /// The bottom of the last node row -- everything below this is free space a
  /// detour lane can use.
  double _rowsBottom(int maxRows) =>
      padding + maxRows * nodeHeight + (maxRows - 1) * rowGap;

  double laneY(int lane, {required int maxRows}) =>
      _rowsBottom(maxRows) + laneGap * (lane + 1);

  /// How far a detour's drop and climb may extend horizontally for an edge
  /// spanning [span] pixels. Capped at half a [columnGap] so the two of them
  /// together never reach past the empty column they start in, and at a
  /// quarter of the span so the lane itself is always the longest part of the
  /// route. See [DagEdgeDetour.shoulder].
  double detourShoulder(double span) => math.min(columnGap / 2, span / 4);

  Size canvasSize({
    required int layerCount,
    required int maxRows,
    int laneCount = 0,
  }) => Size(
    padding * 2 + layerCount * nodeWidth + (layerCount - 1) * columnGap,
    _rowsBottom(maxRows) + laneGap * laneCount + padding,
  );

  /// This grid, with the slack between its natural width and [width] spent on
  /// [columnGap] -- up to [AppLayout.dagColumnGapMax] (Issue #85).
  ///
  /// Only the gaps grow. Growing the nodes instead would buy nothing: a node
  /// holds 設問番号 and a state label, both of which are already fully legible
  /// at [AppLayout.dagNodeWidth]. The gaps are where the arrows live, and an
  /// arrow with room is the one thing on this diagram that gets easier to read
  /// when it is longer.
  DagMetrics spreadAcross(double width, {required int layerCount}) {
    if (layerCount < 2 || !width.isFinite) return this;
    final natural = canvasSize(layerCount: layerCount, maxRows: 1).width;
    final slack = width - natural;
    if (slack <= 0) return this;
    return DagMetrics(
      nodeWidth: nodeWidth,
      nodeHeight: nodeHeight,
      columnGap: math.min(
        columnGap + slack / (layerCount - 1),
        columnGap * AppLayout.dagColumnGapSpreadLimit,
      ),
      rowGap: rowGap,
      padding: padding,
      laneGap: laneGap,
    );
  }
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

  /// How many questions are in each of [QuestionStatus]' values -- the header
  /// summary, so collapsing the panel does not hide whether anything is
  /// still moving.
  int countWhere(bool Function(QuestionStatus) test) =>
      nodes.where((n) => test(n.status)).length;

  Set<String> get satisfiedEdgeKeys => {
    for (final edge in edges)
      if (edge.satisfied) edge.key,
  };

  Map<String, QuestionStatus> get statusById => {
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
/// [availableWidth] is the width the panel has to draw in, and only widens
/// the gaps between layers ([DagMetrics.spreadAcross]) -- the diagram never
/// shrinks to fit, because a fitted diagram loses the label legibility that
/// is its whole point. Leave it out (or pass [double.infinity]) to get the
/// natural, unspread grid.
///
/// Returns `null` if [edges] contain a cycle -- there is no sensible layered
/// drawing of one, and a confirmed graph can never have one.
DependencyDagLayout? buildDependencyDagLayout({
  required List<DagQuestion> questions,
  required List<DependencyEdgeModel> edges,
  required Set<String> releasedQuestionIds,
  DagMetrics metrics = const DagMetrics(),
  double availableWidth = double.infinity,
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
  // Everything below lays out on the *spread* grid, not the natural one: the
  // panel is handed a full band's width and the diagram used to hug its left
  // edge (Issue #85).
  final grid = metrics.spreadAcross(availableWidth, layerCount: layers.length);

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
        rect: grid.rectAt(layerIndex, row),
        waitingForLabel: switch (byId[id]!.blockedOnQuestionId) {
          final blockedOn? => byId[blockedOn]?.label,
          null => null,
        },
      );
      nodes.add(node);
      nodeById[id] = node;
    }
  }

  // Straight first, then a lane for each edge that a node is standing in the
  // way of. Assigned in `drawable` order so the same graph always draws the
  // same way.
  var laneCount = 0;
  final lines = <DagEdgeLine>[];
  for (final edge in drawable) {
    final from = nodeById[edge.fromQuestionId]!;
    final to = nodeById[edge.toQuestionId]!;
    final start = from.rect.centerRight;
    final end = to.rect.centerLeft;
    final blocked = _crossesANode(from: from, to: to, nodes: nodes);
    lines.add(
      DagEdgeLine(
        fromQuestionId: edge.fromQuestionId,
        toQuestionId: edge.toQuestionId,
        start: start,
        end: end,
        satisfied: releasedQuestionIds.contains(edge.fromQuestionId),
        detour: blocked
            ? DagEdgeDetour(
                y: grid.laneY(laneCount++, maxRows: maxRows),
                shoulder: grid.detourShoulder(end.dx - start.dx),
              )
            : null,
      ),
    );
  }

  return DependencyDagLayout(
    nodes: nodes,
    edges: lines,
    size: grid.canvasSize(
      layerCount: layers.length,
      maxRows: maxRows,
      laneCount: laneCount,
    ),
  );
}

/// Whether a straight edge from [from] to [to] might pass behind another
/// node's card.
///
/// Conservative, not exact, and deliberately so. The curve the panel draws
/// between two node edges is monotone in y, so its whole vertical extent is
/// the band between the two endpoints -- which means a node overlapping
/// neither that band nor the layers in between can never be crossed, and this
/// test therefore **misses nothing**. It does report the other way round: a
/// card can overlap the band vertically while the curve has not reached that
/// y by the time it passes the card's x, and the edge is then sent on a
/// detour it did not need.
///
/// That asymmetry is the one worth having. A needless detour costs a slightly
/// longer line and a slightly taller panel; a missed one takes a dependency,
/// and whether it is satisfied, off the screen.
bool _crossesANode({
  required DagNode from,
  required DagNode to,
  required List<DagNode> nodes,
}) {
  if (to.layer - from.layer < 2) return false;
  final top = math.min(from.rect.center.dy, to.rect.center.dy);
  final bottom = math.max(from.rect.center.dy, to.rect.center.dy);
  return nodes.any(
    (node) =>
        node.layer > from.layer &&
        node.layer < to.layer &&
        node.rect.top <= bottom &&
        node.rect.bottom >= top,
  );
}
