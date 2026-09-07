/// Where the Python sidecar executable lives, for the two ways this app ever
/// runs: installed on a user's machine, and `flutter run` in a checkout.
///
/// Pure string work with every environment value passed in, so the installed
/// Windows layout is verifiable from a Linux `flutter test` run (`AGENTS.md`:
/// inject the filesystem from outside the core).
library;

/// Directory the installer places the PyInstaller onedir tree in, beside the
/// Flutter executable (`docs/windows-distribution.md` §2).
///
/// Beside the executable rather than inside `data/`: `data/` is Flutter's own
/// (it rewrites `data/flutter_assets/` wholesale on every build), so anything
/// left there is both at risk of being cleaned out and easy to mistake for a
/// build product.
const String sidecarBundleDirectory = 'sidecar';

/// Basename of the frozen sidecar, matching `[project.scripts]` in
/// `backend/pyproject.toml` and the `name=` in
/// `backend/packaging/auto-scoring-sidecar.spec`.
const String sidecarExecutableName = 'auto-scoring-sidecar';

/// Every path the sidecar could be at, best first.
///
/// [resolvedExecutable] is this process's own executable (`Platform
/// .resolvedExecutable`) and [workingDirectory] its CWD (`Directory.current
/// .path`); both are passed in rather than read here so tests can describe a
/// Windows install from any host.
///
/// The installed location comes first because it is the only one that exists
/// on a user's machine, and a developer who has just built an installer
/// locally should still get the bundle they built rather than a stale venv.
/// The two development fallbacks are the same `backend/.venv` console script
/// `app/test/sidecar_api_client_test.dart` already runs, reached from either
/// place `flutter run` is normally invoked (`app/`, or the repository root).
///
/// Deliberately *not* `uv run auto-scoring-sidecar`: on Windows `uv` has no
/// `execve` to hand the process over with, so it stays alive as a parent and
/// the sidecar becomes its grandchild -- killing the process we spawned would
/// then leave the real sidecar running, which is the exact failure this
/// issue's "port/processが残らない" acceptance criterion is about.
List<String> sidecarExecutableCandidates({
  required String resolvedExecutable,
  required String workingDirectory,
  required bool isWindows,
}) {
  final separator = isWindows ? r'\' : '/';
  final suffix = isWindows ? '.exe' : '';
  final venvBinDirectory = isWindows ? 'Scripts' : 'bin';

  String join(List<String> segments) => segments.join(separator);

  String venvCandidate(String backendRoot) => join([
    backendRoot,
    'backend',
    '.venv',
    venvBinDirectory,
    '$sidecarExecutableName$suffix',
  ]);

  return [
    join([
      _parentDirectory(resolvedExecutable),
      sidecarBundleDirectory,
      '$sidecarExecutableName$suffix',
    ]),
    venvCandidate(_parentDirectory(workingDirectory)),
    venvCandidate(workingDirectory),
  ];
}

/// The first of [candidates] that [exists] accepts, or `null` when the sidecar
/// is not installed -- which the supervisor reports as its own failure rather
/// than letting a spawn fail with a bare OS error.
String? resolveSidecarExecutable(
  List<String> candidates, {
  required bool Function(String path) exists,
}) {
  for (final candidate in candidates) {
    if (exists(candidate)) return candidate;
  }
  return null;
}

/// [path] with its last segment removed, accepting either separator.
///
/// Both are accepted regardless of platform because Windows itself does:
/// `Platform.resolvedExecutable` comes back with backslashes, but a path a
/// developer typed (or that arrived through a tool) can mix them, and taking
/// the last separator of either kind is what the OS would do.
String _parentDirectory(String path) {
  final cut = path.lastIndexOf(RegExp(r'[/\\]'));
  if (cut <= 0) return path;
  return path.substring(0, cut);
}
