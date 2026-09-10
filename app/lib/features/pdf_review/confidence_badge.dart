import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/confidence_level.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 「採点信頼度: 88% (中)」 -- 0..1 の Confidence を、数と語とアイコンで1行に
/// 出す ([ConfidenceLevel])。
///
/// 添削レビュー画面と答案確定画面 (Issue #145) が同じものを出すので、`pdf_review_page.dart`
/// から出してある。**同じ数を2つの画面が違う顔で見せると、どちらが本当か
/// 分からなくなる** (Issue #84)。
///
/// **これは確定の可否に一切関与しない。** 簡易設計書 §25.2、および確信度1.00の
/// 誤った0点を14件中7件見た Issue #136 -- ここが出すのは「AIがどれくらい自信が
/// あると言ったか」であって、正しさではない。
class ConfidenceBadge extends StatelessWidget {
  const ConfidenceBadge({
    super.key,
    required this.label,
    required this.confidence,
  });

  final String label;
  final double confidence;

  @override
  Widget build(BuildContext context) {
    final level = ConfidenceLevel.of(confidence);
    // 中と高は同じ無彩色の目盛りアイコンで、区別は数値と「中」「高」の語が
    // 付ける。高だけ別のアイコンを与えれば、色を外しても「高は良い印」が
    // 残ってしまう -- Issue #156 で外したのは色ではなく、太鼓判そのもの。
    final icon = switch (level) {
      ConfidenceLevel.high || ConfidenceLevel.medium => Icons.straighten,
      ConfidenceLevel.low => Icons.warning_amber,
    };
    // 低Confidence は「人間が見ないと決められない」の代表例なので、この画面で
    // 強調色を使ってよい数少ない場所。中/高は進行中と同じく無彩色に置く --
    // 全部に色を付ければ、どれも目立たなくなる。
    final tone = switch (level) {
      ConfidenceLevel.high || ConfidenceLevel.medium => AppStatusTone.neutral,
      ConfidenceLevel.low => AppStatusTone.attention,
    };
    final color = tone.color(context);
    final percent = (confidence * 100).round();
    return Semantics(
      label: '$label $percent% ${level.label}',
      // Without this, the child Text's own auto-generated semantics label
      // merges with this one (joined by a newline) instead of being
      // replaced by it, and a screen reader would announce both.
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: AppIconSize.dense, color: color),
          const SizedBox(width: AppSpacing.xs),
          Text(
            '$label: $percent% (${level.label})',
            style: context.texts.bodySmall?.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}
