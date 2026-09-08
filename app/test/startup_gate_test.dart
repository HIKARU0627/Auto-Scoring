import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_registration_page.dart';
import 'package:auto_scoring_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// What the reviewer sees while the sidecar starts, when it fails, and after
/// they press 再起動 (simplified-design-specification.md §24).
void main() {
  ({SidecarSupervisor supervisor, _StubPlatform platform}) build(
    WidgetTester tester, {
    bool healthy = false,
    String? handshake,
    int? exitImmediatelyWith,
    String? executablePath = '/opt/sidecar',
  }) {
    final platform = _StubPlatform()
      ..healthy = healthy
      ..handshake = handshake
      ..exitImmediatelyWith = exitImmediatelyWith;
    final supervisor = SidecarSupervisor(
      platform: platform,
      executablePath: executablePath,
    );
    addTearDown(supervisor.dispose);
    return (supervisor: supervisor, platform: platform);
  }

  const readyHandshake = '{"host":"127.0.0.1","port":1234,"token":"t"}';

  testWidgets('waits on a splash, then shows the app once healthy', (
    tester,
  ) async {
    final app = build(tester);
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));

    // Still starting: no handshake written and nothing answering yet.
    expect(find.text('バックエンドを起動しています…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byType(HomePage), findsNothing);

    app.platform
      ..handshake = readyHandshake
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
    final app = build(tester, healthy: true, handshake: readyHandshake);
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
    await tester.pumpAndSettle();
    expect(app.supervisor.state.value, isA<SidecarReady>());

    // What Flutter does when the user closes the window: ask every observer,
    // which reaches the composition root's `didRequestAppExit`.
    final response = await tester.binding.handleRequestAppExit();

    expect(response, AppExitResponse.exit);
    expect(app.supervisor.state.value, isA<SidecarStopped>());
  });

  testWidgets('offers a restart button when the sidecar exits', (tester) async {
    final app = build(tester, exitImmediatelyWith: 1);
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
    await tester.pumpAndSettle();

    expect(find.text('バックエンドの起動に失敗しました。'), findsOneWidget);
    expect(find.text('終了コード: 1'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, '再起動'), findsOneWidget);

    // 再起動 recovers, without restarting the app itself.
    app.platform
      ..exitImmediatelyWith = null
      ..healthy = true
      ..handshake = readyHandshake;
    await tester.tap(find.widgetWithText(FilledButton, '再起動'));
    await tester.pumpAndSettle();

    expect(find.byType(HomePage), findsOneWidget);
    expect(app.platform.spawnCount, 2);
  });

  // The regression this file exists for (Issue #24 review round 1, P1).
  //
  // The overlay used to be `MaterialApp.home`, i.e. the *bottom* route of the
  // Navigator. A crash while the reviewer had a page pushed swapped out a
  // subtree nobody could see: the error screen and its restart button stayed
  // buried underneath, and all the reviewer got was their own screen failing
  // every request with no explanation and no way back.
  testWidgets(
    'a crash with a page pushed still shows the error screen and restart button',
    (tester) async {
      final app = build(tester, healthy: true, handshake: readyHandshake);
      await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
      await tester.pumpAndSettle();
      expect(find.byType(HomePage), findsOneWidget);

      // Exactly what HomePage does: push a real page on top of the gate.
      // By key, not by text: ホーム画面 cannot reach this fake sidecar, so it
      // is showing its own error state -- and the entry-point row is
      // deliberately the one part that survives it (Issue #68).
      await tester.tap(find.byKey(const Key('home-open-test-registration')));
      await tester.pumpAndSettle();
      expect(find.byType(TestRegistrationPage), findsOneWidget);

      app.platform.crashRunningProcess(-1);
      await tester.pumpAndSettle();

      expect(
        app.supervisor.state.value,
        isA<SidecarFailed>().having(
          (s) => s.failure,
          'failure',
          SidecarFailure.crashed,
        ),
      );
      expect(find.text('バックエンドが予期せず終了しました。'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '再起動'), findsOneWidget);
      // The pushed page is dropped rather than left holding a closed client.
      expect(find.byType(TestRegistrationPage), findsNothing);

      // And the button actually works from here.
      app.platform.handshake = '{"host":"127.0.0.1","port":5678,"token":"t2"}';
      await tester.tap(find.widgetWithText(FilledButton, '再起動'));
      await tester.pumpAndSettle();

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '再起動'), findsNothing);
    },
  );

  testWidgets('names the double-launch case instead of showing a crash', (
    tester,
  ) async {
    final app = build(
      tester,
      exitImmediatelyWith: sidecarAlreadyRunningExitCode,
    );
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
    await tester.pumpAndSettle();

    expect(find.text('Auto-Scoring はすでに起動しています。'), findsOneWidget);
  });

  testWidgets('a missing bundle points at reinstalling, not at the log', (
    tester,
  ) async {
    final app = build(tester, executablePath: null);
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
    await tester.pumpAndSettle();

    expect(find.text('インストーラーから再インストールしてください。'), findsOneWidget);
  });

  testWidgets('the error screen never renders the bearer token', (
    tester,
  ) async {
    const secret = 'must-not-be-rendered';
    final app = build(
      tester,
      handshake: '{"host":"127.0.0.1","port":1234,"token":"$secret"}',
      exitImmediatelyWith: 9,
    );
    await tester.pumpWidget(AutoScoringApp(supervisor: app.supervisor));
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

  final List<_StubProcess> _processes = [];
  Duration _elapsed = Duration.zero;

  /// Ends the sidecar the way a real crash would: from outside, unannounced.
  void crashRunningProcess(int exitCode) {
    _processes.last.exitWith(exitCode);
  }

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
    final process = _StubProcess(exitImmediatelyWith);
    _processes.add(process);
    return process;
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

  void exitWith(int code) {
    if (!_exit.isCompleted) _exit.complete(code);
  }

  @override
  Future<int> get exitCode => _exit.future;

  @override
  void kill() => exitWith(-9);
}
