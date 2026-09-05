import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/test_registration/test_registration_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

TestResponse _test({String id = 'test-1', String status = 'draft'}) {
  return TestResponse(
    (b) => b
      ..id = id
      ..name = '国語 第1回'
      ..status = status
      ..createdAt = DateTime.utc(2026, 1, 1),
  );
}

Future<PickedPdfFile?> _fakeModelAnswerPick() async => const PickedPdfFile(
  path: 'C:/tmp/model-answer.pdf',
  name: 'model-answer.pdf',
);

Widget _wrap(Widget page) => MaterialApp(home: page);

void main() {
  testWidgets('registers a test and navigates to the settings screen', (
    tester,
  ) async {
    String? capturedName;
    String? capturedSubject;
    String? capturedModelAnswerPath;
    String? capturedManualPath;
    final dependencies = AppDependencies(
      createTest:
          ({
            required name,
            subject,
            required modelAnswerPath,
            required manualPath,
          }) async {
            capturedName = name;
            capturedSubject = subject;
            capturedModelAnswerPath = modelAnswerPath;
            capturedManualPath = manualPath;
            return _test();
          },
      getTest: (testId) async => _test(),
    );

    var pickCount = 0;
    Future<PickedPdfFile?> pickFile() async {
      pickCount++;
      return pickCount == 1
          ? await _fakeModelAnswerPick()
          : const PickedPdfFile(path: 'C:/tmp/manual.pdf', name: 'manual.pdf');
    }

    await tester.pumpWidget(
      _wrap(
        TestRegistrationPage(dependencies: dependencies, pickFile: pickFile),
      ),
    );
    await tester.pumpAndSettle();

    // The register button starts disabled: no name and no PDFs yet.
    final registerButtonFinder = find.byKey(const Key('register-test-button'));
    expect(tester.widget<FilledButton>(registerButtonFinder).onPressed, isNull);

    await tester.enterText(find.byKey(const Key('test-name-field')), '国語 第1回');
    await tester.enterText(find.byKey(const Key('test-subject-field')), '国語');
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('model-answer-picker')));
    await tester.pumpAndSettle();
    expect(find.text('model-answer.pdf'), findsOneWidget);

    await tester.tap(find.byKey(const Key('manual-picker')));
    await tester.pumpAndSettle();
    expect(find.text('manual.pdf'), findsOneWidget);

    expect(
      tester.widget<FilledButton>(registerButtonFinder).onPressed,
      isNotNull,
    );

    await tester.tap(registerButtonFinder);
    await tester.pumpAndSettle();

    expect(capturedName, '国語 第1回');
    expect(capturedSubject, '国語');
    expect(capturedModelAnswerPath, 'C:/tmp/model-answer.pdf');
    expect(capturedManualPath, 'C:/tmp/manual.pdf');
    expect(find.byType(TestSettingsPage), findsOneWidget);
  });

  testWidgets('shows an error banner with a working retry action', (
    tester,
  ) async {
    var attempts = 0;
    final dependencies = AppDependencies(
      createTest:
          ({
            required name,
            subject,
            required modelAnswerPath,
            required manualPath,
          }) async {
            attempts++;
            if (attempts == 1) {
              throw SidecarApiException(
                SidecarErrorKind.badResponse,
                'file does not start with the PDF signature (%PDF-)',
                statusCode: 400,
              );
            }
            return _test();
          },
      getTest: (testId) async => _test(),
    );

    var pickCount = 0;
    Future<PickedPdfFile?> pickFile() async {
      pickCount++;
      return pickCount.isOdd
          ? await _fakeModelAnswerPick()
          : const PickedPdfFile(path: 'C:/tmp/manual.pdf', name: 'manual.pdf');
    }

    await tester.pumpWidget(
      _wrap(
        TestRegistrationPage(dependencies: dependencies, pickFile: pickFile),
      ),
    );
    await tester.enterText(find.byKey(const Key('test-name-field')), '国語 第1回');
    await tester.tap(find.byKey(const Key('model-answer-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('manual-picker')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('register-test-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('file does not start with the PDF signature (%PDF-)'),
      findsOneWidget,
    );

    await tester.tap(find.text('再試行'));
    await tester.pumpAndSettle();

    expect(find.byType(TestSettingsPage), findsOneWidget);
  });
}
