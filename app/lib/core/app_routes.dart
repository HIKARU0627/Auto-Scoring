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

  /// 答案キュー -- そのテストの答案が何枚あって、どれが済んでいて、次はどれか
  /// (Issue #113)。
  ///
  /// ここから添削レビューへ入り、最後の設問を確定すると**次の答案へ直接進む**。
  /// 40枚を続けてさばくのにホームへ戻らせない、というのがこの経路の理由である。
  static const String submissionQueuePattern = '/tests/:testId/submissions';
  static String submissionQueue(String testId) =>
      '/tests/${Uri.encodeComponent(testId)}/submissions';

  /// 答案確定画面 -- その答案の**全設問を1画面に並べ、1回で確定する**
  /// (Issue #145)。
  ///
  /// 答案キューから開くのはここである。設問ごとに承認させると 40枚 × 5設問 で
  /// 200回になり、#113 が消したのはホームへの往復80回だけだった。**確定の単位を
  /// 設問から答案へ移すのがこの経路の理由である。**
  ///
  /// 1設問を詳しく見る・直すときは、ここから [pdfReview] へ入る。
  static const String submissionConfirmPattern =
      '/tests/:testId/submissions/:submissionId/confirm';
  static String submissionConfirm({
    required String testId,
    required String submissionId,
  }) =>
      '/tests/${Uri.encodeComponent(testId)}'
      '/submissions/${Uri.encodeComponent(submissionId)}/confirm';

  /// 添削レビュー画面 for one submission of one test.
  ///
  /// [questionId] を渡すと、その設問を開いた状態で始まる。答案確定画面の
  /// 「この設問を直す」から入るときに要る -- 問4を直しに来た人を問1に降ろすと、
  /// **どれを直しに来たかを人の側に覚えさせる**ことになる。クエリなのは、
  /// 「どの設問から見始めるか」は画面の初期状態であって、この画面が指している
  /// もの (答案1件) ではないからである。
  static const String pdfReviewPattern =
      '/tests/:testId/submissions/:submissionId/review';
  static String pdfReview({
    required String testId,
    required String submissionId,
    String? questionId,
  }) {
    final path =
        '/tests/${Uri.encodeComponent(testId)}'
        '/submissions/${Uri.encodeComponent(submissionId)}/review';
    if (questionId == null) return path;
    return '$path?$pdfReviewQuestionParam=${Uri.encodeComponent(questionId)}';
  }

  /// [pdfReview] の「最初に開く設問」を運ぶクエリパラメータ名。
  static const String pdfReviewQuestionParam = 'question';
}
