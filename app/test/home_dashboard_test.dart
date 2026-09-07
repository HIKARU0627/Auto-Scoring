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
      expect(HomeWorkBucket.of('ai_processed'), HomeWorkBucket.awaitingReview);
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
      expect(progress.order, 2);
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

    test('要確認が無くレビュー待ちだけならそちらを開く', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('レビュー待ち'));
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
      expect(action.route, AppRoutes.answerIntake);
    });

    test('取込失敗があってもレビュー待ちが先', () {
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

      expect(dashboard.nextAction.route, AppRoutes.answerIntake);
    });

    test('テストが1件も無ければテスト登録へ', () {
      final dashboard = build(const {});

      expect(dashboard.isEmpty, isTrue);
      expect(dashboard.nextAction.route, AppRoutes.testRegistration);
    });
  });
}
