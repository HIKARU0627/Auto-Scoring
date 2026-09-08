/// AI採点の起票 (`POST /submissions/{id}/jobs`) が失敗したときの言い方を、
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

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// 起票を始めるボタンの文言。2つの画面で同じ語にする。
const String startGradingLabel = 'AI採点を開始';

/// [error] が再試行で解消しうるか。
///
/// 404（答案そのものが無い）だけが「押しても変わらない」。確定DAG未確定の
/// 409 はテスト設定でグラフを確定すれば通り、競合の409とタイムアウトは
/// そのまま押し直せば通りうる。
bool gradingKickoffIsRetryable(SidecarApiException error) =>
    error.statusCode != 404;

/// [error] に対して画面が出す日本語。
///
/// **409 の2種類を区別しない。** サイドカーは「確定した依存関係グラフが無い、
/// または古い」（`SubmissionNotReadyError`）と「同時起票の競合」
/// （`SubmissionJobCreationConflictError`）の両方を 409 で返し、`detail` は
/// どちらも英語の内部メッセージである。文字列の中身で分岐するのは壊れやすい
/// うえ、画面の出しかたは変わらない -- どちらも「答案は取り込めているが採点は
/// 始まっていない」「時間をおくか、依存関係を確定し直せば通りうる」という
/// 同じ扱いで足りる。両方の可能性を書いて、断定しない。
String gradingKickoffErrorMessage(SidecarApiException error) {
  if (!gradingKickoffIsRetryable(error)) {
    return 'この答案が見つかりません。AI採点を開始できません。';
  }
  if (error.kind == SidecarErrorKind.conflict) {
    return 'AI採点を開始できませんでした。テストの設問依存関係が確定していないか、'
        'ほかの操作と競合しています。テスト設定で依存関係を確定してから、'
        'もう一度お試しください。';
  }
  // ここまで来るのは通信不能・タイムアウト・想定外の応答。`SidecarApiClient`
  // が付ける短い理由をそのまま添える -- 答案取込画面・テスト設定画面が既に
  // 同じ値を出しているので、ここだけ隠すと原因が分からなくなる。
  return 'AI採点を開始できませんでした: ${error.message}';
}
