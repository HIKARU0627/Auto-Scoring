import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/startup/startup_gate.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// What the user sees while the sidecar starts, when it fails, and after they
/// press 再起動 (simplified-design-specification.md §24).
void main() {
  Future<void> pumpGate(WidgetTester tester, SidecarSupervisor supervisor) =>
      tester.pumpWidget(MaterialApp(home: StartupGate(supervisor: supervisor)));

  testWidgets('waits on a splash, then shows the app once healthy', (
    tester,
  ) async {
    final platform = _StubPlatform();
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: '/opt/sidecar',
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);

    // Still starting: no handshake written and nothing answering yet.
    expect(find.text('バックエンドを起動しています…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byType(HomePage), findsNothing);

    platform
      ..handshake = '{"host":"127.0.0.1","port":1234,"token":"t"}'
      ..healthy = true;
    // `pumpAndSettle` and not a bare `pump`: it also proves the splash's
    // indeterminate progress indicator is gone, since a running animation
    // would never let the tree settle.
    await tester.pumpAndSettle();

    expect(find.byType(HomePage), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('closing the window kills the sidecar before exiting', (
    tester,
  ) async {
    final platform = _StubPlatform()
      ..healthy = true
      ..handshake = '{"host":"127.0.0.1","port":1234,"token":"t"}';
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: '/opt/sidecar',
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);
    await tester.pumpAndSettle();
    expect(supervisor.state.value, isA<SidecarReady>());

    // What Flutter does when the user closes the window: ask every observer,
    // which reaches `StartupGate.didRequestAppExit`.
    final response = await tester.binding.handleRequestAppExit();

    expect(response, AppExitResponse.exit);
    expect(supervisor.state.value, isA<SidecarStopped>());
  });

  testWidgets('offers a restart button when the sidecar exits', (tester) async {
    final platform = _StubPlatform()..exitImmediatelyWith = 1;
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: '/opt/sidecar',
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);
    await tester.pumpAndSettle();

    expect(find.text('バックエンドの起動に失敗しました。'), findsOneWidget);
    expect(find.text('終了コード: 1'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, '再起動'), findsOneWidget);

    // 再起動 recovers, without restarting the app itself.
    platform
      ..exitImmediatelyWith = null
      ..healthy = true
      ..handshake = '{"host":"127.0.0.1","port":1234,"token":"t"}';
    await tester.tap(find.widgetWithText(FilledButton, '再起動'));
    await tester.pumpAndSettle();

    expect(find.byType(HomePage), findsOneWidget);
    expect(platform.spawnCount, 2);
  });

  testWidgets('names the double-launch case instead of showing a crash', (
    tester,
  ) async {
    final platform = _StubPlatform()
      ..exitImmediatelyWith = sidecarAlreadyRunningExitCode;
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: '/opt/sidecar',
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);
    await tester.pumpAndSettle();

    expect(find.text('Auto-Scoring はすでに起動しています。'), findsOneWidget);
  });

  testWidgets('a missing bundle points at reinstalling, not at the log', (
    tester,
  ) async {
    final supervisor = SidecarSupervisor(
      platform: _StubPlatform(),
      executablePath: null,
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);
    await tester.pumpAndSettle();

    expect(find.text('インストーラーから再インストールしてください。'), findsOneWidget);
  });

  testWidgets('the error screen never renders the bearer token', (
    tester,
  ) async {
    const secret = 'must-not-be-rendered';
    final platform = _StubPlatform()
      ..handshake = '{"host":"127.0.0.1","port":1234,"token":"$secret"}'
      ..exitImmediatelyWith = 9;
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: '/opt/sidecar',
    );
    addTearDown(supervisor.dispose);

    await pumpGate(tester, supervisor);
    await tester.pumpAndSettle();

    for (final text in tester.widgetList<Text>(find.byType(Text))) {
      expect(text.data ?? '', isNot(contains(secret)));
    }
  });
}

/// A [SidecarPlatform] that answers immediately, so widget tests never wait on
/// real time or a real process.
class _StubPlatform implements SidecarPlatform {
  bool healthy = false;
  String? handshake;
  int? exitImmediatelyWith;
  int spawnCount = 0;

  Duration _elapsed = Duration.zero;

  @override
  Future<String> createHandshakeFile() async => '/tmp/handshake.json';

  @override
  Future<String?> readHandshakeFile(String path) async => handshake;

  @override
  Future<void> deleteHandshakeFile(String path) async {}

  @override
  Future<SidecarProcessHandle> start(
    String executable,
    List<String> arguments,
  ) async {
    spawnCount++;
    return _StubProcess(exitImmediatelyWith);
  }

  @override
  Future<bool> probeHealth(SidecarConnection connection) async => healthy;

  @override
  Future<void> delay(Duration duration) async {
    _elapsed += duration;
    await Future<void>.delayed(Duration.zero);
  }

  @override
  DateTime now() => DateTime.utc(2026, 1, 1).add(_elapsed);
}

class _StubProcess implements SidecarProcessHandle {
  _StubProcess(int? exitImmediatelyWith) {
    if (exitImmediatelyWith != null) _exit.complete(exitImmediatelyWith);
  }

  final Completer<int> _exit = Completer<int>();

  @override
  Future<int> get exitCode => _exit.future;

  @override
  void kill() {
    if (!_exit.isCompleted) _exit.complete(-9);
  }
}
