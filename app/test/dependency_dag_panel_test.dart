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

/// Issue #86 のスクリーンショットと同じ形。問1・問2・問4 が並列、問3 は
/// 問2 待ち、問5 は問3 待ち。[q2] を入れ替えると「要確認で止まっている画面」
/// と「失敗した画面」になる。
DependencyDagLayout _stalled({
  required QuestionStatus q2,
  String? lastError,
  String? errorCode,
}) => buildDependencyDagLayout(
  questions: [
    DagQuestion(id: 'q1', label: '1', status: QuestionStatus.approved),
    DagQuestion(
      id: 'q2',
      label: '2',
      status: q2,
      lastError: lastError,
      errorCode: errorCode,
    ),
    DagQuestion(
      id: 'q3',
      label: '3',
      status: QuestionStatus.blocked,
      blockedOnQuestionId: 'q2',
    ),
    DagQuestion(id: 'q4', label: '4', status: QuestionStatus.graded),
    DagQuestion(
      id: 'q5',
      label: '5',
      status: QuestionStatus.blocked,
      blockedOnQuestionId: 'q3',
    ),
  ],
  edges: [_edge('q1', 'q3'), _edge('q2', 'q3'), _edge('q3', 'q5')],
  releasedQuestionIds: const {'q1'},
)!;

/// 畳んでいるかどうかに関わらず、いま画面に出ている全部の文字。
List<String> _visibleText(WidgetTester tester) => [
  for (final text in tester.widgetList<Text>(find.byType(Text)))
    text.data ?? text.textSpan?.toPlainText() ?? '',
];

String _summaryOf(WidgetTester tester) =>
    tester.widget<Text>(find.byKey(const Key('dag-summary'))).data!;

String _nodeStatusOf(WidgetTester tester, String id) =>
    tester.widget<Text>(find.byKey(Key('dag-node-status-$id'))).data!;

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

