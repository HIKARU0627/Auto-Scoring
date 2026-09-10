/// 答案1枚を1回で確定するための判定 (Issue #145)。
///
/// **確定の単位は設問ではなく答案1枚である。** 40枚 × 5設問の現場で、設問ごとに
/// 承認させると200回の操作になる。#113 が消したのはホームへの往復80回だけで、
/// 残る200回はこの単位を変えないと減らない。
///
/// ただし **「1回で確定」を、見ていないものを確定させる口実にしてはならない**
/// (Issue #85)。だからここは「確定してよいか」を2つの事実だけから決める。
///
/// 1. その設問の判断材料が**画面に出て、人がそこへ到達した** ([QuestionConfirmation.isReached])。
/// 2. 確定する対象が**実在する** -- AIの点数がある、まだ確定していない、読み込めている。
///
/// **確信度は入力にしない。** 簡易設計書 §25.2「確信度から完了を導かない」。
/// Issue #136 が実測したとおり、確信度1.00の誤った0点は14件中7件あり、正しい0点と
/// 画面上で同じ顔をしている。**閾値で選別すれば、誤りだけが選ばれて確定する。**
/// このライブラリに confidence を受け取る引数が1つも無いのは、忘れたからではない。
///
/// ウィジェットを持たないのは `core/review_queue.dart` / `core/question_status.dart`
/// と同じ理由で、確定してよいかの判断はこのアプリで最も間違えたくない部分だから、
/// 画面を立ち上げずに `submission_confirmation_test.dart` から直接読める。
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// 設問1件の、確定に関わる事実だけを写したもの。
class QuestionConfirmation {
  const QuestionConfirmation({
    required this.questionId,
    required this.number,
    required this.materialLoaded,
    required this.isConfirmed,
    required this.aiGradeId,
    required this.expectedVersion,
    required this.isReached,
  });

  final String questionId;

  /// 画面に出る設問番号。**id は出さない** -- 「問q-3が未到達です」は誰にも読めない。
  final String number;

  /// この設問の判断材料が読み終わっているか。
  ///
  /// 読み込み中や取得失敗を「確定できる」側に数えない。人が見ていないものを
  /// 確定させないという話は、**そもそも画面が出せていないもの**にもそのまま
  /// かかる (添削レビュー画面の `_canDecide` と同じ判断)。
  final bool materialLoaded;

  /// すでに人が確定している (`approved` / `modified`、Undo 済みでない)。
  final bool isConfirmed;

  /// 確定の対象になる AI の点数。無ければ `null`。
  ///
  /// `Review.APPROVED` は `ai_grade_result_id` を必須にしている
  /// (`domain/models.py`) ので、これが `null` の設問は**承認できない**。
  /// 人が自分で点数を入れるしかない (Issue #118 の「点数を入力」)。
  final String? aiGradeId;

  /// 次の確定要求に渡す楽観ロックのトークン -- この設問のレビュー履歴の長さ
  /// (`docs/review-edit-history.md` §2)。
  final int expectedVersion;

  /// **人がこの設問の判断材料まで到達した。**
  ///
  /// 「表示された」ではなく「到達した」である。画面のどこかに描かれていても、
  /// 下端の外にあるものは見られていない -- Issue #85 が5往復かけて確かめた
  /// ことで、まとめて確定する画面ではその危険がそのまま設問の数だけ増える。
  final bool isReached;

  bool get hasAiGrade => aiGradeId != null;

  /// この確定操作が実際に承認しにいく設問。
  bool get needsApproval => materialLoaded && !isConfirmed && hasAiGrade;

  /// AIが点数を出せなかったので、**人が自分で入れないと終わらない**設問。
  bool get needsHumanScore => materialLoaded && !isConfirmed && !hasAiGrade;

  /// 承認しに行くのに、まだ人が到達していない設問。
  ///
  /// **確定済みの設問は数えない。** もう一度見せろと言うことになるが、その確定は
  /// 過去に人が見て決めたものであり、この画面がやり直させるものではない。
  bool get isUnreached => needsApproval && !isReached;
}

/// 答案1枚を確定してよいかを、確定できない理由まで込みで答える。
class SubmissionConfirmation {
  const SubmissionConfirmation(this.questions);

  /// 画面に並ぶ順。**確定する順でもある** -- 部分失敗したとき「どこまで確定した
  /// か」が画面の並びと一致していないと、残りがどれか読めない。
  final List<QuestionConfirmation> questions;

  /// まだ読み込めていない設問。
  List<QuestionConfirmation> get unloaded =>
      questions.where((q) => !q.materialLoaded).toList();

  /// この操作が承認する設問。
  List<QuestionConfirmation> get pending =>
      questions.where((q) => q.needsApproval).toList();

