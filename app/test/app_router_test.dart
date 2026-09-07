import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/answer_intake/answer_intake_page.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_registration_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';

import 'app_harness.dart';

/// Every location in [AppRoutes] resolves to the screen it names.
///
/// `AppRoutes` states each parameterised location twice -- once as the pattern
/// `lib/app_router.dart` declares (`/tests/:testId/settings`) and once as the
/// builder features call (`AppRoutes.testSettings(id)`). A drift between the
/// two compiles fine and only shows up at runtime, as go_router's "no route
/// found" screen. This pins them together.
///
/// The pages are pumped with the default (not-connected) `AppDependencies`, so
/// each renders its own error/empty state rather than reaching a sidecar. That
/// is all this test needs: it is about routing, not about what a screen does
/// once it is on.
///
/// [AppRoutes.starting] is deliberately absent -- it is a blank placeholder,
/// not a screen, and what it is for is covered by `startup_gate_test.dart`.
void main() {
  final locations = <String, Type>{
    AppRoutes.home: HomePage,
    AppRoutes.testRegistration: TestRegistrationPage,
    AppRoutes.testList: TestListPage,
    AppRoutes.testSettings('test-1'): TestSettingsPage,
    AppRoutes.answerIntake: AnswerIntakePage,
    AppRoutes.pdfReview(testId: 'test-1', submissionId: 'sub-1'): PdfReviewPage,
  };

  locations.forEach((location, page) {
    testWidgets('$location opens $page', (tester) async {
      await pumpAppAt(tester, location);
      await tester.pump();

      expect(find.byType(page), findsOneWidget);
    });
  });

  testWidgets('an id with URL-significant characters still resolves', (
    tester,
  ) async {
    // Test ids come from the sidecar, so a path builder that did not encode
    // them would turn one id into several path segments and miss the route.
    await pumpAppAt(tester, AppRoutes.testSettings('a/b?c'));
    await tester.pump();

    final page = tester.widget<TestSettingsPage>(find.byType(TestSettingsPage));
    expect(page.testId, 'a/b?c');
  });
}
