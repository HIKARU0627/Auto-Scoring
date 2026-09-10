/// 無効になっている操作について「何を満たせば有効になるか」(Issue #88)。
///
/// **文言はここにしか無い。** 画面は条件を数え、ここが返した文を並べるだけで、
/// 自分の言い回しを持たない。[ActionRequirement] のコンストラクタが private
/// なのはそのためである -- `features/` から新しい理由を1つも作れない。
///
/// なぜ1か所に集めるのか。直前まで、この種の文言は画面ごとに書き下ろして
/// あった (`test_settings_page._buildRemainingWork`、`_buildConfirmBlocker`、
/// `api_key_tab` の `helperText`)。条件のほうが変わったとき、**型検査も
/// リンタもテストも通ったまま文言だけが古くなる** -- Issue #111 と #138 は
/// どちらもその形の再発だった。無効にしている条件そのものから理由を導けば、
/// 片方だけ直すことができなくなる。
///
/// だから呼び手の使い方は必ずこの向きになる:
///
/// ```dart
/// final unmet = intakeImportRequirements(...);
/// FilledButton(onPressed: unmet.isEmpty ? _import : null, ...)
/// DisabledActionReason(requirements: unmet)
/// ```
///
/// **押せないこと**と**押せない理由**が同じ1つの計算から出るので、理由の無い
/// 無効ボタンも、無効でないのに出ている理由も、書けない。
///
/// ウィジェットを持たないのは `core/dag_failure_guidance.dart` と
/// `core/question_status.dart` と同じ理由で、レンダーツリー無しで検証できる
/// ようにするためである (Issue #126 の方針)。文言の方針そのものは
/// `docs/design-tokens.md` §8 にある。
library;

/// 無効な操作について、まだ満たされていない条件1つ。
///
/// [message] はそのまま画面に出す1文で、[id] は文言が変わっても変わらない
/// 識別子である。テストと `Key` が [id] を見るので、**言い回しを直すために
/// テストを書き換える必要が無い** -- 逆に、条件が1つ増えたり消えたりすれば
/// [id] の並びが変わり、テストはそこで落ちる。
class ActionRequirement {
  /// private: 理由を作れるのはこのファイルだけである。上の library コメント。
  const ActionRequirement._(this.id, this.message);

  /// 安定した識別子。`disabled-reason-<id>` が画面上の `Key` になる。
  final String id;

  /// 画面にそのまま出す1文。
  ///
  /// 方針 (`docs/design-tokens.md` §8): **満たすべき条件を1文で、画面上の
  /// 操作の名前で言う。** 「できません」で終えず、何をすれば有効になるかまで
  /// 書く。診断文・例外文・内部の理由語は載せない。
  final String message;

  @override
  String toString() => 'ActionRequirement($id)';

  // --- 共通 ---------------------------------------------------------------

  /// 進行中の処理がある。
  ///
  /// 「条件」と呼ぶには弱いが、**無効なのに理由が1つも無い状態を作らない**
  /// ためにこれも理由として数える。画面が進捗表示を出している間だけ立つ。
  static const ActionRequirement busy = ActionRequirement._(
    'busy',
    'この画面の処理が終わるまで待ってください。',
  );

  // --- 資料取込 (features/intake) ----------------------------------------

  static const ActionRequirement intakeTemplate = ActionRequirement._(
    'intake-template',
    '上の「取込の型」で、どの型で振り分けるかを選んでください。',
  );

  /// 取込先 (新規テスト / 既存テスト / 答案ごと) が未選択のフォルダがある。
  static ActionRequirement intakeTargetUnassigned(int groups) =>
      ActionRequirement._(
        'intake-target-unassigned',
        '取込先が決まっていないフォルダが$groups件あります。'
            'フォルダごとに「取込先」を選んでください。',
      );

