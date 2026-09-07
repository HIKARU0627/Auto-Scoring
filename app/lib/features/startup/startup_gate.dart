import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/sidecar_supervisor.dart';

/// Covers the whole app while the sidecar is not usable: a splash during
/// startup, and a recoverable error screen with a 再起動 button when it has
/// failed (`docs/technology-stack.md` §1.2, simplified-design-specification.md
/// §24).
///
/// Wraps `MaterialApp.builder`'s [child] -- the app's entire Navigator --
/// rather than sitting inside it as a route.
///
/// That placement is the whole point. As `MaterialApp.home` this was the
/// *bottom* route of the Navigator, so a sidecar crash while the reviewer had
/// 答案取込 or 添削レビュー open swapped out a subtree nobody could see: the
/// error screen and its restart button stayed buried under every pushed page,
/// and the only thing the reviewer actually saw was their own screen failing
/// every request for no stated reason (Issue #24 review round 1, P1).
///
/// [child] is kept mounted underneath rather than replaced, so nothing is torn
/// down mid-frame; the composition root separately drops any pushed route
/// before it closes the client those routes captured.
class SidecarStartupOverlay extends StatelessWidget {
  const SidecarStartupOverlay({
    super.key,
    required this.state,
    required this.onRestart,
    required this.child,
  });

  final SidecarState state;

  /// Runs the supervisor's start/restart. Wired by the composition root.
  final VoidCallback onRestart;

  /// The app's Navigator, as handed to `MaterialApp.builder`.
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final overlay = switch (state) {
      SidecarReady() => null,
      SidecarStarting() => const _SidecarSplash(),
      SidecarStopped() => const _SidecarSplash(message: '終了しています…'),
      SidecarFailed(:final failure, :final exitCode) => _SidecarErrorScreen(
        failure: failure,
        exitCode: exitCode,
        onRestart: onRestart,
      ),
    };
    if (overlay == null) return child ?? const SizedBox.shrink();

    return Stack(
      children: [
        ?child,
        // Both children are opaque `Scaffold`s, so this also stops taps
        // reaching whatever is still mounted underneath.
        Positioned.fill(child: overlay),
      ],
    );
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