  /// **どれが未到達か。** 画面はこれを名指しで出す (Issue #145 受入)。
  List<QuestionConfirmation> get unreached =>
      questions.where((q) => q.isUnreached).toList();

  /// 人が点数を入れないと確定できない設問。
  List<QuestionConfirmation> get needingHumanScore =>
      questions.where((q) => q.needsHumanScore).toList();

  int get confirmedCount => questions.where((q) => q.isConfirmed).length;

  int get total => questions.length;

  /// 全設問が確定済み -- この答案にもう用は無い。
  bool get isFullyConfirmed =>
      questions.isNotEmpty && questions.every((q) => q.isConfirmed);

  /// 確定を押せない理由。押せるなら `null`。
  ///
  /// 順番に意味がある。**読み込めていないことが最優先** -- 出ていないものに
  /// ついて「見ましたか」と訊いても答えようがない。次が「人が点数を入れないと
  /// 承認できない設問」で、これは到達したところで消えない。最後が未到達で、
  /// これはスクロールすれば消える。
  SubmissionConfirmBlock? get blocker {
    if (questions.isEmpty) return SubmissionConfirmBlock.noQuestions;
    if (unloaded.isNotEmpty) return SubmissionConfirmBlock.materialUnavailable;
    if (needingHumanScore.isNotEmpty) {
      return SubmissionConfirmBlock.humanScoreRequired;
    }
    if (unreached.isNotEmpty) return SubmissionConfirmBlock.unreached;
    if (pending.isEmpty) return SubmissionConfirmBlock.nothingToConfirm;
    return null;
  }

  bool get canConfirm => blocker == null;
}

/// なぜ確定できないか。
enum SubmissionConfirmBlock {
  /// この答案に設問が1つも無い（テストの設問がまだ登録されていない）。
  noQuestions,

  /// 判断材料が読み込めていない設問がある。
  materialUnavailable,

  /// AIが採点できなかった設問がある -- 人が点数を入れるまで承認できない。
  humanScoreRequired,

  /// まだ人が到達していない設問がある。
  unreached,

  /// 確定するものが残っていない（全部確定済み）。
  nothingToConfirm,
}

/// N回の確定要求を流した結果。
///
/// **成功したかどうかではなく、どこまで進んだかを持つ。** OpenAPI schema を
/// 変えない以上、答案1枚の確定は設問ごとの確定APIをN回呼ぶ形にしかならず、
/// **途中で失敗しうる**。そのとき「確定できませんでした」とだけ言う画面は、
/// 3問目まで確定した事実を人から隠すことになる。**「1回で確定」は、失敗を
/// 隠す言い訳にしてはならない** (Issue #145 制約)。
class SubmissionConfirmationOutcome {
  const SubmissionConfirmationOutcome({
    required this.confirmed,
    required this.remaining,
    this.failedNumber,
    this.message,
  });

  /// この操作で確定できた設問番号。**失敗した回でも空とは限らない。**
  final List<String> confirmed;

  /// 確定できずに残った設問番号（失敗したものを含む）。
  final List<String> remaining;

  /// 失敗した設問番号。最後まで通ったなら `null`。
  final String? failedNumber;

  /// サイドカーが返した理由。
  final String? message;

  bool get isComplete => failedNumber == null;
}

/// [questions] を順に確定する。**最初の失敗で止める。**
///
/// 止めるのは、失敗の多くが競合 (409) だからである。誰か（あるいは自分の別の
/// 操作）がこの答案を触っていたなら、後続の `expectedVersion` も同じように
/// 古い。押し通しても失敗が並ぶだけで、**どこで何が起きたかは読みにくくなる**。
/// 止めて、そこまでを見せて、読み直してからやり直させるほうが速い。
///
/// [approve] は設問1件を確定する呼び出し。ウィジェットもサイドカーも要らない
/// 形にしてあるので、部分失敗の筋書きは `submission_confirmation_test.dart` から
/// そのまま作れる。
Future<SubmissionConfirmationOutcome> runSubmissionConfirmation({
  required List<QuestionConfirmation> questions,
  required Future<void> Function(QuestionConfirmation question) approve,
}) async {
  final confirmed = <String>[];
  for (var i = 0; i < questions.length; i++) {
    final question = questions[i];
    try {
      await approve(question);
    } on SidecarApiException catch (error) {
      return SubmissionConfirmationOutcome(
        confirmed: confirmed,
        remaining: [for (final rest in questions.skip(i)) rest.number],
        failedNumber: question.number,
        message: error.message,
      );
    }
    confirmed.add(question.number);
  }
  return SubmissionConfirmationOutcome(
    confirmed: confirmed,
    remaining: const [],
  );
}
