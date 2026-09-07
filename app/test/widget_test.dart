import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/main.dart';

/// The composition root's smoke test: `AutoScoringApp` without a supervisor
/// boots straight to ホーム画面 under the app's own theme.
///
/// It used to assert `backend: ok` -- the debug string ホーム画面 carried while
/// it was a boot check. That is gone (Issue #68): sidecar health is
/// `SidecarStartupOverlay`'s job (Issue #24), and this screen is only reached
/// once the connection is up. What ホーム画面 shows instead is covered by
/// `home_page_test.dart`; here we only care that the root wires it at all.
void main() {
  testWidgets('boots into ホーム画面 with the app theme', (tester) async {
    await tester.pumpWidget(const AutoScoringApp());

    expect(find.text('Auto-Scoring'), findsOneWidget);
    expect(find.byType(HomePage), findsOneWidget);

    // Settles the default (not-connected) dependencies' failure into the
    // screen's own error state -- no exception escapes it.
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme?.useMaterial3, isTrue);
  });
}
