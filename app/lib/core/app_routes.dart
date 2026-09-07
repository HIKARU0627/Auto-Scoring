/// Every location the app can be at, as the paths `lib/app_router.dart`
/// declares and features navigate to (`docs/technology-stack.md` §2).
///
/// Only the paths live here, not the route table: building a route means
/// naming a page, and `core` must not import `features` (`AGENTS.md`
/// "Architecture"). This split is what lets a feature push another feature's
/// screen without importing it.
abstract final class AppRoutes {
  /// ホーム画面.
  static const String home = '/';

  /// The placeholder the app sits at while the sidecar is not usable.
  ///
  /// Not a screen: `SidecarStartupOverlay` covers the whole app in that state
  /// (splash or error). The composition root navigates here instead of leaving
  /// the reviewer's pushed pages on the stack, because each one captured the
  /// `AppDependencies` of a connection that no longer exists -- see
  /// `main.dart`.
  static const String starting = '/starting';

  /// テスト登録画面.
  static const String testRegistration = '/tests/new';

  /// テスト一覧画面.
  static const String testList = '/tests';

  /// テスト設定画面 for one test.
  static const String testSettingsPattern = '/tests/:testId/settings';
  static String testSettings(String testId) =>
      '/tests/${Uri.encodeComponent(testId)}/settings';

  /// 答案取込画面.
  static const String answerIntake = '/intake';

  /// 添削レビュー画面 for one submission of one test.
  static const String pdfReviewPattern =
      '/tests/:testId/submissions/:submissionId/review';
  static String pdfReview({
    required String testId,
    required String submissionId,
  }) =>
      '/tests/${Uri.encodeComponent(testId)}'
      '/submissions/${Uri.encodeComponent(submissionId)}/review';
}
