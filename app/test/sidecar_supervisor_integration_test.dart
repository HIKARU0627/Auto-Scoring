@Tags(['sidecar'])
@Timeout(Duration(minutes: 5))
library;

import 'dart:convert';
import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/sidecar_platform_io.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:flutter_test/flutter_test.dart';

/// Drives the real supervisor against the real Python sidecar: the pieces the
/// unit tests deliberately fake (`Process.start`, the handshake file, the HTTP
/// probe, the Job Object) are exactly the pieces this exercises.
///
/// Covers the three behaviours Issue #24's 検証 section names -- process
/// cleanup, dynamic port, and crash recovery -- against a live process. Tagged
/// `sidecar` like `sidecar_api_client_test.dart`, so `flutter test -x sidecar`
/// still passes on a machine with no `uv`. Runs on the Windows CI runner,
/// which is where the Job Object and `TerminateProcess` paths are real.
///
/// Uses the same `backend/.venv` console script as that file, and for the same
/// reason: `uv run` would leave the sidecar as a surviving grandchild on
/// Windows.
void main() {
  final backendDir = Directory(
    '${Directory.current.path}/../backend',
  ).absolute.path;
  final sidecarExe = Platform.isWindows
      ? '$backendDir/.venv/Scripts/auto-scoring-sidecar.exe'
      : '$backendDir/.venv/bin/auto-scoring-sidecar';

  late Directory appData;
  late SidecarPlatformIo platform;
  late SidecarSupervisor supervisor;

  setUp(() async {
    appData = await Directory.systemTemp.createTemp('supervisor_it_');
    platform = SidecarPlatformIo();
    supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: sidecarExe,
      appDataDirectory: '${appData.path}/app-data',
    );
  });

  tearDown(() async {
    await supervisor.shutdown();
    supervisor.dispose();
    platform.dispose();
    await _deleteWithRetry(appData);
  });

  Future<SidecarConnection> startAndExpectReady() async {
    await supervisor.start();
    final state = supervisor.state.value;
    expect(
      state,
      isA<SidecarReady>(),
      reason: state is SidecarFailed
          ? 'sidecar failed to start: ${state.failure} (exit ${state.exitCode})'
          : 'sidecar did not become ready',
    );
    return (state as SidecarReady).connection;
  }

  test('starts a real sidecar on a dynamic port and reaches it', () async {
    final connection = await startAndExpectReady();

    // Dynamic port: nothing fixed, and it is a real loopback port the
    // supervisor learned from the handshake, not a guess.
    final port = Uri.parse(connection.baseUrl).port;
    expect(port, greaterThan(0));
    expect(Uri.parse(connection.baseUrl).host, '127.0.0.1');
    expect(connection.token, isNotEmpty);

    final client = SidecarApiClient(connection);
    addTearDown(client.close);
    expect(await client.isHealthy(), isTrue);
    // The token really is this session's: a protected call succeeds with it.
    expect(await client.listTests(), isA<List<TestSummary>>());
  });

  test('leaves no handshake file holding the token on disk', () async {
    // Scoped to what appears *during* this test rather than to everything
    // matching under the system temp root: `%TEMP%` is shared with every other
    // process on the machine, so a directory an interrupted earlier run (or a
    // real app session) left behind is not this supervisor's leak.
    final before = _handshakeDirectories();

    await startAndExpectReady();

    // The supervisor deletes the per-attempt temp directory as soon as it has
    // read the token (docs/windows-distribution.md §4), so by the time the
    // sidecar is ready its handshake directory is already gone.
    expect(_handshakeDirectories().difference(before), isEmpty);
  });

  test('shutdown releases the port and the app-data lock', () async {
    final connection = await startAndExpectReady();

    await supervisor.shutdown();
    expect(supervisor.state.value, isA<SidecarStopped>());

    // Our sidecar is gone -- the acceptance criterion
    // "通常終了後にport/processが残らない".
    //
    // Probed rather than checked by re-binding the port: a just-closed
    // listener's port can still be refused by `bind` for a minute or two while
    // connections the health probes opened sit in TIME_WAIT, which says
    // nothing about whether a *process* survived.
    expect(
      await _stillServing(connection),
      isFalse,
      reason: 'the sidecar this session started is still answering',
    );

    // The exclusive app-data lock is released too: a fresh supervisor over the
    // same directory starts cleanly rather than being refused as
    // "already running".
    final second = SidecarSupervisor(
      platform: platform,
      executablePath: sidecarExe,
      appDataDirectory: '${appData.path}/app-data',
    );
    addTearDown(second.dispose);
    await second.start();
    expect(supervisorFailureOf(second), isNull);
    await second.shutdown();
  });

  test('another sidecar holding the port is not read as a survivor', () async {
    // The regression guard for the assertion above. Issue #57's flake was the
    // shutdown check reading a *different* test's sidecar, handed the port
    // ours had just released, as our own survivor. Reproduced here without any
    // timing at all: a stand-in that behaves towards a foreign caller exactly
    // as the real sidecar does -- `/healthz` unauthenticated and answering
    // everyone, every other route rejecting a token it never minted with 401.
    // Both halves of that behaviour are pinned against the real sidecar by
    // `sidecar_api_client_test.dart`.
    //
    // Re-binding the genuinely released port would put the timing back: on
    // Windows `bind` can be refused for minutes while the health probes'
    // connections sit in TIME_WAIT.
    final foreign = await _startForeignSidecar();
    addTearDown(() => foreign.close(force: true));
    final ours = SidecarConnection(
      baseUrl: 'http://127.0.0.1:${foreign.port}',
      token: 'the-token-our-sidecar-had',
    );

    // What the old probe saw, and why it reported a false positive.
    final health = SidecarApiClient(ours);
    addTearDown(health.close);
    expect(await health.isHealthy(), isTrue);

    // What the shutdown test asks instead.
    expect(await _stillServing(ours), isFalse);
  });

  test('a crashed sidecar is reported, and restart recovers', () async {
    final first = await startAndExpectReady();

    // Kill it the way an actual crash would: from outside, with no warning.
    // `Process.run` rather than the supervisor's own kill, so the supervisor
    // learns about it exactly as it would in production.
    await _killListenerOn(first);
    await _waitFor(() => supervisor.state.value is SidecarFailed);

    expect(
      supervisor.state.value,
      isA<SidecarFailed>().having(
        (s) => s.failure,
        'failure',
        SidecarFailure.crashed,
      ),
    );

    // 再起動: a second sidecar over the same app-data, with a fresh port and
    // a fresh token.
    final second = await startAndExpectReady();
    expect(second.token, isNot(first.token));

    final client = SidecarApiClient(second);
    addTearDown(client.close);
    expect(await client.isHealthy(), isTrue);
  });

  test(
    'a second sidecar over the same app-data is refused, not left running',
    () async {
      await startAndExpectReady();

      final second = SidecarSupervisor(
        platform: platform,
        executablePath: sidecarExe,
        appDataDirectory: '${appData.path}/app-data',
        // The refusal is an immediate exit, so this must not need the full
        // startup budget -- that it finishes at all within this timeout is
        // itself the assertion that "exited early" short-circuits the wait.
        startupTimeout: const Duration(seconds: 30),
      );
      addTearDown(second.dispose);

      await second.start();

      expect(
        second.state.value,
        isA<SidecarFailed>().having(
          (s) => s.failure,
          'failure',
          SidecarFailure.alreadyRunning,
        ),
      );
      // The first one is untouched and still serving.
      expect(supervisor.state.value, isA<SidecarReady>());
    },
  );
}

