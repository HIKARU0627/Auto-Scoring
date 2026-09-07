/// The real [SidecarPlatform]: `dart:io` processes and files, a live HTTP
/// health probe, and the wall clock.
///
/// Everything here is untestable-by-nature glue -- it exists so that
/// `sidecar_supervisor.dart`, which holds all the actual decisions, has
/// nothing platform-specific left in it.
library;

import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/child_process_group.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';

class SidecarPlatformIo implements SidecarPlatform {
  SidecarPlatformIo({ChildProcessGroup? processGroup})
    : _processGroup = processGroup ?? ChildProcessGroup.forCurrentPlatform();

  final ChildProcessGroup _processGroup;

  /// Reused across the poll loop's probes. Rebuilt whenever the connection
  /// changes (a restart mints a new port and token), because each client
  /// pins its base URL and bearer token at construction.
  SidecarApiClient? _probeClient;
  SidecarConnection? _probeConnection;

  @override
  Future<String> createHandshakeFile() async {
    // A fresh directory per attempt, in the OS temp area rather than under
    // `app-data/`:
    //
    // * `%TEMP%` on Windows is `%LOCALAPPDATA%\Temp`, already ACL'd to this
    //   user only, and `createTemp` adds a random name inside it -- so the
    //   file is no more reachable by another user than an `app-data/` one
    //   would be, and it is *not* inside the tree the sidecar serves files
    //   out of.
    // * It holds a live bearer token, so it should not sit in a directory
    //   that deliberately survives restarts. The supervisor deletes it the
    //   moment the token has been read (`docs/windows-distribution.md` §4);
    //   being under `%TEMP%` means even a hard crash between those two
    //   points leaves it somewhere the OS already cleans up.
    //
    // This settles the open question `docs/sidecar-api.md` §3 left for this
    // issue: a file, not an inherited fd. dart:io offers no supported way to
    // pass an extra inherited handle to a child on Windows, and a file the
    // parent creates and deletes needs no such platform-specific plumbing.
    final directory = await Directory.systemTemp.createTemp('auto-scoring-');
    final file = File(
      '${directory.path}${Platform.pathSeparator}handshake.json',
    );
    await file.create();
    return file.path;
  }

  @override
  Future<String?> readHandshakeFile(String path) async {
    final file = File(path);
    try {
      return await file.readAsString();
    } on FileSystemException {
      // Not written yet, or caught mid-write. Both are "try again", which is
      // what returning null means to the supervisor.
      return null;
    }
  }

  @override
  Future<void> deleteHandshakeFile(String path) async {
    // The whole per-attempt directory, not just the file: `createHandshakeFile`
    // made both, so leaving the directory behind would leak one per launch.
    final directory = File(path).parent;
    try {
      await directory.delete(recursive: true);
    } on FileSystemException {
      // Already gone, or held open by something else. Nothing here is worth
      // failing a startup over -- the OS reclaims %TEMP% either way.
    }
  }

  @override
  Future<SidecarProcessHandle> start(
    String executable,
    List<String> arguments,
  ) async {
    final process = await Process.start(executable, arguments);
    // Immediately, so the window in which a crash of *this* process could
    // orphan the sidecar is as short as dart:io allows. (Windows' own
    // airtight answer is CREATE_SUSPENDED + assign + resume, which
    // `Process.start` does not expose; the residual window is the few
    // microseconds between the child being created and this line.)
    _processGroup.adopt(process.pid);
    return _IoSidecarProcess(process);
  }

  @override
  Future<bool> probeHealth(SidecarConnection connection) async {
    if (_probeConnection?.baseUrl != connection.baseUrl ||
        _probeConnection?.token != connection.token) {
      _probeClient?.close();
      _probeConnection = connection;
      // A short timeout: this runs in a poll loop that retries anyway, so
      // waiting out the default 10 seconds would only make the loop blind
      // to the process dying in the meantime.
      _probeClient = SidecarApiClient(
        connection,
        timeout: const Duration(seconds: 2),
      );
    }
    // `isHealthy` never throws -- an unreachable sidecar is false, not an
    // error (see its doc comment).
    return _probeClient!.isHealthy();
  }

  @override
  Future<void> delay(Duration duration) => Future<void>.delayed(duration);

  @override
  DateTime now() => DateTime.now();

  /// Releases the probe client.
  ///
  /// The running app never calls this -- it holds one platform for its whole
  /// life and the OS reclaims the socket on exit. It exists for tests, which
  /// build many supervisors in one process. The job object is deliberately
  /// *not* closed here (see `core/child_process_group.dart`): closing it is
  /// what kills the children.
  void dispose() {
    _probeClient?.close();
    _probeClient = null;
    _probeConnection = null;
  }
}

class _IoSidecarProcess implements SidecarProcessHandle {
  _IoSidecarProcess(this._process) {
    // Drained, not ignored: a child whose stdout/stderr pipe fills up because
    // nobody reads it blocks on its next write. Uvicorn's access log makes
    // that a matter of a few hundred requests, and the symptom would be the
    // sidecar mysteriously hanging partway through a batch of answers.
    _process.stdout.drain<void>().ignore();
    _process.stderr.drain<void>().ignore();
  }

  final Process _process;

  @override
  Future<int> get exitCode => _process.exitCode;

  @override
  void kill() {
    _process.kill();
  }
}
