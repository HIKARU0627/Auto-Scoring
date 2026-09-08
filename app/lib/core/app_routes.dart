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

  /// 資料取込画面 — choose a folder, check what will be imported, import
  /// (Issue #101). Replaced the separate テスト登録 and 答案取込 screens.
  static const String intake = '/intake';

  /// 設定画面. One screen with tabs; Issue #101 fills in the 取込の型 tab and
  /// Issue #96's API-key tab is meant to join it there rather than becoming a
  /// second settings screen.
  static const String settings = '/settings';

  /// テスト一覧画面.
  static const String testList = '/tests';

  /// テスト設定画面 for one test.
  static const String testSettingsPattern = '/tests/:testId/settings';
  static String testSettings(String testId) =>
      '/tests/${Uri.encodeComponent(testId)}/settings';

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
