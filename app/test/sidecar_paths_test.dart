import 'package:auto_scoring_app/core/sidecar_paths.dart';
import 'package:flutter_test/flutter_test.dart';

/// The installed Windows layout is what actually has to be right, and it is
/// the one layout a Linux CI runner cannot observe -- so every value it
/// depends on is passed in and asserted here instead.
void main() {
  group('on Windows', () {
    List<String> candidates({
      String resolvedExecutable =
          r'C:\Program Files\Auto-Scoring\auto_scoring_app.exe',
      String workingDirectory = r'C:\repo\app',
    }) => sidecarExecutableCandidates(
      resolvedExecutable: resolvedExecutable,
      workingDirectory: workingDirectory,
      isWindows: true,
    );

    test('prefers the bundle the installer wrote beside the app', () {
      expect(
        candidates().first,
        r'C:\Program Files\Auto-Scoring\sidecar\auto-scoring-sidecar.exe',
      );
    });

    test(
      'falls back to the venv console script from app/ and from the root',
      () {
        expect(candidates().skip(1), [
          r'C:\repo\backend\.venv\Scripts\auto-scoring-sidecar.exe',
          r'C:\repo\app\backend\.venv\Scripts\auto-scoring-sidecar.exe',
        ]);
      },
    );
  });

  group('on POSIX', () {
    List<String> candidates() => sidecarExecutableCandidates(
      resolvedExecutable: '/opt/auto-scoring/auto_scoring_app',
      workingDirectory: '/repo/app',
      isWindows: false,
    );

    test('uses no .exe suffix and the bin/ venv layout', () {
      expect(candidates(), [
        '/opt/auto-scoring/sidecar/auto-scoring-sidecar',
        '/repo/backend/.venv/bin/auto-scoring-sidecar',
        '/repo/app/backend/.venv/bin/auto-scoring-sidecar',
      ]);
    });
  });

  test('resolves to the first candidate that exists', () {
    const installed = '/opt/app/sidecar/auto-scoring-sidecar';
    const venv = '/repo/backend/.venv/bin/auto-scoring-sidecar';

    expect(
      resolveSidecarExecutable([installed, venv], exists: (p) => p == venv),
      venv,
    );
    expect(
      resolveSidecarExecutable([installed, venv], exists: (_) => true),
      installed,
    );
  });

  test('resolves to null when the sidecar is not installed', () {
    // Reported as `SidecarFailure.executableMissing` rather than crashing on
    // a spawn, so a broken install still renders the app's error screen.
    expect(
      resolveSidecarExecutable(const ['/a', '/b'], exists: (_) => false),
      isNull,
    );
  });

  test('the bundle directory matches what the installer script writes', () {
    // `installer/auto-scoring.iss` copies the PyInstaller onedir tree into
    // this subdirectory; nothing else connects the two.
    expect(sidecarBundleDirectory, 'sidecar');
    expect(sidecarExecutableName, 'auto-scoring-sidecar');
  });
}
