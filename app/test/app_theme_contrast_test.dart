import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/design/app_color_schemes.dart';
import 'package:auto_scoring_app/core/design/app_typography.dart';

/// Measures the theme's contrast ratios instead of trusting them (Issue #67
/// acceptance: 「コントラスト比を確認すること」; Issue #25's rule that a state
/// must survive without colour is enforced at the call sites).
///
/// The numbers this asserts are the ones written down in
/// `docs/design-tokens.md` §3. Re-run this after touching any colour token:
/// the palette was tuned until these passed, so a failure here means the
/// change made something unreadable, not that the threshold is wrong.
void main() {
  /// WCAG 2.1 relative luminance.
  double luminance(Color color) {
    double channel(double c) =>
        c <= 0.03928 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4) as double;
    return 0.2126 * channel(color.r) +
        0.7152 * channel(color.g) +
        0.0722 * channel(color.b);
  }

  /// WCAG 2.1 contrast ratio, 1.0 (identical) to 21.0 (black on white).
  double contrast(Color foreground, Color background) {
    final a = luminance(foreground);
    final b = luminance(background);
    return (math.max(a, b) + 0.05) / (math.min(a, b) + 0.05);
  }

  /// WCAG AA for body text. Everything this app puts on a surface is body-sized
  /// or smaller, so nothing gets the 3:1 large-text allowance.
  const double aaText = 4.5;

  /// WCAG AA for a non-text boundary a user must be able to find (1.4.11).
  const double aaNonText = 3.0;

  for (final brightness in Brightness.values) {
    final name = brightness.name;
    final scheme = appColorScheme(brightness);
    final status = brightness == Brightness.light
        ? AppStatusColors.light
        : AppStatusColors.dark;

    test('$name: text is readable on every surface step', () {
      // The elevation ramp exists so panels can be told apart; each step still
      // has to carry ordinary text, or a card on a card becomes unreadable.
      final surfaces = <String, Color>{
        'surface': scheme.surface,
        'surfaceDim': scheme.surfaceDim,
        'surfaceContainerLowest': scheme.surfaceContainerLowest,
        'surfaceContainerLow': scheme.surfaceContainerLow,
        'surfaceContainer': scheme.surfaceContainer,
        'surfaceContainerHigh': scheme.surfaceContainerHigh,
        'surfaceContainerHighest': scheme.surfaceContainerHighest,
      };
      for (final surface in surfaces.entries) {
        expect(
          contrast(scheme.onSurface, surface.value),
          greaterThanOrEqualTo(aaText),
          reason: 'onSurface on ${surface.key}',
        );
        // Secondary text (labels, subtitles, the neutral status tone) is the
        // one that gets quietly lost when a surface is retuned.
        expect(
          contrast(scheme.onSurfaceVariant, surface.value),
          greaterThanOrEqualTo(aaText),
          reason: 'onSurfaceVariant on ${surface.key}',
        );
      }
    });

    test('$name: every Material on/role pair meets AA', () {
      final pairs = <String, (Color, Color)>{
        'onPrimary/primary': (scheme.onPrimary, scheme.primary),
        'onPrimaryContainer/primaryContainer': (
          scheme.onPrimaryContainer,
          scheme.primaryContainer,
        ),
        'onSecondaryContainer/secondaryContainer': (
          scheme.onSecondaryContainer,
          scheme.secondaryContainer,
        ),
        'onTertiaryContainer/tertiaryContainer': (
          scheme.onTertiaryContainer,
          scheme.tertiaryContainer,
        ),
        'onError/error': (scheme.onError, scheme.error),
        'onErrorContainer/errorContainer': (
          scheme.onErrorContainer,
          scheme.errorContainer,
        ),
        'onInverseSurface/inverseSurface': (
          scheme.onInverseSurface,
          scheme.inverseSurface,
        ),
      };
      for (final pair in pairs.entries) {
        expect(
          contrast(pair.value.$1, pair.value.$2),
          greaterThanOrEqualTo(aaText),
          reason: pair.key,
        );
      }
    });

    test('$name: status colours are readable where they are actually used', () {
      // `attention`/`success` are drawn as an icon plus a line of text directly
      // on a surface (`AppStatusTone.color`), so they are text contrast, not
      // decoration -- including on the containers a card raises them onto.
      for (final background in <String, Color>{
        'surface': scheme.surface,
        'surfaceContainerLow': scheme.surfaceContainerLow,
        'surfaceContainerHighest': scheme.surfaceContainerHighest,
      }.entries) {
        expect(
          contrast(status.attention, background.value),
          greaterThanOrEqualTo(aaText),
          reason: 'attention on ${background.key}',
        );
        expect(
          contrast(status.success, background.value),
          greaterThanOrEqualTo(aaText),
          reason: 'success on ${background.key}',
        );
        expect(
          contrast(scheme.error, background.value),
          greaterThanOrEqualTo(aaText),
          reason: 'error on ${background.key}',
        );
      }
      expect(
        contrast(status.onAttentionContainer, status.attentionContainer),
        greaterThanOrEqualTo(aaText),
        reason: 'onAttentionContainer/attentionContainer',
      );
      expect(
        contrast(status.onSuccessContainer, status.successContainer),
        greaterThanOrEqualTo(aaText),
        reason: 'onSuccessContainer/successContainer',
      );
    });

    test('$name: a disabled button can be found and read', () {
      // Issue #88 受入条件2。**目で見て決めない。** Material の既定
      // (`onSurface` を 12%/38% で重ねる) は、このアプリの静かなランプの上では
      // 数値が出ない -- 下の `Material の既定では足りない` がその実測で、ここは
      // 上書きした3色が足りていることの実測である。役割の分担は
      // `core/design/app_color_schemes.dart` の `AppDisabledButtonColors`。
      final surfaces = <String, Color>{
        'surface': scheme.surface,
        'surfaceContainerLow': scheme.surfaceContainerLow,
        'surfaceContainerHigh': scheme.surfaceContainerHigh,
        'surfaceContainerHighest': scheme.surfaceContainerHighest,
      };
      for (final surface in surfaces.entries) {
        // 境界線。「ボタンがそこにある」を持つのはこれなので、1.4.11 の 3:1。
        expect(
          contrast(scheme.disabledButtonOutline, surface.value),
          greaterThanOrEqualTo(aaNonText),
          reason: 'disabled outline on ${surface.key}',
        );
        // ラベル。読む文字なので 4.5:1。どのカードの上でも読めること。
        expect(
          contrast(scheme.disabledButtonLabel, surface.value),
          greaterThanOrEqualTo(aaText),
          reason: 'disabled label on ${surface.key}',
        );
      }
      // ラベルは自分の板の上でも読める。
      expect(
        contrast(scheme.disabledButtonLabel, scheme.disabledButtonContainer),
        greaterThanOrEqualTo(aaText),
        reason: 'disabled label on its own container',
      );
      // そして**有効なときより静か**であること。数値が有効と並ぶと、押せない
      // ボタンが押せるボタンに見える。色だけで「押せない」を伝えてはいないが
      // (理由の文がそれをする)、色が逆を言ってしまってもいけない。
      expect(
        contrast(scheme.disabledButtonLabel, scheme.surfaceContainerLow),
        lessThan(contrast(scheme.onSurface, scheme.surfaceContainerLow)),
        reason: 'disabled label must be quieter than body text',
      );
    });

    test('$name: Material の既定では足りない', () {
      // この上書きが何を直したのかを数値で残す。ここが `aaNonText` を超える日が
      // 来たら、それは Material が既定を変えた日であり、上書きを見直す合図で
      // ある -- 「なんとなく入れた上書き」にしないための1本。
      final defaultOutline = Color.alphaBlend(
        scheme.onSurface.withValues(alpha: 0.12),
        scheme.surfaceContainerLow,
      );
      expect(
        contrast(defaultOutline, scheme.surfaceContainerLow),
        lessThan(aaNonText),
        reason:
            'Material の既定の無効枠 (onSurface 12%) はカードの上で見つからない。'
            'これが #88 受入条件2 の「ボタンであることすら判別しにくい」である',
      );
    });

    test('$name: the theme actually hands those colours to every button', () {
      // 色を定義しただけでは何も変わらない。3種類のボタンのテーマが無効状態で
      // 実際にその色を返すことまで見る -- `_buttonStyle` の上書きを外すと、
      // 上の2本は通ったままここだけが落ちる。
      final theme = brightness == Brightness.light
          ? AppTheme.light()
          : AppTheme.dark();
      const disabled = <WidgetState>{WidgetState.disabled};
      final styles = <String, ButtonStyle?>{
        'filled': theme.filledButtonTheme.style,
        'outlined': theme.outlinedButtonTheme.style,
        'text': theme.textButtonTheme.style,
      };
      for (final entry in styles.entries) {
        final style = entry.value;
        expect(style, isNotNull, reason: entry.key);
        expect(
          style!.foregroundColor?.resolve(disabled),
          scheme.disabledButtonLabel,
          reason: '${entry.key}: disabled label',
        );
        expect(
          style.iconColor?.resolve(disabled),
          scheme.disabledButtonLabel,
          reason: '${entry.key}: disabled icon',
        );
        expect(
          style.backgroundColor?.resolve(disabled),
          scheme.disabledButtonContainer,
          reason: '${entry.key}: disabled container',
        );
        expect(
          style.side?.resolve(disabled)?.color,
          scheme.disabledButtonOutline,
          reason: '${entry.key}: disabled outline',
        );
        // 有効のときは `null` を返して Material の既定へ落とす。ここが値を
        // 返し始めると、3種類のボタンの既定を書き写したことになる。
        expect(
          style.backgroundColor?.resolve(const <WidgetState>{}),
          isNull,
          reason: '${entry.key}: enabled state must fall through to Material',
        );
      }
    });

    test('$name: an outline can be found against the surface it bounds', () {
      expect(
        contrast(scheme.outline, scheme.surface),
        greaterThanOrEqualTo(aaNonText),
        reason: 'outline is what marks a focused/enabled control boundary',
      );
    });
  }

  test('the annotation mark stays legible on the PDF page, not the theme', () {
    // 添削記号 are painted over the rendered page, which is white in both
    // themes -- so the one value has to work against paper, and both themes
    // must keep using the same one.
    expect(
      AppStatusColors.light.annotationMark,
      AppStatusColors.dark.annotationMark,
    );
    expect(
      contrast(AppStatusColors.light.annotationMark, const Color(0xFFFFFFFF)),
      greaterThanOrEqualTo(aaText),
      reason: '○×△ and the score number are read as text on the answer sheet',
    );
  });

  test('dark text is soft, not maximum-contrast', () {
    // The design decision this locks in: pure white on near-black maximises
    // halation around dense kanji strokes over a long grading session. If a
    // later change pushes this back towards Material's ~14:1 default, that is
    // a decision to make deliberately -- and to re-record in
    // `docs/design-tokens.md` -- not to slip in.
    final dark = appColorScheme(Brightness.dark);
    expect(
      contrast(dark.onSurface, dark.surface),
      inInclusiveRange(7.0, 13.0),
      reason: 'far past WCAG AAA (7:1), deliberately short of white-on-black',
    );
  });

  test('both themes carry the design-token extensions', () {
    // `context.statusColors` / `context.textRoles` resolve these with `!`, so
    // a theme missing one is a crash on the screen that reads it, not a
    // fallback to something duller.
    for (final theme in [AppTheme.light(), AppTheme.dark()]) {
      expect(theme.extension<AppStatusColors>(), isNotNull);
      expect(theme.extension<AppTextRoles>(), isNotNull);
      expect(theme.useMaterial3, isTrue);
    }
  });
}
