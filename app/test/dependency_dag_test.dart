import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/dag_failure_guidance.dart';
import 'package:auto_scoring_app/core/dependency_dag.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/question_status.dart';

DependencyEdgeModel _edge(String from, String to) => DependencyEdgeModel(
  (b) => b
    ..fromQuestionId = from
    ..toQuestionId = to
    ..rationale = '前提'
    ..provides.replace(const <DependencyProvision>[]),
);

JobResponse _job({
  String state = 'running',
  bool? usable,
  String? blockedOnQuestionId,
  String questionId = 'q1',
  String? id,
  int createdAtSeconds = 0,
}) => JobResponse(
  (b) => b
    ..id = id ?? 'job-$questionId'
    ..kind = 'grading'
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..state = state
    ..usable = usable
    ..blockedOnQuestionId = blockedOnQuestionId
    ..attempts = 1
    ..maxAttempts = 3
    ..createdAt = DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: createdAtSeconds))
    ..updatedAt = DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: createdAtSeconds)),
);

DagQuestion _question(
  String id, {
  String? label,
  QuestionStatus status = QuestionStatus.pending,
  String? blockedOnQuestionId,
  String? lastError,
  String? errorCode,
}) => DagQuestion(
  id: id,
  label: label ?? id,
  status: status,
  blockedOnQuestionId: blockedOnQuestionId,
  lastError: lastError,
  errorCode: errorCode,
);

/// Issue #86 のスクリーンショットと同じ形の答案。
///
/// 問1・問2・問4 が同じ層で並列に走りうる。問3 は問2 待ち、問5 は問3 待ち
/// なので、**問2 で止まると下流2件が止まる**。[q2] を 要確認 と 失敗 の
/// あいだで入れ替えたときに画面が何と言うかが、この Issue の全部である。
DependencyDagLayout _submission({
  required QuestionStatus q2,
  String? lastError,
  String? errorCode,
}) => buildDependencyDagLayout(
  questions: [
    _question('q1', label: '1', status: QuestionStatus.approved),
    _question(
      'q2',
      label: '2',
      status: q2,
      lastError: lastError,
      errorCode: errorCode,
    ),
    _question(
      'q3',
      label: '3',
      status: QuestionStatus.blocked,
      blockedOnQuestionId: 'q2',
    ),
    _question('q4', label: '4', status: QuestionStatus.graded),
    _question(
      'q5',
      label: '5',
      status: QuestionStatus.blocked,
      blockedOnQuestionId: 'q3',
    ),
  ],
  edges: [_edge('q1', 'q3'), _edge('q2', 'q3'), _edge('q3', 'q5')],
  releasedQuestionIds: const {'q1'},
)!;

String _statusLabelOf(DependencyDagLayout layout, String id) =>
    layout.nodes.firstWhere((n) => n.id == id).statusLabel;

