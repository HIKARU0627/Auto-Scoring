/// AI採点の起票 (`POST /submissions/{id}/jobs`) が失敗したときの見せ方を、
/// 1箇所に置いたもの (Issue #80)。
///
/// 起票は2箇所から呼ぶ -- 答案取込画面（取込成功の直後に自動）と添削レビュー
/// 画面（ジョブが0件の答案に対する明示操作）。同じ失敗を2つの画面が別々の
/// 言葉で説明するのは、Issue #84 で直した食い違いと同じ種類のものなので、
/// 文言も再試行できるかどうかの判定もここにしか無い。
///
/// なぜここに置けるか: 起票の失敗は `SidecarApiException` だけから決まり、
/// 画面の状態を要らない。ウィジェットを含まないので
/// `core/question_status.dart` と同じくレンダーツリー無しで単体テストできる。
///
/// 決定の全文は `docs/job-queue.md`「起票のタイミング」。
library;

import 'package:flutter/foundation.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// 起票を始めるボタンの文言。2つの画面で同じ語にする。
const String startGradingLabel = 'AI採点を開始';

/// 起票が失敗したという事実そのもの -- レビュアーに出す日本語 [message] と、
/// もう一度投げる価値があるか [retryable] の2点セット。
///
/// **2つを別々に取り出せないようにしてあるのが要点。** 元は
/// `gradingKickoffErrorMessage` と `gradingKickoffIsRetryable` という2つの
/// 関数で、答案取込画面は両方を使い、添削レビュー画面は文言だけを使って
/// 再試行可否を握り潰していた -- 404（答案が無い）を出しておきながら、その
/// 真上の「AI採点を開始」を何度でも押せた（review round 1, P2-2）。
/// [QuestionStatus] が語・形・強調度を1つの値として持つのと同じ理由で、
/// ここも1つの値にしてある。片方だけ使うことができなければ、2つの画面が
/// 別々の振る舞いへ分かれようがない。
@immutable
class GradingKickoffFailure {
  const GradingKickoffFailure._(this.message, {required this.retryable});

  /// [error] をレビュアーの言葉へ翻訳する。
  ///
  /// **409 の2種類を区別しない。** サイドカーは「確定した依存関係グラフが
  /// 無い、または古い」（`SubmissionNotReadyError`）と「同時起票の競合」
  /// （`SubmissionJobCreationConflictError`）の両方を 409 で返し、`detail` は
  /// どちらも英語の内部メッセージである。文字列の中身で分岐するのは壊れやすい
  /// うえ、画面の出しかたは変わらない -- どちらも「答案は取り込めているが採点は
  /// 始まっていない」「時間をおくか、依存関係を確定し直せば通りうる」という
  /// 同じ扱いで足りる。両方の可能性を書いて、断定しない。
  ///
  /// 404 だけが [retryable] を `false` にする。答案そのものが無いという答えは、
  /// 同じ要求を投げ直しても変わらない。
  factory GradingKickoffFailure.of(SidecarApiException error) {
    if (error.statusCode == 404) {
      return const GradingKickoffFailure._(
        'この答案が見つかりません。AI採点を開始できません。',
        retryable: false,
      );
    }
    if (error.kind == SidecarErrorKind.conflict) {
      return const GradingKickoffFailure._(
        'AI採点を開始できませんでした。テストの設問依存関係が確定していないか、'
        'ほかの操作と競合しています。テスト設定で依存関係を確定してから、'
        'もう一度お試しください。',
        retryable: true,
      );
    }
    // ここまで来るのは通信不能・タイムアウト・想定外の応答。`SidecarApiClient`
    // が付ける短い理由をそのまま添える -- 答案取込画面・テスト設定画面が既に
    // 同じ値を出しているので、ここだけ隠すと原因が分からなくなる。
    return GradingKickoffFailure._(
      'AI採点を開始できませんでした: ${error.message}',
      retryable: true,
    );
  }

  /// 画面がそのまま出す日本語。サイドカーの英語メッセージは、原因が
  /// 通信まわりのときにだけ末尾へ添える。
  final String message;

  /// もう一度起票を投げる価値があるか。`false` の失敗に対して再試行の導線を
  /// 出してはいけない -- 押せるのに何も変わらないボタンは、押せないことを
  /// 伝えるより悪い。
  final bool retryable;
}
