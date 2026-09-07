/// Process supervision for the Python sidecar: spawn it, wait for it to be
/// reachable, notice when it dies, restart it, and kill it on the way out.
///
/// This is the "future work" `app_dependencies.dart` referred to and
/// `docs/technology-stack.md` §1.2 specified. Every boundary it touches --
/// spawning, the filesystem, the network probe, the clock -- arrives through
/// [SidecarPlatform] (`AGENTS.md`: "Inject boundaries (DB, clock, randomness,
/// network, filesystem) from outside the core"), so the whole state machine
/// runs on any OS in a plain `flutter test`, including the Windows-only paths.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// How long a sidecar gets to go from "spawned" to "answering `/healthz`"
/// before the supervisor gives up, kills it, and offers a retry.
///
/// Generous because the first launch on a machine is the slow one: the
/// sidecar runs every Alembic migration against a brand-new database, and
/// Windows Defender scans a freshly installed, unsigned executable tree
/// on its first execution. `app/test/sidecar_api_client_test.dart` records
/// startups approaching a minute from exactly that combination on GitHub's
/// hosted Windows runners. A sidecar that fails *outright* does not wait
/// this out -- [SidecarSupervisor] watches for the process exiting and
/// reports that immediately.
const Duration sidecarStartupTimeout = Duration(seconds: 60);

/// Gap between handshake reads / health probes while waiting for startup.
const Duration sidecarStartupPollInterval = Duration(milliseconds: 250);

/// Exit code `auto_scoring.api.sidecar.ALREADY_RUNNING_EXIT_CODE` uses for
/// "another live process already owns this app-data directory". Kept in sync
/// by `backend/tests/test_sidecar.py` and this file's own test.
const int sidecarAlreadyRunningExitCode = 3;

/// Why a sidecar is not available.
enum SidecarFailure {
  /// No sidecar executable at any known path: a broken install, or a
  /// checkout where `uv sync` has never run.
  executableMissing,

  /// The sidecar refused to start because another instance already owns the
  /// app-data directory -- i.e. the app is already running (Issue #24:
  /// 二重起動). The one failure the user can fix themselves.
  alreadyRunning,

  /// The process exited on its own before it ever became reachable.
  exitedDuringStartup,

  /// The process stayed alive but never answered `/healthz` in time.
  startupTimedOut,

  /// The process exited *after* it had been serving requests
  /// (simplified-design-specification.md §24).
  crashed,
}

/// What the UI renders (`features/startup/startup_gate.dart`).
sealed class SidecarState {
  const SidecarState();
}

/// Spawning, or waiting for the handshake and the first healthy probe. The
/// splash screen's state.
final class SidecarStarting extends SidecarState {
  const SidecarStarting();
}

/// Reachable. [connection] is what the composition root builds the real
/// [SidecarApiClient] from.
final class SidecarReady extends SidecarState {
  const SidecarReady(this.connection);

  final SidecarConnection connection;
}

/// Not available, and not coming back without [SidecarSupervisor.start] being
/// called again (the 再起動 button of simplified-design-specification.md §24).
final class SidecarFailed extends SidecarState {
  const SidecarFailed(this.failure, {this.exitCode});

  final SidecarFailure failure;

  /// The process's exit code, when there was a process that exited.
  final int? exitCode;
}

/// Shut down on purpose, on the way out of the app.
final class SidecarStopped extends SidecarState {
  const SidecarStopped();
}

/// A spawned child process, narrowed to what supervision actually needs.
abstract interface class SidecarProcessHandle {
  /// Completes with the process's exit code once it has exited.
  Future<int> get exitCode;

  /// Asks the OS to terminate the process. Safe to call after it has already
  /// exited.
  void kill();
}

/// Everything outside the supervisor's own state machine.
///
/// One interface rather than half a dozen injected closures: these calls are
/// a single collaborator (the operating system) and are always faked
/// together.
abstract interface class SidecarPlatform {
  /// Creates a fresh, empty file for one launch's handshake and returns its
  /// path. Each attempt gets its own, so a previous attempt's stale contents
  /// can never be mistaken for this one's.
  Future<String> createHandshakeFile();

