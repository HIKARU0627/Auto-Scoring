import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

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

    await tester.pumpWidget(
      MaterialApp(home: TestListPage(dependencies: dependencies)),
    );
    await tester.pumpAndSettle();

    expect(find.text('下書き'), findsOneWidget);

    await tester.tap(find.byKey(const Key('test-list-tile-test-1')));
    await tester.pumpAndSettle();
    expect(find.byType(TestSettingsPage), findsOneWidget);

    // Simulate the reviewer finishing on the settings screen and coming
    // back, without needing to drive that whole flow from here.
    Navigator.of(tester.element(find.byType(TestSettingsPage))).pop();
    await tester.pumpAndSettle();

    expect(find.byType(TestSettingsPage), findsNothing);
    expect(find.text('登録完了'), findsOneWidget);
    expect(find.text('下書き'), findsNothing);
  });
}
