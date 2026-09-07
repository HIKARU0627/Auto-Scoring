/// "Is the sidecar this connection was minted for still serving?", for tests
/// that assert a sidecar has gone away.
///
/// Deliberately strict, and deliberately raw HTTP rather than
/// [SidecarApiClient]: the question is about the process on the other end, and
/// every convenience the production client offers its real callers is a way to
/// answer it wrongly here. `sidecar_probe_test.dart` pins each case.
///
/// Two wrong diagnoses of Issue #57 came from probes that were looser than they
/// looked:
///
/// * `/healthz` needs no auth (`api/app.py` registers it outside the
///   `require_token` router), so *any* sidecar answers `{"status": "ok"}` to
///   anyone. "Someone is on this port" was being read as "our sidecar survived".
/// * `listTests()` on the generated client throws only outside 2xx, and turns a
///   null payload into an empty list -- so a 204, or a 200 with no body at all,
///   read as a healthy sidecar with no tests registered.
///
/// So the bar here is a real answer to a real protected call: HTTP 200, from a
/// token this session minted, carrying the JSON array `GET /tests` returns.
/// Anything else -- a refused connection, a connection accepted and dropped, a
/// half-written header, a truncated body, 401 from a sidecar that never minted
/// this token, any other status -- is "not serving".
library;

import 'dart:convert';
import 'dart:io';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// The verdict, plus what it was based on, so a test that fails on it can say
/// what it actually saw instead of only that it was disappointed.
typedef SidecarProbeResult = ({bool serving, String detail});

Future<SidecarProbeResult> sidecarStillServing(
  SidecarConnection connection, {
  Duration timeout = const Duration(seconds: 5),
}) async {
  final client = HttpClient()..connectionTimeout = timeout;
  try {
    final request = await client.getUrl(
      Uri.parse('${connection.baseUrl}/tests'),
    );
    // The token goes on the wire; it never goes into [detail] below.
    request.headers.set(
      HttpHeaders.authorizationHeader,
      'Bearer ${connection.token}',
    );
    final response = await request.close().timeout(timeout);
    final body = await response
        .transform(const Utf8Decoder(allowMalformed: true))
        .join()
        .timeout(timeout);
    final decoded = _decodeJson(body);
    final serving = response.statusCode == HttpStatus.ok && decoded is List;
    return (
      serving: serving,
      detail:
          'status=${response.statusCode} '
          'contentType=${response.headers.contentType} '
          'bodyLength=${body.length} '
          'json=${decoded.runtimeType}',
    );
  } on Object catch (error) {
    // Refused, reset, timed out, half a response: all of them mean the sidecar
    // is not answering, and none of them should reach the caller as an error.
    return (serving: false, detail: 'threw ${error.runtimeType}: $error');
  } finally {
    client.close(force: true);
  }
}

Object? _decodeJson(String body) {
  try {
    return jsonDecode(body);
  } on FormatException {
    return null;
  }
}