/// Whether the keyboard focus is currently inside the widget carrying [key].
bool _focusIsInside(Key key) {
  final context = FocusManager.instance.primaryFocus?.context;
  if (context == null) return false;
  var found = false;
  context.visitAncestorElements((element) {
    if (element.widget.key == key) {
      found = true;
      return false;
    }
    return true;
  });
  return found;
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

  // ------------------------------------------------------------------ //
  // Issue #86: 失敗が要約から漏れ、下流の「待ち」が恒久停止を隠していた。
  //
  // 直す前のこのパネルを、同じ組み立ての答案で実測した結果:
  //
  //   要確認: summary="実行中 0 ・ 待機 2 ・ 完了 3" q3="問2 待ち" q5="問3 待ち"
  //   失敗  : summary="実行中 0 ・ 待機 2 ・ 完了 3" q3="問2 待ち" q5="問3 待ち"
  //   畳んだあと、画面に「失敗」の語: 0 箇所
  //
  // 要約が同一だったのは 失敗 も 要確認 も `DagNodeProgress.settled`(完了)
  // に畳まれていたから、ラベルが同一だったのは `labelWaitingFor` が前提の
  // 番号だけを見ていたからである。
  // ------------------------------------------------------------------ //
  group('Issue #86: 失敗を画面から消さない', () {
    testWidgets('要確認で止まった画面と、失敗した画面は、ヘッダーの文字列が違う', (tester) async {
      await _pumpPanel(tester, _stalled(q2: QuestionStatus.needsCheck));
      final blocked = _summaryOf(tester);

      await _pumpPanel(tester, _stalled(q2: QuestionStatus.failed));
      final failed = _summaryOf(tester);

      // 実際の文字列を両方固定してから、違うことを言う。「どちらも空に
      // なった」では緑にならない。
      expect(blocked, '実行中 0 ・ 待機 2 ・ 要確認 1 ・ 完了 2');
      expect(failed, '実行中 0 ・ 待機 2 ・ 失敗 1 ・ 完了 2');
      expect(blocked, isNot(failed));
    });

    testWidgets('パネルを畳んでも、失敗が画面に残る', (tester) async {
      final selected = <String>[];
      await _pumpPanel(
        tester,
        _stalled(q2: QuestionStatus.failed, errorCode: 'server_error'),
        onQuestionSelected: selected.add,
      );

      await tester.tap(find.byKey(const Key('dag-toggle-button')));
      await tester.pumpAndSettle();

      // 図そのものは消える -- 畳む目的はPDFビューアに縦を返すことなので。
      expect(find.byKey(const Key('dag-node-q2')), findsNothing);
      // 失敗のほうは残る。件数も、何が起きたかも、次の一手も、そこへ行く
      // ボタンも。
      expect(_summaryOf(tester), contains('失敗 1'));
      expect(find.byKey(const Key('dag-failure-q2')), findsOneWidget);
      expect(
        tester
            .widget<Text>(find.byKey(const Key('dag-failure-headline-q2')))
            .data,
        '問2 が失敗し、問3・問5 は人が対応するまで進みません。',
      );
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-failure-next-q2'))).data,
        allOf(contains('再判定'), contains('点数を入力')),
      );

      // 畳んだままでも、そこから失敗した設問へ行ける。
      await tester.tap(find.byKey(const Key('dag-failure-open-q2')));
      await tester.pump();
      expect(selected, ['q2']);
    });

    testWidgets('下流の「待ち」が、上流の理由で変わる', (tester) async {
      await _pumpPanel(tester, _stalled(q2: QuestionStatus.needsCheck));
      final blockedQ3 = _nodeStatusOf(tester, 'q3');
      final blockedQ5 = _nodeStatusOf(tester, 'q5');

      await _pumpPanel(tester, _stalled(q2: QuestionStatus.failed));
      final failedQ3 = _nodeStatusOf(tester, 'q3');
      final failedQ5 = _nodeStatusOf(tester, 'q5');

      expect(blockedQ3, '問2 確認待ち');
      expect(failedQ3, '問2 失敗で停止');
      expect(blockedQ3, isNot(failedQ3));
      // 問5 は問3 待ちだが、問3 にできることは何も無い。動ける場所を名指す。
      expect(blockedQ5, '問2 確認待ち');
      expect(failedQ5, '問2 失敗で停止');
      expect(blockedQ5, isNot(failedQ5));
    });

    testWidgets('失敗したノードから、理由と次にできることへ行ける', (tester) async {
      final selected = <String>[];
      await _pumpPanel(
        tester,
        _stalled(
          q2: QuestionStatus.failed,
          errorCode: 'permanent',
          lastError:
              "gemini AI provider reported that the answer image is not "
              "this question's answer (crop_not_the_answer)",
        ),
        onQuestionSelected: selected.add,
      );

      // 理由と次の一手が、この失敗に合っている -- 回答欄がずれているときに
      // 「もう一度AIに任せる」と書いたら、同じ結果を待たせることになる。
      final next = tester
          .widget<Text>(find.byKey(const Key('dag-failure-next-q2')))
          .data!;
      expect(next, contains('回答欄'));
      expect(next, isNot(contains('もう一度')));

      // ノードそのものからも同じところへ行ける（クリックでもキーボードでも、
      // 既存の設問選択と同じ経路）。
      await tester.tap(find.byKey(const Key('dag-node-q2')));
      await tester.pump();
      expect(selected, ['q2']);
    });

    testWidgets('生の last_error は画面に出ない', (tester) async {
      await _pumpPanel(
        tester,
        _stalled(
          q2: QuestionStatus.failed,
          errorCode: 'server_error',
          lastError:
              'gemini AI provider returned a malformed response '
              '[vertex-ai/gemini-2.5-pro SchemaViolation, '
              'https://aiplatform.googleapis.com 503]',
        ),
      );

      final shown = _visibleText(tester).join('\n');
      for (final fragment in [
        'gemini',
        'vertex-ai',
        'SchemaViolation',
        'https://',
        '503',
      ]) {
        expect(shown, isNot(contains(fragment)), reason: '$fragment が漏れている');
      }
      // 黙ったのではない: 分類に応じた日本語は出ている。
      expect(shown, contains('AIとの通信が最後まで通らず'));
    });

    testWidgets('要約の数字が何の数かを、ヘッダーが言える', (tester) async {
      // 「完了 2」は何個かは言うが、何の2個かは言わない。5体のうち1体が
      // まさにそこを指摘している (codex ambiguous-completion-count)。
      await _pumpPanel(tester, _stalled(q2: QuestionStatus.failed));

      final tooltip = tester.widget<Tooltip>(
        find.ancestor(
          of: find.byKey(const Key('dag-summary')),
          matching: find.byType(Tooltip),
        ),
      );
      expect(tooltip.message, contains('完了: AI処理が終わり、人を待っていないもの'));
      expect(tooltip.message, contains('失敗: 人が対応するまで進まないもの'));
      // 0件で要約から消えているバケツも、凡例には残る。「その数字は何の数か」
      // は、今日の答えがゼロでも問われる。
      expect(_summaryOf(tester), isNot(contains('要確認')));
      expect(tooltip.message, contains('要確認: 人が確認するまで下流が進まないもの'));
    });

    testWidgets('失敗していない答案には、失敗の告知が出ない', (tester) async {
      await _pumpPanel(tester, _stalled(q2: QuestionStatus.needsCheck));

      expect(find.byKey(const Key('dag-failure-q2')), findsNothing);
      expect(_summaryOf(tester), isNot(contains('失敗')));
    });

    testWidgets('狭幅・ダーク・キーボードのみでも壊れない', (tester) async {
      final selected = <String>[];
      // Issue #88 と同じ基準の狭幅。
      await _pumpPanel(
        tester,
        _stalled(q2: QuestionStatus.failed, errorCode: 'timeout'),
        size: const Size(700, 720),
        brightness: Brightness.dark,
        onQuestionSelected: selected.add,
      );

      expect(tester.takeException(), isNull);
      // 色に依らない: アイコン・日本語の1文・名前のあるボタン。
      expect(find.byIcon(QuestionStatus.failed.icon), findsWidgets);
      expect(find.byKey(const Key('dag-failure-headline-q2')), findsOneWidget);

      // キーボードだけで「問2 を開く」まで届く。
      var reached = false;
      for (var i = 0; i < 12 && !reached; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pump();
        reached = _focusIsInside(const Key('dag-failure-open-q2'));
      }
      expect(reached, isTrue, reason: 'Tab だけで「問2 を開く」に届かない');

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      expect(selected, ['q2']);
    });
  });
}
