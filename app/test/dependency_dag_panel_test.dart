import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/question_status.dart';
import 'package:auto_scoring_app/features/pdf_review/dependency_dag_panel.dart';

DependencyEdgeModel _edge(String from, String to) => DependencyEdgeModel(
  (b) => b
    ..fromQuestionId = from
    ..toQuestionId = to
    ..rationale = '前提'
    ..provides.replace(const <DependencyProvision>[]),
);

/// q1 and q2 run in parallel; q3 waits for q1.
DependencyDagLayout _layout({
  QuestionStatus q1 = QuestionStatus.running,
  QuestionStatus q2 = QuestionStatus.queued,
  QuestionStatus q3 = QuestionStatus.blocked,
  Set<String> released = const {},
}) => buildDependencyDagLayout(
  questions: [
    DagQuestion(id: 'q1', label: '1', status: q1),
    DagQuestion(id: 'q2', label: '2', status: q2),
    DagQuestion(
      id: 'q3',
      label: '3',
      status: q3,
      blockedOnQuestionId: q3 == QuestionStatus.blocked ? 'q1' : null,
    ),
  ],
  edges: [_edge('q1', 'q3')],
  releasedQuestionIds: released,
)!;

Future<void> _pumpPanel(
  WidgetTester tester,
  DependencyDagLayout layout, {
  ValueChanged<String>? onQuestionSelected,
  String? selectedQuestionId,
  Size size = const Size(1200, 800),
  double maxCanvasHeight = AppLayout.dagPanelHeight,
  bool disableAnimations = false,
  Brightness brightness = Brightness.light,
}) async {
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    MaterialApp(
      // The real theme: the panel reads `AppStatusColors` through a
      // `ThemeExtension` only `AppTheme` installs (Issue #67).
      theme: brightness == Brightness.light
          ? AppTheme.light()
          : AppTheme.dark(),
      home: Scaffold(
        body: MediaQuery(
          data: MediaQueryData(disableAnimations: disableAnimations),
          child: Column(
            children: [
              DependencyDagPanel(
                layout: layout,
                maxCanvasHeight: maxCanvasHeight,
                selectedQuestionId: selectedQuestionId,
                onQuestionSelected: onQuestionSelected ?? (_) {},
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

/// What the panel is currently announcing, straight off the painter.
DagEdgePainter _painter(WidgetTester tester) =>
    tester.widget<CustomPaint>(find.byKey(const Key('dag-edges'))).painter!
        as DagEdgePainter;

/// The id of the DAG node that currently holds focus, or `null` if focus is
/// somewhere else entirely.
String? _focusedNodeId() {
  final context = FocusManager.instance.primaryFocus?.context;
  if (context == null) return null;
  String? id;
  context.visitAncestorElements((element) {
    final key = element.widget.key;
    if (key is ValueKey<String> && key.value.startsWith('dag-node-')) {
      id = key.value.substring('dag-node-'.length);
      return false;
    }
    return true;
  });
  return id;
}

void main() {
  testWidgets('shows every question with its own state in words', (
    tester,
  ) async {
    await _pumpPanel(tester, _layout());

    expect(find.text('問1'), findsOneWidget);
    expect(find.text('問2'), findsOneWidget);
    expect(find.text('問3'), findsOneWidget);
    // The state is text, not only a colour and not only an icon (Issue #25).
    expect(
      tester.widget<Text>(find.byKey(const Key('dag-node-status-q1'))).data,
      'AI処理中',
    );
    expect(
      tester.widget<Text>(find.byKey(const Key('dag-node-status-q2'))).data,
      '実行待ち',
    );
    // The blocked node names what it waits for, which is the question the
    // whole diagram exists to answer.
    expect(
      tester.widget<Text>(find.byKey(const Key('dag-node-status-q3'))).data,
      '問1 待ち',
    );
  });

  testWidgets('announces each node to a screen reader', (tester) async {
    final handle = tester.ensureSemantics();
    await _pumpPanel(tester, _layout());

    expect(
      find.bySemanticsLabel('問3 問1 待ち'),
      findsOneWidget,
      reason: 'a node must be readable without seeing the diagram',
    );
    handle.dispose();
  });

  testWidgets('the header summary survives collapsing the diagram', (
    tester,
  ) async {
    await _pumpPanel(tester, _layout());

    expect(find.text('実行中 1 ・ 待機 2 ・ 完了 0'), findsOneWidget);
    expect(find.byKey(const Key('dag-node-q1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('dag-toggle-button')));
    await tester.pumpAndSettle();

    // Collapsing buys the PDF viewer its vertical space back without costing
    // the reviewer the answer to 「まだ動いているのか」.
    expect(find.byKey(const Key('dag-node-q1')), findsNothing);
    expect(find.text('実行中 1 ・ 待機 2 ・ 完了 0'), findsOneWidget);
  });

  // ------------------------------------------------------------------ //
  // Issue #85: the band is a share of the height the pane it shares with the
  // PDF viewer actually has, not a fixed slice of every window.
  // ------------------------------------------------------------------ //
  testWidgets('the band only takes the height it is allowed', (tester) async {
    double panelHeight(WidgetTester tester) =>
        tester.getSize(find.byType(DependencyDagPanel)).height;

    await _pumpPanel(tester, _layout(), maxCanvasHeight: 80);
    final tight = panelHeight(tester);
    // The diagram itself is taller than either allowance and scrolls inside
    // whatever band it is given.
    expect(
      tester.getRect(find.byKey(const Key('dag-edges'))).height,
      greaterThan(160),
    );

    await _pumpPanel(tester, _layout(), maxCanvasHeight: 160);
    expect(panelHeight(tester) - tight, 80);
  });

  testWidgets('below one node row the diagram does not open at all, and says '
      'why', (tester) async {
    await _pumpPanel(tester, _layout(), maxCanvasHeight: 20);

    // The header -- and so the answer to 「まだ動いているのか」 -- is still
    // there; only the diagram is gone.
    expect(find.text('実行中 1 ・ 待機 2 ・ 完了 0'), findsOneWidget);
    expect(find.byKey(const Key('dag-node-q1')), findsNothing);
    // Disabled rather than removed: a control that vanishes reads as a bug,
    // and the reason is something the reviewer can act on.
    final toggle = tester.widget<IconButton>(
      find.byKey(const Key('dag-toggle-button')),
    );
    expect(toggle.onPressed, isNull);
    expect(toggle.tooltip, contains('画面の高さ'));
  });

  testWidgets('a diagram narrower than its band is centred in it, not left '
      'aligned', (tester) async {
    await _pumpPanel(tester, _layout(), size: const Size(1200, 800));

    final canvas = tester.getRect(find.byKey(const Key('dag-edges')));
    expect(canvas.left, greaterThan(0));
    expect((canvas.left - (1200 - canvas.right)).abs(), lessThan(1));
  });

  testWidgets('a submission whose jobs are not enqueued yet reads as 待機', (
    tester,
  ) async {
    // 未処理 used to fall through to 完了, so collapsing the panel left the
    // header claiming a submission nothing had started was fully done
    // (review round 1, P2).
    await _pumpPanel(
      tester,
      _layout(
        q1: QuestionStatus.pending,
        q2: QuestionStatus.pending,
        q3: QuestionStatus.pending,
      ),
    );

    expect(find.text('実行中 0 ・ 待機 3 ・ 完了 0'), findsOneWidget);
  });

  testWidgets('a click selects that question', (tester) async {
    final selected = <String>[];
    await _pumpPanel(tester, _layout(), onQuestionSelected: selected.add);

    await tester.tap(find.byKey(const Key('dag-node-q3')));
    await tester.pump();

    expect(selected, ['q3']);
  });

  testWidgets('the focused node shows where the keyboard is', (tester) async {
    // `InkWell`'s own focus highlight is painted on the ancestor `Material`,
    // under the card's opaque background -- so without a ring of its own,
    // moving through the diagram by keyboard was invisible until Enter
    // (review round 2, P2).
    await _pumpPanel(tester, _layout());
    BoxDecoration decorationOf(String id) =>
        tester
                .widget<AnimatedContainer>(
                  find.descendant(
                    of: find.byKey(Key('dag-node-$id')),
                    matching: find.byType(AnimatedContainer),
                  ),
                )
                .decoration!
            as BoxDecoration;

    expect(decorationOf('q1').boxShadow, isNull);

    for (var i = 0; i < 5 && _focusedNodeId() == null; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
    }
    expect(_focusedNodeId(), 'q1');
    await tester.pump(AppMotion.stateChange);

    expect(decorationOf('q1').boxShadow, isNotEmpty);
    expect(decorationOf('q2').boxShadow, isNull);

    // And it moves with the focus rather than sticking to the first node.
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump(AppMotion.stateChange);

    expect(_focusedNodeId(), 'q2');
    expect(decorationOf('q1').boxShadow, isNull);
    expect(decorationOf('q2').boxShadow, isNotEmpty);
  });

  testWidgets('is operable with the keyboard alone', (tester) async {
    final selected = <String>[];
    await _pumpPanel(tester, _layout(), onQuestionSelected: selected.add);

    // Tab into the diagram (the header's collapse button comes first).
    for (var i = 0; i < 5 && _focusedNodeId() == null; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pump();
    }
    expect(_focusedNodeId(), 'q1');

    // → moves along the dependency direction, into the next layer. The page
    // binds ↑/↓ to 設問移動 and Enter to 承認して次へ; inside the panel they
    // have to mean "move around the diagram" and "select this node" instead.
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    expect(_focusedNodeId(), 'q3');

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(selected, ['q3']);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();
    expect(_focusedNodeId(), 'q1');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pump();
    expect(_focusedNodeId(), 'q2');
  });

  testWidgets('only a running node moves, and it stops when the job does', (
    tester,
  ) async {
    await _pumpPanel(tester, _layout());

    // Exactly one: the whole screen is watched for hours, so continuous
    // motion is rationed to "this question is being processed right now"
    // (docs/design-tokens.md §5).
    expect(find.byKey(const Key('dag-activity-running')), findsOneWidget);

    await _pumpPanel(
      tester,
      _layout(q1: QuestionStatus.graded, released: const {'q1'}),
    );
    await tester.pump();

    expect(find.byKey(const Key('dag-activity-running')), findsNothing);
    await tester.pumpAndSettle();
  });

  testWidgets('reduced motion keeps the indicator but stops the movement', (
    tester,
  ) async {
    await _pumpPanel(tester, _layout(), disableAnimations: true);

    expect(find.byKey(const Key('dag-activity-running')), findsNothing);
    expect(find.byKey(const Key('dag-activity-static')), findsOneWidget);
  });

  testWidgets('the moment an upstream finishes and the downstream is '
      'released is announced once, then the diagram settles', (tester) async {
    await _pumpPanel(tester, _layout(q1: QuestionStatus.queued));
    // Nothing is being announced before the transition -- a diagram that is
    // always mid-animation cannot make one moment stand out.
    expect(_painter(tester).revealing, isEmpty);
    expect(_painter(tester).edges.single.satisfied, isFalse);

    await _pumpPanel(
      tester,
      _layout(
        q1: QuestionStatus.graded,
        q3: QuestionStatus.queued,
        released: const {'q1'},
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));

    // The edge q1 -> q3 is the one that just became satisfied, and it is
    // mid-wipe from the prerequisite towards the dependent.
    expect(_painter(tester).revealing, {'q1>q3'});
    expect(_painter(tester).progress, greaterThan(0));
    expect(_painter(tester).progress, lessThan(1));

    await tester.pump(AppMotion.emphasis);
    // Bounded: it says what happened and stops, rather than leaving the
    // released edge permanently highlighted.
    expect(_painter(tester).revealing, isEmpty);
    expect(_painter(tester).edges.single.satisfied, isTrue);
    expect(
      tester.widget<Text>(find.byKey(const Key('dag-node-status-q3'))).data,
      '実行待ち',
    );
  });

  testWidgets('reduced motion skips the announcement but not the change', (
    tester,
  ) async {
    await _pumpPanel(
      tester,
      _layout(q1: QuestionStatus.queued),
      disableAnimations: true,
    );
    await _pumpPanel(
      tester,
      _layout(
        q1: QuestionStatus.graded,
        q3: QuestionStatus.queued,
        released: const {'q1'},
      ),
      disableAnimations: true,
    );
    await tester.pump(const Duration(milliseconds: 100));

    expect(_painter(tester).revealing, isEmpty);
    // The change itself still lands -- it is in the node's icon and label,
    // which is where the information actually lives.
    expect(_painter(tester).edges.single.satisfied, isTrue);
    expect(
      tester.widget<Text>(find.byKey(const Key('dag-node-status-q3'))).data,
      '実行待ち',
    );
  });

  testWidgets('draws under the dark theme too', (tester) async {
    // The panel takes every colour from the theme; a hard-coded one would
    // pass in light and be unreadable (or throw, for a missing
    // `ThemeExtension`) in dark. `design_tokens_screens_test.dart` walks the
    // 添削レビュー screen through its shell-error state, so this is where the
    // diagram itself gets its dark pass.
    await _pumpPanel(tester, _layout(), brightness: Brightness.dark);

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('dag-node-q1')), findsOneWidget);
  });

  testWidgets('a narrow window scrolls the diagram instead of breaking it', (
    tester,
  ) async {
    // Narrower than the diagram itself: the nodes keep their size (shrinking
    // them would cost the labels their readability) and the band scrolls.
    await _pumpPanel(tester, _layout(), size: const Size(360, 640));
    await tester.pump();

    expect(tester.takeException(), isNull);
    final scrollable = find.byType(Scrollable).first;
    expect(
      tester.widget<Scrollable>(scrollable).axisDirection,
      AxisDirection.right,
    );
    expect(find.byKey(const Key('dag-node-q1')), findsOneWidget);
    // The second layer is off-screen at this width, and reachable by
    // scrolling rather than by being squeezed into it.
    await tester.drag(scrollable, const Offset(-400, 0));
    await tester.pump();
    expect(find.byKey(const Key('dag-node-q3')), findsOneWidget);
  });
}