  /// 除外を外したあと、どのフォルダにも取り込むファイルが残っていない。
  ///
  /// 「ファイルの無いフォルダが1件ある」ではない -- 空のフォルダ自体は取込を
  /// 止めない (`IntakeReviewState.importRequirements`)。止まるのは、batch 全体で
  /// 取り込む物が無くなったときだけである。
  static const ActionRequirement intakeNothingToImport = ActionRequirement._(
    'intake-nothing-to-import',
    '取り込むファイルが1件もありません。除外を外すか、別のフォルダを選び直してください。',
  );

  static ActionRequirement intakeTestNameEmpty(int groups) =>
      ActionRequirement._(
        'intake-test-name-empty',
        '新しいテストを作るフォルダのうち$groups件に名前がありません。'
            '「テスト名」を入力してください。',
      );

  static ActionRequirement intakeRequiredRoleMissing(int roles) =>
      ActionRequirement._(
        'intake-required-role-missing',
        '新しいテストに必要な役割の資料が$roles件足りません。'
            'その役割のファイルの役割を選び直すか、取込先を既存のテストに変えてください。',
      );

  static ActionRequirement intakeProposalUnconfirmed(int files) =>
      ActionRequirement._(
        'intake-proposal-unconfirmed',
        'AIの提案を$files件まだ確認していません。'
            '一覧の各行で内容を確かめてください。',
      );

  static ActionRequirement intakeAnswerUnrouted(int files) =>
      ActionRequirement._(
        'intake-answer-unrouted',
        'どのテストの答案か決まっていないファイルが$files件あります。'
            '答案ごとにテストを選んでください。',
      );

  static ActionRequirement intakeNonAnswerUnroutable(int files) =>
      ActionRequirement._(
        'intake-non-answer-unroutable',
        '答案ごとに振り分けるフォルダに、答案以外のファイルが$files件あります。'
            '除外するか、そのフォルダの取込先を変えてください。',
      );

  // --- テスト設定 (features/test_registration) ---------------------------

  static const ActionRequirement answerRegionsMissing = ActionRequirement._(
    'answer-regions-missing',
    '回答欄が1つもありません。「回答欄を自動検出」するか「領域を手動追加」で引いてください。',
  );

  static ActionRequirement answerRegionsUnassigned(int regions) =>
      ActionRequirement._(
        'answer-regions-unassigned',
        '設問が割り当てられていない回答欄が$regions件あります。設問を選ぶか削除してください。',
      );

  /// 答案そのものが画面に出ていない。`mustSeeAnswerSheetFirst` の言い換え。
  static const ActionRequirement answerSheetUnseen = ActionRequirement._(
    'answer-sheet-unseen',
    '回答欄の位置は答案の上で確認します。この様式の答案を1枚登録してください。',
  );

  /// 答案は登録済みだが描画できていない。上と別の文にするのは、講師の次の
  /// 手が違うからである -- 登録ではなく再試行。
  static const ActionRequirement answerSheetUnrendered = ActionRequirement._(
    'answer-sheet-unrendered',
    '答案を表示できていません。上の「再試行」を押して、実際の答案を出してください。',
  );

  static const ActionRequirement profileAlreadyConfirmed = ActionRequirement._(
    'profile-already-confirmed',
    'テストプロファイルは確定済みです。確定した回答欄は変更できません。',
  );

  static const ActionRequirement dependencyGraphMissing = ActionRequirement._(
    'dependency-graph-missing',
    '設問依存関係グラフがまだありません。「依存関係を分析」を押してください。',
  );

  static const ActionRequirement dependencyGraphAlreadyConfirmed =
      ActionRequirement._(
        'dependency-graph-already-confirmed',
        '設問依存関係グラフは確定済みです。',
      );

  static const ActionRequirement criteriaUnconfirmed = ActionRequirement._(
    'criteria-unconfirmed',
    '配点と採点基準が未確定です。上の「配点」で確定してください。',
  );

  static const ActionRequirement profileUnconfirmed = ActionRequirement._(
    'profile-unconfirmed',
    '回答欄（テストプロファイル）が未確定です。上の「プロファイルを確定」を押してください。',
  );

