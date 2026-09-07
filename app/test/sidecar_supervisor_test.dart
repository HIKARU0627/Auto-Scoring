import 'dart:async';
import 'dart:convert';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:flutter_test/flutter_test.dart';

/// Covers every state transition of the sidecar supervisor against a fake
/// [SidecarPlatform]: startup, the handshake write race, health polling,
/// startup timeout, immediate exit, "already running", crash recovery,
/// restart, and shutdown.
///
/// Nothing here touches a process, a file, a socket, or the wall clock, so
/// the whole Windows-targeted lifecycle is verified on a Linux CI runner --
/// which is the point (`AGENTS.md`: inject the boundaries).
void main() {
  test('reaches ready once the handshake parses and health passes', () async {
    final platform = _FakePlatform();
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    // The realistic ordering: the process is up for a while before it has
    // written anything, then the handshake appears, then it starts serving.
    platform.onPoll = (poll) {
      if (poll == 2) platform.writeHandshake(port: 51234, token: 'tok');
      if (poll >= 4) platform.healthy = true;
    };

    await supervisor.start();

    final state = supervisor.state.value;
    expect(state, isA<SidecarReady>());
    expect(
      (state as SidecarReady).connection.baseUrl,
      'http://127.0.0.1:51234',
    );
    expect(state.connection.token, 'tok');
  });

  test('passes --port 0 and the handshake path it created', () async {
    final platform = _FakePlatform()..healthy = true;
    platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    await supervisor.start();

    expect(platform.spawns.single.executable, '/opt/sidecar');
    expect(platform.spawns.single.arguments, [
      '--port',
      '0',
      '--handshake-file',
      platform.handshakePaths.single,
    ]);
  });

  test(
    'omits --app-data-dir unless one was configured, and passes it when it was',
    () async {
      final platform = _FakePlatform()..healthy = true;
      platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
      final supervisor = SidecarSupervisor(
        platform: platform,
        executablePath: '/opt/sidecar',
        appDataDirectory: r'D:\data',
      );
      addTearDown(supervisor.dispose);

      await supervisor.start();

      expect(
        platform.spawns.single.arguments,
        containsAllInOrder(['--app-data-dir', r'D:\data']),
      );
    },
  );

  group('handshake reading', () {
    // The race the sidecar's own writer creates: `createHandshakeFile` makes
    // the file, and a *different* process fills it in later. Anything short
    // of a complete, parseable object means "not yet", never "give up".
    for (final (name, contents) in [
      ('an empty file', ''),
      ('whitespace only', '   \n'),
      ('a truncated write', '{"host": "127.0.0.1", "po'),
      ('valid JSON that is not an object', '["127.0.0.1", 1234]'),
      ('a missing token', '{"host": "127.0.0.1", "port": 1234}'),
      ('an empty token', '{"host": "127.0.0.1", "port": 1, "token": ""}'),
      (
        'a port that is not a number',
        '{"host": "127.0.0.1", "port": "1234", "token": "t"}',
      ),
    ]) {
      test('retries past $name', () async {
        final platform = _FakePlatform()..handshakeContents = contents;
        final supervisor = _supervisor(platform);
        addTearDown(supervisor.dispose);

        platform.onPoll = (poll) {
          if (poll == 3) {
            platform.writeHandshake(port: 4242, token: 'good');
            platform.healthy = true;
          }
        };

        await supervisor.start();

        expect(supervisor.state.value, isA<SidecarReady>());
        expect(
          (supervisor.state.value as SidecarReady).connection.baseUrl,
          'http://127.0.0.1:4242',
        );
      });
    }
  });

  test('deletes the handshake file once the token has been read', () async {
    final platform = _FakePlatform()..healthy = true;
    platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    await supervisor.start();

    expect(supervisor.state.value, isA<SidecarReady>());
    expect(platform.deletedHandshakePaths, platform.handshakePaths);
  });

  test(
    'fails without spawning anything when no executable was found',
    () async {
      final platform = _FakePlatform();
      final supervisor = SidecarSupervisor(
        platform: platform,
        executablePath: null,
      );
      addTearDown(supervisor.dispose);

      await supervisor.start();

      expect(
        supervisor.state.value,
        isA<SidecarFailed>().having(
          (s) => s.failure,
          'failure',
          SidecarFailure.executableMissing,
        ),
      );
      expect(platform.spawns, isEmpty);
    },
  );

  test('reports a spawn that throws as a missing executable', () async {
    final platform = _FakePlatform()..spawnError = FakeSpawnFailure();
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    await supervisor.start();

    expect(
      supervisor.state.value,
      isA<SidecarFailed>().having(
        (s) => s.failure,
        'failure',
        SidecarFailure.executableMissing,
      ),
    );
    // Even a failed spawn must not leave the temp handshake directory behind.
    expect(platform.deletedHandshakePaths, platform.handshakePaths);
  });

  test('reports an immediate exit without waiting out the timeout', () async {
    final platform = _FakePlatform();
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    platform.onPoll = (poll) {
      if (poll == 1) platform.exitProcess(1);
    };

    await supervisor.start();

    expect(
      supervisor.state.value,
      isA<SidecarFailed>()
          .having(
            (s) => s.failure,
            'failure',
            SidecarFailure.exitedDuringStartup,
          )
          .having((s) => s.exitCode, 'exitCode', 1),
    );
    // The whole point: it gave up in a couple of polls, not 60 seconds of
    // them.
    expect(platform.elapsed, lessThan(const Duration(seconds: 5)));
  });

  test(
    'reports the sidecar refusing a second instance as alreadyRunning',
    () async {
      final platform = _FakePlatform();
      final supervisor = _supervisor(platform);
      addTearDown(supervisor.dispose);

      platform.onPoll = (poll) {
        if (poll == 1) platform.exitProcess(sidecarAlreadyRunningExitCode);
      };

      await supervisor.start();

      expect(
        supervisor.state.value,
        isA<SidecarFailed>().having(
          (s) => s.failure,
          'failure',
          SidecarFailure.alreadyRunning,
        ),
      );
    },
  );

  test('kills a sidecar that never becomes healthy, and times out', () async {
    final platform = _FakePlatform(); // never healthy, never exits
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);
    platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');

    await supervisor.start();

    expect(
      supervisor.state.value,
      isA<SidecarFailed>().having(
        (s) => s.failure,
        'failure',
        SidecarFailure.startupTimedOut,
      ),
    );
    expect(platform.spawns.single.killed, isTrue);
    expect(platform.elapsed, greaterThanOrEqualTo(sidecarStartupTimeout));
    expect(platform.deletedHandshakePaths, platform.handshakePaths);
  });

  test('reports an exit after ready as a crash', () async {
    final platform = _FakePlatform()..healthy = true;
    platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    await supervisor.start();
    expect(supervisor.state.value, isA<SidecarReady>());

    platform.exitProcess(-1);
    await pumpEventQueue();

    expect(
      supervisor.state.value,
      isA<SidecarFailed>()
          .having((s) => s.failure, 'failure', SidecarFailure.crashed)
          .having((s) => s.exitCode, 'exitCode', -1),
    );
  });

  test(
    'restarting after a crash spawns a fresh sidecar and recovers',
    () async {
      final platform = _FakePlatform()..healthy = true;
      platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 'first');
      final supervisor = _supervisor(platform);
      addTearDown(supervisor.dispose);

      await supervisor.start();
      platform.exitProcess(-1);
      await pumpEventQueue();
      expect(supervisor.state.value, isA<SidecarFailed>());

      // The 再起動 button (simplified-design-specification.md §24).
      platform.onPoll = (_) =>
          platform.writeHandshake(port: 2, token: 'second');
      await supervisor.start();

      expect(supervisor.state.value, isA<SidecarReady>());
      expect(
        (supervisor.state.value as SidecarReady).connection.token,
        'second',
      );
      expect(platform.spawns, hasLength(2));
      // Each attempt gets its own handshake file, so a previous attempt's
      // contents can never be read as this one's.
      expect(platform.handshakePaths.toSet(), hasLength(2));
    },
  );

  test(
    'a restart kills the process the previous attempt left running',
    () async {
      final platform = _FakePlatform()..healthy = true;
      platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
      final supervisor = _supervisor(platform);
      addTearDown(supervisor.dispose);

      await supervisor.start();
      await supervisor.start();

      expect(platform.spawns, hasLength(2));
      expect(platform.spawns.first.killed, isTrue);
      expect(platform.spawns.last.killed, isFalse);
    },
  );

  test('shutdown kills the sidecar and stops reporting crashes', () async {
    final platform = _FakePlatform()..healthy = true;
    platform.onPoll = (_) => platform.writeHandshake(port: 1, token: 't');
    final supervisor = _supervisor(platform);
    addTearDown(supervisor.dispose);

    await supervisor.start();
    await supervisor.shutdown();

    expect(supervisor.state.value, isA<SidecarStopped>());
    expect(platform.spawns.single.killed, isTrue);

    // The kill itself completes the exitCode future; a deliberate shutdown
    // must not then be re-reported to the UI as a crash.
    await pumpEventQueue();
    expect(supervisor.state.value, isA<SidecarStopped>());
  });

  test('the exit code shared with the sidecar has not drifted', () {
    // `backend/src/auto_scoring/api/sidecar.py::ALREADY_RUNNING_EXIT_CODE`.
    // The two constants are the whole protocol behind the "already running"
    // error screen, and nothing else would catch them diverging.
    expect(sidecarAlreadyRunningExitCode, 3);
  });
}

