import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/review_queue/submission_queue_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'app_harness.dart';

TestResponse _test({required String id, required String status}) {
  return TestResponse(
    (b) => b
      ..id = id
      ..name = 'テスト $id'
      ..status = status
      ..createdAt = DateTime.utc(2026, 1, 1),
  );
}

Never _notFound() => throw SidecarApiException(
  SidecarErrorKind.badResponse,
  'not found',
  statusCode: 404,
);

void main() {
  testWidgets('opening a draft test and returning reloads its status', (
    tester,
  ) async {
    // The list's own response is fetched once, before the tile is ever
    // tapped -- a status change made on the settings screen (e.g.
    // completing registration) must not be masked by that stale snapshot
    // once the reviewer comes back (Issue #16 review round 5).
    var listCallCount = 0;
    final dependencies = AppDependencies(
      listTestRegistrations: () async {
        listCallCount++;
        final status = listCallCount == 1 ? 'draft' : 'ready';
        return [_test(id: 'test-1', status: status)];
      },
      getTest: (testId) async => _test(id: testId, status: 'draft'),
      getProfile: (testId) async => _notFound(),
      getDependencyGraph: (testId) async => _notFound(),
    );

    await pumpAppAt(tester, AppRoutes.testList, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(find.text('下書き — 登録を続ける'), findsOneWidget);

    await tester.tap(find.byKey(const Key('test-list-tile-test-1')));
    await tester.pumpAndSettle();
    expect(find.byType(TestSettingsPage), findsOneWidget);

    // Simulate the reviewer finishing on the settings screen and coming
    // back, without needing to drive that whole flow from here.
    GoRouter.of(tester.element(find.byType(TestSettingsPage))).pop();
    await tester.pumpAndSettle();

    expect(find.byType(TestSettingsPage), findsNothing);
    expect(find.text('登録完了 — 答案を見る'), findsOneWidget);
    expect(find.text('下書き — 登録を続ける'), findsNothing);
  });

  testWidgets(
    'a reload failure after returning from settings shows an error banner, '
    'not an uncaught exception',
    (tester) async {
      // The initial load succeeds; the reload triggered by returning from
      // the settings screen fails. `_reload` awaits that same failing
      // Future itself (to hand it to FutureBuilder via `_testsFuture`), so
      // if it didn't also catch it, the failure would reach this test as
      // an unhandled async exception and fail it -- on top of whatever
      // FutureBuilder rendered (Issue #16 review round 8).
      var listCallCount = 0;
      final dependencies = AppDependencies(
        listTestRegistrations: () async {
          listCallCount++;
          if (listCallCount == 1) {
            return [_test(id: 'test-1', status: 'draft')];
          }
          _notFound();
        },
        getTest: (testId) async => _test(id: testId, status: 'draft'),
        getProfile: (testId) async => _notFound(),
        getDependencyGraph: (testId) async => _notFound(),
      );

      await pumpAppAt(tester, AppRoutes.testList, dependencies: dependencies);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('test-list-tile-test-1')));
      await tester.pumpAndSettle();
      expect(find.byType(TestSettingsPage), findsOneWidget);

      GoRouter.of(tester.element(find.byType(TestSettingsPage))).pop();
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('test-list-error')), findsOneWidget);
    },
  );

  testWidgets('登録を終えたテストから答案キューへ入れる (Issue #151)', (tester) async {
    // #113 の答案キューへの入口はホームのテストカードだけだった。ホームは
    // テストを絞って載せるので、**カードに載らなかったテストの答案には
    // 到達手段が無かった**。全テストを出すのはこの画面だけである。
    final dependencies = AppDependencies(
      listTestRegistrations: () async => [_test(id: 'test-1', status: 'ready')],
      getTest: (testId) async => _test(id: testId, status: 'ready'),
      listSubmissions: (_) async => const [],
      listReviewProgress: (_) async => const [],
    );

    await pumpAppAt(tester, AppRoutes.testList, dependencies: dependencies);
    await tester.pumpAndSettle();

    // 一覧が描けていること。ここを言わずに「キューが出た」だけを見ると、
    // タップが空振りしても気付けない。
    expect(find.byKey(const Key('test-list-tile-test-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('test-list-tile-test-1')));
    await tester.pumpAndSettle();

    expect(find.byType(SubmissionQueuePage), findsOneWidget);
    expect(find.byType(TestSettingsPage), findsNothing);
  });

  testWidgets('登録を終えたテストの設定へは、末尾のボタンから行ける', (tester) async {
    // 答案キューへ寄せた代わりに、テスト設定が届かなくなってはいけない。
    final dependencies = AppDependencies(
      listTestRegistrations: () async => [_test(id: 'test-1', status: 'ready')],
      getTest: (testId) async => _test(id: testId, status: 'ready'),
      getProfile: (testId) async => _notFound(),
      getDependencyGraph: (testId) async => _notFound(),
    );

    await pumpAppAt(tester, AppRoutes.testList, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('test-list-settings-test-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('test-list-settings-test-1')));
    await tester.pumpAndSettle();

    expect(find.byType(TestSettingsPage), findsOneWidget);
  });

  testWidgets('下書きのタイルは、いまも登録の続きへ行く', (tester) async {
    // `draft` のテストは答案を取り込めないので、キューは必ず空にしかならない。
    // そこへ送ると行き止まりが1つ増えるだけである。
    final dependencies = AppDependencies(
      listTestRegistrations: () async => [_test(id: 'test-1', status: 'draft')],
      getTest: (testId) async => _test(id: testId, status: 'draft'),
      getProfile: (testId) async => _notFound(),
      getDependencyGraph: (testId) async => _notFound(),
    );

    await pumpAppAt(tester, AppRoutes.testList, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('test-list-tile-test-1')), findsOneWidget);
    // 下書きに設定ボタンは要らない。タイルそのものが同じ行き先である。
    expect(find.byKey(const Key('test-list-settings-test-1')), findsNothing);

    await tester.tap(find.byKey(const Key('test-list-tile-test-1')));
    await tester.pumpAndSettle();

    expect(find.byType(TestSettingsPage), findsOneWidget);
    expect(find.byType(SubmissionQueuePage), findsNothing);
  });
}
