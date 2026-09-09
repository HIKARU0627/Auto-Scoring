/// 答案の状態を、画面が数える単位へ畳んだもの。
///
/// もとは `features/home/home_dashboard.dart` にあった。Issue #113 で答案キューが
/// 同じ畳み方と**同じ並び順**を必要としたので `core/` へ移した -- 2か所で別々に
/// 畳むと、ホームが開く1件とキューの先頭が食い違いうる。`core` は `features` を
/// import できない (`AGENTS.md` "Architecture") ので、共有するには降ろすしかない。
///
/// 語彙としては `core/submission_status.dart` (答案1件の状態を1行で見せる) や
/// `core/question_status.dart` (設問1件の状態) と同じ棚にある。あちらが
/// 「1件をどう見せるか」なのに対し、これは「何件あるかを数える単位」である。
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_status_tone.dart';

/// §25の7つの答案状態を、件数を数える画面が実際に区別する5つへ畳んだもの。
///
/// 答案取込・添削レビューは7状態をそのまま1行ずつ見せるが、ホームは
/// 「人間を待たせているものが何件あるか」を数える画面なので、単位が違う。
/// だからあの2画面のラベル表と共通化していない (docs/design-tokens.md §6)。
///
/// [intakeDone] と [needsReview] を分けているのが要点。`needs_review` は
/// 取込の時点で「人が見ないと先へ進めない」と判定された答案で、色を割く価値が
/// あるのはこちらだけである (docs/design-tokens.md §3.1)。[intakeDone] は
/// 「取込が終わった」以上のことを何も言わない置き場で、その中身の幅は §3.1。
enum HomeWorkBucket {
  /// `needs_review` -- 取込時に回答欄を確定できなかった、確認していない設問が
  /// 残っているなど、**人が見ないと先へ進めない**もの。理由そのものは
  /// `review_reason` にあり、答案取込画面が1行ずつ出す。
  needsReview(
    label: '要確認',
    icon: Icons.warning_amber,
    tone: AppStatusTone.attention,
  ),

  /// `ai_processed` -- **取込と回答欄の抽出が終わった、それだけが言える**答案。
  ///
  /// その先について、この bucket は何も主張しない。同じ `ai_processed` に、
  /// 起票されていない答案・実行待ち・AI処理中・成功・`usable=false`・失敗・
  /// 中止、そして**人間がレビューを済ませた答案**まで入る -- 答案の `state` を
  /// 動かすのは取込と `_sync_submission_review_state` だけで、後者は
  /// `needs_review` / `reviewed` の答案にしか働かないためである
  /// (`docs/home-dashboard.md` §3.1 に一覧と理由)。
  ///
  /// **だからラベルは「取込済み」でしかありえない。** 「レビュー待ち」は
  /// 「AIは終わって人間だけが残っている」の断定、「採点中」は「動いている」の
  /// 断定、「採点・レビュー待ち」は「どちらもまだ済んでいない」の断定であり、
  /// 最後のものは承認済みの答案がここに残る以上、実際に偽になる。
  intakeDone(
    label: '取込済み',
    icon: Icons.rate_review_outlined,
    tone: AppStatusTone.neutral,
  ),

  /// `unprocessed` / `ai_processing` -- 待っていれば進むもの。ホームでは
  /// 人間に何も求めないので色を持たない。
  processing(label: '処理中', icon: Icons.autorenew, tone: AppStatusTone.neutral),

  /// `error` -- 取込・処理が完了しなかったもの。放っておくとその生徒の答案が
  /// 黙って欠けるので、件数が0でない限りホームから隠さない。
  failed(label: '取込失敗', icon: Icons.error_outline, tone: AppStatusTone.danger),

  /// `reviewed` / `exported` -- 終わったもの。進捗バーの分子。
  done(
    label: '確認済み',
    icon: Icons.verified_outlined,
    tone: AppStatusTone.success,
  );

  const HomeWorkBucket({
    required this.label,
    required this.icon,
    required this.tone,
  });

  /// 日本語ラベル。色は状態の唯一の手がかりにしない (Issue #25) ため、
  /// ラベル・アイコン・強調度は常に3点セットで決める。
  final String label;
  final IconData icon;
  final AppStatusTone tone;

  static HomeWorkBucket of(String submissionState) => switch (submissionState) {
    'needs_review' => HomeWorkBucket.needsReview,
    'ai_processed' => HomeWorkBucket.intakeDone,
    'unprocessed' || 'ai_processing' => HomeWorkBucket.processing,
    'error' => HomeWorkBucket.failed,
    'reviewed' || 'exported' => HomeWorkBucket.done,
    // 知らない状態を [done] に入れると進捗バーが嘘をつく。サイドカーが
    // 先に新しい状態を覚えた場合でも「まだ動いている」側へ倒す。
    _ => HomeWorkBucket.processing,
  };
}
