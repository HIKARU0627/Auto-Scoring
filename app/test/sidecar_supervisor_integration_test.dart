@Tags(['sidecar'])
@Timeout(Duration(minutes: 5))
library;

import 'dart:convert';
import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/sidecar_platform_io.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:flutter_test/flutter_test.dart';

import 'sidecar_keyring_env.dart';
import 'sidecar_probe.dart';

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
    platform = _KeyringSafePlatform();
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
    // And the shutdown test's survivor check says so too. Without this, a
    // `_stillServing` broken to always answer `false` would look fine: every
    // other use of it asserts the negative.
    expect((await sidecarStillServing(connection)).serving, isTrue);
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
    // Recorded before the shutdown, so a failure report below can say whether
    // whatever is answering afterwards is the same process that was.
    final listenerBeforeShutdown = await _listenerPidOn(connection);

    await supervisor.shutdown();
    expect(supervisor.state.value, isA<SidecarStopped>());

    // Our sidecar is gone -- the acceptance criterion
    // "通常終了後にport/processが残らない".
    //
    // Probed rather than checked by re-binding the port: a just-closed
    // listener's port can still be refused by `bind` for a minute or two while
    // connections the health probes opened sit in TIME_WAIT, which says
    // nothing about whether a *process* survived.
    final probe = await sidecarStillServing(connection);
    // Asked of the process directly, not through the port. This is the half of
    // Issue #24's 「通常終了後にport/processが残らない」 that no HTTP answer can
    // stand in for: whatever the port says, the process that was serving must
    // be gone. It costs one `tasklist`/`ps` spawn, so it reads the state a few
    // hundred milliseconds after `shutdown()` returned rather than at the
    // instant it did.
    final serverStillAlive =
        listenerBeforeShutdown != null &&
        await _isAlive(listenerBeforeShutdown);

    if (probe.serving || serverStillAlive) {
      // TEMPORARY (Issue #57): this assertion fails intermittently on the
      // Windows CI runner and only there, so the evidence has to be collected
      // by the run that fails rather than reproduced afterwards.
      // ignore: avoid_print
      print(
        await _survivorReport(
          connection: connection,
          appDataDirectory: '${appData.path}/app-data',
          listenerBeforeShutdown: listenerBeforeShutdown,
          serverStillAlive: serverStillAlive,
          probeDetail: probe.detail,
        ),
      );
    }
    expect(
      serverStillAlive,
      isFalse,
      reason: 'the process that was serving is still running',
    );
    expect(
      probe.serving,
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
    expect((await sidecarStillServing(ours)).serving, isFalse);
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

/// The real [SidecarPlatformIo], except on Linux it spawns the sidecar with
/// [linuxKeyringEnvironment] so `import keyring` cannot stall on D-Bus
/// (Issue #438).
///
/// Only `start` differs, and only on Linux. On Windows it delegates straight to
/// `super.start`, keeping the Job Object adoption (`ChildProcessGroup`) that
/// matters there. The Linux override skips that adoption deliberately:
/// `ChildProcessGroup.forCurrentPlatform()` is a no-op off Windows, so there is
/// nothing to lose.
class _KeyringSafePlatform extends SidecarPlatformIo {
  @override
  Future<SidecarProcessHandle> start(
    String executable,
    List<String> arguments,
  ) {
    if (!Platform.isLinux) return super.start(executable, arguments);
    return Process.start(
      executable,
      arguments,
      environment: linuxKeyringEnvironment,
    ).then(_KeyringSidecarProcess.new);
  }
}

/// [SidecarProcessHandle] for the Linux spawn above. Mirrors the private
/// `_IoSidecarProcess` in `sidecar_platform_io.dart`; the draining is what
/// keeps a chatty uvicorn from blocking on a full pipe.
class _KeyringSidecarProcess implements SidecarProcessHandle {
  _KeyringSidecarProcess(this._process) {
    _process.stdout.drain<void>().ignore();
    _process.stderr.drain<void>().ignore();
  }

  final Process _process;

  @override
  Future<int> get exitCode => _process.exitCode;

  @override
  void kill() => _process.kill();
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

SidecarFailure? supervisorFailureOf(SidecarSupervisor supervisor) =>
    switch (supervisor.state.value) {
      SidecarFailed(:final failure) => failure,
      _ => null,
    };

/// The process id listening on [connection]'s port, or `null` if nothing is.
Future<String?> _listenerPidOn(SidecarConnection connection) async {
  final port = Uri.parse(connection.baseUrl).port;
  if (Platform.isWindows) {
    // `netstat` rather than a PowerShell one-liner: available on every Windows
    // image without an execution-policy question.
    final netstat = await Process.run('netstat', ['-ano', '-p', 'TCP']);
    final line = const LineSplitter()
        .convert(netstat.stdout as String)
        .firstWhere(
          (l) => l.contains(':$port ') && l.contains('LISTENING'),
          orElse: () => '',
        );
    return line.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).lastOrNull;
  }
  final ss = await Process.run('bash', [
    '-c',
    "ss -ltnpH 'sport = :$port' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2",
  ]);
  final pid = (ss.stdout as String).trim();
  return pid.isEmpty ? null : pid;
}

/// Terminates whatever process is listening on [connection]'s port, without
/// going through the supervisor.
Future<void> _killListenerOn(SidecarConnection connection) async {
  final pid = await _listenerPidOn(connection);
  final port = Uri.parse(connection.baseUrl).port;
  expect(pid, isNotNull, reason: 'no listener found on port $port');
  await Process.run(
    Platform.isWindows ? 'taskkill' : 'kill',
    Platform.isWindows ? ['/F', '/PID', pid!] : ['-9', pid!],
  );
}

/// Whether [pid] still names a live process. One spawn, nothing else, because
/// this is the measurement that has to happen before the survivor is gone.
Future<bool> _isAlive(String pid) async {
  if (Platform.isWindows) {
    final result = await Process.run('tasklist', ['/FI', 'PID eq $pid', '/NH']);
    return '${result.stdout}'.contains(pid);
  }
  final result = await Process.run('ps', ['-p', pid, '-o', 'pid=']);
  return result.exitCode == 0 && '${result.stdout}'.trim().isNotEmpty;
}

/// TEMPORARY (Issue #57): everything worth knowing about a sidecar that is
/// still answering after `shutdown()` returned.
///
/// Collected here rather than reproduced by a separate script because the
/// failure is intermittent and Windows-only: only the run that actually fails
/// can say what was alive at that moment. Delete once the cause is settled.
Future<String> _survivorReport({
  required SidecarConnection connection,
  required String appDataDirectory,
  required String? listenerBeforeShutdown,
  required bool serverStillAlive,
  required String probeDetail,
}) async {
  final port = Uri.parse(connection.baseUrl).port;
  final report = StringBuffer()
    ..writeln('=== Issue #57: something answered after shutdown ===')
    ..writeln('port: $port')
    ..writeln('app-data: $appDataDirectory')
    ..writeln('listener pid before shutdown: ${listenerBeforeShutdown ?? "-"}')
    ..writeln('what the probe that returned true saw: $probeDetail');

  // Measured by the caller, before any of the slower collection below: a
  // survivor that only outlives the shutdown briefly would already be gone by
  // the time the snapshot at the end runs, so an empty snapshot there does not
  // mean nobody was there when the check ran.
  report.writeln(
    'was that pid still alive when checked? ${serverStillAlive ? "yes" : "no"}',
  );

  // What the protected call actually got back. `_stillServing` only sees
  // "threw or did not", and dio's default validateStatus accepts any 2xx --
  // so an empty 204 would read as alive just as a full 200 would.
  try {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    final request =
        await client.getUrl(Uri.parse('${connection.baseUrl}/tests'))
          ..headers.set('Authorization', 'Bearer ${connection.token}');
    final response = await request.close();
    final body = await response.transform(const Utf8Decoder()).join();
    report
      ..writeln('GET /tests with this session token -> ${response.statusCode}')
      ..writeln('  content-type: ${response.headers.contentType}')
      ..writeln(
        '  body: ${body.length > 500 ? "${body.substring(0, 500)}..." : body}',
      );
    client.close();
  } on Object catch (error) {
    report.writeln('GET /tests with this session token -> $error');
  }

  report.writeln(
    'listener pid now: ${await _listenerPidOn(connection) ?? "-"}',
  );
  report.write(await _processSnapshot(port, appDataDirectory));
  return report.toString();
}

/// Who owns [port], and every process whose command line names
/// [appDataDirectory] -- which is unique to this test, so it picks out exactly
/// the chain this supervisor started, however many processes deep it goes.
Future<String> _processSnapshot(int port, String appDataDirectory) async {
  try {
    if (Platform.isWindows) {
      // `$` is escaped throughout: this is a PowerShell script, and the only
      // two values Dart fills in are the port and the marker.
      final script =
          """
\$port = $port
\$marker = '${appDataDirectory.replaceAll("'", "''")}'
Write-Output '--- listeners on the port ---'
Get-NetTCPConnection -LocalPort \$port -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object {
    \$owner = Get-CimInstance Win32_Process -Filter "ProcessId = \$(\$_.OwningProcess)" -ErrorAction SilentlyContinue
    "pid \$(\$_.OwningProcess) \$(\$owner.Name) :: \$(\$owner.CommandLine)"
  }
Write-Output '--- processes started for this test app-data ---'
Get-CimInstance Win32_Process |
  Where-Object { \$_.CommandLine -and \$_.CommandLine.Contains(\$marker) -and \$_.ProcessId -ne \$PID } |
  ForEach-Object { "pid \$(\$_.ProcessId) parent \$(\$_.ParentProcessId) \$(\$_.Name) :: \$(\$_.CommandLine)" }
Write-Output '--- every sidecar-looking process ---'
Get-CimInstance Win32_Process |
  Where-Object { \$_.Name -match 'python|auto-scoring' } |
  ForEach-Object { "pid \$(\$_.ProcessId) parent \$(\$_.ParentProcessId) \$(\$_.Name) :: \$(\$_.CommandLine)" }
""";
      final result = await Process.run('powershell', [
        '-NoProfile',
        '-Command',
        script,
      ]);
      return '${result.stdout}${result.stderr}';
    }
    final result = await Process.run('bash', [
      '-c',
      "echo '--- listeners on the port ---'; ss -ltnp 'sport = :$port'; "
          "echo '--- processes for this app-data ---'; "
          'ps -eo pid,ppid,args | grep -F "$appDataDirectory" | grep -v grep',
    ]);
    return '${result.stdout}${result.stderr}';
  } on Object catch (error) {
    return 'process snapshot failed: $error\n';
  }
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