/// Every directory under the system temp root that currently holds a sidecar
/// handshake file.
Set<String> _handshakeDirectories() => Directory.systemTemp
    .listSync()
    .whereType<Directory>()
    .where((d) => d.path.contains('auto-scoring-'))
    .where(
      (d) =>
          File('${d.path}${Platform.pathSeparator}handshake.json').existsSync(),
    )
    .map((d) => d.path)
    .toSet();

/// Stands in for *another* sidecar instance that has been handed the port ours
/// just released, with the only two behaviours [_stillServing] depends on.
Future<HttpServer> _startForeignSidecar() async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    final response = request.response;
    if (request.uri.path == '/healthz') {
      response
        ..headers.contentType = ContentType.json
        ..write('{"status": "ok"}');
    } else {
      response.statusCode = HttpStatus.unauthorized;
    }
    await response.close();
  });
  return server;
}

/// Whether the sidecar that [connection] was minted for is still serving.
///
/// A *protected* call carrying that session's token, deliberately not the
/// `/healthz` probe this used to be (Issue #57). `/healthz` needs no auth, so
/// every sidecar instance answers `{"status": "ok"}` to anyone -- which makes
/// "someone answers on this port" indistinguishable from "our sidecar survived".
/// The token is what tells the port's occupant apart, and it separates all
/// three outcomes:
///
/// * our sidecar is still up -- the token is still valid, so the call succeeds
///   (the leak this file exists to catch);
/// * a *different* sidecar holds the port -- it minted a different token, so
///   the call is refused with 401;
/// * nothing is listening -- the connection is refused.
///
/// So "the protected call did not succeed" is the assertion, and no other
/// test's sidecar can satisfy it on our behalf. That matters because
/// `sidecar_api_client_test.dart` runs its own sidecar concurrently with this
/// file, and Windows hands a just-released ephemeral port straight back out.
Future<bool> _stillServing(SidecarConnection connection) async {
  final client = SidecarApiClient(connection);
  try {
    await client.listTests();
    return true;
  } on SidecarApiException {
    return false;
  } finally {
    client.close();
  }
}

