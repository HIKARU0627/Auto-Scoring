/// 設問1件の状態を表す語彙。**この画面で設問の状態を出すところは、全部ここを
/// 読む** (Issue #84)。
///
/// 添削レビュー画面は同じ設問の状態を3箇所で出す -- 処理の進み方パネル (DAG)、
/// 左の設問レール、右のインスペクタ。この3つはそれぞれ別々に状態を組み立てて
/// いたので、同じ「問1」について DAG が「承認済み」、インスペクタが「要確認」
/// と言い、レールは 要確認・前提待ち・レビュー待ち を同じ砂時計に潰していた。
/// 提供元の異なる5体のAIエージェントが互いの評価を見ずに独立に、全員 high で
/// 指摘した唯一の項目である (Issue #71 の集約結果)。
///
/// 直し方は「3箇所の描画を揃える」ではなく **状態を導く場所を1つにする** こと。
/// [QuestionStatus] が語(ラベル)・形(アイコン)・強調度(トーン)を1組で持ち、
/// [deriveQuestionStatus] だけが `Job` と `Review` からそれを決める。3箇所は
/// 同じ入力を同じ関数に通すので、**食い違いようがない**。
///
/// ウィジェットを含まないのは意図的で、`core/dependency_dag.dart` と同じ理由
/// (レンダーツリー無しで単体テストできる)。`features` 側は描くだけである。
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';

/// Where one question stands in the pipeline, as a reviewer needs to read it.
///
/// This is *not* `Job.state` renamed: the queue's six states and the four
/// review actions describe two different halves of the same question's life,
/// and a reviewer wants one answer per question. See [deriveQuestionStatus]
/// for how the two are combined.
///
/// Every value carries its own icon and Japanese label as well as a tone, so
/// each of the three places reads without colour (Issue #25's rule, restated
/// in `docs/design-tokens.md` §3.4) -- and, because the three take their
/// icon and label from the *same* value, they cannot drift into two
/// vocabularies for one state (Issue #84).
enum QuestionStatus {
  /// No `Job` exists for this question yet -- 答案 has been taken in but its
  /// per-question jobs have not been enqueued (Issue #18: jobs are only ever
  /// created by an explicit `POST .../jobs`, never implicitly).
  pending('未処理', Icons.radio_button_unchecked, AppStatusTone.neutral),

  /// `BLOCKED`: a prerequisite has not released this question yet. Every
  /// place that has the prerequisite to hand names *which* one
  /// (`Job.blocked_on_question_id`, via [labelWaitingFor]) rather than just
  /// saying "waiting" -- that name is the whole point of drawing the graph
  /// (`docs/job-queue.md` §「`BLOCKED`を…両方に使う」).
  blocked('前提待ち', Icons.lock_clock, AppStatusTone.neutral),

  /// `QUEUED`: every prerequisite is satisfied and the worker will pick this
  /// up next. This is the state the 「上流が完了して下流が解ける瞬間」
  /// transition lands in.
  queued('実行待ち', Icons.schedule, AppStatusTone.neutral),

  /// `RUNNING`: an OCR/AI provider call is in flight for this question.
  running('AI処理中', Icons.play_circle_outline, AppStatusTone.neutral),

  /// `SUCCEEDED` but `usable == false`: the pipeline finished and decided its
  /// own result is not trustworthy enough to release the questions that
  /// depend on it (low Confidence -- `docs/job-queue.md` §「依存の解放は
  /// 「usable」を…」). Nothing downstream moves until a person looks, which is
  /// exactly what [AppStatusTone.attention] is reserved for.
  needsCheck('要確認', Icons.help_outline, AppStatusTone.attention),

  /// `FAILED`: the job did not complete. Distinct from [needsCheck] -- there
  /// is no result to judge here.
  failed('失敗', Icons.error_outline, AppStatusTone.danger),

  /// `CANCELLED`: a person or a re-submission stopped this job.
  cancelled('中止', Icons.block, AppStatusTone.neutral),

  /// The AI is done and usable, and no human decision has been recorded yet.
  /// Deliberately [AppStatusTone.neutral]: on this screen "waiting to be
  /// reviewed" is the *normal* state, and colouring it would leave the whole
  /// screen shouting -- with three places drawing it, all the more so.
  graded('レビュー待ち', Icons.rate_review_outlined, AppStatusTone.neutral),

  /// A reviewer asked for a re-grade and the replacement job has not been
  /// created yet -- a brief interim, since `regradeReview` enqueues one.
  regradeRequested('再判定待ち', Icons.autorenew, AppStatusTone.neutral),

  /// A reviewer rejected the AI's grade. A decision, not a failure, so it
  /// stays neutral.
  rejected('却下', Icons.cancel_outlined, AppStatusTone.neutral),

  /// A reviewer approved (or edited and thereby confirmed) the grade.
  approved('承認済み', Icons.check_circle, AppStatusTone.success);

  const QuestionStatus(this.label, this.icon, this.tone);

  /// The Japanese label. Short enough to fit a DAG node at
  /// `AppLayout.dagNodeWidth` without wrapping, which is the tightest of the
  /// three places it appears in.
  final String label;

  /// The shape half of the state, so every one of the three reads with
  /// colour removed.
  final IconData icon;

  final AppStatusTone tone;

  /// [label], except that [blocked] names the prerequisite it is waiting on
  /// when [prerequisiteNumber] is known -- 「問2 待ち」 rather than a bare
  /// 「前提待ち」, since *what* it is waiting for is the one thing a blocked
  /// question exists to tell the reviewer.
  ///
  /// Lives here rather than in the DAG node so the rail and the Inspector
  /// say the same words about the same question as the diagram does. A
  /// caller with no prerequisite to name just gets [label].
  String labelWaitingFor(String? prerequisiteNumber) =>
      this == QuestionStatus.blocked && prerequisiteNumber != null
      ? '問$prerequisiteNumber 待ち'
      : label;
}