void main() {
  group('dependencyExecutionLayers', () {
    test('puts every independent question in the first layer', () {
      expect(dependencyExecutionLayers(['q1', 'q2', 'q3'], const []), [
        ['q1', 'q2', 'q3'],
      ]);
    });

    test('places a question after every prerequisite it has', () {
      // q1 -> q3, q2 -> q3: q3 must wait for both, so it cannot share their
      // layer even though q1/q2 are independent of each other.
      final layers = dependencyExecutionLayers(
        ['q1', 'q2', 'q3'],
        [_edge('q1', 'q3'), _edge('q2', 'q3')],
      );
      expect(layers, [
        ['q1', 'q2'],
        ['q3'],
      ]);
    });

    test('returns null for a cyclic edge set', () {
      expect(
        dependencyExecutionLayers(
          ['q1', 'q2'],
          [_edge('q1', 'q2'), _edge('q2', 'q1')],
        ),
        isNull,
      );
    });

    test('ignores an edge naming a question that is not in the set', () {
      // A graph fetched for the whole test can name a question this
      // submission's own question list no longer has.
      expect(dependencyExecutionLayers(['q1'], [_edge('q1', 'gone')]), [
        ['q1'],
      ]);
    });
  });

  group('releasesDependents', () {
    test('reads the persisted usable flag, not the job state', () {
      // A SUCCEEDED job can be not-usable (low Confidence), and a FAILED one
      // can be usable once a person unstuck it with mark_question_usable.
      expect(
        releasesDependents(_job(state: 'succeeded', usable: true)),
        isTrue,
      );
      expect(
        releasesDependents(_job(state: 'succeeded', usable: false)),
        isFalse,
      );
      expect(releasesDependents(_job(state: 'failed', usable: true)), isTrue);
      expect(releasesDependents(_job(state: 'succeeded')), isFalse);
      expect(releasesDependents(null), isFalse);
    });
  });

  group('DagNodeProgress', () {
    test('未処理 counts as 待機, never as 完了', () {
      // A submission whose per-question jobs have not been enqueued yet has
      // nothing finished; reporting every node as 完了 was the one lie a
      // collapsed panel left standing (review round 1, P2).
      expect(QuestionStatus.pending.progress, DagNodeProgress.waiting);
      expect(
        QuestionStatus.values
            .where((s) => s.progress == DagNodeProgress.settled)
            .toSet(),
        {
          // 失敗 and 要確認 left this bucket in Issue #86: both mean a person
          // is needed, and counting them as 完了 is what made the failed
          // screen and the blocked screen print the same header.
          QuestionStatus.cancelled,
          QuestionStatus.graded,
          QuestionStatus.rejected,
          QuestionStatus.approved,
        },
      );
      expect(QuestionStatus.needsCheck.progress, DagNodeProgress.needsCheck);
      expect(QuestionStatus.failed.progress, DagNodeProgress.failed);
      expect(
        QuestionStatus.values
            .where((s) => s.progress == DagNodeProgress.running)
            .toSet(),
        {QuestionStatus.running},
      );
    });
  });

  group('buildDependencyDagLayout', () {
    const metrics = DagMetrics(
      nodeWidth: 100,
      nodeHeight: 40,
      columnGap: 20,
      rowGap: 10,
      padding: 5,
      laneGap: 10,
    );

    test('lays layers out along +x and layer members down +y', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q3'), _edge('q2', 'q3')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      Rect rectOf(String id) => layout.nodes.firstWhere((n) => n.id == id).rect;

      expect(rectOf('q1'), const Rect.fromLTWH(5, 5, 100, 40));
      expect(rectOf('q2'), const Rect.fromLTWH(5, 55, 100, 40));
      // Second layer: one column to the right, back at the first row.
      expect(rectOf('q3'), const Rect.fromLTWH(125, 5, 100, 40));
      expect(layout.nodes.firstWhere((n) => n.id == 'q3').layer, 1);
      // padding*2 + 2 columns + 1 gap;  padding*2 + 2 rows + 1 gap.
      expect(layout.size, const Size(230, 100));
    });

    test('rows within a layer follow the screen order, not the id order', () {
      // The rail beside the diagram lists questions by page then 設問番号;
      // the layer itself is id-sorted to match the backend, so the row order
      // has to be re-derived from the caller's list or the two disagree.
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q9', label: '1'),
          _question('q1', label: '2'),
        ],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.map((n) => n.id), ['q9', 'q1']);
    });

    test('an edge that would run behind a node is routed into a free lane', () {
      // `A -> B`, `B -> C` *and* `A -> C` is an ordinary graph, and the three
      // land in the same row of three consecutive layers -- so A -> C runs
      // straight through B's opaque card unless it is moved (review round 1,
      // P2).
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q2'), _edge('q2', 'q3'), _edge('q1', 'q3')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      DagEdgeLine lineFor(String from, String to) =>
          layout.edges.firstWhere((e) => e.key == '$from>$to');

      // Adjacent layers have nothing in between and stay direct.
      expect(lineFor('q1', 'q2').detour, isNull);
      expect(lineFor('q2', 'q3').detour, isNull);
      // The skipping edge travels below every node row: rows bottom is
      // padding(5) + 1 row(40) = 45, plus one laneGap(10).
      expect(lineFor('q1', 'q3').detour?.y, 55);
      // The drop and the climb are each at most half a column gap, so the two
      // of them together never reach out of the empty column they start in
      // and into the next layer's cards.
      expect(lineFor('q1', 'q3').detour!.shoulder, metrics.columnGap / 2);
      // The canvas grows to hold the lane, so it is never simply clipped.
      expect(layout.size.height, 60);
    });

    test('a skipping edge with a clear diagonal keeps its direct line', () {
      // Only edges a node is actually standing in the way of pay for a lane;
      // routing every skipping edge below the diagram would send a perfectly
      // readable line on a detour and grow the panel for nothing.
      //
      // Layers here are {q1,q2} / {q3} / {q4,q5}. The skipping edge q2 -> q5
      // runs along the *second* row, and the only node in between (q3) is
      // alone in its layer and therefore in the first -- nothing is in the
      // way.
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1'),
          _question('q2'),
          _question('q3'),
          _question('q4'),
          _question('q5'),
        ],
        edges: [
          _edge('q2', 'q3'),
          _edge('q3', 'q4'),
          _edge('q3', 'q5'),
          _edge('q2', 'q5'),
        ],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.firstWhere((n) => n.id == 'q3').rect.top, 5);
      expect(layout.edges.firstWhere((e) => e.key == 'q2>q5').detour, isNull);
      expect(layout.size.height, 100);
    });

    test('a detour never drops further out than the column it starts in', () {
      // The lane is what clears the cards; the drop and the climb have to be
      // kept away from them separately, because that part of the route is not
      // down in the lane yet. Half a column gap each is what guarantees it,
      // whatever the node size -- with the panel's own metrics the two
      // together are exactly one empty column wide.
      const wide = DagMetrics(columnGap: 8);
      expect(wide.detourShoulder(1000), 4);
      // ...and never so long that the lane stops being the longest part of
      // the route.
      expect(wide.detourShoulder(8), 2);
    });

    test('an edge is satisfied only when its prerequisite released it', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2'), _question('q3')],
        edges: [_edge('q1', 'q2'), _edge('q2', 'q3')],
        releasedQuestionIds: const {'q1'},
        metrics: metrics,
      )!;
      expect(layout.satisfiedEdgeKeys, {'q1>q2'});
    });

    test('an edge runs from the prerequisite\'s right to the dependent\'s '
        'left, so its direction is the layout\'s own', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      final edge = layout.edges.single;
      expect(edge.start, const Offset(105, 25));
      expect(edge.end, const Offset(125, 25));
      expect(edge.key, 'q1>q2');
    });

    test('drops an edge whose endpoint is not on screen', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1')],
        edges: [_edge('q1', 'gone')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.edges, isEmpty);
      expect(layout.size, const Size(110, 50));
    });

    test('a blocked node names the question it is waiting on', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', label: '1'),
          _question(
            'q2',
            label: '2',
            status: QuestionStatus.blocked,
            blockedOnQuestionId: 'q1',
          ),
        ],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      final blocked = layout.nodes.firstWhere((n) => n.id == 'q2');
      expect(blocked.statusLabel, '問1 待ち');
      expect(blocked.semanticsLabel, '問2 問1 待ち');
    });

    test('a blocked node with no recorded prerequisite still says so', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', label: '1', status: QuestionStatus.blocked),
        ],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.nodes.single.statusLabel, '前提待ち');
    });

    test('returns null for a cyclic graph and for no questions', () {
      expect(
        buildDependencyDagLayout(
          questions: [_question('q1'), _question('q2')],
          edges: [_edge('q1', 'q2'), _edge('q2', 'q1')],
          releasedQuestionIds: const {},
        ),
        isNull,
      );
      expect(
        buildDependencyDagLayout(
          questions: const [],
          edges: const [],
          releasedQuestionIds: const {},
        ),
        isNull,
      );
    });

    // ---------------------------------------------------------------- //
    // Issue #85: a 3-layer diagram is ~480px wide, and in a full-width band
    // it sat in the left three fifths of the window with nothing to its
    // right. The slack goes into the gaps between layers, where the arrows
    // are, and stops before an arrow reads as two unrelated groups.
    // ---------------------------------------------------------------- //
    test('spreads the gaps between layers to fill the width it is given', () {
      final natural = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      // padding*2 + 2 columns + 1 gap.
      expect(natural.size.width, 230);

      final spread = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
        availableWidth: 260,
      )!;
      expect(spread.size.width, 260);
      // Only the gap grew: the nodes are the same size, and the first one is
      // still where the padding puts it.
      final first = spread.nodes.firstWhere((n) => n.id == 'q1').rect;
      final second = spread.nodes.firstWhere((n) => n.id == 'q2').rect;
      expect(first, const Rect.fromLTWH(5, 5, 100, 40));
      expect(second.width, 100);
      expect(second.left - first.right, 50);
      // The rows are untouched -- this is a horizontal decision only.
      expect(spread.size.height, natural.size.height);
    });

    test('stops spreading at the cap, and never shrinks to fit', () {
      final capped = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
        availableWidth: 100000,
      )!;
      // padding*2 + 2 columns + the capped gap (3x the 20 this test set).
      expect(capped.size.width, 210 + 20 * AppLayout.dagColumnGapSpreadLimit);

      // Narrower than the diagram needs: it keeps its natural size and the
      // panel scrolls, because a fitted diagram loses the label legibility
      // that is the whole reason the nodes are the size they are.
      final squeezed = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: [_edge('q1', 'q2')],
        releasedQuestionIds: const {},
        metrics: metrics,
        availableWidth: 50,
      )!;
      expect(squeezed.size.width, 230);
    });

    test('a single-layer diagram has no gap to spend the slack on', () {
      final layout = buildDependencyDagLayout(
        questions: [_question('q1'), _question('q2')],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
        availableWidth: 1000,
      )!;
      expect(layout.size.width, 110);
    });

    test('counts the states the collapsed header summarises', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', status: QuestionStatus.running),
          _question('q2', status: QuestionStatus.blocked),
          _question('q3', status: QuestionStatus.approved),
        ],
        edges: const [],
        releasedQuestionIds: const {},
        metrics: metrics,
      )!;
      expect(layout.countWhere((s) => s == QuestionStatus.running), 1);
      expect(
        layout.countWhere((s) => s.progress == DagNodeProgress.waiting),
        1,
      );
      expect(
        layout.countWhere((s) => s.progress == DagNodeProgress.settled),
        1,
      );
      expect(layout.statusById, {
        'q1': QuestionStatus.running,
        'q2': QuestionStatus.blocked,
        'q3': QuestionStatus.approved,
      });
    });
  });

  // ------------------------------------------------------------------ //
  // Issue #86: 失敗が要約から漏れ、下流の「待ち」が恒久停止を隠していた。
  //
  // 直す前の実測 (`flutter test`, このファイルと同じ組み立ての答案):
  //
  //   要確認: summary="実行中 0 ・ 待機 2 ・ 完了 3" q3="問2 待ち" q5="問3 待ち"
  //   失敗  : summary="実行中 0 ・ 待機 2 ・ 完了 3" q3="問2 待ち" q5="問3 待ち"
  //
  // 3つとも完全に同一だった。要約が同一なのは `DagNodeProgress` が 失敗 も
  // 要確認 も `settled`(完了) に畳んでいたからで、ラベルが同一なのは
  // `labelWaitingFor` が前提の**番号だけ**を見て、その前提がどんな状態かを
  // 見ていなかったからである。
  // ------------------------------------------------------------------ //
  group('Issue #86: 人の対応を待って止まっているもの', () {
    test('要確認で止まった答案と、失敗した答案は、要約の文字列が違う', () {
      final blocked = _submission(q2: QuestionStatus.needsCheck);
      final failed = _submission(q2: QuestionStatus.failed);

      expect(blocked.progressSummary, '実行中 0 ・ 待機 2 ・ 要確認 1 ・ 完了 2');
      expect(failed.progressSummary, '実行中 0 ・ 待機 2 ・ 失敗 1 ・ 完了 2');
      // 否定形そのもの。上の2行が両方とも実際の文字列を固定しているので、
      // 「どちらも空になって等しくなくなった」では緑にならない。
      expect(blocked.progressSummary, isNot(failed.progressSummary));
    });

    test('要確認と失敗が0件のときは、要約に出さない', () {
      final quiet = buildDependencyDagLayout(
        questions: [
          _question('q1', status: QuestionStatus.running),
          _question('q2', status: QuestionStatus.approved),
        ],
        edges: const [],
        releasedQuestionIds: const {},
      )!;

      // 常時点いている旗は旗として働かない (§1.3 が一度払った授業料)。
      // 呼ばれていないときは、呼ばれていないと分かる形にする。
      expect(quiet.progressSummary, '実行中 1 ・ 待機 0 ・ 完了 1');
    });

    test('どのノードもちょうど1つのバケツに入る', () {
      // 「実行中 n ・ 待機 n ・ …」の合計がノード数と一致しなくなると、
      // 畳んだヘッダが答案の一部を黙って落とすことになる。
      for (final status in QuestionStatus.values) {
        final layout = _submission(q2: status);
        final counts = layout.progressCounts;
        expect(
          counts.values.fold(0, (a, b) => a + b),
          layout.nodes.length,
          reason: '$status を含む答案でバケツの合計がノード数と合わない',
        );
      }
    });

    test('下流の「待ち」が、上流が失敗したのか確認待ちなのかで変わる', () {
      final blocked = _submission(q2: QuestionStatus.needsCheck);
      final failed = _submission(q2: QuestionStatus.failed);

      expect(_statusLabelOf(blocked, 'q3'), '問2 確認待ち');
      expect(_statusLabelOf(failed, 'q3'), '問2 失敗で停止');
      expect(
        _statusLabelOf(blocked, 'q3'),
        isNot(_statusLabelOf(failed, 'q3')),
      );
    });

    test('2つ先で止まっている設問も、直せる設問のほうを名指す', () {
      // 問5 は問3 待ちで、問3 は問2 待ちで、問2 が失敗している。「問3 待ち」
      // と書くと、問3 に何かできるかのように読める -- 問3 にできることは
      // 何も無い。人が動ける場所は問2 だけである。
      final failed = _submission(q2: QuestionStatus.failed);
      expect(_statusLabelOf(failed, 'q5'), '問2 失敗で停止');

      // 上流がまだ動いているなら話は別で、そのときは直前の前提を名指す。
      // 待っていれば本当に進むからである。
      final running = _submission(q2: QuestionStatus.running);
      expect(_statusLabelOf(running, 'q3'), '問2 待ち');
      expect(_statusLabelOf(running, 'q5'), '問3 待ち');
    });

    test('失敗したノードは、理由と次の一手と、止めている下流を持つ', () {
      final failed = _submission(
        q2: QuestionStatus.failed,
        errorCode: 'permanent',
        lastError:
            "gemini AI provider reported that the answer image is not this "
            'question\'s answer (crop_not_the_answer)',
      );

      expect(failed.failures, hasLength(1));
      final failure = failed.failures.single;
      expect(failure.questionId, 'q2');
      expect(failure.guidance, DagFailureGuidance.answerAreaWrong);
      // 止まっているのは直接の下流だけではない。
      expect(failure.stalledQuestionLabels, ['3', '5']);
      expect(failure.headline, '問2 が失敗し、問3・問5 は人が対応するまで進みません。');
    });

    test('何も止めていない失敗は、下流のことを言わない', () {
      final layout = buildDependencyDagLayout(
        questions: [
          _question('q1', label: '1', status: QuestionStatus.failed),
          _question('q2', label: '2', status: QuestionStatus.graded),
        ],
        edges: const [],
        releasedQuestionIds: const {},
      )!;

      expect(layout.failures.single.stalledQuestionLabels, isEmpty);
      expect(layout.failures.single.headline, '問1 が失敗しました。');
    });

    test('失敗していない答案には、失敗の告知が無い', () {
      expect(_submission(q2: QuestionStatus.needsCheck).failures, isEmpty);
    });

    test('生の last_error はノードにも要約にも残らない', () {
      // `DagQuestion` が受け取って捨てる。持ち出せる形で残っていないことを、
      // ノードの持ち物すべてを1本の文字列にして確かめる。
      final failed = _submission(
        q2: QuestionStatus.failed,
        errorCode: 'server_error',
        lastError: 'gemini AI provider timed out [vertex-ai 503]',
      );
      final everything = [
        failed.progressSummary,
        for (final node in failed.nodes) ...[
          node.statusLabel,
          node.semanticsLabel,
          node.question.label,
        ],
        for (final failure in failed.failures) ...[
          failure.headline,
          failure.guidance.cause,
          failure.guidance.nextStep,
        ],
      ].join('\n');

      for (final fragment in ['gemini', 'vertex-ai', '503', 'timed out']) {
        expect(everything, isNot(contains(fragment)));
      }
      // 落としただけではない。分類はちゃんと届いている。
      expect(failed.failures.single.guidance, DagFailureGuidance.temporary);
    });

    test('止まった設問は、読み上げでも「進まない」と言う', () {
      final failed = _submission(q2: QuestionStatus.failed);
      final q3 = failed.nodes.firstWhere((n) => n.id == 'q3');
      expect(q3.semanticsLabel, '問3 問2 失敗で停止。人が対応するまで進みません');
    });
  });

  group('resolveQuestionWait', () {
    QuestionWait? resolve(
      String from,
      Map<String, (String?, QuestionStatus)> chain,
    ) => resolveQuestionWait(
      from,
      blockedOn: (id) => chain[id]?.$1,
      statusOf: (id) => chain[id]?.$2 ?? QuestionStatus.pending,
      numberOf: (id) => chain.containsKey(id) ? id.substring(1) : null,
    );

    test('名指せない前提は名指さない', () {
      // グラフはテスト全体ぶん取ってくるので、この答案の設問一覧に無い設問を
      // 名指してくることがある。番号が引けないものは「前提待ち」のままにする。
      expect(resolve('q1', {'q1': ('q9', QuestionStatus.failed)}), isNull);
    });

    test('止まっていない前提は、直前のものを返す', () {
      expect(
        resolve('q1', {
          'q1': ('q2', QuestionStatus.blocked),
          'q2': ('q3', QuestionStatus.running),
          'q3': (null, QuestionStatus.running),
        }),
        const QuestionWait(
          questionId: 'q2',
          number: '2',
          status: QuestionStatus.running,
        ),
      );
    });

    test('循環しているポインタで固まらない', () {
      // 確定済みグラフは非巡回だが、これが辿るのはキューの `blocked_on` の
      // 行であって、再起票の途中では古い行が残りうる。ここで回ると
      // フレームごと止まる。
      expect(
        resolve('q1', {
          'q1': ('q2', QuestionStatus.blocked),
          'q2': ('q1', QuestionStatus.blocked),
        }),
        const QuestionWait(
          questionId: 'q2',
          number: '2',
          status: QuestionStatus.blocked,
        ),
      );
    });
  });
}
