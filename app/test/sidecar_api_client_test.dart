@Tags(['sidecar'])
@Timeout(Duration(minutes: 3))
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
  // this file can still take on the order of a minute to become healthy,
  // both on some local Windows runs *and* on GitHub Actions' hosted
  // `windows-latest` runners (confirmed by a real CI failure -- this is not
  // only a local-machine quirk). Isolated locally to `_waitUntilHealthy`
  // retrying a real HTTP GET that times out (not "connection refused")
  // against a socket the sidecar itself confirms it is listening on a
  // moment later -- consistent with real-time antivirus/network-inspection
  // interference on a freshly spawned, unrecognized child process (Windows
  // Defender's real-time protection is on by default on GitHub's hosted
  // Windows runners too, and would treat a just-built, unsigned executable
  // with more scrutiny than one it has already scanned). Two mitigations,
  // neither a fix for the interference itself (out of this repo's control):
  //
  // * `@Timeout(Duration(minutes: 3))` above replaces package:test's
  //   default 30-second per-test timeout, which was the immediate cause of
  //   the CI failure: it fired on the *first* test to call `ensureSidecar`
  //   well before the shared spawn (delayed, not hung -- it did eventually
  //   finish) could complete, and every following test then repeated the
  //   same 30-second wait against the still-pending shared `Future`,
  //   compounding a startup delay into a hard failure. `_readHandshake` and
  //   `_waitUntilHealthy` below give the delayed startup itself a
  //   correspondingly longer budget to actually succeed in.
  // * `startSidecar` now drains and records the sidecar's stdout/stderr as
  //   they arrive, and prints everything captured so far if either helper
  //   times out -- previously, a slow or failed startup left zero
  //   diagnostic output in the test log (as happened in that CI run: the
  //   failure was visible, but nothing about *why* the process was slow to
  //   respond was ever captured).
  Future<SidecarConnection> startSidecar() async {
    tempDir = await Directory.systemTemp.createTemp('sidecar_it_');
    final handshakeFile = File('${tempDir!.path}/handshake.json');

    final process = await Process.start(sidecarExe, [
      '--handshake-file',
      handshakeFile.path,
      '--app-data-dir',
      '${tempDir!.path}/app-data',
    ]);
    sidecar = process;

    final output = StringBuffer();
    process.stdout.transform(utf8.decoder).listen(output.write);
    process.stderr.transform(utf8.decoder).listen(output.write);

    try {
      final handshake = await _readHandshake(handshakeFile);
      final started = SidecarConnection(
        baseUrl: 'http://${handshake['host']}:${handshake['port']}',
        token: handshake['token'] as String,
      );
      await _waitUntilHealthy(SidecarApiClient(started));
      return started;
    } catch (_) {
      // ignore: avoid_print
      print('sidecar stdout/stderr captured so far:\n$output');
      rethrow;
    }
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

  test(
    'material roles cross the boundary as wire names, not enum names',
    () async {
      final connection = await ensureSidecar();
      final client = SidecarApiClient(connection);
      addTearDown(client.close);

      // The roles `IntakePage._importGroup` can attach to a test. It never
      // sends `studentAnswer` (that becomes a submission) or `ignore` (filtered
      // out before the request is built), so those two do not cross here.
      const attachable = {
        MaterialRole.gradingCriteria,
        MaterialRole.annotationResource,
        MaterialRole.annotationSample,
        MaterialRole.reference,
      };

      // A real PDF, copied per material: the sidecar parses every PDF it is
      // handed (pypdf *and* pdfium) before storing it, so a stub header would
      // be rejected before the role is ever looked at. Identical bytes are
      // fine -- materials are de-duplicated by (role, content), and every role
      // here is distinct.
      final pdf = await File('test/fixtures/a4-portrait.pdf').readAsBytes();
      var copies = 0;
      Future<String> materialCopy() async {
        final file = File('${tempDir!.path}/material-role-${copies++}.pdf');
        await file.writeAsBytes(pdf);
        return file.path;
      }

      // Both call sites build `material_roles` by hand, so both are
      // exercised. `createTest` is the one real material hit first, because
      // every subject folder has a 添削資料 (Issue #139).
      //
      // `gradingCriteria` is not among the extras: the criteria file travels
      // as its own parameter and is what lands under that role.
      final extras = attachable.where(
        (role) => role != MaterialRole.gradingCriteria,
      );
      final registered = await client.createTest(
        name: 'material role wire names',
        criteriaPath: await materialCopy(),
        materials: [
          for (final role in extras) (role: role, path: await materialCopy()),
        ],
      );
      // Round-tripping through the sidecar is the whole point: it rejects a
      // role it does not know with 422 `unknown material role`, which is what
      // `role.name` (`annotationResource` rather than `annotation_resource`)
      // hit for every subject in the real material. The response side is
      // typed, so what comes back is proof the right rows were written.
      final stored = await client.listMaterials(registered.id);
      expect({for (final material in stored) material.role}, attachable);

      final attached = await client.addMaterials(
        registered.id,
        materials: [
          for (final role in attachable)
            (role: role, path: await materialCopy()),
        ],
      );
      expect({for (final material in attached) material.role}, attachable);
    },
  );

  test('a sidecar that is not running surfaces as unavailable', () async {
    final connection = await ensureSidecar();

    // A port nothing can be listening on, so the OS refuses the connection
    // immediately. Fixed rather than obtained by binding an ephemeral port and
    // closing it again: that is only free until something takes it, and the
    // sidecars this suite starts with `--port 0` are handed exactly those
    // ports -- eagerly enough on Windows to have made
    // `sidecar_supervisor_integration_test.dart` flaky (Issue #57). 1 is below
    // every OS's ephemeral range, so no `--port 0` can ever land on it.
    const deadPort = 1;

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

  test('a 409 carries the sidecar\'s own refusal code through', () async {
    // Issue #150: `SidecarErrorKind.conflict` is one kind over several
    // refusals whose remedies differ, so the code the sidecar names
    // (`domain.pdf_export.ExportRefusalReason`) has to survive translation.
    // Without it the caller can only guess, and the guess it had been making
    // told a reviewer to redo work that was already done.
    final connection = await ensureSidecar();
    final dio = Dio()
      ..interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) => handler.reject(
            DioException(
              requestOptions: options,
              type: DioExceptionType.badResponse,
              response: Response<Object?>(
                requestOptions: options,
                statusCode: 409,
                data: const {
                  'detail': {
                    'code': 'no_room_for_score',
                    'message':
                        'one or more questions have no area to write '
                        'the score in',
                    'question_ids': ['q-3'],
                  },
                },
              ),
            ),
          ),
        ),
      );
    final client = SidecarApiClient(connection, dio: dio);
    addTearDown(client.close);

    await expectLater(
      client.requestExport('sub-1'),
      throwsA(
        isA<SidecarApiException>()
            .having((error) => error.kind, 'kind', SidecarErrorKind.conflict)
            .having(
              (error) => error.conflictCode,
              'conflictCode',
              'no_room_for_score',
            )
            .having(
              (error) => error.conflictQuestionIds,
              'conflictQuestionIds',
              const ['q-3'],
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
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (DateTime.now().isBefore(deadline)) {
    if (file.existsSync() && file.lengthSync() > 0) {
      return jsonDecode(await file.readAsString()) as Map<String, dynamic>;
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError('sidecar did not write a handshake file at ${file.path}');
}

Future<void> _waitUntilHealthy(SidecarApiClient client) async {
  try {
    // Generous on purpose: writing the handshake file only proves the
    // process itself started, not that create_app()'s migrations have
    // finished and uvicorn is actually accepting connections yet, and both
    // that work and this health check's own request/response can be
    // delayed well past what a healthy machine would need -- see the
    // antivirus/network-inspection note on `startSidecar` above.
    final deadline = DateTime.now().add(const Duration(minutes: 2));
    while (DateTime.now().isBefore(deadline)) {
      if (await client.isHealthy()) return;
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    throw StateError('sidecar never became healthy');
  } finally {
    client.close();
  }
}
