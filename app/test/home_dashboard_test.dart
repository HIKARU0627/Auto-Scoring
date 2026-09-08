import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/home/home_dashboard.dart';

/// ホーム画面が「次に何をすればいいか」をどう決めているか (Issue #68).
///
/// 画面を立ち上げずにここで検査するのは、この優先順位がホームで唯一の
/// 意見らしい意見だからである。ウィジェットの中に埋めると、順序を変えた
/// つもりが無いのに変わってしまっても誰も気付かない。
void main() {
  TestResponse buildTest({
    required String id,
    String name = 'テスト',
    String status = 'ready',
    int createdDay = 1,
  }) => TestResponse(
    (b) => b
      ..id = id
      ..name = name
      ..status = status
      ..createdAt = DateTime.utc(2026, 1, createdDay),
  );

  SubmissionResponse buildSubmission({
    required String id,
    required String testId,
    required String state,
    int createdDay = 1,
    String? studentLabel,
  }) => SubmissionResponse(
    (b) => b
      ..id = id
      ..testId = testId
      ..state = state
      ..pageCount = 1
      ..studentLabel = studentLabel
      ..createdAt = DateTime.utc(2026, 2, createdDay),
  );

  HomeDashboard build(
    Map<TestResponse, List<SubmissionResponse>> work, {
    int hiddenTestCount = 0,
  }) => HomeDashboard.from(
    tests: work.keys.toList(),
    submissionsByTestId: {
      for (final entry in work.entries) entry.key.id: entry.value,
    },
    hiddenTestCount: hiddenTestCount,
  );

  group('HomeWorkBucket', () {
    test('答案の7状態をホームが数える5つへ畳む', () {
      expect(HomeWorkBucket.of('needs_review'), HomeWorkBucket.needsReview);
      expect(HomeWorkBucket.of('ai_processed'), HomeWorkBucket.intakeDone);
      expect(HomeWorkBucket.of('unprocessed'), HomeWorkBucket.processing);
      expect(HomeWorkBucket.of('ai_processing'), HomeWorkBucket.processing);
      expect(HomeWorkBucket.of('error'), HomeWorkBucket.failed);
      expect(HomeWorkBucket.of('reviewed'), HomeWorkBucket.done);
      expect(HomeWorkBucket.of('exported'), HomeWorkBucket.done);
    });

    test('知らない状態は完了ではなく処理中に倒す', () {
      // サイドカーが先に新しい状態を覚えた場合、それを [done] に数えると
      // 進捗バーが「終わった」と嘘をつく。
      expect(HomeWorkBucket.of('something_new'), HomeWorkBucket.processing);
    });
  });

  group('HomeTestProgress', () {
    test('確認済みの分母は取り込んだ答案の総数', () {
      final test = buildTest(id: 't1');
      final progress = HomeTestProgress(
        test: test,
        submissions: [
          buildSubmission(id: 's1', testId: 't1', state: 'reviewed'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
          buildSubmission(id: 's3', testId: 't1', state: 'needs_review'),
          buildSubmission(id: 's4', testId: 't1', state: 'ai_processing'),
        ],
      );

      expect(progress.total, 4);
      expect(progress.doneCount, 2);
      expect(progress.countOf(HomeWorkBucket.needsReview), 1);
      expect(progress.countOf(HomeWorkBucket.processing), 1);
      expect(progress.countOf(HomeWorkBucket.failed), 0);
    });

    test('続きの1件は要確認を優先し、同じ状態なら取込の古い順', () {
      final progress = HomeTestProgress(
        test: buildTest(id: 't1'),
        submissions: [
          buildSubmission(
            id: 'old-processed',
            testId: 't1',
            state: 'ai_processed',
            createdDay: 1,
          ),
          buildSubmission(
            id: 'new-flagged',
            testId: 't1',
            state: 'needs_review',
            createdDay: 5,
          ),
          buildSubmission(
            id: 'old-flagged',
            testId: 't1',
            state: 'needs_review',
            createdDay: 3,
          ),
        ],
      );

      expect(progress.resumableSubmission?.id, 'old-flagged');
    });

    test('人間待ちが無ければ続きの1件も無い', () {
      final progress = HomeTestProgress(
        test: buildTest(id: 't1'),
        submissions: [
          buildSubmission(id: 's1', testId: 't1', state: 'ai_processing'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
        ],
      );

      expect(progress.resumableSubmission, isNull);
      expect(progress.order, 3);
    });
  });

  group('表示順', () {
    test('レビューが止まっているテストが先、その中では新しい順', () {
      final idle = buildTest(id: 'idle', createdDay: 9);
      final waiting = buildTest(id: 'waiting', createdDay: 2);
      final alsoWaiting = buildTest(id: 'also-waiting', createdDay: 5);

      final dashboard = build({
        idle: [buildSubmission(id: 's1', testId: 'idle', state: 'exported')],
        waiting: [
          buildSubmission(id: 's2', testId: 'waiting', state: 'needs_review'),
        ],
        alsoWaiting: [
          buildSubmission(
            id: 's3',
            testId: 'also-waiting',
            state: 'needs_review',
          ),
        ],
      });

      expect(dashboard.tests.map((t) => t.test.id), [
        'also-waiting',
        'waiting',
        'idle',
      ]);
    });
    test('新しい下書きでも、レビューが止まっているテストより後ろ', () {
      // 「次の一手」がレビューを指しているのに、その下の1枚目が下書きだと
      // 目の動きが噛み合わない。並びは nextAction の優先順位に合わせる。
      final draft = buildTest(id: 'draft', status: 'draft', createdDay: 9);
      final waiting = buildTest(id: 'waiting', createdDay: 1);
      final failed = buildTest(id: 'failed', createdDay: 5);

      final dashboard = build({
        draft: const [],
        waiting: [
          buildSubmission(id: 's1', testId: 'waiting', state: 'needs_review'),
        ],
        failed: [buildSubmission(id: 's2', testId: 'failed', state: 'error')],
      });

      expect(dashboard.tests.map((t) => t.test.id), [
        'waiting',
        'draft',
        'failed',
      ]);
    });
  });

  group('次の一手', () {
    test('要確認があれば、その最古の答案の添削レビューへ', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(
            id: 'newer',
            testId: 't1',
            state: 'needs_review',
            createdDay: 4,
          ),
          buildSubmission(
            id: 'oldest',
            testId: 't1',
            state: 'needs_review',
            createdDay: 2,
          ),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('要確認'));
      expect(action.headline, contains('2件'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 't1', submissionId: 'oldest'),
      );
    });

    test('古いテストの要確認が、新しいテストの通常レビューより先', () {
      // テストの新しさで先にタイブレークすると、新しい方の「取込済み」が
      // 勝ってしまう。優先順位は答案のbucketが先 (§2.1)。
      final older = buildTest(id: 'older', createdDay: 1);
      final newer = buildTest(id: 'newer', createdDay: 9);
      final dashboard = build({
        newer: [
          buildSubmission(
            id: 'awaiting',
            testId: 'newer',
            state: 'ai_processed',
          ),
        ],
        older: [
          buildSubmission(
            id: 'flagged',
            testId: 'older',
            state: 'needs_review',
          ),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('要確認'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 'older', submissionId: 'flagged'),
      );
      // カードの並びも同じ順序でないと、上のボタンと1枚目が食い違う。
      expect(dashboard.tests.map((t) => t.test.id), ['older', 'newer']);
    });

    test('見出しは名指ししたbucketだけを数え、残りは説明文が引き取る', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 'flagged', testId: 't1', state: 'needs_review'),
          for (var index = 0; index < 9; index++)
            buildSubmission(
              id: 'awaiting-$index',
              testId: 't1',
              state: 'ai_processed',
            ),
        ],
      });

      final action = dashboard.nextAction;
      // 「要確認の答案が10件あります」だと、カードが示す 要確認 1件 と食い違う。
      expect(action.headline, '要確認の答案が1件あります');
      expect(action.detail, contains('ほかに取込済みが9件'));
    });

    test('要確認だけのときは説明文に但し書きを付けない', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 'flagged', testId: 't1', state: 'needs_review'),
        ],
      });

      expect(dashboard.nextAction.detail, isNot(contains('ほかに')));
    });

    test('取込済みの答案について、採点もレビューもどこまで進んだか断定しない', () {
      // `ai_processed` は取込時の画像前処理・回答欄抽出まで終わった状態で、
      // OCR/AI採点はその先から始まる (backend の submission_intake.py)。
      //
      // ホームが知らないのは「終わったか」だけではない。**始まったかどうかも
      // 知らない**: 起票が409や通信断で失敗した答案と、Issue #80 より前に
      // 取り込まれた答案は `ai_processed` のままジョブ0件で止まっていて、
      // ホームは `listJobs` を引かないのでそれを見分けられない
      // (docs/home-dashboard.md §3.1、review round 1 P2-1)。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('取込と回答欄の抽出は終わっています'));
      expect(detail, contains('AI採点とレビューがどこまで進んだかはホームでは分かりません'));
      // 「開始済み」も「採点済み」も、ホームは知らない。
      expect(detail, isNot(contains('開始済み')));
      expect(detail, isNot(contains('採点済みです')));
      expect(detail, isNot(contains('採点中')));
      expect(dashboard.nextAction.headline, isNot(contains('採点済み')));
      // 「待ち」とも言わない -- 承認済みの答案も `ai_processed` のまま
      // ここに残る (review round 2, P3)。
      expect(HomeWorkBucket.intakeDone.label, '取込済み');
      expect(dashboard.nextAction.headline, isNot(contains('レビュー待ち')));
    });

    test('答案が1件も無いときも、採点が必ず始まるとは言わない', () {
      // 回答欄が揃わなければ要確認で止まり、起票そのものが失敗することもある。
      final test = buildTest(id: 't1');
      final dashboard = build({test: const []});

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('問題がなければ'));
      expect(detail, isNot(contains('AI採点の開始まで自動で行われます')));
    });

    test('要確認が無く取込済みだけならそちらを開く', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('取込済み'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 't1', submissionId: 's1'),
      );
    });

    test('レビューすべき答案が無くなってから取込失敗を出す', () {
      final withError = buildTest(id: 't1', name: '国語 第1回');
      final dashboard = build({
        withError: [
          buildSubmission(id: 's1', testId: 't1', state: 'error'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('取込に失敗'));
      expect(action.detail, contains('国語 第1回'));
      expect(action.route, AppRoutes.intake);
    });

    test('取込失敗があっても取込済みが先', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 's1', testId: 't1', state: 'error'),
          buildSubmission(id: 's2', testId: 't1', state: 'needs_review'),
        ],
      });

      expect(dashboard.nextAction.headline, contains('要確認'));
    });

    test('登録が途中のテストはテスト設定画面へ', () {
      final draft = buildTest(id: 't1', name: '数学 第2回', status: 'draft');
      final dashboard = build({draft: const []});

      final action = dashboard.nextAction;
      expect(action.headline, contains('登録が途中'));
      expect(action.detail, contains('数学 第2回'));
      expect(action.route, AppRoutes.testSettings('t1'));
    });

    test('AI処理中しか無いときは行き先を持たず、更新だけを促す', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 's1', testId: 't1', state: 'ai_processing'),
          buildSubmission(id: 's2', testId: 't1', state: 'unprocessed'),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('2件'));
      expect(action.route, isNull);
    });

    test('片付いていれば次の取込を促す', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'exported')],
      });

      expect(dashboard.nextAction.route, AppRoutes.intake);
    });

    test('載せきれなかったテストがあるとき、不在も件数も範囲を明示する', () {
      // 直近8件が片付いていても、答案を取得していないテストに開くべき答案が
      // 残っているかどうかは分からない。「ありません」と言い切れない。
      final settled = buildTest(id: 't1');
      final dashboard = build({
        settled: [buildSubmission(id: 's1', testId: 't1', state: 'exported')],
      }, hiddenTestCount: 4);

      final action = dashboard.nextAction;
      expect(action.headline, '直近1件のテストに、いま開く答案はありません');
      expect(action.detail, contains('ほかに4件'));
    });

    test('載せきれなかったテストがあるとき、件数にも範囲の但し書きが付く', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'needs_review')],
      }, hiddenTestCount: 2);

      expect(dashboard.nextAction.detail, contains('ほかに2件'));
    });

    test('全テストを載せているときは範囲の但し書きを付けない', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'needs_review')],
      });

      expect(dashboard.nextAction.detail, isNot(contains('ほかに1件')));
      expect(dashboard.nextAction.detail, isNot(contains('数えたのは')));
    });

    test('取込失敗からの復旧を保証しない', () {
      // 再取込が受け付けられるのは下流データ (認識・採点・レビュー・ジョブ) が
      // 無い答案だけで、あるものは409で拒否される。ホームは下流の有無を
      // 取得していないので「取り込み直せば直る」とは言えない。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'error')],
      });

      final action = dashboard.nextAction;
      expect(action.detail, isNot(contains('やり直せます')));
      expect(action.detail, isNot(contains('取り込み直す')));
    });

    test('処理中の行き先を1つに決めつけない', () {
      // 取込の結果は ai_processed / needs_review / error の3通りある。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processing')],
      });

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('要確認'));
      expect(detail, contains('取込失敗'));
    });

    test('取込済みの答案の順序を、テストをまたいだ最古と読ませない', () {
      // 実際の選択は「テストを選んでから、その中で取込の古い順」。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      expect(dashboard.nextAction.detail, contains('テストごとに'));
    });

    test('下書きのどの確認手順が残っているかは断定しない', () {
      // `ready` にはプロファイルと依存関係グラフ両方の確定が要るが、どちらが
      // 済んでいるかはホームが取得していない。
      final draft = buildTest(id: 't1', name: '理科 第1回', status: 'draft');
      final dashboard = build({draft: const []});

      expect(dashboard.nextAction.detail, contains('登録がまだ完了していません'));
      expect(dashboard.nextAction.detail, isNot(contains('終わっていません')));
    });

    test('テストが1件も無ければテスト登録へ', () {
      final dashboard = build(const {});

      expect(dashboard.isEmpty, isTrue);
      expect(dashboard.nextAction.route, AppRoutes.intake);
    });
  });
}
