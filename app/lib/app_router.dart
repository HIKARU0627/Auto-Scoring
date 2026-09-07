import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/answer_intake/answer_intake_page.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_registration_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';

/// The app's route table (`docs/technology-stack.md` §2: go_router).
///
/// Lives next to `main.dart` rather than under `core/`, because building a
/// route means naming a page and `core` must not import `features`
/// (`AGENTS.md` "Architecture"). The paths themselves are `AppRoutes`, which
/// features may import.
///
/// Every builder takes nothing but the identifiers in the path: a screen's
/// collaborators come from `appDependenciesProvider`, so a route never has to
/// carry them.
GoRouter createAppRouter({String initialLocation = AppRoutes.home}) {
  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(
        path: AppRoutes.home,
        builder: (context, state) => const HomePage(),
      ),
      GoRoute(
        // Deliberately blank: `SidecarStartupOverlay` is covering the whole
        // app whenever the router is here. See [AppRoutes.starting].
        path: AppRoutes.starting,
        builder: (context, state) => const Scaffold(),
      ),
      GoRoute(
        path: AppRoutes.testRegistration,
        builder: (context, state) => const TestRegistrationPage(),
      ),
      GoRoute(
        path: AppRoutes.testList,
        builder: (context, state) => const TestListPage(),
      ),
      GoRoute(
        path: AppRoutes.testSettingsPattern,
        builder: (context, state) =>
            TestSettingsPage(testId: state.pathParameters['testId']!),
      ),
      GoRoute(
        path: AppRoutes.answerIntake,
        builder: (context, state) => const AnswerIntakePage(),
      ),
      GoRoute(
        path: AppRoutes.pdfReviewPattern,
        builder: (context, state) => PdfReviewPage(
          testId: state.pathParameters['testId']!,
          submissionId: state.pathParameters['submissionId']!,
        ),
      ),
    ],
  );
}