SidecarSupervisor _supervisor(_FakePlatform platform) =>
    SidecarSupervisor(platform: platform, executablePath: '/opt/sidecar');

/// Stands in for `Process.start` failing on a path that is not executable.
class FakeSpawnFailure implements Exception {}

class _Spawn {
  _Spawn(this.executable, this.arguments);

  final String executable;
  final List<String> arguments;
  final Completer<int> exit = Completer<int>();
  bool killed = false;
}

class _FakeProcess implements SidecarProcessHandle {
  _FakeProcess(this._spawn);

  final _Spawn _spawn;

  @override
  Future<int> get exitCode => _spawn.exit.future;

  @override
  void kill() {
    _spawn.killed = true;
    if (!_spawn.exit.isCompleted) _spawn.exit.complete(-9);
  }
}

/// An operating system that never sleeps: [delay] advances a counter instead
/// of real time, so a 60-second startup timeout is exercised instantly.
class _FakePlatform implements SidecarPlatform {
  final List<_Spawn> spawns = [];
  final List<String> handshakePaths = [];
  final List<String> deletedHandshakePaths = [];

  /// Contents the handshake file currently has. `null` means "no file yet".
  String? handshakeContents;

  bool healthy = false;
  Object? spawnError;

  /// Called before each poll's `delay`, with the 1-based poll number, so a
  /// test can describe *when* the sidecar reaches each milestone.
  void Function(int poll)? onPoll;

