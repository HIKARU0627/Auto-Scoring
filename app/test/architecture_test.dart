import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Enforces the app dependency direction `features -> core -> api`
/// (see `AGENTS.md` "Architecture", `docs/technology-stack.md` §5).
///
/// A layer may import layers to its right, never to its left.
void main() {
  /// Every `package:auto_scoring_app/...` import found under `lib/<layer>/`.
  List<({String file, String target})> importsFrom(String layer) {
    final dir = Directory('lib/$layer');
    if (!dir.existsSync()) return const [];
    final pattern = RegExp(
      r'''import\s+['"](package:auto_scoring_app/[^'"]+)['"]''',
    );
    return [
      for (final file in dir.listSync(recursive: true).whereType<File>())
        if (file.path.endsWith('.dart'))
          for (final line in file.readAsLinesSync())
            if (pattern.firstMatch(line) case final m?)
              (file: file.path, target: m.group(1)!),
    ];
  }

  bool targets(({String file, String target}) edge, String layer) =>
      edge.target.startsWith('package:auto_scoring_app/$layer/');

  test('api layer imports neither core nor features', () {
    final bad = importsFrom(
      'api',
    ).where((e) => targets(e, 'core') || targets(e, 'features')).toList();
    expect(bad, isEmpty, reason: 'api must be self-contained: $bad');
  });

  test('core layer does not import features', () {
    final bad = importsFrom(
      'core',
    ).where((e) => targets(e, 'features')).toList();
    expect(bad, isEmpty, reason: 'core must not depend on features: $bad');
  });
}