  static const ActionRequirement dependencyGraphUnconfirmed =
      ActionRequirement._(
        'dependency-graph-unconfirmed',
        '設問依存関係グラフが未確定です。上の「依存関係グラフを確定」を押してください。',
      );

  /// 確定済みだが、そのあと設問が変わった。
  ///
  /// 「このまま押すと断られます」まで言うのは、**確定済みの印が出ている画面で
  /// 断られるから**である。状態表示と結果が食い違う場面では、どちらが本当かを
  /// 先に書く。
  static const ActionRequirement dependencyGraphStale = ActionRequirement._(
    'dependency-graph-stale',
    '設問が変わったため、設問依存関係グラフを分析し直して確定してください。'
        'このまま「登録完了」を押すと断られます。',
  );

  static const ActionRequirement registrationAlreadyComplete =
      ActionRequirement._(
        'registration-already-complete',
        '登録は完了しています。答案を取り込むと採点が始まります。',
      );

  // --- 設定 (features/settings) ------------------------------------------

  static const ActionRequirement credentialStoreUnavailable =
      ActionRequirement._(
        'credential-store-unavailable',
        'この PC の資格情報ストアが使えないため、キーを保存できません。'
            '上の通知にある理由を解消するか、環境変数でキーを渡してください。',
      );

  static const ActionRequirement apiKeyNotConfigured = ActionRequirement._(
    'api-key-not-configured',
    'キーがまだありません。上の欄に入力して「保存する」を押すと疎通を確認できます。',
  );
}

// ---------------------------------------------------------------------------
// 操作ごとの判定。**返り値が空かどうかが、そのままボタンの有効・無効である。**
// ---------------------------------------------------------------------------

/// 進行中の処理が終わるまでしか無効にならない操作。
///
/// 理由が1つしか無いのに関数にするのは、**画面が `ActionRequirement.busy` を
/// 自分で並べ始めないようにする**ためである。そこを許すと、次は条件を1つ
/// 足したくなった画面が自分で文を書き始める。
List<ActionRequirement> whileRunningRequirements({required bool running}) => [
  if (running) ActionRequirement.busy,
];

/// 資料取込の「フォルダを選ぶ」。
List<ActionRequirement> intakeFolderPickRequirements({
  required bool busy,
  required bool templateChosen,
}) => [
  if (busy) ActionRequirement.busy,
  if (!templateChosen) ActionRequirement.intakeTemplate,
];

/// 資料取込の「この内容で取り込む」。
///
/// [folderRequirements] は `IntakeReviewState.importRequirements` -- `canImport`
/// の実装そのもので、この関数はそこに画面の状態 (進行中かどうか) を足すだけ
/// である。`core/intake_review.dart` を import し返さないのは、あちらが
/// [ActionRequirement] を使う側だからで、文言の置き場が1方向に保たれる。
List<ActionRequirement> intakeImportRequirements({
  required bool busy,
  required bool classifying,
  required List<ActionRequirement> folderRequirements,
}) => [if (busy || classifying) ActionRequirement.busy, ...folderRequirements];

/// テスト設定の「修正内容を保存」。
List<ActionRequirement> answerProfileSaveRequirements({
  required bool busy,
  required bool hasRegions,
  required bool alreadyConfirmed,
}) => [
  if (busy) ActionRequirement.busy,
  if (alreadyConfirmed) ActionRequirement.profileAlreadyConfirmed,
  if (!hasRegions) ActionRequirement.answerRegionsMissing,
];