  Duration elapsed = Duration.zero;
  int _polls = 0;
  int _handshakeCounter = 0;

  void writeHandshake({required int port, required String token}) {
    handshakeContents = jsonEncode({
      'host': '127.0.0.1',
      'port': port,
      'token': token,
    });
  }

  void exitProcess(int code) {
    final spawn = spawns.last;
    if (!spawn.exit.isCompleted) spawn.exit.complete(code);
  }

  @override
  Future<String> createHandshakeFile() async {
    handshakeContents = null;
    final path = '/tmp/handshake-${_handshakeCounter++}.json';
    handshakePaths.add(path);
    return path;
  }

  @override
  Future<String?> readHandshakeFile(String path) async => handshakeContents;

  @override
  Future<void> deleteHandshakeFile(String path) async {
    deletedHandshakePaths.add(path);
  }

  @override
  Future<SidecarProcessHandle> start(
    String executable,
    List<String> arguments,
  ) async {
    if (spawnError case final error?) throw error;
    final spawn = _Spawn(executable, arguments);
    spawns.add(spawn);
    return _FakeProcess(spawn);
  }

  @override
  Future<bool> probeHealth(SidecarConnection connection) async => healthy;

  @override
  Future<void> delay(Duration duration) async {
    elapsed += duration;
    onPoll?.call(++_polls);
    // Yields to the event loop so a completed `exitCode` future's listener
    // runs, exactly as a real delay would.
    await Future<void>.delayed(Duration.zero);
  }

  @override
  DateTime now() => DateTime.utc(2026, 1, 1).add(elapsed);
}
