import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_theme_context.dart';

/// How urgently a state wants the reviewer's eye.
///
/// Screens map their own domain states (答案の取込状態, Confidence, 設問の
/// レビュー状態) onto one of these four, and the tone decides the colour. That
/// indirection is the point: the rule "強調色は人間の確認が要る状態のためだけ"
/// is then stated once, here, instead of being re-decided every time a new
/// state is added to a screen.
///
/// A tone is never the only signal -- Issue #25's rule is that every state
/// carries an icon and a Japanese label too, and these colours only sharpen a
/// distinction that already survives without them.
enum AppStatusTone {
  /// Nothing is being asked of the reviewer: 未処理, AI処理中, 未評価.
  ///
  /// Deliberately uncoloured. Work in progress is the most common state on a
  /// busy screen, and if it were tinted it would drown out [attention].
  neutral,

  /// 人間が見ないと先へ進めない: 要確認, 低Confidence, 判断できなかった設問.
  /// The one state allowed to pull the eye across the screen.
  attention,

  /// 済んだもの: 承認済み, 確認済み, 出力済み. Muted, so finished work recedes.
  success,

  /// 失敗したもの: エラー, 取込失敗. Distinct from [attention] -- this is an
  /// operation that did not complete, not a result that needs judging.
  danger;

  /// The foreground colour for an icon or a line of text in this tone.
  Color color(BuildContext context) => switch (this) {
    AppStatusTone.neutral => context.colors.onSurfaceVariant,
    AppStatusTone.attention => context.statusColors.attention,
    AppStatusTone.success => context.statusColors.success,
    AppStatusTone.danger => context.colors.error,
  };
}
