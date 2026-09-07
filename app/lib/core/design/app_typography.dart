/// Typography tokens (Issue #67).
///
/// This app's screen text is Japanese almost end to end -- 設問文, the
/// characters OCR read off a handwritten answer, and the grading comment a
/// teacher will hand back. Latin appears only in scores (`5 / 5`) and a few
/// labels. So the font is chosen *for Japanese* and Latin comes along with it,
/// not the other way round: a Latin UI font with the OS filling in kanji
/// behind it mixes two designs' weights, widths and baselines in the middle of
/// a sentence, which is exactly the text a reviewer has to read most carefully.
///
/// **Noto Sans JP**, bundled (`app/assets/fonts/`, SIL OFL 1.1). Why this one,
/// what was weighed against it, and the licence terms: `docs/design-tokens.md`
/// §2. Two properties matter enough to restate here, because code below
/// depends on them and `test/app_typography_test.dart` asserts them:
///
/// * Its digits are all one width, so a score column does not shuffle sideways
///   as `1` and `8` swap places. No `tnum` feature is needed -- the font has
///   none, and does not need one.
/// * It is a variable font on the `wght` axis, and Flutter maps [FontWeight]
///   straight onto that axis, so a plain `fontWeight:` gives real weights (not
///   a synthesised smear) from a single 9.6 MB file.
library;

import 'package:flutter/material.dart';

/// The bundled family, as declared in `pubspec.yaml`.
const String appFontFamily = 'Noto Sans JP';

/// Japanese needs more leading than Material's Latin-tuned defaults: kanji fill
/// their em box top to bottom, so lines set at Latin leading visually collide.
///
/// Only the two styles that wrap get a name here. The display/headline/title
/// steps set their own, tighter, values inline: a heading is one or two lines,
/// and paragraph leading makes it read as two separate things.
const double _readingHeight = 1.75;
const double _uiHeight = 1.4;

/// Material's body/label styles carry a positive `letterSpacing` tuned for
/// Latin. Applied to Japanese it opens gaps *inside* a word, since there are no
/// spaces to carry the rhythm -- so the reading styles set it to zero. The one
/// exception is [AppTextRoles.recognizedText]; see its doc.
const double _noTracking = 0.0;

TextStyle _style(
  double size,
  FontWeight weight, {
  double height = _uiHeight,
  double letterSpacing = _noTracking,
}) {
  return TextStyle(
    fontFamily: appFontFamily,
    fontSize: size,
    fontWeight: weight,
    height: height,
    letterSpacing: letterSpacing,
    // Splits the extra leading evenly above and below the line instead of
    // hanging it all under the baseline, which is what keeps a Japanese line
    // optically centred in its row (list tiles, chips, table cells).
    leadingDistribution: TextLeadingDistribution.even,
  );
}

/// The Material type scale, at Material's own sizes, restated with this app's
/// font, leading and tracking.
///
/// The sizes are not re-invented: every Material component resolves its text
/// from one of these slots, so keeping the canonical steps means a `Chip`, a
/// `ListTile` and a `SnackBar` stay proportioned as designed. What changes is
/// how a Japanese line sits inside them.
TextTheme appTextTheme(ColorScheme colorScheme) {
  final theme = TextTheme(
    displayLarge: _style(57, FontWeight.w400, height: 1.15),
    displayMedium: _style(45, FontWeight.w400, height: 1.2),
    displaySmall: _style(36, FontWeight.w400, height: 1.25),
    headlineLarge: _style(32, FontWeight.w400, height: 1.3),
    headlineMedium: _style(28, FontWeight.w400, height: 1.3),
    headlineSmall: _style(24, FontWeight.w500, height: 1.35),
    titleLarge: _style(22, FontWeight.w500, height: 1.35),
    titleMedium: _style(16, FontWeight.w500, height: 1.5),
    titleSmall: _style(14, FontWeight.w500, height: 1.5),
    bodyLarge: _style(16, FontWeight.w400, height: _readingHeight),
    bodyMedium: _style(14, FontWeight.w400, height: _readingHeight),
    bodySmall: _style(12, FontWeight.w400, height: 1.7),
    labelLarge: _style(14, FontWeight.w500, height: _uiHeight),
    labelMedium: _style(12, FontWeight.w500, height: _uiHeight),
    labelSmall: _style(11, FontWeight.w500, height: _uiHeight),
  );
  return theme.apply(
    bodyColor: colorScheme.onSurface,
    displayColor: colorScheme.onSurface,
  );
}

