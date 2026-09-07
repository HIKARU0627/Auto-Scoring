import 'dart:io';

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/sidecar_paths.dart';
import 'package:auto_scoring_app/core/sidecar_platform_io.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/startup/startup_gate.dart';

void main() {
  // Required before `Platform`/`Directory` are touched below, and before
  // `StartupGate` registers a `WidgetsBindingObserver` for the exit hook.
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AutoScoringApp(supervisor: buildSidecarSupervisor()));
}

/// The one supervisor the app runs with, resolved against the real filesystem.
///
/// Separate from [main] so the resolution is nameable in a stack trace and so
/// nothing about it depends on `runApp` having happened.
SidecarSupervisor buildSidecarSupervisor() {
  return SidecarSupervisor(
    platform: SidecarPlatformIo(),
    executablePath: resolveSidecarExecutable(
      sidecarExecutableCandidates(
        resolvedExecutable: Platform.resolvedExecutable,
        workingDirectory: Directory.current.path,
        isWindows: Platform.isWindows,
      ),
      exists: (path) => File(path).existsSync(),
    ),
    // No `appDataDirectory`: the sidecar owns that decision -- see
    // `SidecarSupervisor`'s field doc and `docs/windows-distribution.md` §3.
  );
}

/// Application root. This is the composition root, so it is allowed to wire
/// `core` and `features` together.
class AutoScoringApp extends StatelessWidget {
  const AutoScoringApp({super.key, this.supervisor, this.dependencies});

  /// Drives sidecar startup and renders the splash/error screens around the
  /// app. `null` in widget tests, which have no sidecar to supervise and go
  /// straight to [HomePage] with [dependencies] (or its stub defaults).
  final SidecarSupervisor? supervisor;

  /// Only used when [supervisor] is `null`. With a supervisor the
  /// dependencies come from the live connection it establishes, so passing
  /// both would be ambiguous.
  final AppDependencies? dependencies;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Auto-Scoring',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      home: switch (supervisor) {
        final supervisor? => StartupGate(supervisor: supervisor),
        null => HomePage(dependencies: dependencies ?? const AppDependencies()),
      },
    );
  }
}
