import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/design/app_typography.dart';

/// Checks the two properties the typography tokens are *chosen* for, against
/// the real font file rather than against the assumption that it has them
/// (Issue #67, `docs/design-tokens.md` §2).
///
/// `flutter test` renders everything in Ahem -- a test font where every glyph
/// is the same square -- so the bundled font has to be loaded explicitly here.
/// Nothing else in the suite does that, which is exactly why these two facts
/// need their own test: no other test could catch the font being swapped for
/// one that fails them.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    final bytes = await File(
      'assets/fonts/NotoSansJP-VariableFont_wght.ttf',
    ).readAsBytes();
    await (FontLoader(
      appFontFamily,
    )..addFont(Future.value(ByteData.sublistView(bytes)))).load();
  });

  double widthOf(String text, {FontWeight weight = FontWeight.w400}) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          fontFamily: appFontFamily,
          fontSize: 40,
          fontWeight: weight,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    return painter.width;
  }

  test('the bundled file is still the whole variable font', () {
    // The two ways this font could silently stop doing its job, both of which
    // look like a harmless size optimisation in a diff:
    //
    // 1. **Subsetting.** The app displays whatever OCR read off a handwritten
    //    answer -- which kanji appear cannot be known in advance. A subset
    //    turns a rare one into tofu (□), and that is not a cosmetic problem:
    //    the screen would be showing a *different character* than the student
    //    wrote, in the one place a reviewer is checking character by character.
    // 2. **Swapping in a static instance.** One weight is ~5.5 MB against this
    //    file's 9.1 MB, so it looks like a saving -- but it flattens every
    //    weight in the type scale, and three static weights are *bigger*
    //    (~16.5 MB) than the whole axis is here.
    //
    // Both are caught by reading the font's own table directory, so neither
    // depends on the test renderer having the font loaded.
    final bytes = File(
      'assets/fonts/NotoSansJP-VariableFont_wght.ttf',
    ).readAsBytesSync();
    final tables = _sfntTableOffsets(bytes);

    expect(
      tables.keys,
      contains('fvar'),
      reason: 'no fvar table: this is a static instance, not the variable font',
    );
    // `maxp.numGlyphs` is a uint16 four bytes into the table. The upstream
    // file carries 17936 glyphs (JIS X 0208/0213 + 人名用漢字 + 互換漢字);
    // any real subset drops far below this.
    final numGlyphs = ByteData.sublistView(
      bytes,
    ).getUint16(tables['maxp']! + 4);
    expect(
      numGlyphs,
      greaterThanOrEqualTo(17000),
      reason: 'only $numGlyphs glyphs -- the font has been subset',
    );
  });

  test('digits are all one width, so a score never shifts as it changes', () {
    // 点数 is shown as `12 / 20 点` and updates in place when the reviewer
    // edits it. With proportional digits the whole line would jump sideways
    // between `1` and `8`. Noto Sans JP is uniform-width by construction and
    // ships no `tnum` feature, so this is the property being relied on -- a
    // font swap that loses it (BIZ UDPGothic, for one) has to be caught here.
    for (final weight in [FontWeight.w400, FontWeight.w500, FontWeight.w700]) {
      final widths = {
        for (final digit in '0123456789'.split(''))
          digit: widthOf(digit, weight: weight),
      };
      expect(
        widths.values.toSet(),
        hasLength(1),
        reason: 'digit advances differ at $weight: $widths',
      );
    }
  });

  test('fontWeight drives the variable font, so weights are real', () {
    // One file covers 100..900 on the `wght` axis. If Flutter did not map
    // `fontWeight` onto that axis, every weight would render identically (and
    // bold would be a synthesised smear), which would quietly flatten the
    // whole type scale -- `titleMedium` and `bodyMedium` are the same size and
    // differ only by weight.
    //
    // Measured on Latin, not Japanese: a kana/kanji glyph keeps its full-width
    // advance at every weight (that is what makes Japanese set evenly), so its
    // width says nothing about whether the axis was applied. Latin advances do
    // grow with weight.
    const sample = 'Auto-Scoring';
    final regular = widthOf(sample);
    final medium = widthOf(sample, weight: FontWeight.w500);
    final bold = widthOf(sample, weight: FontWeight.w700);
    expect(medium, greaterThan(regular));
    expect(bold, greaterThan(medium));
  });

  test('every text role comes from the bundled family', () {
    for (final theme in [AppTheme.light(), AppTheme.dark()]) {
      final roles = theme.extension<AppTextRoles>();
      expect(roles, isNotNull);
      final styles = [
        roles!.questionText,
        roles.recognizedText,
        roles.gradingComment,
        roles.score,
        roles.uiLabel,
        theme.textTheme.bodyMedium!,
        theme.textTheme.labelLarge!,
      ];
      for (final style in styles) {
        expect(style.fontFamily, appFontFamily);
        // A Latin-tuned `height` is what makes stacked Japanese lines collide.
        expect(style.height, isNotNull);
      }
    }
  });

  test('認識文字 is set apart from ordinary reading text', () {
    // The role exists to be *compared* against handwriting character by
    // character, so it is larger and tracked out; if it ever collapses back
    // onto `bodyLarge` the role has stopped meaning anything.
    final roles = AppTheme.light().extension<AppTextRoles>()!;
    final body = AppTheme.light().textTheme.bodyLarge!;
    expect(roles.recognizedText.fontSize, greaterThan(body.fontSize!));
    expect(roles.recognizedText.letterSpacing, greaterThan(0));
    expect(
      roles.gradingComment.letterSpacing,
      0,
      reason: 'Latin tracking opens gaps inside a Japanese word',
    );
  });
}

/// Table tag -> byte offset, from an sfnt (TrueType/OpenType) table directory:
/// a 12-byte header whose 5th and 6th bytes are the table count, then one
/// 16-byte record per table (4-byte tag, checksum, offset, length).
Map<String, int> _sfntTableOffsets(Uint8List bytes) {
  final data = ByteData.sublistView(bytes);
  final tableCount = data.getUint16(4);
  return {
    for (var i = 0; i < tableCount; i++)
      String.fromCharCodes(bytes, 12 + i * 16, 12 + i * 16 + 4): data.getUint32(
        12 + i * 16 + 8,
      ),
  };
}
