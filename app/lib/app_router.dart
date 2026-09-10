import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/intake/intake_page.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';
import 'package:auto_scoring_app/features/review_queue/submission_queue_page.dart';
import 'package:auto_scoring_app/features/settings/settings_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';
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
        path: AppRoutes.intake,
        builder: (context, state) => const IntakePage(),
      ),
      GoRoute(
        path: AppRoutes.settings,
        builder: (context, state) => const SettingsPage(),
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
        path: AppRoutes.submissionQueuePattern,
        builder: (context, state) =>
            SubmissionQueuePage(testId: state.pathParameters['testId']!),
      ),
      GoRoute(
        path: AppRoutes.pdfReviewPattern,
        builder: (context, state) {
          final testId = state.pathParameters['testId']!;
          final submissionId = state.pathParameters['submissionId']!;
          // Keyed by the answer it shows. Without this, navigating from one
          // submission's review straight to another's (same route pattern,
          // different parameters) would let Flutter reuse the existing
          // `State` -- `initState` would not run again, and the screen would
          // keep the previous answer's PDF, questions, jobs and cached
          // per-question results while claiming to show the new one. Every
          // cache on that screen is scoped to one `submissionId`
          // (`_PdfReviewPageState._jobsGeneration` enumerates them), so the
          // cheapest correct answer is to make a different answer a
          // different `State` by construction (review round 3).
          return PdfReviewPage(
            key: ValueKey('pdf-review/$testId/$submissionId'),
            testId: testId,
            submissionId: submissionId,
            initialQuestionId:
                state.uri.queryParameters[AppRoutes.pdfReviewQuestionParam],
          );
        },
      ),
    ],
  );
}
