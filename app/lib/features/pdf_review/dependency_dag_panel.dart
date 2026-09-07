import 'dart:math' as math;
import 'dart:ui' show PathMetric;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 添削レビュー画面の「処理の進み方」パネル (Issue #64).
///
/// Draws the confirmed 設問依存DAG as nodes and edges, laid out by
/// [DependencyDagLayout] (`core/dependency_dag.dart`) along the graph's own
/// parallel-execution layers: one column per layer, so a column is literally
/// "these may run at the same time" and every arrow points rightwards, into
/// the future.
///
/// The thing this panel exists to show is **上流が完了して下流の blocked が
/// 解ける瞬間**: an edge stays dashed with an open arrowhead while its
/// prerequisite has not released it, turns solid with a filled head when it
/// has, and that turn is drawn once as a short wipe from prerequisite to
/// dependent. Everything else is static -- the only continuous motion on the
/// whole screen is the hairline under a `RUNNING` node
/// (`docs/design-tokens.md` §5).
///
/// Nothing here decides anything: layer assignment, node state and every
/// coordinate come from `core`, which is where they can be unit-tested. This
/// file paints and handles input.
class DependencyDagPanel extends StatefulWidget {
  const DependencyDagPanel({
    super.key,
    required this.layout,
    required this.selectedQuestionId,
    required this.onQuestionSelected,
  });

  final DependencyDagLayout layout;

  /// The question the rest of the screen is showing, highlighted here so the
  /// diagram doubles as "where am I".
  final String? selectedQuestionId;

  final ValueChanged<String> onQuestionSelected;

  @override
  State<DependencyDagPanel> createState() => _DependencyDagPanelState();
}

class _DependencyDagPanelState extends State<DependencyDagPanel>
    with SingleTickerProviderStateMixin {
  /// Runs once per batch of transitions, never repeats. See [_reveal].
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: AppMotion.emphasis,
  );

  /// The previous frame's facts, to diff the new ones against. Held rather
  /// than recomputed because the layout object is rebuilt from scratch on
  /// every poll tick -- identity tells us nothing, the contents do.
  Set<String> _satisfiedEdgeKeys = const {};
  Map<String, DagNodeStatus> _statusById = const {};

  /// Which edges/nodes the *current* run of [_controller] is announcing.
  Set<String> _revealingEdgeKeys = const {};
  Set<String> _releasedNodeIds = const {};

  bool _expanded = true;

  /// Owned rather than left implicit so both `Scrollbar`s can be told to stay
  /// visible on the axis that actually overflows -- a permanently-shown thumb
  /// is how the panel says "there is more diagram here" without moving.
  final _horizontal = ScrollController();
  final _vertical = ScrollController();

  @override
  void initState() {
    super.initState();
    _satisfiedEdgeKeys = widget.layout.satisfiedEdgeKeys;
    _statusById = widget.layout.statusById;
    _controller.addStatusListener(_handleAnimationStatus);
  }

  @override
  void didUpdateWidget(DependencyDagPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    _reveal();
  }

  @override
  void dispose() {
    _controller.removeStatusListener(_handleAnimationStatus);
    _controller.dispose();
    _horizontal.dispose();
    _vertical.dispose();
    super.dispose();
  }

  void _handleAnimationStatus(AnimationStatus status) {
    // Drop the "this just happened" sets once the announcement is over, so
    // the diagram settles back to its plain, static rendering instead of
    // keeping a transition highlighted indefinitely.
    if (status == AnimationStatus.completed && mounted) {
      setState(() {
        _revealingEdgeKeys = const {};
        _releasedNodeIds = const {};
      });
    }
  }

  /// Diffs this build's layout against the last one and, if a dependency was
  /// satisfied or a node stopped being blocked, plays the announcement once.
  ///
  /// Only those two transitions animate. A node going 実行待ち → AI処理中,
  /// or a reviewer's own 承認, changes the node in place through
  /// [AnimatedContainer]; drawing an emphasis for every state change on a
  /// screen someone watches for an hour is exactly the fatigue
  /// `docs/design-tokens.md` §5 rules out.
  void _reveal() {
    final satisfied = widget.layout.satisfiedEdgeKeys;
    final statuses = widget.layout.statusById;
    final newlySatisfied = satisfied.difference(_satisfiedEdgeKeys);
    final released = {
      for (final entry in statuses.entries)
        if (_statusById[entry.key] == DagNodeStatus.blocked &&
            entry.value != DagNodeStatus.blocked)
          entry.key,
    };
    _satisfiedEdgeKeys = satisfied;
    _statusById = statuses;
    if (newlySatisfied.isEmpty && released.isEmpty) return;
    // A reviewer who has asked for reduced motion still gets the change --
    // it is already in the node's icon and label -- just not the wipe.
    if (MediaQuery.disableAnimationsOf(context)) return;
    // No `setState`: this runs from `didUpdateWidget`, i.e. inside the
    // rebuild that is about to read these fields anyway.
    _revealingEdgeKeys = newlySatisfied;
    _releasedNodeIds = released;
    _controller.forward(from: 0);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildHeader(context),
        if (_expanded) ...[
          const Divider(height: AppLayout.hairline),
          SizedBox(
            // Only as tall as the diagram, up to the band's maximum. A test
            // with two questions must not reserve the same slice of the PDF
            // viewer as one with twelve.
            height: math.min(
              widget.layout.size.height,
              AppLayout.dagPanelHeight,
            ),
            child: _buildCanvas(),
          ),
        ],
        const Divider(height: AppLayout.hairline),
      ],
    );
  }

  /// The header carries the summary itself, so collapsing the panel to buy
  /// the PDF viewer back its vertical space does not cost the reviewer the
  /// answer to 「まだ動いているのか」.
  Widget _buildHeader(BuildContext context) {
    final layout = widget.layout;
    final running = layout.countWhere((s) => s == DagNodeStatus.running);
    final waiting = layout.countWhere(
      (s) => s == DagNodeStatus.blocked || s == DagNodeStatus.queued,
    );
    final done = layout.countWhere((s) => !s.isInFlight);
    return Padding(
      padding: AppSpacing.banner,
      child: Row(
        children: [
          const Icon(Icons.account_tree_outlined, size: AppIconSize.dense),
          const SizedBox(width: AppSpacing.sm),
          Text('処理の進み方', style: context.texts.titleSmall),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              key: const Key('dag-summary'),
              '実行中 $running ・ 待機 $waiting ・ 完了 $done',
              style: context.texts.bodySmall,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          IconButton(
            key: const Key('dag-toggle-button'),
            tooltip: _expanded ? '依存グラフを閉じる' : '依存グラフを開く',
            icon: Icon(_expanded ? Icons.expand_less : Icons.expand_more),
            onPressed: () => setState(() => _expanded = !_expanded),
          ),
        ],
      ),
    );
  }

  /// Scrolls in both directions rather than scaling to fit: at a narrow
  /// window a fitted diagram would shrink the labels out of readability,
  /// and the node size is what keeps 設問番号 + 状態 legible (Issue #64
  /// acceptance: desktop標準幅・狭幅の両方でレイアウトが破綻しない).
  Widget _buildCanvas() {
    final layout = widget.layout;
    return Shortcuts(
      // The page binds ↑/↓ to 設問移動 and Enter to 承認して次へ. Both are
      // wrong while focus is on a node, and a `CallbackShortcuts` higher up
      // the focus chain would swallow them before the node's own
      // `ActivateIntent` ever ran -- so the panel re-binds them, closer to
      // the focus, to mean "move around the diagram" and "select this node".
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowLeft): DirectionalFocusIntent(
          TraversalDirection.left,
        ),
        SingleActivator(LogicalKeyboardKey.arrowRight): DirectionalFocusIntent(
          TraversalDirection.right,
        ),
        SingleActivator(LogicalKeyboardKey.arrowUp): DirectionalFocusIntent(
          TraversalDirection.up,
        ),
        SingleActivator(LogicalKeyboardKey.arrowDown): DirectionalFocusIntent(
          TraversalDirection.down,
        ),
        SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
      },
      child: FocusTraversalGroup(
        child: LayoutBuilder(
          builder: (context, constraints) => Scrollbar(
            controller: _horizontal,
            thumbVisibility: layout.size.width > constraints.maxWidth,
            child: SingleChildScrollView(
              controller: _horizontal,
              scrollDirection: Axis.horizontal,
              child: Scrollbar(
                controller: _vertical,
                thumbVisibility: layout.size.height > constraints.maxHeight,
                child: SingleChildScrollView(
                  controller: _vertical,
                  child: SizedBox.fromSize(
                    size: layout.size,
                    child: AnimatedBuilder(
                      animation: _controller,
                      builder: (context, _) => Stack(
                        children: [
                          Positioned.fill(
                            child: CustomPaint(
                              key: const Key('dag-edges'),
                              painter: DagEdgePainter(
                                edges: layout.edges,
                                revealing: _revealingEdgeKeys,
                                progress: _controller.value,
                                pendingColor: context.colors.outlineVariant,
                                satisfiedColor: context.colors.onSurfaceVariant,
                                revealColor: context.statusColors.success,
                              ),
                            ),
                          ),
                          for (final node in layout.nodes)
                            Positioned.fromRect(
                              rect: node.rect,
                              child: _DagNodeCard(
                                node: node,
                                selected: node.id == widget.selectedQuestionId,
                                releasedHighlight:
                                    _releasedNodeIds.contains(node.id)
                                    ? 1 - _controller.value
                                    : 0,
                                onSelected: () =>
                                    widget.onQuestionSelected(node.id),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One question. A real widget rather than something the painter draws, so it
/// can be focused, tapped, and read out -- the diagram has to be operable by
/// keyboard alone (Issue #64 acceptance), and a `CustomPaint` is a single
/// opaque node to both the focus system and a screen reader.
class _DagNodeCard extends StatelessWidget {
  const _DagNodeCard({
    required this.node,
    required this.selected,
    required this.releasedHighlight,
    required this.onSelected,
  });

  final DagNode node;
  final bool selected;

  /// 1 → 0 while this node's 「解けた」 announcement plays; 0 the rest of the
  /// time.
  final double releasedHighlight;

  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) {
    final tone = node.status.tone;
    final toneColor = tone.color(context);
    final border = selected
        ? context.colors.primary
        : tone == AppStatusTone.neutral
        ? context.colors.outlineVariant
        : toneColor;
    // One semantics node per question, labelled 設問番号 + 状態 in words and
    // carrying the InkWell's own button/tap/focus flags: `MergeSemantics`
    // folds them together, and `ExcludeSemantics` keeps the two `Text`s
    // inside from repeating the label a second time.
    return MergeSemantics(
      child: Semantics(
        button: true,
        selected: selected,
        label: node.semanticsLabel,
        child: Tooltip(
          message: node.semanticsLabel,
          excludeFromSemantics: true,
          child: InkWell(
            key: Key('dag-node-${node.id}'),
            onTap: onSelected,
            borderRadius: AppRadius.mdAll,
            child: AnimatedContainer(
              duration: AppMotion.stateChange,
              curve: AppMotion.standard,
              decoration: BoxDecoration(
                color: selected
                    ? context.colors.primaryContainer
                    : context.colors.surfaceContainerLow,
                borderRadius: AppRadius.mdAll,
                border: Border.all(
                  color: Color.lerp(
                    border,
                    context.statusColors.success,
                    releasedHighlight,
                  )!,
                  width: selected || releasedHighlight > 0
                      ? AppLayout.hairline * 2
                      : AppLayout.hairline,
                ),
              ),
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              child: ExcludeSemantics(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          node.status.icon,
                          size: AppIconSize.dense,
                          color: toneColor,
                        ),
                        const SizedBox(width: AppSpacing.xs),
                        Expanded(
                          child: Text(
                            '問${node.question.label}',
                            style: context.textRoles.uiLabel,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      node.statusLabel,
                      key: Key('dag-node-status-${node.id}'),
                      style: context.texts.labelSmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    _ActivityBar(running: node.status == DagNodeStatus.running),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The one thing on this screen allowed to keep moving: a hairline saying
/// "this question is being processed right now"
/// (`docs/design-tokens.md` §5). Low contrast on purpose -- it has to be
/// findable, not attention-grabbing, on a screen someone watches for an hour.
///
/// A reviewer who asked the OS for reduced motion gets the same bar, filled
/// and still: the information is "a job is running here", and that survives
/// without the movement.
class _ActivityBar extends StatelessWidget {
  const _ActivityBar({required this.running});

  final bool running;

  @override
  Widget build(BuildContext context) {
    if (!running) {
      return const SizedBox(height: AppLayout.activityBarHeight);
    }
    final color = context.colors.onSurfaceVariant;
    if (MediaQuery.disableAnimationsOf(context)) {
      return Container(
        key: const Key('dag-activity-static'),
        height: AppLayout.activityBarHeight,
        color: color,
      );
    }
    return LinearProgressIndicator(
      key: const Key('dag-activity-running'),
      minHeight: AppLayout.activityBarHeight,
      color: color,
      backgroundColor: context.colors.outlineVariant,
    );
  }
}

/// Draws the dependency arrows.
///
/// Public only so a widget test can assert *what* the panel is announcing
/// ([revealing], [progress]) rather than inferring it from pixels.
///
/// A `CustomPainter` rather than a graph-drawing package: the hard part of a
/// node graph is deciding where the nodes go, and Issue #26 already solved
/// that by giving every question a parallel-execution layer. What is left is
/// lines and arrowheads. See `docs/dependency-dag-progress-view.md`.
class DagEdgePainter extends CustomPainter {
  const DagEdgePainter({
    required this.edges,
    required this.revealing,
    required this.progress,
    required this.pendingColor,
    required this.satisfiedColor,
    required this.revealColor,
  });

  final List<DagEdgeLine> edges;

  /// Edges that became satisfied since the previous frame -- drawn as a wipe
  /// running from prerequisite to dependent, so the eye is carried in the
  /// direction the work just flowed.
  final Set<String> revealing;
  final double progress;

  final Color pendingColor;
  final Color satisfiedColor;
  final Color revealColor;

  @override
  void paint(Canvas canvas, Size size) {
    for (final edge in edges) {
      final isRevealing = revealing.contains(edge.key);
      final color = isRevealing
          ? Color.lerp(revealColor, satisfiedColor, progress)!
          : edge.satisfied
          ? satisfiedColor
          : pendingColor;
      final paint = Paint()
        ..color = color
        ..strokeWidth = edge.satisfied
            ? AppLayout.hairline * 2
            : AppLayout.hairline
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke;
      final path = _edgePath(edge);
      final metric = path.computeMetrics().first;
      // While revealing, only the part of the edge the wipe has reached is
      // drawn in its satisfied form; the rest stays in the pending form, so
      // the line is never momentarily missing.
      final reached = isRevealing ? metric.length * progress : metric.length;
      if (isRevealing && reached < metric.length) {
        canvas.drawPath(
          metric.extractPath(reached, metric.length),
          Paint()
            ..color = pendingColor
            ..strokeWidth = AppLayout.hairline
            ..style = PaintingStyle.stroke,
        );
      }
      if (edge.satisfied) {
        canvas.drawPath(metric.extractPath(0, reached), paint);
      } else {
        _drawDashed(canvas, metric, paint);
      }
      // The arrowhead only appears once the line reaches it, so a wipe reads
      // as the dependency *arriving* rather than as a line growing under a
      // head that was already there.
      if (!isRevealing || progress >= 1) {
        _drawArrowHead(canvas, edge, paint);
      }
    }
  }

  /// A shallow S-curve rather than a straight line: two nodes in adjacent
  /// layers are rarely in the same row, and a cubic keeps the arrow leaving
  /// horizontally and arriving horizontally, which is what makes the
  /// left-to-right direction readable when several edges overlap.
  Path _edgePath(DagEdgeLine edge) {
    final dx = (edge.end.dx - edge.start.dx) / 2;
    return Path()
      ..moveTo(edge.start.dx, edge.start.dy)
      ..cubicTo(
        edge.start.dx + dx,
        edge.start.dy,
        edge.end.dx - dx,
        edge.end.dy,
        edge.end.dx,
        edge.end.dy,
      );
  }

  /// An unsatisfied dependency is dashed and a satisfied one is solid, so
  /// 「まだ待っている」 survives with the colour removed (Issue #25).
  void _drawDashed(Canvas canvas, PathMetric metric, Paint paint) {
    const dash = AppSpacing.sm;
    const gap = AppSpacing.xs;
    var start = 0.0;
    while (start < metric.length) {
      final end = (start + dash).clamp(0.0, metric.length);
      canvas.drawPath(metric.extractPath(start, end), paint);
      start = end + gap;
    }
  }

  /// Filled once the dependency is satisfied, open (a chevron) while it is
  /// not -- the second shape cue, again so direction and state both read
  /// without colour.
  void _drawArrowHead(Canvas canvas, DagEdgeLine edge, Paint paint) {
    const length = AppSpacing.sm;
    final tip = edge.end;
    final head = Path()
      ..moveTo(tip.dx - length, tip.dy - length / 2)
      ..lineTo(tip.dx, tip.dy)
      ..lineTo(tip.dx - length, tip.dy + length / 2);
    if (edge.satisfied) {
      canvas.drawPath(head..close(), Paint()..color = paint.color);
    } else {
      canvas.drawPath(head, paint);
    }
  }

  @override
  bool shouldRepaint(DagEdgePainter old) =>
      old.progress != progress ||
      old.revealing != revealing ||
      old.edges != edges ||
      old.pendingColor != pendingColor ||
      old.satisfiedColor != satisfiedColor;
}
