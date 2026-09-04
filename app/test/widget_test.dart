import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/main.dart';

void main() {
  testWidgets('renders the home screen and reports backend health', (
    tester,
  ) async {
    await tester.pumpWidget(const AutoScoringApp());

    expect(find.text('Auto-Scoring'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.text('backend: ok'), findsOneWidget);

    final materialApp = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(materialApp.theme?.useMaterial3, isTrue);
  });
}
