/// 失敗した設問について、処理の進み方パネルが出してよい日本語 (Issue #86)。
///
/// **`Job.last_error` はそのまま画面に出さない。** あれは provider 名・例外
/// クラス名・HTTPステータス・内部の理由語を並べた診断文であって
/// (`jobs.grading_processor._failed`)、「次に何ができるか」を答える文では
/// ない。インスペクタは診断文をそのまま出す —— 初回起動で 401 / 403 / 404 の
/// どれで詰まっているかを区別するためで、それは Issue #97 review round 4 の
/// 決定である。このパネルは違う問いに答えている: **畳んでも残る一行**で、
/// 「この答案は誰かが手を入れるまで進まない」ことと「その手の入れ方」を
/// 言う。診断文はそこに置く物ではない (AGENTS.md «Security» の
/// secret masking も同じ向きを指す)。
///
/// 分類に使うのは `Job.error_code` —— backend の `domain.models.ErrorCategory`
/// で、**すでに OpenAPI schema にも生成済みDartクライアントにも入っている**
/// (`JobResponse.errorCode`)。schema には触っていない。
///
/// ウィジェットを持たないのは `core/question_status.dart` と同じ理由で、
/// レンダーツリー無しで検証できるようにするためである
/// (Issue #126 の方針)。
library;

import 'package:auto_scoring_app/core/grading_failure_reason.dart';

/// 失敗の理由と、そこからの復旧手段の組。
///
/// 「何が起きたか」と「次に何ができるか」を別々に持つのは、**どちらか片方
/// だけの文言を書けないようにする**ためである。1本の文字列にすると、片方
/// しか言っていないことに誰も気づけない。分けてあれば
/// `dag_failure_guidance_test.dart` が全分類について両方あることを検査
/// できる。画面はこの2つを1つの段落として並べて出す。
enum DagFailureGuidance {
  /// 採点AIが「渡された画像はこの設問の解答ではない」と報告した
  /// (Issue #136、`crop_not_the_answer`)。再判定は同じ画像を同じモデルへ
  /// 送り直すだけなので、直す場所は回答欄の枠のほうである。
  answerAreaWrong(
    'AIは、この設問に渡された画像がこの設問の解答ではないと判断しました。',
    'テスト設定の「回答欄」で、この設問の枠の位置を直してください。位置を直さないまま再判定しても、同じ結果になります。',
  ),

  /// `rate_limited`。待てば通るが、待つのは自動再試行の予算内だけで、
  /// それを使い切ってここに来ている (Issue #153)。
  rateLimited('AIの利用上限に達したため、この設問の処理を打ち切りました。', 'しばらく置いてから「再判定」でやり直せます。'),

  /// `timeout` / `server_error`。相手側の一時的な不調で、再試行の上限まで
  /// 使ってなお通らなかったもの。
  temporary('AIとの通信が最後まで通らず、再試行の上限に達しました。', '「再判定」でもう一度試すか、「点数を入力」で自分で採点できます。'),

  /// `permanent`。同じ材料・同じ設定で投げ直しても結果は変わらないと
  /// キューが分類したもの (`RETRYABLE_ERROR_CATEGORIES` に入っていない)。
  /// だから「再判定」を先に勧めない。
  permanent(
    'AIはこの設問を処理できませんでした。同じ設定のままでは、やり直しても結果は変わりません。',
    'テスト設定の教材（模範解答・採点基準）とAIの設定を見直すか、「点数を入力」で自分で採点してください。',
  ),

  /// `error_code` が無い、または**このビルドが知らない分類**。新しい
  /// sidecar が増やした分類を勝手に言い当てるより、両方の出口を示すほうが
  /// 正直である。
  unknown('AIはこの設問を処理できませんでした。', '「再判定」でもう一度AIに任せるか、「点数を入力」で自分で採点できます。');

  const DagFailureGuidance(this.cause, this.nextStep);

  /// 何が起きたか。人に向けた1文で、診断文の引き写しではない。
  final String cause;

  /// 次にできること。**必ず画面上の操作の名前**（「再判定」「点数を入力」
  /// 「回答欄」）で言う。
  final String nextStep;
}

/// [errorCode]（`Job.error_code`）と [lastError]（`Job.last_error`）から
/// 出す文言を決める。
///
/// [lastError] を**読むだけ**で、返り値には一切載せない。載せてよい形の
/// 文字列は [DagFailureGuidance] のリテラルだけである。ここが唯一
/// `last_error` に触る場所なので、パネル側は生の文字列を持たない。
///
/// 回答欄の取り違えを [errorCode] より先に見るのは、それが
/// `ErrorCategory.PERMANENT` の中の1つで、しかも
/// **`permanent` の一般的な出口（設定を見直す）では直らない**唯一の
/// ものだからである (`jobs.grading_processor._crop_is_not_the_answer`)。
DagFailureGuidance dagFailureGuidance({String? errorCode, String? lastError}) {
  if (isNotTheAnswerCrop(lastError)) return DagFailureGuidance.answerAreaWrong;
  return switch (errorCode) {
    'rate_limited' => DagFailureGuidance.rateLimited,
    'timeout' || 'server_error' => DagFailureGuidance.temporary,
    'permanent' => DagFailureGuidance.permanent,
    _ => DagFailureGuidance.unknown,
  };
}
