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

  late Process sidecar;
  late Directory tempDir;
  late SidecarConnection connection;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('sidecar_it_');
    final handshakeFile = File('${tempDir.path}/handshake.json');

    sidecar = await Process.start(sidecarExe, [
      '--handshake-file',
      handshakeFile.path,
      '--app-data-dir',
      '${tempDir.path}/app-data',
    ]);

    final handshake = await _readHandshake(handshakeFile);
    connection = SidecarConnection(
      baseUrl: 'http://${handshake['host']}:${handshake['port']}',
      token: handshake['token'] as String,
    );
    await _waitUntilHealthy(SidecarApiClient(connection));
  });

  tearDownAll(() async {
    sidecar.kill(ProcessSignal.sigkill);
    await sidecar.exitCode;
    await _deleteWithRetry(tempDir);
  });

  test('health check succeeds even with a bogus token', () async {
    final client = SidecarApiClient(
      SidecarConnection(baseUrl: connection.baseUrl, token: 'bogus'),
    );
    addTearDown(client.close);

    expect(await client.isHealthy(), isTrue);
  });

  test('protected call succeeds with the session token', () async {
    final client = SidecarApiClient(connection);
    addTearDown(client.close);

    final result = await client.score(key: 'q1', raw: 15, maximum: 10);

    expect(result.key, 'q1');
    expect(result.awarded, 10);
    expect(result.maximum, 10);
    expect(result.ratio, 1.0);
  });

  test('protected call is rejected with a wrong token', () async {
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
    final client = SidecarApiClient(connection);
    addTearDown(client.close);

    expect(await client.listTests(), isA<List<TestSummary>>());
  });

  test(
    'createSubmission sends a PDF content type the sidecar accepts',
    () async {
      final client = SidecarApiClient(connection);
      addTearDown(client.close);

      final pdfFile = File('${tempDir.path}/content-type-check.pdf');
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
