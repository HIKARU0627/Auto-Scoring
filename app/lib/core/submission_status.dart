/// 答案1件の取込状態を表す語彙 (`SubmissionResponse.state`)。
///
/// 設問の状態を [QuestionStatus] が1箇所に持っているのと同じ理由で1箇所に
/// 置いてある。答案の状態を出す画面は2つ (答案取込の一覧、添削レビューの
/// AppBar) あり、それぞれが自前の対応表を持っていたため、同じ `ai_processed`
/// を一方は「処理済み」、他方は「AI処理済み」と呼んでいた。同じ状態を2つの語で
/// 呼ぶのは、Issue #84 で直した食い違いの小さい方の版である。
///
/// **設問の状態とは別の語彙である。** 混ぜてはならない -- 答案の状態を設問の
/// 見出しの直下に置いたことが Issue #84 そのものだった。答案の状態を出す側は、
/// 対象が答案だと分かる位置と語で出すこと。
library;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_status_tone.dart';

/// アイコン・日本語ラベル・強調度の3点セット。状態を色だけでは表さない
/// (Issue #25) ので、この3つは常に一緒に決まる。
///
/// 「AI処理中」に色を付けないのが要点: 取込直後の一覧はほぼ全部が処理中で、
/// そこへ色を割くと本当に人間を呼んでいる 要確認/エラー が埋もれる。
@immutable
class SubmissionStatusVisual {
  const SubmissionStatusVisual._(this.icon, this.label, this.tone);

  /// [state] に対応する見せ方。`null` は答案をまだ読めていない場合で、
  /// 取込前と同じ「未処理」として扱う。
  ///
  /// 知らない state は**そのまま出す**。新しいバックエンドが増やした状態を
  /// 既知のどれかに丸めると、画面が知らないことを知っているように見せる
  /// ことになる。
  factory SubmissionStatusVisual.of(String? state) => switch (state) {
    null || 'unprocessed' => const SubmissionStatusVisual._(
      Icons.hourglass_empty,
      '未処理',
      AppStatusTone.neutral,
    ),
    'ai_processing' => const SubmissionStatusVisual._(
      Icons.autorenew,
      'AI処理中',
      AppStatusTone.neutral,
    ),
    'ai_processed' => const SubmissionStatusVisual._(
      Icons.check_circle_outline,
      'AI処理済み',
      AppStatusTone.success,
    ),
    'needs_review' => const SubmissionStatusVisual._(
      Icons.warning_amber,
      '要確認',
      AppStatusTone.attention,
    ),
    'reviewed' => const SubmissionStatusVisual._(
      Icons.verified_outlined,
      '確認済み',
      AppStatusTone.success,
    ),
    'exported' => const SubmissionStatusVisual._(
      Icons.file_download_done,
      '出力済み',
      AppStatusTone.success,
    ),
    'error' => const SubmissionStatusVisual._(
      Icons.error_outline,
      'エラー',
      AppStatusTone.danger,
    ),
    _ => SubmissionStatusVisual._(
      Icons.help_outline,
      state,
      AppStatusTone.neutral,
    ),
  };

  final IconData icon;

  final String label;

  final AppStatusTone tone;
}
