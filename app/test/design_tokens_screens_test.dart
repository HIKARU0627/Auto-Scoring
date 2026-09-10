import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_color_schemes.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_harness.dart';

/// Walks every screen under **both** themes (Issue #67 acceptance:
/// 「ライト/ダーク両方で、主要5画面が新しいトークンで一貫して描画される」).
///
/// This stands in for the before/after screenshots that criterion also asks
/// for: screenshot capture is not trustworthy until Issue #73 lands, so what
/// can be checked now is that every screen builds under either theme and takes
/// its ground colour from that theme's ramp rather than from a hard-coded
/// white. A screen that reached for a missing `ThemeExtension`, or painted its
/// own background, fails here in dark and passes in light.
///
/// It is deliberately shallow -- each screen's behaviour is covered by its own
/// test file. What is new here is running them twice.
void main() {
  TestResponse buildTest() => TestResponse(
    (b) => b
      ..id = 'test-1'
      ..name = '国語 第1回'
      ..status = 'draft'
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  Never notFound() => throw SidecarApiException(
    SidecarErrorKind.badResponse,
    'not found',
    statusCode: 404,
  );

  // Enough of the sidecar to get each screen past its initial load. The
  // 添削レビュー entry deliberately fails to load: its full path renders a real
  // PDF through pdfium, and the shell-error state exercises the tokens this
  // test is about (`AppErrorBanner`, the icon scale, the surface ramp) without
  // dragging a native decoder into a theme check.
  final dependencies = AppDependencies(
    listTests: () async => [
      TestSummary(
        (b) => b
          ..id = 'test-1'
          ..name = '国語 第1回',
      ),
    ],
    listTestRegistrations: () async => [buildTest()],
    getTest: (_) async => buildTest(),
    listSubmissions: (_) async => const [],
    getProfile: (_) async => notFound(),
    getDependencyGraph: (_) async => notFound(),
    getSubmission: (_) async => notFound(),
  );

  final screens = <String, String>{
    'ホーム画面': AppRoutes.home,
    '資料取込画面': AppRoutes.intake,
    'テスト一覧画面': AppRoutes.testList,
    'テスト設定画面': AppRoutes.testSettings('test-1'),
    '設定画面': AppRoutes.settings,
    '添削レビュー画面': AppRoutes.pdfReview(testId: 'test-1', submissionId: 'sub-1'),
    '答案確定画面': AppRoutes.submissionConfirm(
      testId: 'test-1',
      submissionId: 'sub-1',
    ),
  };

  for (final brightness in Brightness.values) {
    for (final screen in screens.entries) {
      testWidgets('${screen.key} renders under the ${brightness.name} theme', (
        tester,
      ) async {
        await pumpAppAt(
          tester,
          screen.value,
          dependencies: dependencies,
          brightness: brightness,
        );
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);

        final scaffold = tester.widget<Material>(
          find
              .descendant(
                of: find.byType(Scaffold),
                matching: find.byType(Material),
              )
              .first,
        );
        expect(
          scaffold.color,
          appColorScheme(brightness).surface,
          reason:
              '${screen.key} must take its ground from the theme ramp, not '
              'from a colour of its own',
        );
      });
    }
  }
}
