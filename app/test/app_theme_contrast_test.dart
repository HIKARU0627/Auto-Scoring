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