/// テスト設定の「プロファイルを確定」。
///
/// [answerSheetRegistered] と [answerSheetVisible] を別々に受けるのは、
/// 「答案がまだ無い」と「答案はあるが描けていない」で次の手が違うからである
/// (`ActionRequirement.answerSheetUnseen` / `answerSheetUnrendered`)。
List<ActionRequirement> answerProfileConfirmRequirements({
  required bool busy,
  required bool alreadyConfirmed,
  required int regionCount,
  required int unassignedRegionCount,
  required bool mustSeeAnswerSheetFirst,
  required bool answerSheetRegistered,
}) => [
  if (busy) ActionRequirement.busy,
  if (alreadyConfirmed) ActionRequirement.profileAlreadyConfirmed,
  if (regionCount == 0) ActionRequirement.answerRegionsMissing,
  if (unassignedRegionCount > 0)
    ActionRequirement.answerRegionsUnassigned(unassignedRegionCount),
  if (mustSeeAnswerSheetFirst)
    answerSheetRegistered
        ? ActionRequirement.answerSheetUnrendered
        : ActionRequirement.answerSheetUnseen,
];

/// テスト設定の「依存関係グラフを確定」。
List<ActionRequirement> dependencyGraphConfirmRequirements({
  required bool busy,
  required bool hasGraph,
  required bool alreadyConfirmed,
}) => [
  if (busy) ActionRequirement.busy,
  if (alreadyConfirmed) ActionRequirement.dependencyGraphAlreadyConfirmed,
  if (!hasGraph) ActionRequirement.dependencyGraphMissing,
];

/// テスト設定の「登録完了」ボタンを無効にしている条件。
///
/// **配点はここに入らない。** `complete-registration` を押せるかどうかの条件は
/// 回答欄と依存グラフの確定だけで、配点が未確定でも押せる -- それは #88 より
/// 前からの仕様で、この Issue は理由を出す話であって条件を緩める / 締める話では
/// ない。配点まで含めた「採点が始まるまでに残っていること」は
/// [gradingStartRequirements] が答える。2つとも同じ [ActionRequirement] の
/// 並びから文を取るので、ボタンの横とパネルで言い回しが分かれることはない。
List<ActionRequirement> completeRegistrationRequirements({
  required bool busy,
  required bool alreadyComplete,
  required bool profileConfirmed,
  required bool dependencyGraphConfirmed,
}) => [
  if (busy) ActionRequirement.busy,
  if (alreadyComplete) ActionRequirement.registrationAlreadyComplete,
  if (!profileConfirmed) ActionRequirement.profileUnconfirmed,
  if (!dependencyGraphConfirmed) ActionRequirement.dependencyGraphUnconfirmed,
];

/// 採点が始まる状態になるまでに、テスト設定画面でまだ残っていること。
///
/// 「登録完了」を押せるかどうか ([completeRegistrationRequirements]) とは別の
/// 問いである。押せてもなお配点が未確定なら採点は始まらないので、そこは
/// ボタンの有効・無効ではなくこの一覧が答える。
///
/// [dependencyGraphStale] は [dependencyGraphConfirmed] が真のときだけ意味を
/// 持つ -- 未確定なら「確定してください」が先で、古いかどうかは次の問題である。
List<ActionRequirement> gradingStartRequirements({
  required bool criteriaSettled,
  required bool profileConfirmed,
  required bool dependencyGraphConfirmed,
  required bool dependencyGraphStale,
}) => [
  if (!criteriaSettled) ActionRequirement.criteriaUnconfirmed,
  if (!profileConfirmed) ActionRequirement.profileUnconfirmed,
  if (!dependencyGraphConfirmed)
    ActionRequirement.dependencyGraphUnconfirmed
  else if (dependencyGraphStale)
    ActionRequirement.dependencyGraphStale,
];

/// 設定画面 API キータブの「保存する」。
List<ActionRequirement> apiKeySaveRequirements({
  required bool busy,
  required bool credentialStoreAvailable,
}) => [
  if (busy) ActionRequirement.busy,
  if (!credentialStoreAvailable) ActionRequirement.credentialStoreUnavailable,
];

/// 設定画面 API キータブの「疎通を確認する」。
List<ActionRequirement> apiKeyVerifyRequirements({
  required bool busy,
  required bool configured,
}) => [
  if (busy) ActionRequirement.busy,
  if (!configured) ActionRequirement.apiKeyNotConfigured,
];