  /// The contents of the handshake file, or `null` if it does not exist yet.
  Future<String?> readHandshakeFile(String path);

  /// Removes the handshake file (and anything created alongside it).
  Future<void> deleteHandshakeFile(String path);

  /// Spawns [executable]. Throws if it cannot be started.
  Future<SidecarProcessHandle> start(String executable, List<String> arguments);

  /// Whether the sidecar at [connection] answers its health endpoint.
  Future<bool> probeHealth(SidecarConnection connection);

  /// Waits [duration]. Injected so tests advance time instead of spending it.
  Future<void> delay(Duration duration);

  /// Now, by the same clock [delay] advances.
  DateTime now();
}

/// Owns the sidecar process for the lifetime of the app.
///
/// Not a singleton and not self-starting: `main.dart` constructs exactly one,
/// and the startup gate drives it.
class SidecarSupervisor {
  SidecarSupervisor({
    required SidecarPlatform platform,
    required String? executablePath,
    String? appDataDirectory,
    Duration startupTimeout = sidecarStartupTimeout,
    Duration pollInterval = sidecarStartupPollInterval,
  }) : _platform = platform,
       _executablePath = executablePath,
       _appDataDirectory = appDataDirectory,
       _startupTimeout = startupTimeout,
       _pollInterval = pollInterval;

  final SidecarPlatform _platform;

  /// `null` when `resolveSidecarExecutable` found nothing -- reported as
  /// [SidecarFailure.executableMissing] on [start] rather than thrown at
  /// construction, so a broken install still renders the app's own error
  /// screen instead of a crash before `runApp`.
  final String? _executablePath;

  /// Passed through as `--app-data-dir`, or omitted so the sidecar applies
  /// its own per-user default.
  ///
  /// Omitted in production on purpose: `auto_scoring.api.sidecar
  /// .default_app_data_dir` is the single definition of where a user's data
  /// lives, and reimplementing `%LOCALAPPDATA%` resolution here in Dart would
  /// give the same installed app two answers that could drift apart
  /// (`docs/windows-distribution.md` §3).
  final String? _appDataDirectory;

  final Duration _startupTimeout;
  final Duration _pollInterval;

  final ValueNotifier<SidecarState> _state = ValueNotifier<SidecarState>(
    const SidecarStarting(),
  );

  /// The current state. `features` listens to this; nothing else writes it.
  ValueListenable<SidecarState> get state => _state;

  SidecarProcessHandle? _process;

  /// Bumped by every [start] and [shutdown]. An attempt (or an exit callback)
  /// that no longer matches has been superseded -- by a restart, or by the
  /// app closing -- and must not write state or kill a process it no longer
  /// owns. Cheaper and harder to get wrong than cancelling the individual
  /// futures involved.
  int _generation = 0;

  /// Starts the sidecar, replacing any process already running. Also the
  /// restart path (§24's 再起動ボタン): a restart is just another start.
  ///
  /// Returns when the sidecar is ready or has failed; the caller normally
  /// watches [state] rather than awaiting this.
  Future<void> start() async {
    await _terminateCurrentProcess();
    final generation = ++_generation;
    _state.value = const SidecarStarting();
    await _attempt(generation);
  }

  /// Kills the sidecar and stops supervising it. Called when the app is
  /// closing (`features/startup/startup_gate.dart`'s `didRequestAppExit`).
  ///
  /// On Windows this is belt and braces: [SidecarPlatform] also enrols the
  /// child in a Job Object that the OS tears down even when this app is
  /// killed outright and never reaches this method
  /// (`core/child_process_group.dart`).
  Future<void> shutdown() async {
    _generation++;
    await _terminateCurrentProcess();
    _state.value = const SidecarStopped();
  }

  void dispose() {
    _state.dispose();
  }