/// Collapses one question's `Job` and `Review` into the single state every
/// place on the 添削レビュー screen shows for it.
///
/// The precedence is "the queue first, the human second", because a live job
/// always describes a *newer* attempt than any review can: a re-submission
/// under a newer confirmed graph version, or a 再判定 request, creates a fresh
/// `Job` while the append-only review history still holds the previous
/// attempt's decision (Issue #18, and the same reasoning behind
/// `_isAwaitingGrade` on the 添削レビュー screen). Showing 承認済み over a
/// job that is running again would tell the reviewer the opposite of what is
/// happening.
///
/// **Once the job has stopped, that reasoning runs out** (Issue #118). A
/// job that failed, was cancelled, or finished with an untrustworthy result
/// is not going to describe anything newer, and a person who has since
/// recorded a decision *is* the newer fact -- they graded the question by
/// hand precisely because the queue could not. Leaving 失敗 on such a
/// question would have made 承認済み unreachable for it forever, in the rail,
/// the DAG and the Inspector at once, while the answer sheet itself
/// correctly counted it as 確認済み ([Issue #112]'s
/// `Submission.REVIEWED`) -- three places saying one thing and the fourth
/// saying the opposite, which is the exact failure Issue #84 collapsed this
/// function into one place to prevent.
///
/// So for a *terminal* job the human decision wins, but only when it was
/// recorded after that job was created -- the same "is this decision about
/// this attempt?" test [_regradeAnswered] already applies in the other
/// direction. A decision predating the job is about an older attempt and
/// stays outranked.
///
/// [review] is the *effective* `Review` (post-Undo) or `null` when none
/// exists -- or when this screen has simply not fetched this question's
/// reviews yet, which is the common case for a question the reviewer has not
/// visited. Both read as "no human decision recorded", which is the right
/// thing to draw: the question then shows how far the *pipeline* got, and
/// gains the human half as soon as it is opened. Unvisited questions are the
/// reason the rail may not simply fall back to "not loaded yet" -- doing so
/// was what flattened 要確認・実行待ち・レビュー待ち into one hourglass
/// (`docs/dependency-dag-progress-view.md` §7).
QuestionStatus deriveQuestionStatus({
  required JobResponse? job,
  required ReviewResponse? review,
}) {
  if (job == null) {
    // A review with no job at all is not something the backend produces, but
    // if it ever appears, the human decision is the only fact available.
    return _reviewStatus(review, job) ?? QuestionStatus.pending;
  }
  return switch (job.state) {
    'blocked' => QuestionStatus.blocked,
    'queued' => QuestionStatus.queued,
    'running' => QuestionStatus.running,
    'failed' => _decisionSince(review, job) ?? QuestionStatus.failed,
    'cancelled' => _decisionSince(review, job) ?? QuestionStatus.cancelled,
    // `usable` is only ever set on a terminal transition, and `false` means
    // the queue itself judged the result not good enough to release anything
    // downstream -- a stronger statement than "nobody has reviewed it yet",
    // so it outranks a review the reviewer recorded *before* this attempt.
    // Not one they recorded after it: that is a person having looked at
    // exactly this result and decided (Issue #118).
    'succeeded' when job.usable == false =>
      _decisionSince(review, job) ?? QuestionStatus.needsCheck,
    'succeeded' => _reviewStatus(review, job) ?? QuestionStatus.graded,
    // An unknown state from a newer backend: say nothing rather than guess.
    _ => QuestionStatus.pending,
  };
}

/// [_reviewStatus], but only for a decision recorded *after* [job] was
/// created -- the human decision that is about this attempt rather than an
/// older one. `null` when there is no such decision, leaving the caller's
/// own job-derived status in place.
QuestionStatus? _decisionSince(ReviewResponse? review, JobResponse job) {
  if (review == null || !review.createdAt.isAfter(job.createdAt)) return null;
  return _reviewStatus(review, job);
}

QuestionStatus? _reviewStatus(ReviewResponse? review, JobResponse? job) =>
    switch (review?.action) {
      'approved' || 'modified' => QuestionStatus.approved,
      'rejected' => QuestionStatus.rejected,
      'regrade_requested' when !_regradeAnswered(review!, job) =>
        QuestionStatus.regradeRequested,
      _ => null,
    };

/// Whether the 再判定 [review] asked for has already been carried out by
/// [job].
///
/// Unlike 承認/却下, a `regrade_requested` row is a *request*, and nothing
/// ever closes it: the replacement grade lands as a new `GradeResult`, not as
/// a new `Review`. Treating the action as the node's state unconditionally
/// therefore left a question stuck on 再判定待ち forever -- AI処理中 while
/// the replacement job ran, then straight back to 再判定待ち once it
/// succeeded, with a fresh grade sitting on screen unmentioned (review round
/// 1, P2).
///
/// Either signal answers it. `Review.regrade_job_id` names the job the
/// request created, which settles the normal case outright and does not
/// depend on two clocks agreeing. The timestamp covers every other job that
/// ran after the request was recorded -- a re-submission under a newer graph
/// version, say -- whose result is likewise not the one the reviewer
/// rejected.
bool _regradeAnswered(ReviewResponse review, JobResponse? job) {
  if (job == null) return false;
  return job.id == review.regradeJobId ||
      job.createdAt.isAfter(review.createdAt);
}