/// The styles this app names by *what the text is*, not by where it sits in the
/// Material scale.
///
/// A screen asking for `titleSmall` says nothing about why; asking for
/// [recognizedText] says the text is a machine's reading of someone's
/// handwriting, and the style can then be tuned for exactly that job without
/// hunting down every `titleSmall` in the app. Reached through
/// `Theme.of(context).extension<AppTextRoles>()` -- or the
/// `context.textRoles` shorthand in `core/design/app_theme_context.dart`.
@immutable
class AppTextRoles extends ThemeExtension<AppTextRoles> {
  const AppTextRoles({
    required this.questionText,
    required this.recognizedText,
    required this.gradingComment,
    required this.score,
    required this.uiLabel,
  });

  /// 設問文。The reviewer reads this to remind themselves what was asked, then
  /// moves on -- ordinary reading text, generous leading.
  final TextStyle questionText;

  /// 認識された答案の文字。
  ///
  /// The one style tuned for *comparing*, not reading: the reviewer holds this
  /// against the handwriting on the page beside it and has to spot a single
  /// wrong character. So it is a step larger than body text and carries the
  /// app's only positive tracking -- separating the glyphs slightly makes each
  /// one an object to check rather than part of a word to skim.
  final TextStyle recognizedText;

  /// 採点コメント。Prose a student will read on the returned sheet, so it is
  /// set for comfortable reading and never condensed to fit a panel.
  final TextStyle gradingComment;

  /// 点数。
  ///
  /// The digits are the content, so they are large and the surrounding `/ 5 点`
  /// is carried by the same style rather than competing with it. Noto Sans JP's
  /// digits are already uniform-width, so a score never shifts as it changes --
  /// see this library's doc.
  final TextStyle score;

  /// A field label, a chip, a button: text that names a control rather than
  /// saying anything itself. Tight leading, since it is one line by design.
  final TextStyle uiLabel;

  /// Derives the roles from [textTheme], so the scale stays the single source
  /// of sizes and only the deliberate deviations are written out.
  factory AppTextRoles.from(TextTheme textTheme) {
    return AppTextRoles(
      questionText: textTheme.bodyLarge!,
      recognizedText: textTheme.bodyLarge!.copyWith(
        // One step above `bodyLarge`'s 16, and the app's only positive
        // tracking -- see this field's doc.
        fontSize: 17,
        letterSpacing: 0.5,
      ),
      gradingComment: textTheme.bodyMedium!,
      score: textTheme.headlineSmall!,
      uiLabel: textTheme.labelLarge!,
    );
  }

  @override
  AppTextRoles copyWith({
    TextStyle? questionText,
    TextStyle? recognizedText,
    TextStyle? gradingComment,
    TextStyle? score,
    TextStyle? uiLabel,
  }) {
    return AppTextRoles(
      questionText: questionText ?? this.questionText,
      recognizedText: recognizedText ?? this.recognizedText,
      gradingComment: gradingComment ?? this.gradingComment,
      score: score ?? this.score,
      uiLabel: uiLabel ?? this.uiLabel,
    );
  }

  @override
  AppTextRoles lerp(ThemeExtension<AppTextRoles>? other, double t) {
    if (other is! AppTextRoles) return this;
    return AppTextRoles(
      questionText: TextStyle.lerp(questionText, other.questionText, t)!,
      recognizedText: TextStyle.lerp(recognizedText, other.recognizedText, t)!,
      gradingComment: TextStyle.lerp(gradingComment, other.gradingComment, t)!,
      score: TextStyle.lerp(score, other.score, t)!,
      uiLabel: TextStyle.lerp(uiLabel, other.uiLabel, t)!,
    );
  }
}
