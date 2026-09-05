@Tags(['sidecar'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

/// Boots the real Python sidecar and exercises the boundary against it: an
/// unauthenticated health check, an authenticated protected call, a rejected
/// token, and a sidecar that is not running.
///
/// Runs the venv's `auto-scoring-sidecar` executable directly rather than
/// `uv run ...`: `uv run` spawns it as a *child* process on Windows (no
/// `execve`), so killing the `uv` process leaks the sidecar. Requires
/// `uv sync` to have populated `backend/.venv` (see `pnpm run bootstrap` /
/// `.github/workflows/ci.yml`).
void main() {
  final backendDir = Directory(
    '${Directory.current.path}/../backend',
  ).absolute.path;
  final sidecarExe = Platform.isWindows
      ? '$backendDir/.venv/Scripts/auto-scoring-sidecar.exe'
      : '$backendDir/.venv/bin/auto-scoring-sidecar';

  Process? sidecar;
  Directory? tempDir;

  // Spawning the sidecar and waiting for it to become healthy used to live
  // in `setUpAll`, moved here for two independent reasons -- see
  // docs/answer-intake-and-preprocessing.md §20 for the full isolation that
  // led to both:
  //
  // 1. package:test does not run this file's top-level `test()` bodies
  //    strictly one at a time -- several can be mid-flight at once, so the
  //    very first version of this helper (which only memoized the
  //    *resolved* `SidecarConnection`, checked with a plain `if (x != null)
  //    return x;`) let multiple tests race in before any of them had
  //    finished: each one saw no connection yet and independently spawned
  //    its own sidecar process, several of which then fought over ephemeral
  //    loopback ports and over `intake_lock`/DB access inside the same
  //    fresh `app-data`. Memoizing the in-flight `Future` itself (assigned
  //    synchronously, before any `await`) closes that window: every caller,
  //    no matter how many arrive before the first spawn finishes, awaits
  //    the one shared attempt.
  // 2. `setUpAll` has some further Windows-specific interaction with
  //    `Process.start` that a `test()` body does not (dart-lang/sdk#49615
  //    and related cover the broader "Process.start inside a Flutter/
  //    package:test hook" class of issues).
  //
  // Neither of those was the whole story, though: even with both fixed,
  // this file can still take on the order of a minute to become healthy on
  // some local Windows runs, independent of anything above. Isolated to
  // `_waitUntilHealthy` retrying a real HTTP GET that times out (not
  // "connection refused") against a socket the sidecar itself confirms it
  // is listening on a moment later -- consistent with local real-time
  // antivirus/network-inspection interference on a freshly spawned,
  // unrecognized child process rather than an application bug (this machine
  // has Windows Defender real-time protection enabled and no third-party
  // AV). CI runs on hosted `windows-latest` runners, a different
  // environment where this has not been observed to reproduce.
  Future<SidecarConnection> startSidecar() async {
    tempDir = await Directory.systemTemp.createTemp('sidecar_it_');
    final handshakeFile = File('${tempDir!.path}/handshake.json');

    sidecar = await Process.start(sidecarExe, [
      '--handshake-file',
      handshakeFile.path,
      '--app-data-dir',
      '${tempDir!.path}/app-data',
    ]);

    final handshake = await _readHandshake(handshakeFile);
    final started = SidecarConnection(
      baseUrl: 'http://${handshake['host']}:${handshake['port']}',
      token: handshake['token'] as String,
    );
    await _waitUntilHealthy(SidecarApiClient(started));
    return started;
  }

  Future<SidecarConnection>? startingSidecar;

  Future<SidecarConnection> ensureSidecar() {
    return startingSidecar ??= startSidecar();
  }

  tearDownAll(() async {
    final process = sidecar;
    if (process != null) {
      process.kill(ProcessSignal.sigkill);
      await process.exitCode;
    }
    final dir = tempDir;
    if (dir != null) await _deleteWithRetry(dir);
  });

  test('health check succeeds even with a bogus token', () async {
    final connection = await ensureSidecar();
    final client = SidecarApiClient(
      SidecarConnection(baseUrl: connection.baseUrl, token: 'bogus'),
    );
    addTearDown(client.close);

    expect(await client.isHealthy(), isTrue);
  });

  test('protected call succeeds with the session token', () async {
    final connection = await ensureSidecar();
    final client = SidecarApiClient(connection);
    addTearDown(client.close);

    final result = await client.score(key: 'q1', raw: 15, maximum: 10);

    expect(result.key, 'q1');
    expect(result.awarded, 10);
    expect(result.maximum, 10);
    expect(result.ratio, 1.0);
  });

  test('protected call is rejected with a wrong token', () async {
    final connection = await ensureSidecar();
    final client = SidecarApiClient(
      SidecarConnection(baseUrl: connection.baseUrl, token: 'not-the-token'),
    );
    addTearDown(client.close);

    await expectLater(
      client.score(key: 'q1', raw: 1, maximum: 10),
      throwsA(
        isA<SidecarApiException>()
            .having((e) => e.kind, 'kind', SidecarErrorKind.unauthorized)
            .having((e) => e.statusCode, 'statusCode', 401),
      ),
    );
  });

  test('listTests succeeds against the real sidecar', () async {
    final connection = await ensureSidecar();
    final client = SidecarApiClient(connection);
    addTearDown(client.close);

    expect(await client.listTests(), isA<List<TestSummary>>());
  });

  test(
    'createSubmission sends a PDF content type the sidecar accepts',
    () async {
      final connection = await ensureSidecar();
      final client = SidecarApiClient(connection);
      addTearDown(client.close);

      final pdfFile = File('${tempDir!.path}/content-type-check.pdf');
      await pdfFile.writeAsBytes(utf8.encode('%PDF-1.7\n%%EOF'));

      // No test with this id is registered. dio's MultipartFile.fromFile
      // defaults to application/octet-stream when no contentType is given,
      // and the sidecar rejects any declared type other than application/pdf
      // (or none) with 400 -- before it even looks at test_id. Getting 404
      // here (test not found) instead of 400 proves the upload's content
      // type passed that check and reached the sidecar's normal pipeline.
      await expectLater(
        client.createSubmission(
          testId: 'does-not-exist',
          filePath: pdfFile.path,
        ),
        throwsA(
          isA<SidecarApiException>()
              .having((e) => e.kind, 'kind', SidecarErrorKind.badResponse)
              .having((e) => e.statusCode, 'statusCode', 404),
        ),
      );
    },
  );

  test('a sidecar that is not running surfaces as unavailable', () async {
    final connection = await ensureSidecar();
    // A port that was free a moment ago and has nothing listening now: the
    // OS refuses the connection immediately.
    final probe = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final deadPort = probe.port;
    await probe.close();

    final client = SidecarApiClient(
      SidecarConnection(
        baseUrl: 'http://127.0.0.1:$deadPort',
        token: connection.token,
      ),
      timeout: const Duration(seconds: 2),
    );
    addTearDown(client.close);

    expect(await client.isHealthy(), isFalse);
    await expectLater(
      client.score(key: 'q1', raw: 1, maximum: 10),
      throwsA(
        isA<SidecarApiException>().having(
          (e) => e.kind,
          'kind',
          SidecarErrorKind.unavailable,
        ),
      ),
    );
  });

  test('rejects a non-loopback destination without echoing credentials', () {
    const remoteUrl = 'https://example.test/private';
    const secret = 'must-not-escape';

    expect(
      () => SidecarApiClient(
        const SidecarConnection(baseUrl: remoteUrl, token: secret),
      ),
      throwsA(
        isA<ArgumentError>().having(
          (error) => error.toString(),
          'message',
          allOf(isNot(contains(remoteUrl)), isNot(contains(secret))),
        ),
      ),
    );
  });

  test('unknown transport errors do not expose connection details', () async {
    final connection = await ensureSidecar();
    const leaked = 'must-not-escape http://127.0.0.1:54321';
    final dio = Dio()
      ..interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) => handler.reject(
            DioException(
              requestOptions: options,
              type: DioExceptionType.unknown,
              message: leaked,
            ),
          ),
        ),
      );
    final client = SidecarApiClient(connection, dio: dio);
    addTearDown(client.close);

    await expectLater(
      client.score(key: 'q1', raw: 1, maximum: 10),
      throwsA(
        isA<SidecarApiException>()
            .having((error) => error.kind, 'kind', SidecarErrorKind.unknown)
            .having(
              (error) => error.toString(),
              'message',
              isNot(contains(leaked)),
            ),
      ),
    );
  });
}

/// Windows can hold the killed sidecar's SQLite WAL/shm files open for a
/// moment after `sigkill`+`exitCode` return, once a test has actually written
/// through the DB (e.g. `createSubmission`) -- a plain `dir.delete` then
/// throws `PathAccessException` even though the process is already gone.
Future<void> _deleteWithRetry(Directory dir) async {
  for (var attempt = 0; attempt < 10; attempt++) {
    try {
      await dir.delete(recursive: true);
      return;
    } on FileSystemException {
      if (attempt == 9) rethrow;
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }
}

Future<Map<String, dynamic>> _readHandshake(File file) async {
  for (var attempt = 0; attempt < 60; attempt++) {
    if (file.existsSync() && file.lengthSync() > 0) {
      return jsonDecode(await file.readAsString()) as Map<String, dynamic>;
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('sidecar did not write a handshake file at ${file.path}');
}

Future<void> _waitUntilHealthy(SidecarApiClient client) async {
  try {
    for (var attempt = 0; attempt < 40; attempt++) {
      if (await client.isHealthy()) return;
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    throw StateError('sidecar never became healthy');
  } finally {
    client.close();
  }
}
