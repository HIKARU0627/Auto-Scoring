import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Keeps the design tokens the single source of dimensions (Issue #67
/// acceptance: 「マジックナンバー(余白・角丸・色のリテラル)が画面コードから
/// 消えている」).
///
/// A screen that writes `EdgeInsets.all(24)` is not wrong on its own -- it is
/// wrong three screens later, when the next one writes 20 and nobody can say
/// which was intended. Same rule as `architecture_test.dart`: the convention is
/// only real if something checks it.
///
/// The properties below are the ones a token exists for. Anything else a
/// widget takes a number for (`maxLines`, `flex`, `strokeWidth`) is a property
/// of that one widget, not a shared decision, and is left alone.
void main() {
  final patterns = <String, RegExp>{
    'padding/margin literal (use AppSpacing)': RegExp(
      r'EdgeInsets\.(all|symmetric|only|fromLTRB)\([^)]*\d',
    ),
    'gap literal (use AppSpacing)': RegExp(
      r'SizedBox\(\s*(width|height):\s*\d',
    ),
    'corner radius literal (use AppRadius)': RegExp(
      r'(BorderRadius|Radius)\.circular\(\s*\d',
    ),
    'elevation literal (use AppElevation)': RegExp(r'elevation:\s*\d'),
    'icon size literal (use AppIconSize)': RegExp(r'\bsize:\s*\d'),
    'width/height constraint literal (use AppLayout)': RegExp(
      r'\b(maxWidth|minWidth|maxHeight|minHeight):\s*\d',
    ),
    'colour literal (use ColorScheme or AppStatusColors)': RegExp(
      // `\b` matters: `context.statusColors.attention` is the right answer, not
      // a violation of it.
      r'(\bColor\(0x|\bColors\.[a-z])',
    ),
  };

  test('no design-token literals under lib/features', () {
    final offenders = <String>[];
    for (final entity in Directory('lib/features').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final lines = entity.readAsLinesSync();
      for (final (index, line) in lines.indexed) {
        for (final pattern in patterns.entries) {
          if (pattern.value.hasMatch(line)) {
            offenders.add(
              '${entity.path}:${index + 1}: ${pattern.key}\n  ${line.trim()}',
            );
          }
        }
      }
    }
    expect(offenders, isEmpty, reason: offenders.join('\n'));
  });
}