SidecarFailure? supervisorFailureOf(SidecarSupervisor supervisor) =>
    switch (supervisor.state.value) {
      SidecarFailed(:final failure) => failure,
      _ => null,
    };

/// Terminates whatever process is listening on [connection]'s port, without
/// going through the supervisor.
Future<void> _killListenerOn(SidecarConnection connection) async {
  final port = Uri.parse(connection.baseUrl).port;
  if (Platform.isWindows) {
    // `netstat` + `taskkill` rather than a PowerShell one-liner: available on
    // every Windows image without an execution-policy question.
    final netstat = await Process.run('netstat', ['-ano', '-p', 'TCP']);
    final line = const LineSplitter()
        .convert(netstat.stdout as String)
        .firstWhere(
          (l) => l.contains(':$port ') && l.contains('LISTENING'),
          orElse: () => '',
        );
    final pid = line
        .split(RegExp(r'\s+'))
        .where((s) => s.isNotEmpty)
        .lastOrNull;
    expect(pid, isNotNull, reason: 'no listener found on port $port');
    await Process.run('taskkill', ['/F', '/PID', pid!]);
    return;
  }
  final lsof = await Process.run('bash', [
    '-c',
    "ss -ltnpH 'sport = :$port' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2",
  ]);
  final pid = (lsof.stdout as String).trim();
  expect(pid, isNotEmpty, reason: 'no listener found on port $port');
  await Process.run('kill', ['-9', pid]);
}

Future<void> _waitFor(bool Function() condition) async {
  for (var attempt = 0; attempt < 200; attempt++) {
    if (condition()) return;
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
  fail('condition never became true');
}

/// Windows can hold a killed sidecar's SQLite WAL/shm files open for a moment
/// after the process is gone (see `sidecar_api_client_test.dart`).
Future<void> _deleteWithRetry(Directory dir) async {
  for (var attempt = 0; attempt < 10; attempt++) {
    try {
      await dir.delete(recursive: true);
      return;
    } on FileSystemException {
      if (attempt == 9) return; // a leaked temp dir must not fail the suite
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }
}
