import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/action_requirements.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 無効なボタンの隣に「何を満たせば有効になるか」を出す (Issue #88)。
///
/// **ツールチップではない。** ツールチップはポインタをボタンの上に置いた人にしか
/// 出ないので、キーボードだけで操作する人には届かない (受入条件1)。ここは常に
/// ツリーに居る `Text` なので、Tab でボタンに到達する前に読める -- 画面を読み上げ
/// させている人にも、ボタンの直後に読まれる。
///
/// 文言は持たない。[ActionRequirement] が持っているものを並べるだけで、
/// この widget は「何件あるとき、どう並べるか」だけを決める。文言の方針は
/// `docs/design-tokens.md` §8。
///
/// [requirements] が空のときは**何も描かない**。余白も取らない: 条件を満たした
/// 瞬間に理由が消えるのが、この widget の振る舞いの半分である (残りの半分は、
/// 無効なら必ず1件以上あること -- `core/action_requirements.dart`)。
class DisabledActionReason extends StatelessWidget {
  const DisabledActionReason({
    super.key,
    required this.requirements,
    this.padding = const EdgeInsets.only(top: AppSpacing.sm),
  });

  /// 満たされていない条件。空ならこの widget は消える。
  final List<ActionRequirement> requirements;

  /// ボタンとの間の余白。既定は「ボタンのすぐ下」。
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    if (requirements.isEmpty) return const SizedBox.shrink();
    // 色ではなく形でも分かるようにアイコンを添える (Issue #25)。`error` では
    // なく `info_outline`: 何かが失敗したのではなく、まだ条件が揃っていない
    // だけである。
    final style = context.texts.bodySmall?.copyWith(
      color: context.colors.onSurfaceVariant,
    );
    return Padding(
      padding: padding,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.info_outline,
            size: AppIconSize.inline,
            color: context.colors.onSurfaceVariant,
          ),
          const SizedBox(width: AppSpacing.xs),
          // `Expanded`: 700px 幅でも文が折り返せるようにする。`Row` は縮まない
          // ので、これが無いと文の右側が画面外に出る。
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 1件のときは見出しを付けない。「有効にするには:」の下に1行
                // だけ並ぶのは、同じことを2回言っているだけである。
                if (requirements.length > 1)
                  Text('この操作を有効にするには、次が必要です:', style: style),
                for (final requirement in requirements)
                  Text(
                    key: Key('disabled-reason-${requirement.id}'),
                    requirements.length > 1
                        ? '・${requirement.message}'
                        : requirement.message,
                    style: style,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
