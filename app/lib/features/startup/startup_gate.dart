import 'dart:async';

// `AppExitResponse` -- the `didRequestAppExit` contract -- is declared in
// dart:ui, and neither material nor widgets re-exports it.
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';

/// Stands between app launch and the first screen: shows a splash while the
/// sidecar starts, the app once it is reachable, and a recoverable error
/// screen if it is not (`docs/technology-stack.md` §1.2,
/// simplified-design-specification.md §24).
///
/// Also the app's exit hook. Closing the window is the only "normal" way this
/// app ends, and it is the moment the sidecar has to be killed.
class StartupGate extends StatefulWidget {
  const StartupGate({super.key, required this.supervisor});

  final SidecarSupervisor supervisor;

  @override
  State<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<StartupGate> with WidgetsBindingObserver {
  /// Built from the connection the supervisor established, and closed again
  /// whenever the sidecar stops being reachable -- a client pins its base URL
  /// and token at construction, and a restart mints new ones.
  SidecarApiClient? _client;
  AppDependencies? _dependencies;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.supervisor.state.addListener(_onSidecarStateChanged);
    // Not awaited: `start()` completes only once the sidecar is ready or has
    // failed, and the whole point of this widget is to render that wait.
    unawaited(widget.supervisor.start());
  }

  @override
  void dispose() {
    widget.supervisor.state.removeListener(_onSidecarStateChanged);
    WidgetsBinding.instance.removeObserver(this);
    _client?.close();
    super.dispose();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    // Flutter asks before closing the window, which is the last point any
    // Dart code runs. On Windows the Job Object would clean up even if this
    // never ran (`core/child_process_group.dart`); this is the orderly path.
    await widget.supervisor.shutdown();
    return AppExitResponse.exit;
  }

  void _onSidecarStateChanged() {
    final state = widget.supervisor.state.value;
    _client?.close();
    if (state is SidecarReady) {
      final client = SidecarApiClient(state.connection);
      _client = client;
      _dependencies = AppDependencies.fromClient(client);
    } else {
      _client = null;
      _dependencies = null;
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return switch (widget.supervisor.state.value) {
      SidecarReady() => HomePage(dependencies: _dependencies!),
      SidecarStarting() => const _SidecarSplash(),
      SidecarStopped() => const _SidecarSplash(message: '終了しています…'),
      SidecarFailed(:final failure, :final exitCode) => _SidecarErrorScreen(
        failure: failure,
        exitCode: exitCode,
        onRestart: () => unawaited(widget.supervisor.start()),
      ),
    };
  }
}

class _SidecarSplash extends StatelessWidget {
  const _SidecarSplash({this.message = 'バックエンドを起動しています…'});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Auto-Scoring',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 32),
            const CircularProgressIndicator(),
            const SizedBox(height: 24),
            Text(message, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 8),
            // The first launch on a machine runs every schema migration and
            // is scanned by Windows Defender, so it is the slow one. Saying
            // so is the difference between "still working" and "hung".
            Text(
              '初回起動には時間がかかることがあります。',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _SidecarErrorScreen extends StatelessWidget {
  const _SidecarErrorScreen({
    required this.failure,
    required this.exitCode,
    required this.onRestart,
  });

  final SidecarFailure failure;
  final int? exitCode;
  final VoidCallback onRestart;

  /// One line the user can act on per failure. No exception text, no paths
  /// beyond the app itself, and never the bearer token -- what a developer
  /// needs is in the sidecar's own log (`docs/windows-distribution.md` §5),
  /// which the detail line below points at.
  String get _headline => switch (failure) {
    SidecarFailure.executableMissing => 'バックエンドが見つかりません。インストールが壊れている可能性があります。',
    SidecarFailure.alreadyRunning => 'Auto-Scoring はすでに起動しています。',
    SidecarFailure.exitedDuringStartup => 'バックエンドの起動に失敗しました。',
    SidecarFailure.startupTimedOut => 'バックエンドが時間内に応答しませんでした。',
    SidecarFailure.crashed => 'バックエンドが予期せず終了しました。',
  };

  String get _detail => switch (failure) {
    SidecarFailure.executableMissing => 'インストーラーから再インストールしてください。',
    SidecarFailure.alreadyRunning =>
      'すでに開いているウィンドウをご利用ください。閉じた直後の場合は、少し待ってから再起動してください。',
    _ => 'ログ: %LOCALAPPDATA%\\Auto-Scoring\\app-data\\logs\\sidecar.log',
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.error_outline,
                  size: 48,
                  color: theme.colorScheme.error,
                ),
                const SizedBox(height: 16),
                Text(
                  _headline,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                Text(
                  _detail,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall,
                ),
                if (exitCode case final code?) ...[
                  const SizedBox(height: 4),
                  Text('終了コード: $code', style: theme.textTheme.bodySmall),
                ],
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: onRestart,
                  icon: const Icon(Icons.refresh),
                  label: const Text('再起動'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
