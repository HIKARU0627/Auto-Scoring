import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// The recoverable-failure banner every screen shows in the same place and the
/// same shape: what failed, in Japanese, and the one button that retries it.
///
/// Extracted from four hand-built copies (答案取込・テスト登録・テスト設定・
/// 添削レビューのInspector) that had drifted apart in padding and in whether
/// the retry sat beside the message or under it.
///
/// This is also the one place Issue #67 spends its motion budget. The banner
/// fades and lifts in over [AppMotion.emphasis] because it is the archetypal
/// "状態が変わった瞬間" -- something the reviewer did not ask for has appeared
/// and they need to notice it. Nothing here loops or moves afterwards.
class AppErrorBanner extends StatelessWidget {
  const AppErrorBanner({
    super.key,
    required this.message,
    this.messageKey,
    this.onRetry,
    this.retryable = true,
    this.retryLabel = '再試行',
  });

  /// The failure, already turned into something a reviewer can act on.
  final String message;

  /// Identifies the message text for widget tests that assert on *this*
  /// screen's failure rather than any text that happens to match.
  final Key? messageKey;

  /// `null` while a retry is already running -- the button is then shown
  /// disabled rather than removed, so the banner does not change size under
  /// the reviewer's pointer.
  final VoidCallback? onRetry;

  /// `false` where the failure has no single thing to re-run: テスト設定画面
  /// reports which of its several explicit actions failed, and the reviewer
  /// presses that action again rather than a generic 再試行.
  final bool retryable;

  final String retryLabel;

  @override
  Widget build(BuildContext context) {
    final banner = Card(
      color: context.colors.errorContainer,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadius.mdAll,
        side: BorderSide(color: context.colors.error),
      ),
      child: Padding(
        padding: AppSpacing.banner,
        child: Row(
          children: [
            // The icon carries the failure as much as the colour does: a
            // container the reviewer cannot distinguish by hue still reads as
            // an error (Issue #25).
            Icon(
              Icons.error_outline,
              color: context.colors.onErrorContainer,
              size: AppIconSize.standard,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                message,
                key: messageKey,
                style: context.texts.bodyMedium?.copyWith(
                  color: context.colors.onErrorContainer,
                ),
              ),
            ),
            if (retryable)
              TextButton(onPressed: onRetry, child: Text(retryLabel)),
          ],
        ),
      ),
    );
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: 1),
      duration: AppMotion.emphasis,
      curve: AppMotion.enter,
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(
          offset: Offset(0, (1 - t) * AppSpacing.sm),
          child: child,
        ),
      ),
      child: banner,
    );
  }
}
