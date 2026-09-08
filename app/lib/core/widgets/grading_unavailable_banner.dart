import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 「この端末では AI 採点が使えない」を、全画面の上に出しっぱなしにする帯
/// (Issue #97)。
///
/// なぜ画面ごとのバナーではなく、Navigator の上に1枚なのか: これは1つの画面で
/// 起きた失敗ではなく、**この端末の設定**という、どの画面にいても同じ1つの事実
/// だからである。答案取込は成功し、ジョブも起票され、レビュー画面は開く。違うのは
/// 設問が1つも採点されないことだけで、その最終形（設問が「失敗」になる）は
/// 「AIが答案を読めなかった」ときの見え方と区別がつかない。区別をつけられる
/// 情報はここにしか無い。
///
/// **消せない。** 閉じるボタンを付けると「消したまま採点されない状態」が作れて
/// しまい、それはこの Issue が消しに来た「黙って採点されない」そのものになる。
/// 代わりに、出す条件を厳しくしてある -- [availability] が `null`、つまり
/// サイドカーにまだ聞けていない・聞いたが答えが返らなかった間は**何も出さない**。
/// 「応答が無い」と「採点が使えない」は別の事実で、前者を後者として断定すると、
/// 一度の通信失敗が設定不備の告知になってしまう。
///
/// 帯の中に再試行を置いていないのも同じ理由で、直し方はこのアプリの中に無い
/// （プロバイダの設定は端末側の作業。配布時の持たせ方は Issue #96 で未決）。
class GradingUnavailableBanner extends StatelessWidget {
  const GradingUnavailableBanner({
    super.key,
    required this.availability,
    required this.child,
  });

  /// サイドカーの `GET /grading/availability` の答え。まだ聞けていなければ
  /// `null` で、そのときは帯を出さない。
  final GradingAvailabilityResponse? availability;

  /// アプリの Navigator (`MaterialApp.builder` が渡してくる子)。
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final state = availability;
    if (state == null || state.available) {
      return child ?? const SizedBox.shrink();
    }
    return Column(
      children: [
        _Banner(reason: state.reason),
        // 帯のぶんだけ画面が縮む。重ねて浮かせないのは、下の画面の一番上
        // （AppBar やスクロールの先頭）を隠さないため。
        Expanded(child: child ?? const SizedBox.shrink()),
      ],
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.reason});

  /// サイドカーが返した理由。設定変数名とホストの前提条件だけで、資格情報の
  /// 値は含まれない (`backend/.../api/app.py` の `build_ai_provider`)。
  /// 日本語ではないが、実際に直せる人が読む唯一の手がかりなので落とさない。
  final String? reason;

  @override
  Widget build(BuildContext context) {
    final tone = AppStatusTone.attention.color(context);
    return Material(
      color: context.colors.surfaceContainerHighest,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: AppSpacing.banner,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 色だけに頼らない (Issue #25)。アイコン・日本語ラベル・強調度の
              // 3点セットは他の状態表示と同じ規約。
              Icon(
                Icons.warning_amber,
                color: tone,
                size: AppIconSize.standard,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'AI採点は使えません（この端末に設定がありません）',
                      key: const Key('grading-unavailable-headline'),
                      style: context.texts.bodyMedium?.copyWith(
                        color: context.colors.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      '答案取込・添削レビュー・PDF出力はこのまま使えます。'
                      '取り込んだ答案の設問は採点されず「失敗」になります。',
                      style: context.texts.bodySmall?.copyWith(
                        color: context.colors.onSurfaceVariant,
                      ),
                    ),
                    if (reason case final detail? when detail.isNotEmpty) ...[
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        detail,
                        key: const Key('grading-unavailable-reason'),
                        style: context.texts.bodySmall?.copyWith(
                          color: context.colors.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
