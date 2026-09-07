import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:flutter_test/flutter_test.dart';

import 'sidecar_probe.dart';

/// Pins what [sidecarStillServing] counts as "our sidecar is still serving".
///
/// `sidecar_supervisor_integration_test.dart` asserts the *negative* of this
/// probe -- that a sidecar has gone away after `shutdown()` -- so a probe that
/// is too generous turns into a flaky failure, and one that is too strict turns
/// into a test that can never fail. Issue #57 was two rounds of the first kind:
/// first `/healthz`, which needs no auth and so answers anyone, then
/// `listTests()`, which throws only outside 2xx and reads a missing payload as
/// an empty list.
///
/// Every case below is a server this test stands up itself, so the answers are
/// measured rather than assumed, and none of it needs a real sidecar.
void main() {
  Future<SidecarProbeResult> probe(Uri url) => sidecarStillServing(
    SidecarConnection(baseUrl: url.toString(), token: 'this-session'),
    timeout: const Duration(seconds: 5),
  );

  group('counts as serving', () {
    test(
      'a real answer to the protected call, even when it is empty',
      () async {
        // A sidecar that is up with nothing registered yet answers `[]`, so the
        // probe cannot demand a non-empty list.
        final url = await _http((response) {
          response
            ..headers.contentType = ContentType.json
            ..write('[]');
        });

        final result = await probe(url);

        expect(result.serving, isTrue, reason: result.detail);
      },
    );

    test('an answer carrying registered tests', () async {
      final url = await _http((response) {
        response
          ..headers.contentType = ContentType.json
          ..write('[{"id": "t1", "name": "midterm"}]');
      });

      final result = await probe(url);

      expect(result.serving, isTrue, reason: result.detail);
    });
  });

  group('does not count as serving', () {
    test('nothing listening at all', () async {
      // Port 1 is below every OS's ephemeral range, so no `--port 0` sidecar
      // this suite starts can ever be handed it.
      final result = await probe(Uri.parse('http://127.0.0.1:1'));

      expect(result.serving, isFalse);
      expect(result.detail, contains('threw'));
    });

    test(
      'a 200 with no body -- the generated client read this as alive',
      () async {
        final url = await _http(
          (response) => response.headers.contentLength = 0,
        );

        final result = await probe(url);

        expect(result.serving, isFalse, reason: result.detail);
      },
    );

    test('204 No Content -- likewise', () async {
      final url = await _http(
        (response) => response.statusCode = HttpStatus.noContent,
      );

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });

    test('a 200 whose body is not a JSON array', () async {
      final url = await _http((response) {
        response
          ..headers.contentType = ContentType.json
          ..write('{"detail": "not the list endpoint"}');
      });

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });

    test('401 from a sidecar that never minted this token', () async {
      // The case that separates "our sidecar survived" from "somebody else is
      // on this port": a different instance rejects a token it did not mint.
      final url = await _http(
        (response) => response.statusCode = HttpStatus.unauthorized,
      );

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });

    // The shapes a listening socket produces while the process behind it is
    // being torn down. These are what a sidecar looks like in the moment
    // between `TerminateProcess` and the socket going away, and mistaking any
    // of them for a live sidecar is exactly the flake this file guards.
    test('a connection accepted and then dropped', () async {
      final url = await _raw((socket) => socket.close());

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });

    test('a response cut off part-way through the headers', () async {
      final url = await _raw((socket) async {
        socket.write('HTTP/1.1 200 OK\r\nCont');
        await socket.flush();
        await socket.close();
      });

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });

    test('complete headers with a truncated body', () async {
      final url = await _raw((socket) async {
        socket.write(
          'HTTP/1.1 200 OK\r\n'
          'Content-Type: application/json\r\n'
          'Content-Length: 64\r\n'
          '\r\n'
          '[',
        );
        await socket.flush();
        await socket.close();
      });

      final result = await probe(url);

      expect(result.serving, isFalse, reason: result.detail);
    });
  });
}

Future<Uri> _http(void Function(HttpResponse response) respond) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  addTearDown(() => server.close(force: true));
  server.listen((request) async {
    respond(request.response);
    await request.response.close();
  });
  return Uri.parse('http://127.0.0.1:${server.port}');
}

/// A raw listener, for the half-written responses `HttpServer` will not
/// produce.
Future<Uri> _raw(Future<void> Function(Socket socket) respond) async {
  final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
  addTearDown(server.close);
  server.listen((socket) async {
    // Drained so the client's request completes before the answer.
    socket.listen((_) {}, onError: (_) {}, cancelOnError: true);
    await respond(socket);
  });
  return Uri.parse('http://127.0.0.1:${server.port}');
}