  Future<void> _attempt(int generation) async {
    final executable = _executablePath;
    if (executable == null) {
      _fail(generation, SidecarFailure.executableMissing);
      return;
    }

    final handshakePath = await _platform.createHandshakeFile();
    final SidecarProcessHandle process;
    try {
      process = await _platform.start(executable, [
        // The sidecar picks the port itself and reports it back; asking for
        // 0 explicitly rather than relying on its default keeps the contract
        // visible at the call site (docs/sidecar-api.md §1).
        '--port', '0',
        '--handshake-file', handshakePath,
        if (_appDataDirectory case final directory?) ...[
          '--app-data-dir',
          directory,
        ],
      ]);
    } on Object {
      await _platform.deleteHandshakeFile(handshakePath);
      _fail(generation, SidecarFailure.executableMissing);
      return;
    }

    if (generation != _generation) {
      // Superseded while the spawn was in flight. Nothing else knows about
      // this process, so it has to be cleaned up here or it leaks.
      process.kill();
      await _platform.deleteHandshakeFile(handshakePath);
      return;
    }
    _process = process;

    int? exitCode;
    unawaited(process.exitCode.then((code) => exitCode = code));

    final deadline = _platform.now().add(_startupTimeout);
    SidecarConnection? connection;
    while (true) {
      if (generation != _generation) return;

      if (exitCode case final code?) {
        // Died on its own. Reported immediately rather than waiting out the
        // startup timeout -- there is nothing left to wait for.
        await _platform.deleteHandshakeFile(handshakePath);
        _fail(
          generation,
          code == sidecarAlreadyRunningExitCode
              ? SidecarFailure.alreadyRunning
              : SidecarFailure.exitedDuringStartup,
          exitCode: code,
        );
        return;
      }

      connection ??= await _readConnection(handshakePath);
      if (connection != null && await _platform.probeHealth(connection)) break;

      if (!_platform.now().isBefore(deadline)) {
        process.kill();
        await process.exitCode;
        await _platform.deleteHandshakeFile(handshakePath);
        _fail(generation, SidecarFailure.startupTimedOut);
        return;
      }
      await _platform.delay(_pollInterval);
    }

    // The token has been read into memory; it does not need to stay on disk
    // for the rest of the session (docs/windows-distribution.md §4).
    await _platform.deleteHandshakeFile(handshakePath);
    if (generation != _generation) return;

    _state.value = SidecarReady(connection);
    unawaited(
      process.exitCode.then((code) {
        if (generation != _generation) return; // restarted, or app closing
        _fail(generation, SidecarFailure.crashed, exitCode: code);
      }),
    );
  }

  /// The handshake, or `null` if it is not readable *yet*.
  ///
  /// "Yet" is the whole point: the file is created empty by
  /// [SidecarPlatform.createHandshakeFile] and filled in by a different
  /// process, so between those two moments a read returns an empty or partial
  /// string. Success is therefore "parsed into a complete host/port/token",
  /// never "the file exists" -- anything short of that is indistinguishable
  /// from "not written yet" and is retried.
  Future<SidecarConnection?> _readConnection(String path) async {
    final contents = await _platform.readHandshakeFile(path);
    if (contents == null || contents.trim().isEmpty) return null;

    final Object? decoded;
    try {
      decoded = jsonDecode(contents);
    } on FormatException {
      return null;
    }
    if (decoded is! Map) return null;

    final host = decoded['host'];
    final port = decoded['port'];
    final token = decoded['token'];
    if (host is! String || port is! int || token is! String) return null;
    if (host.isEmpty || token.isEmpty) return null;

    return SidecarConnection(baseUrl: 'http://$host:$port', token: token);
  }

  void _fail(int generation, SidecarFailure failure, {int? exitCode}) {
    if (generation != _generation) return;
    _process = null;
    _state.value = SidecarFailed(failure, exitCode: exitCode);
  }

  Future<void> _terminateCurrentProcess() async {
    final process = _process;
    _process = null;
    if (process == null) return;
    // A hard kill, not a graceful signal: `Process.kill` is `TerminateProcess`
    // on Windows regardless of the signal asked for, so there is no graceful
    // path to prefer there. Safe because every write the sidecar makes is
    // already crash-safe -- SQLite in WAL mode, `os.replace`-based atomic file
    // writes, and a startup repair sweep for anything caught in between
    // (`adapters/local_storage.py`, `api/app.py`).
    process.kill();
    await process.exitCode;
  }
}
