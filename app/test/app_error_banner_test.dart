import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/widgets/app_error_banner.dart';

/// The one banner 答案取込・テスト登録・テスト設定・添削レビュー all show when
/// something recoverable fails (Issue #67).
void main() {
  Future<void> pump(WidgetTester tester, Widget banner) {
    return tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(body: banner),
      ),
    );
  }

  testWidgets('shows the failure and a working retry', (tester) async {
    var retries = 0;
    await pump(
      tester,
      AppErrorBanner(message: 'offline', onRetry: () => retries++),
    );
    await tester.pumpAndSettle();

    expect(find.text('offline'), findsOneWidget);
    await tester.tap(find.text('再試行'));
    expect(retries, 1);
  });

  testWidgets('a retry already in flight disables the button rather than '
      'removing it, so the banner does not resize under the pointer', (
    tester,
  ) async {
    await pump(tester, const AppErrorBanner(message: 'offline'));
    await tester.pumpAndSettle();

    expect(find.text('再試行'), findsOneWidget);
    expect(
      tester.widget<TextButton>(find.byType(TextButton)).onPressed,
      isNull,
    );
  });

  testWidgets('offers no retry where the screen has nothing to re-run', (
    tester,
  ) async {
    await pump(
      tester,
      const AppErrorBanner(message: 'offline', retryable: false),
    );
    await tester.pumpAndSettle();

    expect(find.text('offline'), findsOneWidget);
    expect(find.byType(TextButton), findsNothing);
  });

  testWidgets('animates in once and then stops', (tester) async {
    // The whole motion budget of Issue #67: an unasked-for banner announces
    // itself, and then nothing on this screen moves again. A banner that never
    // settled would keep `pumpAndSettle` (and a reviewer's eye) busy forever.
    await pump(tester, const AppErrorBanner(message: 'offline'));
    await tester.pump();
    expect(
      tester.widget<Opacity>(find.byType(Opacity)).opacity,
      lessThan(1.0),
      reason: 'it should still be fading in on the first frame',
    );

    await tester.pump(AppMotion.emphasis);
    expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 1.0);
    // `pumpAndSettle` throws if frames keep being scheduled, so reaching the
    // assertion after it is the proof that nothing here loops.
    await tester.pumpAndSettle();
    expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 1.0);
  });
}
