/// 1つのテストの答案キュー -- 並び順・現在地・次の1件 (Issue #113)。
///
/// **並び順をここ1か所に置くのが要点である。** これを読むのは答案キュー画面と
/// 添削レビュー画面の2つで、前者は「どの順で並べるか」を、後者は「Enterで次に
/// どれへ進むか」を訊く。**2か所で別々に並べると、一覧で見えている順と実際に
/// 進む順がずれる。ずれた瞬間、講師は自分がどこにいるか分からなくなる。**
///
/// ウィジェットを持たないのは `home_dashboard.dart` と同じ理由で、優先順位は
/// このアプリで最も意見の入る部分だから、画面を立ち上げずに
/// `review_queue_test.dart` から直接読めるようにしてある。
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/submission_work_bucket.dart';

/// 答案1件が、キューの中でどう見えるか。
///
/// 答案の `state` だけでは足りない。**全設問が確定して初めて `reviewed` へ動く**
/// (Issue #112) ので、3/5 まで確定した答案は `ai_processed` のままであり、
/// 手つかずの答案と `state` では区別がつかない。だから設問粒度の数
/// ([confirmedQuestions]) を併せ持つ。
class ReviewQueueEntry {
  const ReviewQueueEntry({
    required this.submission,
    required this.totalQuestions,
    required this.confirmedQuestions,
    required this.manualGradingQuestions,
  });

  final SubmissionResponse submission;

  /// そのテストの設問数。進捗が取れていないときは0。
  final int totalQuestions;

  /// 人が確定した設問の数。
  final int confirmedQuestions;

  /// **最新のジョブが失敗した設問の数。**
  ///
  /// この答案は、そのぶんだけ**人が自分で点数を入れないと終わらない**
  /// (Issue #118 の「点数を入力」)。ほかの答案がAIの提案を確認するだけで済むのに
  /// 対して、ここは手を動かす量が違う。
  ///
  /// **金曜の午後の終わりに「残り3枚」を見たとき、その中身が読み分けられる**
  /// ようにするためにある。3枚が「AIの提案を見るだけ」なのか「1問ずつ自分で
  /// 採点する」なのかで、残り時間の見積もりがまるで違う。
  ///
  /// **Issue #118 が入る前は、この数は「詰んだ」を意味していた** -- AI が
  /// 失敗した設問に人が点数を入れる経路が無く、その答案は本当に終わらなかった。
  /// いまは終わらせられる。**意味が変わったので、名前も文言もそこに合わせてある。**
  final int manualGradingQuestions;

  String get id => submission.id;

  /// 人が確認し終えた答案 (`reviewed` / `exported`)。
  bool get isDone => HomeWorkBucket.of(submission.state) == HomeWorkBucket.done;

  /// 取込が「人が見ないと先へ進めない」と判定した答案。
  bool get needsAttention =>
      HomeWorkBucket.of(submission.state) == HomeWorkBucket.needsReview;

  /// AIが採点できなかった設問を抱えている -- 人が自分で点数を入れる必要がある。
  bool get needsManualGrading => manualGradingQuestions > 0;

  /// 済んでいないが、1問以上は確定している。
  ///
  /// **この判定のためだけに設問粒度の数を引いている。** これが無いと、中断して
  /// 戻ってきた講師には「どこまでやったか」が画面から読めない。
  bool get isPartiallyReviewed =>
      !isDone && confirmedQuestions > 0 && confirmedQuestions < totalQuestions;

  /// 全設問が確定していて、**PDF出力を試す価値がある**答案 (Issue #137)。
  ///
  /// **[isDone] ではなくこちらで出力の導線を出す。** 状態は設問粒度の事実の
  /// 写しであって、事実そのものではないからである。取りこぼすのは
  /// **全設問を確定したのに `reviewed` へ動かなかった答案**で、これは実在する:
  /// Issue #112 より前は `ai_processed` が `_REVIEWABLE_SUBMISSION_STATES` から
  /// 外れており、**普通に取り込めた答案ほど、全問承認しても状態が動かなかった**。
  /// #112 に遡って直すマイグレーションは無い (`backend/migrations/versions/` の
  /// 最新は `0016`) ので、それ以前に採点し終えた答案はいまも `ai_processed` の
  /// まま、全設問が確定した状態で残っている。**出力できるのに導線が出ない**のは
  /// #137 が消しに来た行き止まりそのものである。
  ///
  /// #113 が `manualGradingQuestions` で踏んだのと同じ形の誤りで、あちらは
  /// 「ジョブが失敗した」という粗い読みが #122・#114 の形を取りこぼしていた。
  /// **粗いほうの記録から細かい事実を推測しない。**
  ///
  /// 数え方はサイドカーの出力ゲートと**同一の述語**である。
  /// `GET /tests/{id}/review-progress` の `confirmed_questions` は
  /// `domain.review_workflow.count_confirmed_questions`、出力が拒む条件は
  /// `domain.pdf_export.unconfirmed_question_ids` で、どちらも
  /// `is_confirmed(effective_latest_review(...))` を設問ごとに評価している。
  /// つまりこれは判定のやり直しではなく、**同じ数を読んでいる**。
  ///
  /// [totalQuestions] が0のとき false になるのは正しい。進捗が引けなかった
  /// (`listReviewProgress` の失敗) ときも0で、そこで導線を出すと「押せるのに
  /// 必ず断られる」ボタンになる。**分からないときは出さない**。出力そのものは
  /// 添削レビュー画面から常に起動できるので、これは近道が消えるだけである。
  bool get isFullyConfirmed =>
      totalQuestions > 0 && confirmedQuestions == totalQuestions;
}

/// 1つのテストの答案キュー。
class ReviewQueue {
  const ReviewQueue._(this.entries);

  /// [submissions] を巡回順に並べ、[progress] の数を突き合わせる。
  ///
  /// [progress] はサイドカーの `GET /tests/{id}/review-progress` の応答。
  /// **答案側に対応する行が無くても落ちない** -- 進捗の取得だけが失敗しても、
  /// 一覧は状態だけで描けたほうがよい (数が出ないのは、一覧が出ないより軽い)。
  factory ReviewQueue.from({
    required List<SubmissionResponse> submissions,
    List<SubmissionReviewProgressResponse> progress = const [],
  }) {
    final progressById = {for (final row in progress) row.submissionId: row};
    final ordered = [...submissions]..sort(_byReviewOrder);
    return ReviewQueue._([
      for (final submission in ordered)
        ReviewQueueEntry(
          submission: submission,
          totalQuestions: progressById[submission.id]?.totalQuestions ?? 0,
          confirmedQuestions:
              progressById[submission.id]?.confirmedQuestions ?? 0,
          manualGradingQuestions:
              progressById[submission.id]?.manualGradingQuestions ?? 0,
        ),
    ]);
  }

  /// 表示順であり、巡回順でもある。**この2つは同じでなければならない。**
  final List<ReviewQueueEntry> entries;

  /// ホーム画面の「レビューを続ける」と**同じ規則**。
  ///
  /// `HomeTestProgress._pickResumable` が要確認を先に、同じ状態内では取込の
  /// 古い順に選ぶ。**ホームが開く1件とキューの先頭が違ったら、講師はどちらも
  /// 信用できなくなる**ので、規則ごと `HomeWorkBucket` の宣言順に乗せている。
  ///
  /// 済んだ答案も並びに含める -- 隠さない理由は [entries] の使い手側
  /// (`docs/review-queue.md`) にある。
  static int _byReviewOrder(SubmissionResponse a, SubmissionResponse b) {
    final byBucket = HomeWorkBucket.of(
      a.state,
    ).index.compareTo(HomeWorkBucket.of(b.state).index);
    if (byBucket != 0) return byBucket;
    return a.createdAt.compareTo(b.createdAt);
  }

  int get total => entries.length;

  int get doneCount => entries.where((entry) => entry.isDone).length;

  bool get isEmpty => entries.isEmpty;

  /// [submissionId] が何枚目か (1始まり)。キューに無ければ0。
  int positionOf(String submissionId) {
    final index = entries.indexWhere((entry) => entry.id == submissionId);
    return index < 0 ? 0 : index + 1;
  }

  ReviewQueueEntry? entryFor(String submissionId) {
    for (final entry in entries) {
      if (entry.id == submissionId) return entry;
    }
    return null;
  }

  /// [submissionId] の次に開くべき答案。無ければ `null`。
  ///
  /// **済んだ答案は飛ばす。** 一覧に出すことと、もう一度開かせることは別である
  /// -- 40枚を流している最中に確認済みの答案を開かされる意味は無い。
  ///
  /// [submissionId] がキューに無いとき (取込のやり直しで消えた、など) は
  /// 先頭から探す。行き先を失うより、先頭へ戻したほうが作業は続く。
  ReviewQueueEntry? nextAfter(String submissionId) {
    final index = entries.indexWhere((entry) => entry.id == submissionId);
    for (var i = index + 1; i < entries.length; i++) {
      if (!entries[i].isDone) return entries[i];
    }
    // 末尾まで見て残っていなければ、前に戻って未了を探す。後回し (S) で送った
    // 答案はキューの手前に残っているので、これが無いと拾えない。
    for (var i = 0; i < index && i < entries.length; i++) {
      if (!entries[i].isDone) return entries[i];
    }
    return null;
  }

  /// 最初に開くべき答案。無ければ `null`。
  ReviewQueueEntry? get first {
    for (final entry in entries) {
      if (!entry.isDone) return entry;
    }
    return null;
  }
}
